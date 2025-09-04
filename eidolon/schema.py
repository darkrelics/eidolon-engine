"""
Schema normalization utilities.

Accepts story/segment data that may include mixed casing from tools and
produces a consistent internal structure. Persistence and API responses
use PascalCase.
"""


def get_first_key(d: dict, *keys: str, default=None):
    """
    Return the first present key's value from a dictionary.

    Args:
        d: Source dictionary
        keys: Keys to try in order
        default: Value to return if none of the keys are present

    Returns:
        The value for the first found key, or default if none found.
    """
    for k in keys:
        if k in d:
            return d[k]
    return default


def coerce_int(value, default: int = 0) -> int:
    """
    Convert a value to int, returning default on failure.

    Args:
        value: Value to convert
        default: Default integer to return if conversion fails

    Returns:
        int value of input or default.
    """
    try:
        return int(value)
    except Exception:
        return default


def normalize_challenges(raw_challenges) -> list:
    """
    Normalize Challenges list to internal field names.

    Args:
        raw_challenges: List of challenge dicts with possible mixed casing

    Returns:
        List of normalized challenge dicts with attribute, skill, difficulty, attempts.
    """
    if not isinstance(raw_challenges, list):
        return []
    norm: list = []
    for c in raw_challenges:
        if not isinstance(c, dict):
            continue
        norm.append(
            {
                "Attribute": c.get("Attribute"),
                "Skill": c.get("Skill"),
                "Difficulty": coerce_int(c.get("Difficulty", 0)),
                "Attempts": coerce_int(c.get("Attempts", 1)),
            }
        )
    return norm


def normalize_wounds(raw_wounds) -> list:
    """
    Normalize wounds into a list of dicts with DamageType.

    Args:
        raw_wounds: List of wound strings or dicts

    Returns:
        List of wound dicts with canonical keys.
    """
    if not isinstance(raw_wounds, list):
        return []
    out: list = []
    for w in raw_wounds:
        if isinstance(w, str):
            out.append({"DamageType": w})
        elif isinstance(w, dict):
            wd = dict(w)
            # Ensure canonical key
            if "DamageType" in wd:
                wd["DamageType"] = wd.get("DamageType")
            out.append(wd)
    return out


def normalize_results(raw_results) -> dict:
    """
    Normalize Results mapping for outcomes.

    Outcome keys are lower-cased for internal lookup. Inner fields use
    'narrative' and 'effects'; per-outcome NextSegmentID is preserved.

    Args:
        raw_results: Dict mapping outcome -> result block

    Returns:
        Dict of normalized results keyed by lower-case outcome.
    """
    if not isinstance(raw_results, dict):
        return {}

    norm: dict = {}
    for outcome_key, outcome_val in raw_results.items():
        if not isinstance(outcome_val, dict):
            continue
        # Normalize outcome key to title case for consistent lookup
        k = str(outcome_key).title()
        narrative = outcome_val.get("Narrative", "")
        effects = outcome_val.get("Effects", {}) or {}

        if isinstance(effects, dict):
            effects = {
                "Room": effects.get("Room"),
                "Items": effects.get("Items", []),
                "Wounds": normalize_wounds(effects.get("Wounds", [])),
            }

        norm[k] = {
            "Narrative": narrative if isinstance(narrative, str) else str(narrative),
            "Effects": effects if isinstance(effects, dict) else {},
        }

        next_seg = outcome_val.get("NextSegmentID")
        if next_seg is not None:
            norm[k]["NextSegmentID"] = next_seg

    return norm


def normalize_combat(raw_combat) -> dict:
    """
    Normalize combat block to canonical keys while tolerating mixed casing.

    Args:
        raw_combat: Combat config dict

    Returns:
        Dict with OpponentID/opponentId, MaxRounds/maxRounds, Environment.
    """
    if not isinstance(raw_combat, dict):
        return {}
    opponent_id = raw_combat.get("OpponentID")
    max_rounds = coerce_int(raw_combat.get("MaxRounds", 0), 0)
    env = raw_combat.get("Environment", {}) or {}
    return {
        "OpponentID": opponent_id,
        "MaxRounds": max_rounds,
        "Environment": env,
    }


def normalize_segment_definition(raw: dict) -> dict:
    """
    Normalize a segment definition to the internal model while keeping
    PascalCase at the top-level for storage and APIs.

    Args:
        raw: Raw segment definition possibly with mixed casing

    Returns:
        Copy of the segment with normalized inner structures.
    """
    if not isinstance(raw, dict):
        return {}

    seg = dict(raw)

    seg_type = raw.get("SegmentType")
    if seg_type:
        seg["SegmentType"] = seg_type

    duration = raw.get("SegmentDuration")
    if duration is not None:
        seg["SegmentDuration"] = coerce_int(duration, 0)

    seg["Challenges"] = normalize_challenges(raw.get("Challenges", []))

    combat = normalize_combat(raw.get("Combat", {}))
    if combat:
        seg["Combat"] = combat

    results = normalize_results(raw.get("Results", {}))
    seg["Results"] = results

    if "DecisionOptions" in raw:
        seg["DecisionOptions"] = raw.get("DecisionOptions", {}) or {}
    if "DecisionText" in raw:
        seg["DecisionText"] = raw.get("DecisionText", "")
    if "DefaultDecision" in raw:
        seg["DefaultDecision"] = raw.get("DefaultDecision")

    # Note: NextSegmentID should only exist within Results for each outcome, not at top level

    return seg
