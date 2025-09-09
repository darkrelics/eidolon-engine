"""
Schema validation utilities.

Enforces PascalCase keys (with capitalized abbreviations) across story and
segment definitions. Use these validators at boundaries (authoring, data
loading, QA). Runtime paths should assume canonical data and avoid repeated
validation.
"""

import re

_PASCAL_CASE_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")


def _is_pascal_case(key: str) -> bool:
    """Return True if key is PascalCase with optional capitalized abbreviations."""
    if not isinstance(key, str):
        return False
    return bool(_PASCAL_CASE_RE.match(key))


def _validate_dict_keys_pascal(d: dict, path: str) -> None:
    """Validate that all keys in the dict are PascalCase field names."""
    if not isinstance(d, dict):
        raise ValueError(f"{path} must be a dict")
    for k in d.keys():
        if not _is_pascal_case(k):
            raise ValueError(f"Invalid key casing at {path}.{k} - expected PascalCase with capitalized abbreviations")


def _validate_challenges(challenges: list, path: str) -> None:
    if not isinstance(challenges, list):
        raise ValueError(f"{path} must be a list")
    for idx, ch in enumerate(challenges):
        if not isinstance(ch, dict):
            raise ValueError(f"{path}[{idx}] must be a dict")
        _validate_dict_keys_pascal(ch, f"{path}[{idx}]")


def _validate_combat(combat: dict, path: str) -> None:
    _validate_dict_keys_pascal(combat, path)
    env = combat.get("Environment")
    if env is not None:
        _validate_dict_keys_pascal(env, f"{path}.Environment")


def _validate_wounds(wounds: list, path: str) -> None:
    if not isinstance(wounds, list):
        raise ValueError(f"{path} must be a list")
    for i, wound in enumerate(wounds):
        if not isinstance(wound, dict):
            raise ValueError(f"{path}[{i}] must be a dict")
        _validate_dict_keys_pascal(wound, f"{path}[{i}]")


def _validate_effects(effects: dict, path: str) -> None:
    _validate_dict_keys_pascal(effects, path)
    wounds = effects.get("Wounds")
    if wounds is not None:
        _validate_wounds(wounds, f"{path}.Wounds")


def _validate_results(results: dict, path: str) -> None:
    if not isinstance(results, dict):
        raise ValueError(f"{path} must be a dict")
    for outcome_key, block in results.items():
        # Outcome keys must be PascalCase words (Death, Failure, Minimal, Normal, Exceptional)
        if not _is_pascal_case(str(outcome_key)):
            raise ValueError(f"Invalid key casing at {path}.{outcome_key} - expected PascalCase outcome key")
        if not isinstance(block, dict):
            raise ValueError(f"{path}.{outcome_key} must be a dict")
        _validate_dict_keys_pascal(block, f"{path}.{outcome_key}")
        effects = block.get("Effects")
        if effects is not None:
            _validate_effects(effects, f"{path}.{outcome_key}.Effects")


def validate_segment_definition(segment: dict) -> dict:
    """
    Strictly validate a segment definition for PascalCase keys throughout.

    Args:
        segment: Segment definition dict (from content or database)

    Returns:
        The original segment dict if validation passes.

    Raises:
        ValueError: If any keys violate the PascalCase policy
    """
    if not isinstance(segment, dict):
        raise ValueError("Segment definition must be a dict")

    _validate_dict_keys_pascal(segment, "Segment")

    if "Challenges" in segment and segment["Challenges"] is not None:
        _validate_challenges(segment.get("Challenges", []), "Segment.Challenges")

    if "Combat" in segment and segment["Combat"] is not None:
        _validate_combat(segment.get("Combat", {}), "Segment.Combat")

    if "Results" in segment and segment["Results"] is not None:
        _validate_results(segment.get("Results", {}), "Segment.Results")

    if "DecisionOptions" in segment and segment["DecisionOptions"] is not None:
        if not isinstance(segment["DecisionOptions"], dict):
            raise ValueError("Segment.DecisionOptions must be a dict")

    return segment
