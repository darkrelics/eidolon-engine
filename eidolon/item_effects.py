"""
Item effects system for Eidolon Engine.

Handles applying consumable item effects to characters (healing, buffs, etc.).
"""

import random
import re

from botocore.exceptions import ClientError

from eidolon.constants import CharState
from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger


def parse_dice_notation(notation: str) -> int:
    """
    Parse dice notation and return a rolled value.

    Supports formats like: "2d4+2", "1d6", "3d8-1", or plain integers "10"

    Args:
        notation: Dice notation string (e.g., "2d4+2" or "10")

    Returns:
        Integer result of dice roll or parsed value

    Examples:
        "2d4+2" -> rolls 2 four-sided dice and adds 2
        "1d6" -> rolls 1 six-sided die
        "10" -> returns 10
    """
    notation = notation.strip()

    # Check for plain integer
    if notation.isdigit():
        return int(notation)

    # Parse dice notation: XdY+Z or XdY-Z
    pattern = r"(\d+)d(\d+)(([+-])(\d+))?"
    match = re.match(pattern, notation, re.IGNORECASE)

    if not match:
        logger.warning(f"Invalid dice notation: {notation}, defaulting to 1")
        return 1

    num_dice = int(match.group(1))
    die_size = int(match.group(2))
    modifier = 0

    if match.group(3):  # Has modifier
        operator = match.group(4)
        modifier_value = int(match.group(5))
        modifier = modifier_value if operator == "+" else -modifier_value

    # Roll the dice
    total = sum(random.randint(1, die_size) for _ in range(num_dice))
    result = total + modifier

    logger.debug(f"Dice roll: {notation} = {total} + {modifier} = {result}")
    return max(1, result)  # Ensure at least 1


def apply_healing(character: dict, healing_amount: int) -> dict:
    """
    Apply healing to a character by removing wounds.

    Args:
        character: Character dict with Wounds list
        healing_amount: Amount of healing (number of wounds to remove)

    Returns:
        Dict with healing results:
            - wounds_healed: Number of wounds actually removed
            - remaining_wounds: Number of wounds still present
            - current_health: Character's health after healing
            - max_health: Character's max health
    """
    wounds = character.get("Wounds", [])
    max_health = character.get("MaxHealth", 10)
    initial_wound_count = len(wounds)

    # Remove wounds (heal from most recent first)
    wounds_to_heal = min(healing_amount, initial_wound_count)
    remaining_wounds = wounds[:-wounds_to_heal] if wounds_to_heal > 0 else wounds

    # Calculate new health
    new_health = max_health - len(remaining_wounds)

    # Update character state if they were dead
    char_state = character.get("CharState")
    was_dead = char_state == CharState.DEAD.value

    if was_dead and len(remaining_wounds) < max_health:
        # Character is no longer dead (has some health)
        character["CharState"] = CharState.ALIVE.value
        logger.info("Character revived from death by healing")

    return {
        "wounds_healed": wounds_to_heal,
        "remaining_wounds": len(remaining_wounds),
        "current_health": new_health,
        "max_health": max_health,
        "was_dead": was_dead,
    }


def apply_item_effects(character_id: str, prototype: dict) -> dict:
    """
    Apply consumable item effects to a character.

    Args:
        character_id: Character UUID
        prototype: Item prototype dict with effect metadata

    Returns:
        Dict with effect results:
            - effects_applied: List of effect descriptions
            - healing: Healing result dict (if healing occurred)
            - message: Flavor text from item's Use verb

    Raises:
        ValueError: If character not found or item not consumable
        RuntimeError: If database operations fail
    """
    # Get character data
    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
        if not character:
            raise ValueError("Character not found")
    except ClientError as err:
        logger.error(f"Failed to fetch character {character_id}: {err}")
        raise RuntimeError("Failed to fetch character data") from err

    # Check if item has consumable effects
    metadata = prototype.get("Metadata", {})
    verbs = prototype.get("Verbs", {})
    use_message = verbs.get("Use", "You use the item.")

    effects_applied = []
    healing_result = None
    update_expressions = []
    expression_values = {}

    # Apply healing effects
    healing_notation = metadata.get("HealingAmount")
    if healing_notation:
        healing_amount = parse_dice_notation(healing_notation)
        healing_result = apply_healing(character, healing_amount)

        # Update wounds list
        wounds = character.get("Wounds", [])
        wounds_to_heal = healing_result["wounds_healed"]
        new_wounds = wounds[:-wounds_to_heal] if wounds_to_heal > 0 else wounds

        update_expressions.append("Wounds = :wounds")
        expression_values[":wounds"] = new_wounds

        # Update character state if revived
        if healing_result.get("was_dead") and healing_result["current_health"] > 0:
            update_expressions.append("CharState = :char_state")
            expression_values[":char_state"] = CharState.ALIVE.value

        effects_applied.append(
            f"Healed {healing_result['wounds_healed']} wound(s) "
            f"({healing_result['current_health']}/{healing_result['max_health']} HP)"
        )

    # Check for other effect types
    nutrition_value = metadata.get("NutritionValue")
    if nutrition_value:
        # Future: Could restore essence, provide temporary buffs, etc.
        effects_applied.append(f"Gained nutrition ({nutrition_value})")
        logger.info(f"Nutrition effect not yet implemented: {nutrition_value}")

    buff_duration = metadata.get("BuffDuration")
    if buff_duration:
        # Future: Temporary stat boosts, resistances, etc.
        effects_applied.append(f"Buff applied (duration: {buff_duration})")
        logger.info(f"Buff effects not yet implemented: {buff_duration}")

    # If no recognizable effects, this item may not be consumable
    if not effects_applied:
        logger.warning(f"Item {prototype.get('PrototypeID')} has no consumable effects")
        # Still allow consumption - some items might just have flavor text
        effects_applied.append("Item used (no mechanical effects)")

    # Apply updates to character
    if update_expressions:
        try:
            dynamo.update_item(
                TableName.CHARACTERS,
                Key={"CharacterID": character_id},
                UpdateExpression=f"SET {', '.join(update_expressions)}",
                ExpressionAttributeValues=expression_values,
            )
            logger.info(f"Applied item effects to character {character_id}: {effects_applied}")
        except ClientError as err:
            logger.error(f"Failed to apply effects to character {character_id}: {err}")
            raise RuntimeError("Failed to apply item effects") from err

    return {
        "effects_applied": effects_applied,
        "healing": healing_result,
        "message": use_message,
    }
