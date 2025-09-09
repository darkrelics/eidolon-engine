"""
Schema normalization utilities.

Accepts story/segment data that may include mixed casing from tools and
produces a consistent internal structure. Persistence and API responses
use PascalCase.
"""


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
        raw_challenges: List of challenge dicts using PascalCase keys

    Returns:
        List of normalized challenge dicts with attribute, skill, difficulty, attempts.
    """
    if not isinstance(raw_challenges, list):
        return []
    norm: list = []
    for c in raw_challenges:
        if not isinstance(c, dict):
            continue
        attribute = c.get("Attribute")
        skill = c.get("Skill")
        difficulty = coerce_int(c.get("Difficulty", 0), 0)
        attempts = coerce_int(c.get("Attempts", 1), 1)
        norm.append(
            {
                "Attribute": attribute,
                "Skill": skill,
                "Difficulty": difficulty,
                "Attempts": attempts,
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
            wd: dict = {}
            damage_type = w.get("DamageType")
            if damage_type is not None:
                wd["DamageType"] = damage_type
            # Preserve only PascalCase keys as-is (no conversion)
            for k, v in w.items():
                if k == "DamageType":
                    continue
                if k and k[0].isupper():
                    wd[k] = v
            out.append(wd)
    return out


def normalize_results(raw_results) -> dict:
    """
    Normalize Results mapping for outcomes.

    Outcome keys are normalized to Title/PascalCase (e.g., "Normal",
    "Exceptional"). Inner fields use PascalCase keys: "Narrative" and
    "Effects". Per-outcome "NextSegmentID" is preserved when present.

    Args:
        raw_results: Dict mapping outcome -> result block

    Returns:
        Dict of normalized results keyed by Title/PascalCase outcome.
    """
    if not isinstance(raw_results, dict):
        return {}

    norm: dict = {}
    for outcome_key, outcome_val in raw_results.items():
        if not isinstance(outcome_val, dict):
            continue
        # Normalize outcome key to Title/PascalCase for consistent lookup
        k = str(outcome_key).title()

        narrative = outcome_val.get("Narrative", "")
        effects_in = outcome_val.get("Effects", {}) or {}

        effects_out: dict = {}
        if isinstance(effects_in, dict):
            room = effects_in.get("Room")
            items = effects_in.get("Items", []) or []
            wounds = effects_in.get("Wounds", []) or []
            if room is not None:
                effects_out["Room"] = room
            if items is not None:
                effects_out["Items"] = items
            effects_out["Wounds"] = normalize_wounds(wounds)

        norm[k] = {
            "Narrative": narrative if isinstance(narrative, str) else str(narrative),
            "Effects": effects_out,
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

    # SegmentType
    seg_type = raw.get("SegmentType")
    if seg_type:
        seg["SegmentType"] = seg_type

    # SegmentDuration
    duration_val = raw.get("SegmentDuration")
    if duration_val is not None:
        seg["SegmentDuration"] = coerce_int(duration_val, 0)

    # Challenges
    challenges_in = raw.get("Challenges", [])
    seg["Challenges"] = normalize_challenges(challenges_in)

    # Combat
    combat_in = raw.get("Combat", {})
    combat = normalize_combat(combat_in)
    if combat:
        seg["Combat"] = combat

    # Results
    results_in = raw.get("Results", {})
    results = normalize_results(results_in)
    seg["Results"] = results

    # Decision fields
    if "DecisionOptions" in raw:
        seg["DecisionOptions"] = raw.get("DecisionOptions", {}) or {}
    if "DecisionText" in raw:
        seg["DecisionText"] = raw.get("DecisionText", "")
    if "DefaultDecision" in raw:
        seg["DefaultDecision"] = raw.get("DefaultDecision")

    # Note: NextSegmentID should only exist within Results for each outcome, not at top level

    return seg
