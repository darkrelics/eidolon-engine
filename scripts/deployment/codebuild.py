"""CodeBuild operations."""

import time

import boto3
from botocore.exceptions import ClientError
from deployment.aws_utils import retry_on_transient_error


def trigger_build(project_name: str, region: str, source_version: str = "") -> bool:
    """Trigger CodeBuild and wait for completion with phase tracking.

    Args:
        project_name: Name of the CodeBuild project
        region: AWS region
        source_version: Git branch/tag/commit to build (overrides project default)

    Returns:
        bool: True if build succeeded, False otherwise
    """
    print(f"Building {project_name}...")
    codebuild = boto3.client("codebuild", region_name=region)

    try:
        build_params = {"projectName": project_name}
        if source_version:
            build_params["sourceVersion"] = source_version
            print(f"  Using branch: {source_version}")
        response = retry_on_transient_error(lambda: codebuild.start_build(**build_params))
    except ClientError as err:
        print(f"  Error starting build: {err}")
        return False

    build = response.get("build", {})
    build_id = build.get("id", "")
    print(f"  Build ID: {build_id}")

    last_phase = ""
    max_attempts = 180  # 30 minutes with 10 second intervals
    attempt = 0
    dots_count = 0

    while attempt < max_attempts:
        try:
            response = retry_on_transient_error(lambda: codebuild.batch_get_builds(ids=[build_id]))
        except ClientError as err:
            print(f"\n  Error checking build status: {err}")
            return False

        builds = response.get("builds", [])
        if not builds:
            print()
            print("  Error: No build found")
            return False
        build = builds[0]
        status = build.get("buildStatus", "")
        current_phase = build.get("currentPhase", "PENDING")

        if current_phase != last_phase:
            if dots_count > 0:
                print()
                dots_count = 0
            print(f"  Phase: {current_phase}", end="", flush=True)
            last_phase = current_phase
        else:
            print(".", end="", flush=True)
            dots_count += 1

        if status == "SUCCEEDED":
            if dots_count > 0:
                print()
            print(f"  {project_name} built successfully")
            return True
        elif status in ["FAILED", "FAULT", "STOPPED", "TIMED_OUT"]:
            if dots_count > 0:
                print()
            print(f"  Build failed: {status}")
            print_build_failure_details(build)
            return False

        time.sleep(10)
        attempt += 1

    if dots_count > 0:
        print()
    print("  Build timeout after 30 minutes")
    return False


def print_build_failure_details(build: dict):
    """Print detailed build failure information.

    Args:
        build: Build response dictionary
    """
    has_phase_errors = False
    for phase in build.get("phases", []):
        if phase.get("phaseStatus") == "FAILED":
            has_phase_errors = True
            phase_type = phase.get("phaseType", "Unknown")
            print(f"    Failed in {phase_type}:")

            contexts = phase.get("contexts", [])
            if contexts:
                for context in contexts:
                    message = context.get("message", "Unknown error")
                    status_code = context.get("statusCode", "")
                    if status_code:
                        print(f"      [{status_code}] {message}")
                    else:
                        print(f"      {message}")
            else:
                print("      No error details available")

    if not has_phase_errors:
        print("    No specific phase errors found")
        build_status_reason = build.get("buildStatus", "")
        if build_status_reason:
            print(f"    Build status: {build_status_reason}")

    logs = build.get("logs", {})
    deep_link = logs.get("deepLink", "")
    if deep_link:
        print(f"    CloudWatch Logs: {deep_link}")
