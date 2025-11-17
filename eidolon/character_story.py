"""
Character story management utilities.

Provides functions for managing character interactions with stories.
"""

from datetime import datetime, timedelta, timezone

from botocore.exceptions import ClientError

from eidolon.character_data import apply_character_updates, character_clear_story, character_get
from eidolon.character_segment import character_get_active_segment
from eidolon.dynamo import TableName, decimal_to_float, dynamo
from eidolon.logger import logger
from eidolon.mechanics import calculate_heal_time
from eidolon.state_machines import GameMode, set_character_game_mode
from eidolon.validation import validate_uuid


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
        items: list = dynamo.query(
            TableName.STORY_HISTORY,
            KeyConditionExpression="CharacterID = :character_id",
            ExpressionAttributeValues={":character_id": character_id},
            ScanIndexForward=False,  # Most recent first (UUIDv7 sorts by time)
        )  # type: ignore

        # Filter for the specific story and find the most recent finished instance
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
            # Calculate time until next midnight UTC
            finished_at = datetime.fromisoformat(history.get("FinishedAt", "").replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)

            # Check if completion was today
            if finished_at.date() == now.date():
                # Next midnight in UTC (safe across month/year boundaries)
                midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
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
        # Extract ItemIDs from inventory (new format: {slot: {"ItemID": "...", "Quantity": int}})
        inventory_item_ids = []
        for item_data in inventory.values():
            if item_data and isinstance(item_data, dict):
                item_id = item_data.get("ItemID")
                if item_id:
                    inventory_item_ids.append(item_id)

        for item_id in required_items:
            if item_id not in inventory_item_ids:
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


def get_stories_with_character(character: dict, available_story_ids: list) -> list:
    """
    Get story details for a list of story IDs using an already-loaded character.

    This function avoids reloading the character from the database when the caller
    already has the character data.

    Args:
        character: Character dict containing character data
        available_story_ids: List of story IDs available to the character

    Returns:
        List of story data dicts with availability information

    Raises:
        RuntimeError: If database operations fail
    """
    if not available_story_ids:
        return []

    character_id = character.get("CharacterID")
    if not character_id:
        logger.error("Character missing CharacterID field")
        return []

    stories: list = []

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

    Delegates to state machine for transition validation.

    Args:
        character_id: Character UUID

    Raises:
        ValueError: If character_id is empty
        RuntimeError: If database update fails
    """
    if not character_id:
        raise ValueError("Character ID cannot be empty")

    # Use state machine to transition back to None
    success = set_character_game_mode(
        character_id=character_id,
        new_mode=GameMode.NONE.value,
    )

    if not success:
        logger.warning(f"Failed to reset GameMode for {character_id} (may already be None)")

    logger.info(f"Reset character game mode and cleared active story fields for {character_id}")


def character_get_active_story(character: dict) -> dict:
    """
    Get active story for a character.

    Args:
        character: Character Record dict

    Returns:
        Story dict. Empty dict if no active story found.

    Raises:
        RuntimeError: If database error occurs
    """
    active_story_id: str = character.get("ActiveStoryID")  # type: ignore

    # First try: If character has ActiveStoryID, use GetItem
    if active_story_id:
        try:
            active_story: dict = dynamo.get_item(TableName.STORY, key={"StoryID": active_story_id})  # type: ignore

            if active_story:
                logger.debug("Active story found via GetItem")
                return active_story
            else:
                logger.warning("Story ID found but story not valid")
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
    try:
        character_updates = {}

        # Handle wounds from story outcomes
        if "Wounds" in outcome_effects:
            # Add heal times to wounds
            wounds_with_heal_times = []
            for wound in outcome_effects["Wounds"]:
                # Handle both string format (from story JSON) and dict format (from combat)
                if isinstance(wound, str):
                    wound_data = {"DamageType": wound, "HealAt": calculate_heal_time(wound)}
                else:
                    # Wound is already a dict from combat processing
                    damage_type = wound.get("DamageType", "lethal")
                    wound_data = {"DamageType": damage_type, "HealAt": wound.get("HealAt", calculate_heal_time(damage_type))}
                wounds_with_heal_times.append(wound_data)
            character_updates["Wounds"] = wounds_with_heal_times

        # Handle room change
        if "Room" in outcome_effects:
            character_updates["Room"] = outcome_effects["Room"]

        # Apply all updates in a single atomic operation
        if character_updates:
            apply_character_updates(character_id, character_updates)
            logger.info(f"Applied story outcome effects for {character_id}")

    except ClientError as err:
        logger.error(f"Failed to apply outcome effects for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to apply outcome effects: {err}") from err


def get_active_story_and_segment(character: dict) -> tuple:
    """
    Retrieve active story and segment for a character, handling broken story chains.

    Logic:
    - If GameMode is not "Incremental", return empty dicts immediately
    - If GameMode is "Incremental":
      - Validate both ActiveStoryID and ActiveSegmentID are valid UUIDs
      - If both valid, fetch and return them
      - If either is missing/invalid, clear story and return empty dicts

    Args:
        character: Character dict to check

    Returns:
        Tuple of (active_story, active_segment) dicts, either may be empty
    """
    # Get the character ID first
    character_id = character.get("CharacterID")
    if not character_id:
        logger.error("Character missing CharacterID field")
        return {}, {}

    # Short circuit if not in Incremental mode
    game_mode = character.get("GameMode", "None")
    if game_mode != "Incremental":
        logger.debug(f"Character not in Incremental mode (GameMode: {game_mode})")
        return {}, {}

    # Check if both story and segment IDs exist
    if not character.get("ActiveStoryID") and not character.get("ActiveSegmentID"):
        logger.warning(f"Character {character_id} has no active story or segment")
        # Clear the story fields in the database
        character_clear_story(character_id)
        return {}, {}

    active_story_id = character.get("ActiveStoryID")
    active_segment_id = character.get("ActiveSegmentID")

    # Validate both IDs are present and valid UUIDs
    story_valid = validate_uuid(active_story_id)
    segment_valid = validate_uuid(active_segment_id)

    if not story_valid or not segment_valid:
        # Invalid or missing IDs = broken story chain
        logger.warning(
            f"Broken story chain for character {character_id}: " f"StoryID valid={story_valid}, SegmentID valid={segment_valid}"
        )

        # Clear the story fields in the database
        character_clear_story(character_id)
        return {}, {}

    # Both IDs are valid UUIDs, fetch the actual data
    active_story: dict = {}
    active_segment: dict = {}

    try:
        active_story = character_get_active_story(character)
        if not active_story:
            # Story ID was valid but story not found = broken chain
            logger.warning(f"Story {active_story_id} not found for character {character_id}")
            character_clear_story(character_id)
            return {}, {}
    except RuntimeError as err:
        logger.error(f"Error retrieving active story: {err}")
        # Database error - don't clear, just return empty
        return {}, {}

    active_segment = character_get_active_segment(character)
    if not active_segment:
        # Segment ID was valid but segment not found = broken chain
        logger.warning(f"Segment {active_segment_id} not found for character {character_id}")
        character_clear_story(character_id)
        return {}, {}

    if not isinstance(active_story_id, str):
        logger.warning(f"ActiveStoryID for character {character_id} is not a string; clearing story state")
        character_clear_story(character_id)
        return {}, {}

    # Everything is valid - convert Decimal types to float for JSON serialization
    logger.debug(f"Valid story and segment found for character {character_id}")
    return decimal_to_float(active_story), decimal_to_float(active_segment)
