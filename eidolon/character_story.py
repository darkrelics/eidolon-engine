"""
Character story management utilities.

Provides functions for managing character interactions with stories.
"""

from datetime import datetime, timezone

from botocore.exceptions import ClientError

from eidolon.character_data import character_get
from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger
from eidolon.mechanics import calculate_heal_time


def get_story_history(character_id: str, story_id: str) -> dict:
    """
    Get most recent story history for a character and story.
    
    Since a character can have multiple instances of the same story,
    this returns the most recent completed or abandoned instance.

    Args:
        character_id: Character UUID
        story_id: Story UUID

    Returns:
        Most recent history record dict or empty dict if not found

    Raises:
        RuntimeError: If database query fails
    """
    if not character_id:
        raise ValueError("Character ID cannot be empty")
    if not story_id:
        raise ValueError("Story ID cannot be empty")

    try:
        # Query all story instances for this character
        response = dynamo.query(
            TableName.STORY_HISTORY,
            KeyConditionExpression="CharacterID = :character_id",
            ExpressionAttributeValues={":character_id": character_id},
            ScanIndexForward=False,  # Most recent first (UUIDv7 sorts by time)
        )
        
        # Filter for the specific story and find the most recent finished instance
        items = response.get("Items", []) # type: ignore
        for item in items:
            if item.get("StoryID") == story_id and item.get("FinishedAt"):
                return item
        
        # No finished instance found, check for in-progress
        for item in items:
            if item.get("StoryID") == story_id:
                return item
                
        return {}  # No history found for this story
    except ClientError as err:
        logger.error(f"Failed to get story history for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get story history: {err}") from err


def get_story_cooldown(character_id: str, story_id: str, story_type: str):
    """
    Calculate cooldown remaining for a story based on its type and last completion.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        story_type: Type of story (one-time, daily, repeatable)

    Returns:
        Seconds remaining on cooldown, 0 if playable, -1 if permanently unavailable
    """
    if story_type == "repeatable":
        return 0

    try:
        history = get_story_history(character_id, story_id)

        if not history:
            return 0  # Never played

        # Check if story was completed or abandoned
        if not history.get("FinishedAt"):
            return 0  # Abandoned stories can be retried

        if story_type == "one-time":
            # Check if it was completed successfully
            outcome = history.get("FinalOutcome", "")
            if outcome in ["normal", "exceptional", "minimal"]:
                return -1  # Permanently unavailable
            return 0  # Failed/died, can retry

        if story_type == "daily":
            # Calculate time until midnight UTC
            finished_at = datetime.fromisoformat(history.get("FinishedAt", "").replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)

            # Check if completion was today
            if finished_at.date() == now.date():
                # Calculate seconds until midnight
                midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
                midnight = midnight.replace(day=midnight.day + 1)
                return int((midnight - now).total_seconds())

            return 0  # Completed on a previous day

    except Exception as err:
        logger.error(f"Error checking story cooldown Error: {err}")
        return 0


def check_story_prerequisites(character: dict, prerequisites: dict) -> bool:
    """
    Check if character meets story prerequisites.

    Args:
        character: Character data
        prerequisites: Story prerequisite requirements

    Returns:
        True if all prerequisites are met
    """
    # Check minimum skills
    min_skills = prerequisites.get("minSkills", {})
    character_skills = character.get("Skills", {})

    for skill, min_value in min_skills.items():
        if character_skills.get(skill, 0) < min_value:
            return False

    # Check required items
    required_items = prerequisites.get("requiredItems", [])
    if required_items:
        inventory = character.get("Inventory", {})
        inventory_items = list(inventory.values())
        for item_id in required_items:
            if item_id not in inventory_items:
                return False

    return True


def get_stories(character_id: str, player_id: str, available_story_ids: list) -> list:
    """
    Get story details for a list of story IDs, checking prerequisites and cooldowns.

    Args:
        character_id: Character UUID
        player_id: Player UUID
        available_story_ids: List of story IDs available to the character

    Returns:
        List of story data dicts with availability information

    Raises:
        RuntimeError: If database operations fail
    """
    if not available_story_ids:
        return []

    stories: list = []

    character: dict = character_get(character_id, player_id)

    for story_id in available_story_ids:
        try:
            story_data = dynamo.get_item(TableName.STORY, {"StoryID": story_id})
            if not story_data:
                continue
        except ClientError as err:
            logger.error(f"Failed to get story for {story_id} Error: {err}", exc_info=True)
            continue

        try:
            # Check prerequisites
            prerequisites = story_data.get("Prerequisites", {})
            if not check_story_prerequisites(character, prerequisites):
                continue

            # Check cooldown
            story_type = story_data.get("StoryType", "repeatable")
            cooldown = get_story_cooldown(character_id, story_id, story_type)

            if cooldown == -1:  # Permanently unavailable
                continue

            # Format story for response with PascalCase
            formatted_story: dict = {
                "StoryID": story_id,
                "Title": story_data.get("Title", "Unknown Story"),
                "Description": story_data.get("Description", ""),
                "Type": story_type,
                "Available": cooldown == 0,
                "CooldownRemaining": max(0, cooldown) if cooldown is not None else 0,
                "EstimatedDuration": int(story_data.get("EstimatedDuration", 0)),
                "Prerequisites": prerequisites,
                "DifficultyMap": story_data.get("DifficultyMap", {}),
                "RewardTiers": story_data.get("RewardTiers", {}),
                "BaseXPMultiplier": float(story_data.get("BaseXPMultiplier", 0.5)),
            }

            stories.append(formatted_story)
            logger.debug(f"Story processed for {story_id}")

        except ValueError:
            logger.warning(f"Story not found for {story_id}")
            continue
        except RuntimeError as err:
            logger.error(f"Error loading story for {story_id} Error: {err}")
            continue

    return stories


def reset_character_game_mode(character_id: str) -> None:
    """
    Reset character's game mode and clear active story/segment fields.

    This function resets the character state when abandoning a story:
    - Sets GameMode back to "None"
    - Clears ActiveStoryID
    - Clears ActiveSegmentID

    Args:
        character_id: Character UUID

    Raises:
        ValueError: If character_id is empty
        RuntimeError: If database update fails
    """
    if not character_id:
        raise ValueError("Character ID cannot be empty")

    try:
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET GameMode = :none REMOVE ActiveStoryID, ActiveSegmentID",
            ExpressionAttributeValues={":none": "None"},
        )
        logger.info(f"Reset character game mode and cleared active story fields for {character_id}")

    except ClientError as err:
        logger.error(f"Failed to reset character state for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to reset character state: {err}") from err


def character_get_active_story(character: dict) -> dict:
    """
    Get active story for a character.

    Args:
        character: Character Record dict

    Returns:
        Story dict. Empty dict if no active segment found.

    Raises:
        RuntimeError: If database error occurs
    """
    active_story_id: str = character.get("ActiveStoryID")  # type: ignore

    # First try: If character has ActiveSegmentID, use GetItem
    if active_story_id:
        try:
            active_story: dict = dynamo.get_item(TableName.STORY, key={"StoryID": active_story_id})  # type: ignore

            if active_story:
                logger.debug("Active story found via GetItem")
                return active_story
            else:
                logger.warning("Segment found but not valid")
                return {}
        except ClientError as err:
            logger.error(f"Error retrieving story by ID: {err}")
            return {}

    return {}


def apply_story_outcome_effects(character_id: str, outcome_effects: dict) -> None:
    """
    Apply story outcome effects like room changes and item rewards.

    Args:
        character_id: Character UUID
        outcome_effects: Dict containing room changes, items, etc.

    Raises:
        RuntimeError: If database operations fail
    """
    from eidolon.character_data import apply_character_updates

    try:
        update_expressions = []
        expression_attribute_names = {}
        expression_attribute_values = {}

        # Handle room change
        if "room" in outcome_effects:
            update_expressions.append("#room = :room")
            expression_attribute_names["#room"] = "RoomID"
            expression_attribute_values[":room"] = outcome_effects["room"]

        # Handle wounds from story outcomes
        if "wounds" in outcome_effects:

            # Add heal times to wounds
            wounds_with_heal_times = []
            for wound in outcome_effects["wounds"]:
                wound_data = wound.copy()
                if "HealAt" not in wound_data:
                    damage_type = wound_data.get("DamageType", "lethal")
                    wound_data["HealAt"] = calculate_heal_time(damage_type)
                wounds_with_heal_times.append(wound_data)

            # Apply wounds through character updates
            try:
                apply_character_updates(character_id, {"Wounds": wounds_with_heal_times})
                logger.info(f"Applied story outcome wounds for {character_id}")
            except Exception as err:
                logger.error(f"Failed to apply story wounds for {character_id} Error: {err}", exc_info=True)
                raise RuntimeError(f"Failed to apply story wounds: {err}") from err

        if update_expressions:
            update_expression: str = "SET " + ", ".join(update_expressions)

            dynamo.update_item(
                TableName.CHARACTERS,
                Key={"CharacterID": character_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_attribute_names,
                ExpressionAttributeValues=expression_attribute_values,
            )

            logger.info(f"Applied story outcome effects for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to apply outcome effects for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to apply outcome effects: {err}") from err
