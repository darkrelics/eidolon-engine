"""Incremental API test rig.

Drives the live Eidolon Incremental API as an authenticated client. Logs in
via Cognito (USER_PASSWORD_AUTH), selects an existing character, walks every
story in AvailableStories, and prints diagnostic information about the API,
story flow, and game mechanics.

The rig runs without AWS credentials. Cognito InitiateAuth and
RespondToAuthChallenge are unauthenticated API calls, so an unsigned boto3
client is used.

Usage:
    python scripts/incremental_test_rig.py [--max-segments N] [--story-id ID]
                                           [--probe-errors] [--log-file PATH]
"""

import argparse
import getpass
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import boto3
import requests
import yaml
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


DEFAULT_MAX_SEGMENTS = 50
DEFAULT_POLL_MIN_SECONDS = 2
DEFAULT_POLL_MAX_SECONDS = 30
DEFAULT_POLL_TIMEOUT_SECONDS = 600
RETRY_AFTER_DEFAULT = 5
TOKEN_REFRESH_MARGIN_SECONDS = 300


@dataclass
class CallRecord:
    """Single HTTP call latency record for diagnostics."""

    method: str
    path: str
    status: int
    latency_ms: float
    request_id: str
    response_bytes: int


@dataclass
class StoryRun:
    """Per-story diagnostics tally."""

    story_id: str
    story_title: str
    segments_processed: int = 0
    decisions_made: int = 0
    outcomes: dict = field(default_factory=dict)
    completed: bool = False
    failure_reason: str = ""


@dataclass
class RunStats:
    """Aggregate diagnostics for the entire run."""

    calls: list = field(default_factory=list)
    stories: list = field(default_factory=list)
    mechanics_warnings: list = field(default_factory=list)


def prompt_param(prompt: str, current: str, required: bool = False) -> str:
    """Prompt for a parameter showing current value as default."""
    if current:
        user_input = input(f"  {prompt} [{current}]: ").strip()
        return user_input if user_input else current
    if required:
        value = ""
        while not value:
            value = input(f"  {prompt}: ").strip()
            if not value:
                print(f"    Value is required for {prompt}")
        return value
    return input(f"  {prompt}: ").strip()


def load_defaults_from_config(config_path: Path) -> dict:
    """Pull rig defaults from config.yml. Missing values produce empty strings."""
    if not config_path.exists():
        print(f"[WARNING] Config file not found: {config_path}")
        return {"region": "", "user_pool_id": "", "client_id": "", "api_base": ""}

    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            data = yaml.safe_load(config_file) or {}
    except (OSError, yaml.YAMLError) as err:
        print(f"[WARNING] Could not load config: {err}")
        return {"region": "", "user_pool_id": "", "client_id": "", "api_base": ""}

    aws = data.get("AWS", {}) or {}
    cognito = data.get("Cognito", {}) or {}
    deployment = data.get("Deployment", {}) or {}
    api_section = data.get("API", {}) or {}

    domain = deployment.get("Domain") or api_section.get("Domain") or ""
    api_host = deployment.get("ApiHost") or api_section.get("Subdomain") or ""
    api_base = f"https://{api_host}.{domain}" if api_host and domain else ""

    return {
        "region": aws.get("Region", ""),
        "user_pool_id": cognito.get("UserPoolId", ""),
        "client_id": cognito.get("UserPoolClientId") or cognito.get("ClientId", ""),
        "api_base": api_base,
    }


def collect_credentials(defaults: dict) -> dict:
    """Interactively gather connection settings and Cognito credentials."""
    print("\nIncremental API Test Rig - Connection Settings")
    region = prompt_param("AWS Region", defaults.get("region", ""), required=True)
    api_base = prompt_param("API Base URL", defaults.get("api_base", ""), required=True)
    user_pool_id = prompt_param("Cognito User Pool ID", defaults.get("user_pool_id", ""), required=True)
    client_id = prompt_param("Cognito Client ID", defaults.get("client_id", ""), required=True)

    print("\nCognito Login")
    username = prompt_param("Username", "", required=True)
    password = getpass.getpass("  Password: ")
    while not password:
        print("    Password is required")
        password = getpass.getpass("  Password: ")

    return {
        "region": region,
        "api_base": api_base.rstrip("/"),
        "user_pool_id": user_pool_id,
        "client_id": client_id,
        "username": username,
        "password": password,
    }


def cognito_login(cfg: dict) -> dict:
    """Authenticate against Cognito and return token bundle."""
    cognito = boto3.client("cognito-idp", region_name=cfg["region"], config=Config(signature_version=UNSIGNED))

    auth_params = {"USERNAME": cfg["username"], "PASSWORD": cfg["password"]}
    try:
        response = cognito.initiate_auth(
            ClientId=cfg["client_id"], AuthFlow="USER_PASSWORD_AUTH", AuthParameters=auth_params
        )
    except ClientError as err:
        raise RuntimeError(f"Cognito auth failed: {err.response.get('Error', {}).get('Message', str(err))}") from err
    except BotoCoreError as err:
        raise RuntimeError(f"Cognito network error: {err}") from err

    challenge = response.get("ChallengeName")
    if challenge:
        response = handle_auth_challenge(cognito, cfg, response)

    result = response.get("AuthenticationResult", {}) or {}
    if not result.get("IdToken"):
        raise RuntimeError("Cognito did not return an IdToken")

    return {
        "id_token": result.get("IdToken", ""),
        "refresh_token": result.get("RefreshToken", ""),
        "expires_at": time.time() + int(result.get("ExpiresIn", 3600)),
    }


def handle_auth_challenge(cognito, cfg: dict, response: dict) -> dict:
    """Handle NEW_PASSWORD_REQUIRED and SOFTWARE_TOKEN_MFA challenges."""
    challenge = response.get("ChallengeName", "")
    session = response.get("Session", "")
    username = cfg["username"]

    if challenge == "NEW_PASSWORD_REQUIRED":
        new_password = getpass.getpass("  New password required. Enter new password: ")
        challenge_responses = {"USERNAME": username, "NEW_PASSWORD": new_password}
    elif challenge == "SOFTWARE_TOKEN_MFA":
        code = prompt_param("MFA code", "", required=True)
        challenge_responses = {"USERNAME": username, "SOFTWARE_TOKEN_MFA_CODE": code}
    else:
        raise RuntimeError(f"Unsupported Cognito challenge: {challenge}")

    try:
        return cognito.respond_to_auth_challenge(
            ClientId=cfg["client_id"],
            ChallengeName=challenge,
            Session=session,
            ChallengeResponses=challenge_responses,
        )
    except ClientError as err:
        raise RuntimeError(f"Challenge response failed: {err}") from err


class ApiClient:
    """HTTP client with latency capture, 429 backoff, and 401 re-auth."""

    def __init__(self, base_url: str, tokens: dict, cfg: dict, stats: RunStats):
        self.base_url = base_url
        self.tokens = tokens
        self.cfg = cfg
        self.stats = stats
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "eidolon-test-rig/1.0", "Accept": "application/json"})

    def auth_header(self) -> dict:
        return {"Authorization": f"Bearer {self.tokens.get('id_token', '')}"}

    def maybe_refresh(self) -> None:
        if time.time() < self.tokens.get("expires_at", 0) - TOKEN_REFRESH_MARGIN_SECONDS:
            return
        print("[OK] Refreshing Cognito session")
        new_tokens = cognito_login(self.cfg)
        self.tokens.update(new_tokens)

    def request(self, method: str, path: str, params: dict, body: dict) -> dict:
        """Send a request, capturing diagnostics and handling 401/429.

        Pass empty dicts ({}) when no params or body are needed.
        """
        self.maybe_refresh()
        url = f"{self.base_url}{path}"
        headers = self.auth_header()
        if body:
            headers["Content-Type"] = "application/json"

        for attempt in range(4):
            start = time.time()
            try:
                resp = self.session.request(
                    method, url, params=params, data=json.dumps(body) if body else None,
                    headers=headers, timeout=30,
                )
            except requests.RequestException as err:
                raise RuntimeError(f"{method} {path} network error: {err}") from err

            latency_ms = (time.time() - start) * 1000.0
            request_id = resp.headers.get("x-amzn-RequestId") or resp.headers.get("apigw-requestid") or ""
            self.stats.calls.append(CallRecord(method, path, resp.status_code, latency_ms, request_id, len(resp.content)))

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", RETRY_AFTER_DEFAULT))
                print(f"[WARNING] 429 from {path}; sleeping {retry_after}s (WAF rate limit)")
                time.sleep(retry_after)
                continue
            if resp.status_code == 401 and attempt == 0:
                print("[WARNING] 401; refreshing token and retrying")
                self.tokens.update(cognito_login(self.cfg))
                headers = self.auth_header()
                continue
            return parse_response(resp, method, path)

        raise RuntimeError(f"{method} {path}: too many retries")


def parse_response(resp: requests.Response, method: str, path: str) -> dict:
    """Parse response body as JSON; raise with status detail on error."""
    try:
        payload = resp.json() if resp.content else {}
    except ValueError:
        payload = {"raw": resp.text}

    if resp.status_code >= 400:
        message = payload.get("message") or payload.get("error") or resp.text
        raise RuntimeError(f"{method} {path} -> HTTP {resp.status_code}: {message}")
    return payload


def select_character(client: ApiClient) -> dict:
    """Fetch character list and prompt operator to choose one."""
    payload = client.request("GET", "/character/list", {}, {})
    characters = payload.get("Characters") or payload.get("characters") or []
    if not characters:
        raise RuntimeError("Account owns no characters - rig does not create characters")

    if len(characters) == 1:
        only = characters[0]
        print(f"[OK] Using sole character: {only.get('Name')} ({only.get('CharacterID')})")
        return only

    print("\nAvailable characters:")
    for index, char in enumerate(characters, start=1):
        print(
            f"  {index}. {char.get('Name', '?')} - {char.get('Archetype', '?')} - "
            f"State={char.get('CharState', '?')} Mode={char.get('GameMode', 'None')}"
        )

    while True:
        raw = input(f"Select character [1-{len(characters)}]: ").strip()
        try:
            idx = int(raw)
        except ValueError:
            print("    Enter a number")
            continue
        if 1 <= idx <= len(characters):
            return characters[idx - 1]
        print(f"    Out of range; choose 1 to {len(characters)}")


def fetch_character(client: ApiClient, character_id: str) -> dict:
    """Get full character record."""
    payload = client.request("GET", "/character", {"CharacterID": character_id}, {})
    return payload.get("Character") or payload


def poll_segment(client: ApiClient, character_id: str, args: argparse.Namespace) -> dict:
    """Poll /segment/status until processed or timeout."""
    deadline = time.time() + args.poll_timeout
    sleep_for = args.poll_min
    while time.time() < deadline:
        status = client.request("GET", "/segment/status", {"CharacterID": character_id}, {})
        processing = status.get("ProcessingStatus", "")
        title = status.get("SegmentTitle", "")
        time_remaining = status.get("TimeRemaining", "?")
        print(
            f"    segment={status.get('SegmentID')} type={status.get('SegmentType')} "
            f"title='{title}' processing={processing} timeRemaining={time_remaining}s"
        )
        if processing == "processed":
            return status
        sleep_for = min(args.poll_max, max(args.poll_min, int(time_remaining) if str(time_remaining).isdigit() else sleep_for))
        time.sleep(sleep_for)
    raise RuntimeError(f"Segment polling timed out after {args.poll_timeout}s")


def submit_decision(client: ApiClient, character_id: str, status: dict) -> str:
    """Pick the first decision option and submit it. Returns chosen option key."""
    options = status.get("DecisionOptions") or {}
    if not options:
        raise RuntimeError("Decision segment has no DecisionOptions")
    decision_id = next(iter(options.keys()))
    chosen = options.get(decision_id, {})
    print(f"    decision='{status.get('DecisionText', '')}' choosing='{chosen.get('Text', decision_id)}'")
    client.request("POST", "/segment/decision", {}, {"CharacterID": character_id, "Decision": decision_id})
    return decision_id


def walk_story(client: ApiClient, character_id: str, story_id: str, args: argparse.Namespace) -> StoryRun:
    """Run a single story end-to-end, returning per-story diagnostics."""
    run = StoryRun(story_id=story_id, story_title="")
    print(f"\n[OK] Starting story {story_id}")

    try:
        start_resp = client.request(
            "POST", "/story/start", {}, {"CharacterID": character_id, "StoryID": story_id}
        )
    except RuntimeError as err:
        run.failure_reason = f"start failed: {err}"
        print(f"[ERROR] {run.failure_reason}")
        return run
    print(f"    started: segment={start_resp.get('SegmentID')} type={start_resp.get('SegmentType')}")

    for _ in range(args.max_segments):
        try:
            status = poll_segment(client, character_id, args)
        except RuntimeError as err:
            run.failure_reason = f"poll failed: {err}"
            print(f"[ERROR] {run.failure_reason}")
            return run

        run.segments_processed += 1
        story_meta = status.get("Story") or {}
        if story_meta.get("Title") and not run.story_title:
            run.story_title = story_meta.get("Title", "")

        log_segment_outcome(status, run)

        if status.get("StoryComplete") or not status.get("NextSegmentID"):
            run.completed = True
            print(f"[OK] Story complete after {run.segments_processed} segments")
            return run

        if (status.get("SegmentType") or "").lower() == "decision":
            try:
                submit_decision(client, character_id, status)
                run.decisions_made += 1
            except RuntimeError as err:
                run.failure_reason = f"decision failed: {err}"
                print(f"[ERROR] {run.failure_reason}")
                return run

    run.failure_reason = f"hit max-segments cap ({args.max_segments})"
    print(f"[WARNING] {run.failure_reason}")
    return run


def log_segment_outcome(status: dict, run: StoryRun) -> None:
    """Print outcome details and tally outcomes for a processed segment."""
    seg_type = (status.get("SegmentType") or "").lower()
    outcome = status.get("Outcome") or "n/a"
    if seg_type == "mechanical":
        events = status.get("ClientEvents") or []
        challenge = status.get("ChallengeResults") or []
        effects = status.get("Effects") or {}
        print(f"    outcome={outcome} effects={effects} events={len(events)} challenges={len(challenge)}")
        run.outcomes[outcome] = run.outcomes.get(outcome, 0) + 1


def check_mechanics(before: dict, after: dict, stats: RunStats) -> None:
    """Compare character snapshots and emit mechanics warnings."""
    if after.get("GameMode", "None") not in ("None", ""):
        msg = f"GameMode did not return to None (now {after.get('GameMode')})"
        stats.mechanics_warnings.append(msg)
        print(f"[WARNING] {msg}")

    valid_states = {"STANDING", "UNCONSCIOUS", "DEAD"}
    if after.get("CharState") not in valid_states:
        msg = f"Unexpected CharState after run: {after.get('CharState')}"
        stats.mechanics_warnings.append(msg)
        print(f"[WARNING] {msg}")

    for stat in ("Health", "Essence"):
        delta = (after.get(stat, 0) or 0) - (before.get(stat, 0) or 0)
        print(f"    {stat} delta: {delta:+d}")

    before_xp = before.get("SkillXP") or {}
    after_xp = after.get("SkillXP") or {}
    for skill in sorted(set(before_xp) | set(after_xp)):
        delta = (after_xp.get(skill, 0) or 0) - (before_xp.get(skill, 0) or 0)
        if delta:
            print(f"    SkillXP {skill}: {delta:+d}")


def probe_error_paths(client: ApiClient, character_id: str) -> None:
    """Opt-in probes for expected 4xx responses."""
    print("\n[OK] Probing error paths")
    probes = [
        ("GET", "/character", {"CharacterID": "not-a-uuid"}, {}, 400),
        ("POST", "/story/start", {}, {"CharacterID": character_id, "StoryID": "not-a-uuid"}, 400),
        ("POST", "/segment/decision", {}, {"CharacterID": character_id, "Decision": "bogus"}, 404),
    ]
    for method, path, params, body, expected in probes:
        try:
            client.request(method, path, params, body)
            print(f"[WARNING] {method} {path}: expected {expected}, got 2xx")
        except RuntimeError as err:
            if f"HTTP {expected}" in str(err):
                print(f"[OK] {method} {path}: {expected} as expected")
            else:
                print(f"[WARNING] {method} {path}: unexpected error: {err}")


def format_summary(stats: RunStats) -> None:
    """Print latency stats per endpoint and overall outcomes."""
    print("\n" + "=" * 60)
    print("Run Summary")
    print("=" * 60)

    by_endpoint = {}
    for call in stats.calls:
        key = f"{call.method} {call.path}"
        by_endpoint.setdefault(key, []).append(call.latency_ms)

    print(f"\n  API calls: {len(stats.calls)} across {len(by_endpoint)} endpoints")
    for key in sorted(by_endpoint):
        latencies = by_endpoint[key]
        median = statistics.median(latencies)
        p95 = sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)]
        print(f"    {key:35s} count={len(latencies):3d} median={median:7.1f}ms p95={p95:7.1f}ms")

    print(f"\n  Stories: {len(stats.stories)}")
    for run in stats.stories:
        flag = "[OK]" if run.completed else "[ERROR]"
        title = run.story_title or run.story_id
        outcomes = ", ".join(f"{k}={v}" for k, v in sorted(run.outcomes.items())) or "none"
        print(
            f"    {flag} {title}: segments={run.segments_processed} decisions={run.decisions_made} "
            f"outcomes=({outcomes})"
        )
        if run.failure_reason:
            print(f"        reason: {run.failure_reason}")

    if stats.mechanics_warnings:
        print(f"\n  Mechanics warnings: {len(stats.mechanics_warnings)}")
        for warn in stats.mechanics_warnings:
            print(f"    [WARNING] {warn}")
    else:
        print("\n  Mechanics warnings: none")


def parse_args() -> argparse.Namespace:
    """CLI argument parser."""
    parser = argparse.ArgumentParser(description="Eidolon Incremental API test rig")
    parser.add_argument("--max-segments", type=int, default=DEFAULT_MAX_SEGMENTS)
    parser.add_argument("--poll-min", type=int, default=DEFAULT_POLL_MIN_SECONDS)
    parser.add_argument("--poll-max", type=int, default=DEFAULT_POLL_MAX_SECONDS)
    parser.add_argument("--poll-timeout", type=int, default=DEFAULT_POLL_TIMEOUT_SECONDS)
    parser.add_argument("--story-id", default="", help="Run only this story id")
    parser.add_argument("--probe-errors", action="store_true", help="Run failure-path probes")
    parser.add_argument("--log-file", default="", help="Mirror stdout to this file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_dir = Path(__file__).resolve().parent.parent
    defaults = load_defaults_from_config(base_dir / "config.yml")
    cfg = collect_credentials(defaults)

    print("\n[OK] Authenticating with Cognito")
    try:
        tokens = cognito_login(cfg)
    except RuntimeError as err:
        print(f"[ERROR] {err}")
        return 1
    print("[OK] Cognito session established")

    stats = RunStats()
    client = ApiClient(cfg["api_base"], tokens, cfg, stats)
    active_character_id = ""

    try:
        client.request("GET", "/archetype", {}, {})
        character = select_character(client)
        active_character_id = character.get("CharacterID", "")

        before = fetch_character(client, active_character_id)
        if before.get("CharState") == "DEAD":
            print("[ERROR] Character is DEAD; cannot run stories")
            return 1
        if before.get("GameMode", "None") not in ("None", ""):
            print(f"[WARNING] Character in GameMode={before.get('GameMode')}; abandoning prior story")
            client.request("POST", "/story/abandon", {}, {"CharacterID": active_character_id})

        story_ids = [args.story_id] if args.story_id else (before.get("AvailableStories") or [])
        if not story_ids:
            print("[WARNING] No available stories for this character")
        for story_id in story_ids:
            stats.stories.append(walk_story(client, active_character_id, story_id, args))

        if args.probe_errors:
            probe_error_paths(client, active_character_id)

        after = fetch_character(client, active_character_id)
        print("\n[OK] Mechanics deltas:")
        check_mechanics(before, after, stats)

    except KeyboardInterrupt:
        print("\n[WARNING] Interrupted by operator")
    except RuntimeError as err:
        print(f"[ERROR] {err}")
    finally:
        if active_character_id:
            try:
                client.request("POST", "/story/abandon", {}, {"CharacterID": active_character_id})
                print("[OK] Cleanup: abandoned any active story")
            except RuntimeError as err:
                print(f"[WARNING] Cleanup abandon failed (likely no active story): {err}")

    format_summary(stats)
    success = all(run.completed for run in stats.stories) and not stats.mechanics_warnings
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
