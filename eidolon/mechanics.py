import math
import random
from datetime import datetime, timedelta, timezone

from botocore.exceptions import ClientError

from eidolon.character_data import get_character
from eidolon.dynamo import TableName, dynamo
from eidolon.environment import DEFAULT_HEALTH
from eidolon.logger import logger

# Wound healing durations (matching MUD server)
BASHING_HEAL_TIME = timedelta(minutes=15)
LETHAL_HEAL_TIME = timedelta(hours=6)
AGGRAVATED_HEAL_TIME = timedelta(days=7)


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
    - If health > 0: standing
    - If health = 0 with any bashing wounds: unconscious
    - If health = 0 with only lethal/aggravated wounds: dead

    Args:
        max_health: Character's maximum health
        wounds: List of wound objects with DamageType field

    Returns:
        Character state: "standing", "unconscious", or "dead"
    """
    if not wounds:
        return "standing"

    current_health = max_health - len(wounds)

    if current_health > 0:
        return "standing"

    # Health is 0 or less - check wound types
    has_bashing = any(w.get("DamageType") == "bashing" for w in wounds)

    if has_bashing:
        return "unconscious"
    else:
        return "dead"


def apply_death_or_unconscious_outcome(character_id: str, outcome: str, wounds: list) -> str:
    """
    Apply death or unconscious state to character based on outcome and wounds.

    Args:
        character_id: Character UUID
        outcome: Segment outcome ("death", "failure", etc.)
        wounds: Current character wounds

    Returns:
        New character state that was applied

    Raises:
        RuntimeError: If database operation fails
    """
    if outcome != "death":
        return "standing"  # Only death outcomes change state

    try:
        # Get character to check current state and max health
        character = get_character(character_id)
        max_health = character.get("MaxHealth", DEFAULT_HEALTH)

        # Determine new state based on wounds
        new_state = determine_character_state_from_wounds(max_health, wounds)

        if new_state != character.get("CharState", "standing"):
            # Update character state
            update_expression = "SET CharState = :state, UpdatedAt = :timestamp"
            expression_values = {":state": new_state, ":timestamp": datetime.now(timezone.utc).isoformat()}

            # If dead, also update location to death room
            if new_state == "dead":
                update_expression += ", Room = :room"
                expression_values[":room"] = "0"  # Death room

            dynamo.update_item(
                TableName.CHARACTERS,
                Key={"CharacterID": character_id},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values,
            )

            logger.info(f"Updated character state due to death outcome for {character_id}")

        return new_state

    except ClientError as err:
        logger.error(f"Failed to apply death/unconscious state for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to apply death/unconscious state: {err}") from err


def resolve_opposed_check(aggressor: float, defender: float) -> dict:
    """
    Resolve an opposed check using MUD mechanics.

    Args:
        aggressor: Aggressor's rating
        defender: Defender's rating

    Returns:
        Dictionary with success (bool) and sigma (float)
    """
    # Constants from MUD mechanics
    k_shift = 0.20  # How much rating difference matters
    k_var = 0.35  # Variance scaling
    min_sig = 0.25  # Minimum variance

    # Calculate difference
    diff: float = aggressor - defender

    # Calculate mean and variance
    mean: float = k_shift * diff
    variance: float = 1.0 + k_var * math.tanh(diff / 10.0)
    variance = max(variance, min_sig)

    # Generate outcome using normal distribution
    sigma: float = random.gauss(mean, variance)
    success: bool = sigma >= 0

    return {"success": success, "sigma": sigma}
