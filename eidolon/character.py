"""
Character management utilities for Lambda functions.

Provides common functions for character creation and management.
"""

import pickle
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.environment import DEFAULT_ESSENCE, DEFAULT_HEALTH, MAX_CHARACTERS_PER_PLAYER
from eidolon.items import create_items_from_prototypes
from eidolon.logger import logger
from eidolon.validation import validate_uuid


class CharacterNameFilter:
    """Manages bloom filter for restricted character names."""

    def __init__(self, filter_path: str = "character_name_filter.pkl"):
        """Initialize the character name filter.

        Args:
            filter_path: Path to the bloom filter pickle file
        """
        self.bloom_filter = None
        self.filter_path = filter_path
        self._load_filter()

    def _load_filter(self) -> None:
        """Load the bloom filter from disk."""
        try:
            with open(self.filter_path, "rb") as f:
                self.bloom_filter = pickle.load(f)
                logger.info("Loaded character name bloom filter")
        except (FileNotFoundError, pickle.UnpicklingError) as err:
            logger.error("Failed to load bloom filter", extra={"error": str(err)})
            self.bloom_filter = None

    def is_restricted(self, name: str) -> bool:
        """Check if a character name is restricted.

        Args:
            name: Character name to check

        Returns:
            True if the name is restricted, False otherwise
        """
        if not self.bloom_filter:
            return False
        return name.lower() in self.bloom_filter


# Global instance of the filter
character_name_filter = CharacterNameFilter()


def generate_character_id() -> str:
    """
    Generate a UUID v4 for the character ID.

    Returns:
        A UUID string for the character ID.
    """
    return str(uuid.uuid4())


def check_character_limit(player_id: str) -> dict:
    """
    Check if player has reached character limit.

    Args:
        player_id: Cognito user ID.

    Returns:
        Dict with:
            - can_create: bool - Whether player can create more characters
            - current_count: int - Current number of characters

    Raises:
        ValueError: If player not found
        RuntimeError: If database error occurs
    """
    try:
        player = dynamo.get_item(TableName.PLAYERS, {"PlayerID": player_id})

        if not player:
            logger.error("Player not found", extra={"player_id": player_id})
            raise ValueError(f"Player {player_id} not found")

        character_list = player.get("CharacterList", {})
        current_count = len(character_list)

        return {
            "can_create": current_count < MAX_CHARACTERS_PER_PLAYER,
            "current_count": current_count,
        }

    except ClientError as err:
        logger.error(
            "Error checking character limit",
            extra={"error": str(err), "player_id": player_id},
        )
        raise RuntimeError(f"Database error checking character limit: {err}") from err


def get_character(character_id: str) -> dict:
    """
    Get character by ID.

    Args:
        character_id: Character UUID

    Returns:
        Character dict with calculated Health field

    Raises:
        ValueError: If character ID invalid or not found
        RuntimeError: If database error occurs
    """
    if not validate_uuid(character_id):
        logger.warning("Invalid character ID format", extra={"character_id": character_id})
        raise ValueError("Invalid character ID format")

    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})

        if not character:
            logger.warning("Character not found", extra={"character_id": character_id})
            raise ValueError("Character not found")

    except ClientError as err:
        logger.error(
            "Error retrieving character",
            extra={"error": str(err), "character_id": character_id},
        )
        raise RuntimeError(f"Failed to retrieve character: {err}") from err

    logger.info(
        "Character retrieved successfully",
        extra={
            "character_id": character_id,
            "character_name": character.get("CharacterName"),
            "game_mode": character.get("GameMode"),
        },
    )

    # Calculate current health from MaxHealth and Wounds
    max_health = character.get("MaxHealth", 10)
    wounds = character.get("Wounds", [])
    character["Health"] = max_health - len(wounds)

    return character


def character_get(character_id: str, player_id: str) -> dict:
    """
    Get character by ID and verify ownership.



    Args:
        character_id: Character UUID
        player_id: Player ID for ownership verification

    Returns:
        Character dict with calculated Health field

    Raises:
        ValueError: If character ID invalid, not found, or not owned by player
        RuntimeError: If database error occurs
    """
    if not validate_uuid(character_id):
        logger.warning(f"Invalid character ID format: {character_id}")
        raise ValueError("Invalid character ID format")

    if not validate_uuid(player_id):
        logger.warning(f"Invalid player ID format: {player_id}")
        raise ValueError("Invalid player ID format")

    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})

        if not character:
            logger.warning("Character not found", extra={"character_id": character_id})
            raise ValueError("Character not found")

    except ClientError as err:
        logger.error(
            "Error retrieving character",
            extra={"error": str(err), "character_id": character_id},
        )
        raise RuntimeError(f"Failed to retrieve character: {err}") from err

    logger.debug(f"Character retrieved successfully: {character_id}")

    # Heal expired wounds

    if character.get("Wounds") and character.get("CharState") != "dead":
        wounds: list = character.get("Wounds", [])
        current_time: datetime = datetime.now(timezone.utc)

        remainging_wounds: list = []

        for wound in wounds:
            heal_at: str = wound.get("HealedAt")

            try:
                if datetime.fromisoformat(heal_at.replace("Z", "+00:00")) > current_time:
                    remainging_wounds.append(wound)
            except AttributeError:
                continue

        if len(remainging_wounds) < len(wounds):
            character["Wounds"] = remainging_wounds

            logger.info("It's a mircical!")

            # Update character with healed wounds

            if character.get("CharState", "standing") == "unconscious":
                character["CharState"] = "standing"

            # Update the character's wounds in the database

            update_expression = "SET Wounds = :wounds, CharState = :state, UpdatedAt = :timestamp"
            expression_values: dict = {
                ":wounds": remainging_wounds,
                ":state": character.get("CharState", "standing"),
                ":timestamp": datetime.now(timezone.utc).isoformat(),
            }

            try:

                dynamo.update_item(
                    TableName.CHARACTERS,
                    Key={"CharacterID": character_id},
                    UpdateExpression=update_expression,
                    ExpressionAttributeValues=expression_values,
                )
                logger.info("Updated character wounds after healing")
            except ClientError as err:
                logger.error("Failed to update character.")
                raise RuntimeError(f"Failed to update character wounds: {err}") from err

    # Validate ownership

    if character.get("PlayerID") != player_id:
        logger.warning(f"Character ownership mismatch: {character_id} not owned by {player_id}")
        raise ValueError("Character not owned by player")

    # Calculate current health from MaxHealth and Wounds
    max_health = character.get("MaxHealth", 10)
    wounds = character.get("Wounds", [])
    character["Health"] = max_health - len(wounds)

    return character


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
        logger.info("Reset character game mode and cleared active story fields", extra={"character_id": character_id})

    except ClientError as err:
        logger.error("Failed to reset character state", extra={"character_id": character_id, "error": str(err)}, exc_info=True)
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





def character_get_active_segment(character: dict) -> dict:
    """
    Get active segment for a character.

    Args:
        character: Character Record dict

    Returns:
        Active segment dict. Empty dict if no active segment found.

    Raises:
        RuntimeError: If database error occurs
    """
    character_id: str = character.get("CharacterID")  # type: ignore
    active_segment_id: str = character.get("ActiveSegmentID")  # type: ignore

    # First try: If character has ActiveSegmentID, use GetItem
    if active_segment_id:
        try:
            active_segment: dict = dynamo.get_item(TableName.ACTIVE_SEGMENTS, key={"ActiveSegmentID": active_segment_id})  # type: ignore

            if active_segment:
                # Verify the segment is still active and belongs to this character
                if active_segment.get("Status") == "active" and active_segment.get("CharacterID") == character_id:
                    logger.debug("Active segment found via GetItem")
                    return active_segment
                else:
                    logger.warning("Segment found but not valid")
        except ClientError as err:
            logger.error(
                "Error retrieving active segment by ID",
                extra={"error": str(err), "character_id": character_id, "active_segment_id": active_segment_id},
            )
            # Fall through to query approach

    # Second try: Query by CharacterID index
    query_params: dict = {
        "IndexName": "CharacterID-index",
        "KeyConditionExpression": "CharacterID = :cid",
        "FilterExpression": "#status = :status",
        "ExpressionAttributeNames": {"#status": "Status"},
        "ExpressionAttributeValues": {
            ":cid": character_id,
            ":status": "active",
        },
    }

    try:
        items: list = dynamo.query(TableName.ACTIVE_SEGMENTS, **query_params)  # type: ignore

        if not items:
            logger.info("No active segment found via query", extra={"character_id": character_id})
            return {}

        # Should only be one active segment per character
        active_segment = items[0]

        logger.info("Active segment found via query")

        return active_segment

    except ClientError as err:
        logger.error(
            "Error querying active segments",
            extra={"error": str(err), "character_id": character_id},
        )
        raise RuntimeError(f"Failed to retrieve active segment: {err}") from err


def verify_character_in_game_mode(character: dict, expected_mode: str = "Incremental") -> dict:
    """
    Verify character is in the expected game mode.

    Args:
        character: Character dict
        expected_mode: Expected game mode

    Returns:
        Dict with:
            - is_valid: bool - Whether character is in expected mode
            - error_message: str - Error message if invalid (empty string if valid)
    """
    current_mode = character.get("GameMode", "None")

    if current_mode != expected_mode:
        logger.warning(
            "Character not in expected game mode",
            extra={
                "character_id": character.get("CharacterID"),
                "current_mode": current_mode,
                "expected_mode": expected_mode,
            },
        )
        return {
            "is_valid": False,
            "error_message": f"Character is not in {expected_mode} mode",
        }

    return {"is_valid": True, "error_message": ""}


def get_character_by_name(player_id: str, character_name: str) -> dict:
    """
    Get character by name for a specific player.

    Args:
        player_id: Player ID
        character_name: Character name

    Returns:
        Character dict

    Raises:
        ValueError: If player/character not found or data corrupted
        RuntimeError: If database error occurs
    """
    try:
        player = dynamo.get_item(TableName.PLAYERS, {"PlayerID": player_id})

        if not player:
            logger.warning("Player not found", extra={"player_id": player_id})
            raise ValueError("Player not found")

        character_list = player.get("CharacterList", {})
        character_info = character_list.get(character_name)

        if not character_info:
            logger.warning(
                "Character not found in player list",
                extra={"player_id": player_id, "character_name": character_name},
            )
            raise ValueError("Character not found")

        character_id = character_info.get("UUID")
        if not character_id:
            logger.error(
                "Character UUID missing",
                extra={"player_id": player_id, "character_name": character_name},
            )
            raise ValueError("Character data corrupted")

        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})

        if not character:
            logger.error(
                "Character not found in characters table",
                extra={"character_id": character_id, "character_name": character_name},
            )
            raise ValueError("Character not found")

        return character

    except ClientError as err:
        logger.error(
            "Error retrieving character by name",
            extra={
                "error": str(err),
                "player_id": player_id,
                "character_name": character_name,
            },
        )
        raise RuntimeError(f"Failed to retrieve character: {err}") from err


def remove_character_from_player_list(player_id: str, character_name: str) -> dict:
    """
    Remove a character from the player's CharacterList.

    Args:
        player_id: Player UUID
        character_name: Name of the character to remove

    Returns:
        Dict with:
            - removed: bool - Whether the character was removed
            - error: str - Error message if removal failed
    """
    result = {"removed": False, "error": None}

    if not player_id or not character_name:
        return result

    try:
        dynamo.update_item(
            TableName.PLAYERS,
            Key={"PlayerID": player_id},
            UpdateExpression="REMOVE CharacterList.#name",
            ConditionExpression="attribute_exists(CharacterList.#name)",
            ExpressionAttributeNames={"#name": character_name},
        )
        result["removed"] = True
        logger.info(
            "Removed character from player list",
            extra={
                "character_name": character_name,
                "player_id": player_id,
            },
        )
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            logger.error(
                "Failed to remove character from player list",
                extra={"error": str(err), "character_name": character_name},
            )
            result["error"] = f"Failed to remove character from player list: {err}"

    return result


def delete_character_items(character: dict) -> dict:
    """
    Delete all items belonging to a character.

    Args:
        character: Character dict containing inventory and equipped items

    Returns:
        Dict with:
            - deleted_count: int - Number of items deleted
            - errors: list - List of error messages
    """
    result = {"deleted_count": 0, "errors": []}

    # Collect all item IDs
    item_ids = []

    # Inventory items
    inventory = character.get("Inventory", {})
    for slot, item_id in inventory.items():
        if item_id:
            item_ids.append(item_id)

    # Equipped items
    if character.get("LeftHandID"):
        item_ids.append(character["LeftHandID"])
    if character.get("RightHandID"):
        item_ids.append(character["RightHandID"])

    # Delete each item
    for item_id in item_ids:
        try:
            dynamo.delete_item(TableName.ITEMS, Key={"ItemID": item_id})
            result["deleted_count"] += 1
        except ClientError as err:
            logger.error(
                "Failed to delete item",
                extra={"item_id": item_id, "error": str(err)},
            )
            result["errors"].append(f"Failed to delete item {item_id}: {err}")

    return result


def delete_character_active_segments(character_id: str) -> dict:
    """
    Delete all active segments for a character.

    Args:
        character_id: Character UUID

    Returns:
        Dict with:
            - deleted_count: int - Number of segments deleted
            - errors: list - List of error messages
    """
    result = {"deleted_count": 0, "errors": []}

    try:
        active_segments = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="CharacterID-index",
            KeyConditionExpression="CharacterID = :cid",
            ExpressionAttributeValues={":cid": character_id},
        )

        for segment in active_segments:  # type: ignore
            try:
                dynamo.delete_item(
                    TableName.ACTIVE_SEGMENTS,
                    Key={"ActiveSegmentID": segment["ActiveSegmentID"]},
                )
                result["deleted_count"] += 1
            except ClientError as err:
                logger.error(
                    "Failed to delete active segment",
                    extra={
                        "error": str(err),
                        "segment_id": segment["ActiveSegmentID"],
                    },
                )
                result["errors"].append(f"Failed to delete active segment {segment['ActiveSegmentID']}: {err}")

    except ClientError as err:
        logger.error(
            "Failed to query active segments",
            extra={"error": str(err), "character_id": character_id},
        )
        result["errors"].append(f"Failed to query active segments: {err}")

    return result


def delete_character_history(character_id: str) -> dict:
    """
    Delete all history records for a character.

    Args:
        character_id: Character UUID

    Returns:
        Dict with:
            - deleted_count: int - Number of history records deleted
            - errors: list - List of error messages
    """
    result = {"deleted_count": 0, "errors": []}

    try:
        history_records = dynamo.query(
            TableName.STORY_HISTORY,
            KeyConditionExpression="CharacterID = :cid",
            ExpressionAttributeValues={":cid": character_id},
        )

        for record in history_records:  # type: ignore
            try:
                dynamo.delete_item(
                    TableName.STORY_HISTORY,
                    Key={"CharacterID": character_id, "StoryID": record["StoryID"]},
                )
                result["deleted_count"] += 1
            except ClientError as err:
                logger.error(
                    "Failed to delete history record",
                    extra={"error": str(err), "story_id": record["StoryID"]},
                )
                result["errors"].append(f"Failed to delete history record for story {record['StoryID']}: {err}")

    except ClientError as err:
        logger.error(
            "Failed to query history",
            extra={"error": str(err), "character_id": character_id},
        )
        result["errors"].append(f"Failed to query history: {err}")

    return result


def delete_character_record(character_id: str) -> dict:
    """
    Delete the character record from the database.

    Args:
        character_id: Character UUID

    Returns:
        Dict with:
            - deleted: bool - Whether the character was deleted
            - error: str - Error message if deletion failed
    """
    result = {"deleted": False, "error": None}

    try:
        dynamo.delete_item(TableName.CHARACTERS, Key={"CharacterID": character_id})
        result["deleted"] = True
        logger.info("Deleted character record", extra={"character_id": character_id})
    except ClientError as err:
        logger.error(
            "Failed to delete character",
            extra={"error": str(err), "character_id": character_id},
        )
        result["error"] = f"Failed to delete character: {err}"

    return result


def delete_character(character_id: str, remove_from_player_list: bool = True) -> dict:
    """
    Delete a character and all associated data.

    Note: Ownership verification should be performed before calling this function.

    Args:
        character_id: UUID of the character to delete
        remove_from_player_list: Whether to remove character from player's CharacterList (default: True)

    Returns:
        Dictionary with deletion results including deleted items
    """
    results = {
        "character_deleted": False,
        "character_removed_from_player": False,
        "items_deleted": 0,
        "active_segments_deleted": 0,
        "history_deleted": 0,
        "errors": [],
    }

    # Retrieve character data
    character = None
    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
    except ClientError as err:
        logger.error(
            "Failed to retrieve character for deletion",
            extra={"error": str(err), "character_id": character_id},
        )
        results["errors"].append(f"Failed to retrieve character: {err}")

    if character:
        # Remove from player list if requested
        if remove_from_player_list:
            player_id = character.get("PlayerID")
            character_name = character.get("CharacterName")

            if player_id and character_name:
                player_result = remove_character_from_player_list(player_id, character_name)
                results["character_removed_from_player"] = player_result["removed"]
                if player_result["error"]:
                    results["errors"].append(player_result["error"])

        # Delete all character items
        items_result = delete_character_items(character)
        results["items_deleted"] = items_result["deleted_count"]
        results["errors"].extend(items_result["errors"])

        # Delete the character record
        char_result = delete_character_record(character_id)
        results["character_deleted"] = char_result["deleted"]
        if char_result["error"]:
            results["errors"].append(char_result["error"])

        # Log character deletion with details
        logger.info(
            "Character deletion processed",
            extra={
                "character_id": character_id,
                "character_name": character.get("CharacterName", "Unknown"),
                "game_mode": character.get("GameMode", "Unknown"),
                "player_id": character.get("PlayerID"),
                "deleted": results["character_deleted"],
            },
        )

    # Delete active segments (can proceed even if character not found)
    segments_result = delete_character_active_segments(character_id)
    results["active_segments_deleted"] = segments_result["deleted_count"]
    results["errors"].extend(segments_result["errors"])

    # Delete history records
    history_result = delete_character_history(character_id)
    results["history_deleted"] = history_result["deleted_count"]
    results["errors"].extend(history_result["errors"])

    # Log deletion summary
    logger.info(
        "Character deletion completed",
        extra={
            "character_id": character_id,
            "character_deleted": results["character_deleted"],
            "items_deleted": results["items_deleted"],
            "segments_deleted": results["active_segments_deleted"],
            "history_deleted": results["history_deleted"],
            "error_count": len(results["errors"]),
        },
    )

    return results


def check_character_name_availability(character_name: str) -> bool:
    """
    Check if a character name is available.

    Args:
        character_name: Name to check

    Returns:
        True if name is available, False if taken

    Raises:
        RuntimeError: If database query fails
    """
    logger.info(
        "Checking character name availability",
        extra={"character_name": character_name},
    )

    try:
        existing_chars = dynamo.query(
            TableName.CHARACTERS,
            IndexName="CharacterNameIndex",
            KeyConditionExpression="CharacterName = :name",
            ExpressionAttributeValues={":name": character_name},
            Limit=1,
        )

        if existing_chars:
            logger.info(
                "Character name already taken",
                extra={"character_name": character_name},
            )
            return False

        return True

    except ClientError as err:
        logger.error(
            "Error checking character name availability",
            extra={"error": str(err), "character_name": character_name},
        )
        raise RuntimeError(f"Failed to check character name availability: {err}") from err


def build_character_record(
    character_id: str,
    player_id: str,
    character_name: str,
    archetype_name: str,
    archetype_data: dict,
    inventory: dict,
    timestamp: str,
) -> dict:
    """
    Build a character record with all required fields.

    Args:
        character_id: Generated character UUID
        player_id: Player UUID
        character_name: Character name
        archetype_name: Archetype name
        archetype_data: Archetype data from database
        inventory: Inventory items mapping
        timestamp: ISO format timestamp

    Returns:
        Complete character record dict
    """
    return {
        "CharacterID": character_id,
        "PlayerID": player_id,
        "CharacterName": character_name,
        "Archetype": archetype_name,
        "Attributes": archetype_data.get("Attributes", {}),
        "Skills": archetype_data.get("Skills", {}),
        "MaxHealth": archetype_data.get("Health", DEFAULT_HEALTH),
        "Essence": archetype_data.get("Essence", DEFAULT_ESSENCE),
        "MaxEssence": archetype_data.get("Essence", DEFAULT_ESSENCE),
        "Wounds": [],
        "RoomID": archetype_data.get("StartRoom", 0),
        "Inventory": inventory,
        "Resources": {},
        "Progress": {},
        "AvailableStories": archetype_data.get("AvailableStories", []),
        "AbandonedStories": [],
        "CompletedStories": [],
        "ActiveStoryID": None,
        "ActiveSegmentID": None,
        "Hidden": False,
        "CharState": "Standing",
        "GameMode": "None",
        "CreatedAt": timestamp,
        "UpdatedAt": timestamp,
        "LastPlayed": timestamp,
    }


def create_character_record(character_item: dict) -> bool:
    """
    Create character record in database.

    Args:
        character_item: Complete character record to create

    Returns:
        True if created successfully

    Raises:
        RuntimeError: If database operation fails
    """
    try:
        dynamo.put_item(TableName.CHARACTERS, character_item)
        logger.info(
            "Character record created successfully",
            extra={"character_id": character_item.get("CharacterID")},
        )
        return True
    except ClientError as err:
        logger.error(
            "Failed to create character record",
            extra={"character_name": character_item.get("CharacterName"), "error": str(err)},
        )
        raise RuntimeError(f"Failed to create character record: {err}") from err


def add_character_to_player_list(player_id: str, character_name: str, character_id: str, timestamp: str) -> bool:
    """
    Add character to player's character list.

    Args:
        player_id: Player UUID
        character_name: Character name
        character_id: Character UUID
        timestamp: ISO format timestamp

    Returns:
        True if added successfully

    Raises:
        RuntimeError: If database operation fails
    """
    character_info = {
        "UUID": character_id,
        "Dead": False,
        "GameMode": "None",
    }

    logger.info(
        "Adding character to player list",
        extra={
            "player_id": player_id,
            "character_name": character_name,
            "character_info": character_info,
        },
    )

    try:
        dynamo.update_item(
            TableName.PLAYERS,
            Key={"PlayerID": player_id},
            UpdateExpression="SET CharacterList.#name = :info, UpdatedAt = :timestamp",
            ExpressionAttributeNames={"#name": character_name},
            ExpressionAttributeValues={
                ":info": character_info,
                ":timestamp": timestamp,
            },
        )
        return True
    except ClientError as err:
        logger.error(
            "Failed to add character to player list",
            extra={
                "error": str(err),
                "character_name": character_name,
                "player_id": player_id,
            },
        )
        raise RuntimeError(f"Failed to add character to player list: {err}") from err


def rollback_character_creation(character_id: str) -> None:
    """
    Attempt to rollback a failed character creation.

    Args:
        character_id: Character UUID to delete
    """
    try:
        dynamo.delete_item(TableName.CHARACTERS, Key={"CharacterID": character_id})
        logger.info("Successfully rolled back character creation", extra={"character_id": character_id})
    except ClientError as err:
        logger.error(
            "Failed to rollback character creation",
            extra={"error": str(err), "character_id": character_id},
        )


def create_character(player_id: str, character_name: str, archetype_name: str, archetype_data: dict) -> dict:
    """Create a new incremental character in DynamoDB.

    Args:
        player_id: Cognito user ID
        character_name: Name of the character
        archetype_name: Name of the archetype
        archetype_data: Archetype data from DynamoDB

    Returns:
        Dict containing:
            - character_id: str - The created character's ID
            - character_name: str - The character's name
            - archetype: str - The archetype used

    Raises:
        ValueError: If character name is already taken
        RuntimeError: If database operations fail
    """
    character_id = generate_character_id()
    timestamp = datetime.now(timezone.utc).isoformat()

    logger.info(
        "Creating new character",
        extra={
            "player_id": player_id,
            "character_name": character_name,
            "archetype_name": archetype_name,
            "character_id": character_id,
        },
    )

    # Check name availability
    if not check_character_name_availability(character_name):
        raise ValueError("Character name is already taken")

    # Process starting items
    inventory = {}
    starting_items = archetype_data.get("StartingItems", [])
    if starting_items:
        logger.info(
            "Processing starting items for character",
            extra={
                "character_id": character_id,
                "archetype": archetype_name,
                "item_count": len(starting_items),
            },
        )
        inventory = create_items_from_prototypes(starting_items, character_id)
        logger.info(
            "Starting items created",
            extra={"character_id": character_id, "inventory_slots": len(inventory)},
        )

    # Build character record
    character_item = build_character_record(
        character_id=character_id,
        player_id=player_id,
        character_name=character_name,
        archetype_name=archetype_name,
        archetype_data=archetype_data,
        inventory=inventory,
        timestamp=timestamp,
    )

    # Create character record
    try:
        create_character_record(character_item)
    except RuntimeError as err:
        # Re-raise as character creation failed
        logger.error(f"Failed to create character record: {err}")
        raise RuntimeError(f"Failed to create character: {err}") from err

    # Add to player's character list
    try:
        add_character_to_player_list(
            player_id=player_id, character_name=character_name, character_id=character_id, timestamp=timestamp
        )
    except RuntimeError as err:
        # Rollback character creation
        rollback_character_creation(character_id)
        raise RuntimeError(f"Failed to create character: {err}") from err

    logger.info(
        "Character creation completed successfully",
        extra={
            "character_name": character_name,
            "character_id": character_id,
            "player_id": player_id,
            "archetype": archetype_name,
        },
    )

    return {"character_id": character_id, "character_name": character_name, "archetype": archetype_name}


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

            logger.info(
                "Updated character state due to death outcome",
                extra={
                    "character_id": character_id,
                    "new_state": new_state,
                    "wound_count": len(wounds),
                    "moved_to_death_room": new_state == "dead",
                },
            )

        return new_state

    except ClientError as err:
        logger.error(
            "Failed to apply death/unconscious state", extra={"character_id": character_id, "error": str(err)}, exc_info=True
        )
        raise RuntimeError(f"Failed to apply death/unconscious state: {err}") from err


def apply_character_updates(character_id: str, updates: dict) -> None:
    """
    Apply accumulated updates to character.

    Handles skill XP, attribute XP, wounds, and room changes.

    Args:
        character_id: Character UUID
        updates: Dict containing CharacterUpdates from segment processing

    Raises:
        RuntimeError: If database update fails
    """
    if not updates:
        logger.info("No character updates to apply", extra={"character_id": character_id})
        return

    update_expressions = []
    expression_names = {}
    expression_values = {}

    # Apply skill XP updates
    skill_xp = updates.get("SkillXP", {})
    for skill, xp_value in skill_xp.items():
        if xp_value > 0:
            safe_skill = skill.replace("-", "_")
            update_expressions.append(
                f"Skills.#skill_{safe_skill} = if_not_exists(Skills.#skill_{safe_skill}, :zero) + :xp_{safe_skill}"
            )
            expression_names[f"#skill_{safe_skill}"] = skill
            expression_values[f":xp_{safe_skill}"] = Decimal(str(xp_value))

    # Apply attribute XP updates
    attribute_xp = updates.get("AttributeXP", {})
    for attribute, xp_value in attribute_xp.items():
        if xp_value > 0:
            safe_attr = attribute.replace("-", "_")
            update_expressions.append(
                f"Attributes.#attr_{safe_attr} = if_not_exists(Attributes.#attr_{safe_attr}, :zero) + :xp_{safe_attr}"
            )
            expression_names[f"#attr_{safe_attr}"] = attribute
            expression_values[f":xp_{safe_attr}"] = Decimal(str(xp_value))

    # Apply wounds
    wounds = updates.get("Wounds", [])
    if wounds:
        update_expressions.append("Wounds = list_append(if_not_exists(Wounds, :empty_list), :new_wounds)")
        expression_values[":new_wounds"] = wounds
        expression_values[":empty_list"] = []

    # Apply room change
    room_id = updates.get("Room")
    if room_id is not None:
        update_expressions.append("RoomID = :room")
        expression_values[":room"] = room_id

    # Set common values
    if expression_values and ":zero" not in expression_values:
        expression_values[":zero"] = Decimal("0")

    # Execute update if there are changes
    if update_expressions:
        try:
            update_expression = "SET " + ", ".join(update_expressions)
            update_expression += ", UpdatedAt = :updated_at"
            expression_values[":updated_at"] = datetime.now(timezone.utc).isoformat()

            dynamo.update_item(
                TableName.CHARACTERS,
                Key={"CharacterID": character_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names if expression_names else None,
                ExpressionAttributeValues=expression_values,
            )

            logger.info(
                "Character updates applied",
                extra={
                    "character_id": character_id,
                    "skills_updated": len(skill_xp),
                    "attributes_updated": len(attribute_xp),
                    "wounds_added": len(wounds),
                    "room_changed": room_id is not None,
                },
            )
        except ClientError as err:
            logger.error(
                "Failed to apply character updates",
                extra={
                    "character_id": character_id,
                    "error": str(err),
                    "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
                },
                exc_info=True,
            )
            raise RuntimeError(f"Failed to apply character updates: {err}") from err
