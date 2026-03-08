"""
Character state utilities.

Provides functions for calculating character state based on wounds and damage.
This module has no dependencies on character_data or items to avoid circular imports.
"""

from datetime import datetime, timedelta, timezone

from eidolon.constants import AGGRAVATED_HEAL_TIME, BASHING_HEAL_TIME, LETHAL_HEAL_TIME, CharState


def calculate_heal_time(damage_type: str) -> str:
    """
    Calculate when a wound will heal based on damage type.

    Args:
        damage_type: Type of damage (bashing, lethal, aggravated)

    Returns:
        ISO 8601 timestamp string for when the wound will heal
    """
    heal_times = {
        "bashing": BASHING_HEAL_TIME,
        "lethal": LETHAL_HEAL_TIME,
        "aggravated": AGGRAVATED_HEAL_TIME,
    }

    heal_delta: timedelta = heal_times.get(damage_type.lower(), LETHAL_HEAL_TIME)
    heal_at: datetime = datetime.now(timezone.utc) + heal_delta
    return heal_at.isoformat()


def determine_character_state_from_wounds(max_health: int, wounds: list) -> str:
    """
    Determine character state based on wounds.

    Implements the MUD damage system rules:
    - If lethal + aggravated wounds >= max_health: dead
    - If total wounds >= max_health with any bashing: unconscious
    - Otherwise: standing

    Args:
        max_health: Character's maximum health
        wounds: List of wound objects with DamageType field

    Returns:
        Character state: "standing", "unconscious", or "dead"
    """
    if not wounds:
        return CharState.STANDING.value

    # Count deadly wounds (lethal and aggravated)
    deadly_wounds = sum(1 for w in wounds if w.get("DamageType") in ["lethal", "aggravated"])

    # If deadly wounds fill all health levels, character is dead
    if deadly_wounds >= max_health:
        return CharState.DEAD.value

    # Check if all health levels are filled
    total_wounds = len(wounds)
    if total_wounds >= max_health:
        # Health track is full but has bashing - unconscious
        return CharState.UNCONSCIOUS.value

    return CharState.STANDING.value
