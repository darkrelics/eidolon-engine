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


def get_archetype(archetype_name: str) -> dict:
    """
    Retrieve and validate an archetype from DynamoDB.

    Args:
        archetype_name: Name of the archetype.

    Returns:
        Archetype data dict. Empty dict if not found/not player-available.
    """
    try:
        archetype = dynamo.get_item(TableName.ARCHETYPES, {"ArchetypeName": archetype_name})

        if not archetype:
            logger.warning("Archetype not found", extra={"archetype_name": archetype_name})
            return {}

        if not archetype.get("Player", False):
            logger.warning(
                "Archetype not available to players",
                extra={"archetype_name": archetype_name},
            )
            return {}

        return archetype

    except ClientError as err:
        logger.error(
            "Error retrieving archetype",
            extra={"error": str(err), "archetype_name": archetype_name},
        )
        return {}


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
        raise RuntimeError(f"Database error checking character limit: {str(err)}")


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
        raise RuntimeError(f"Failed to retrieve character: {str(err)}")

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


def validate_character_ownership(character: dict, player_id: str) -> None:
    """
    Validate that character is owned by player.

    Args:
        character: Character dict
        player_id: Player ID for ownership verification

    Raises:
        ValueError: If character not owned by player
    """
    character_owner = character.get("PlayerID")
    character_id = character.get("CharacterID")

    if character_owner != player_id:
        logger.warning(
            "Character ownership mismatch",
            extra={
                "character_id": character_id,
                "player_id": player_id,
                "character_owner": character_owner,
            },
        )
        raise ValueError("Character not found")  # Generic message for security


def get_character_with_ownership(character_id: str, player_id: str) -> dict:
    """
    Get character by ID and verify ownership.

    This function combines get_character and validate_character_ownership
    for backward compatibility.

    Args:
        character_id: Character UUID
        player_id: Player ID for ownership verification

    Returns:
        Character dict

    Raises:
        ValueError: If character ID invalid, not found, or not owned by player
        RuntimeError: If database error occurs
    """
    character = get_character(character_id)
    validate_character_ownership(character, player_id)
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
        raise RuntimeError(f"Failed to reset character state: {str(err)}")


def get_active_segment_for_character(character_id: str, player_id: str, segment_type=None) -> dict:
    """
    Get active segment for a character with ownership verification.

    Args:
        character_id: Character UUID
        player_id: Player ID for ownership verification
        segment_type: Optional segment type filter (e.g., "decision")

    Returns:
        Active segment dict. Empty dict if no active segment found.

    Raises:
        RuntimeError: If database error occurs
    """

    query_params = {
        "IndexName": "CharacterID-index",
        "KeyConditionExpression": "CharacterID = :cid",
        "FilterExpression": "PlayerID = :pid AND #status = :status",
        "ExpressionAttributeNames": {"#status": "Status"},
        "ExpressionAttributeValues": {
            ":cid": character_id,
            ":pid": player_id,
            ":status": "active",
        },
    }

    if segment_type:
        query_params["FilterExpression"] += " AND SegmentType = :type"
        query_params["ExpressionAttributeValues"][":type"] = segment_type

    try:
        items = dynamo.query(TableName.ACTIVE_SEGMENTS, **query_params)

        if not items:
            logger.info(
                "No active segment found",
                extra={"character_id": character_id, "segment_type": segment_type},
            )
            return {}

        # Should only be one active segment per character
        active_segment = items[0]

        logger.info(
            "Active segment found",
            extra={
                "character_id": character_id,
                "segment_id": active_segment.get("SegmentID"),
                "segment_type": active_segment.get("SegmentType"),
                "story_id": active_segment.get("StoryID"),
            },
        )

        return active_segment

    except ClientError as err:
        logger.error(
            "Error querying active segments",
            extra={"error": str(err), "character_id": character_id},
        )
        raise RuntimeError(f"Failed to retrieve active segment: {str(err)}")


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
        raise RuntimeError(f"Failed to retrieve character: {str(err)}")


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
            result["error"] = f"Failed to remove character from player list: {str(err)}"

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
            result["errors"].append(f"Failed to delete item {item_id}: {str(err)}")

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
                result["errors"].append(f"Failed to delete active segment {segment['ActiveSegmentID']}: {str(err)}")

    except ClientError as err:
        logger.error(
            "Failed to query active segments",
            extra={"error": str(err), "character_id": character_id},
        )
        result["errors"].append(f"Failed to query active segments: {str(err)}")

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
                result["errors"].append(f"Failed to delete history record for story {record['StoryID']}: {str(err)}")

    except ClientError as err:
        logger.error(
            "Failed to query history",
            extra={"error": str(err), "character_id": character_id},
        )
        result["errors"].append(f"Failed to query history: {str(err)}")

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
        result["error"] = f"Failed to delete character: {str(err)}"

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
        results["errors"].append(f"Failed to retrieve character: {str(err)}")

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
        raise RuntimeError(f"Failed to check character name availability: {str(err)}")


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
        raise RuntimeError(f"Failed to create character record: {str(err)}")


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
        raise RuntimeError(f"Failed to add character to player list: {str(err)}")


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
    except RuntimeError:
        # Re-raise as character creation failed
        raise

    # Add to player's character list
    try:
        add_character_to_player_list(
            player_id=player_id, character_name=character_name, character_id=character_id, timestamp=timestamp
        )
    except RuntimeError as err:
        # Rollback character creation
        rollback_character_creation(character_id)
        raise RuntimeError(f"Failed to create character: {str(err)}")

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


def heal_expired_wounds(character_id: str) -> dict:
    """
    Check and heal wounds that have passed their recovery timestamp.

    This function removes wounds from the character's wounds list where the HealAt
    timestamp is in the past. Should be called at the start of every segment.
    Dead characters do not heal and will return immediately with no changes.

    Args:
        character_id: Character UUID

    Returns:
        Dict with:
            - healed_count: Number of wounds healed
            - remaining_wounds: List of wounds still active
            - error: Error message if operation failed

    Raises:
        ValueError: If character_id is invalid
        RuntimeError: If database operation fails
    """
    if not validate_uuid(character_id):
        raise ValueError("Invalid character ID format")

    try:
        # Get character to check wounds
        character = get_character(character_id)

        # Dead characters don't heal
        if character.get("CharState") == "dead":
            logger.info("Character is dead, no healing occurs", extra={"character_id": character_id})
            return {"healed_count": 0, "remaining_wounds": character.get("Wounds", []), "error": None}

        wounds = character.get("Wounds", [])

        if not wounds:
            logger.info("No wounds to heal", extra={"character_id": character_id})
            return {"healed_count": 0, "remaining_wounds": [], "error": None}

        # Current time for comparison
        current_time = datetime.now(timezone.utc)

        # Separate wounds into healed and remaining
        remaining_wounds = []
        healed_wounds = []

        for wound in wounds:
            heal_at_str = wound.get("HealAt")
            if not heal_at_str:
                # Keep wounds without HealAt timestamp
                remaining_wounds.append(wound)
                continue

            try:
                # Parse HealAt timestamp
                heal_at = datetime.fromisoformat(heal_at_str.replace("Z", "+00:00"))

                if heal_at <= current_time:
                    # Wound has healed
                    healed_wounds.append(wound)
                    logger.debug(
                        "Wound healed",
                        extra={
                            "character_id": character_id,
                            "damage_type": wound.get("DamageType"),
                            "heal_at": heal_at_str,
                        },
                    )
                else:
                    # Wound still active
                    remaining_wounds.append(wound)
            except (ValueError, AttributeError) as err:
                logger.warning(
                    "Invalid wound HealAt timestamp",
                    extra={"character_id": character_id, "heal_at": heal_at_str, "error": str(err)},
                )
                # Keep wounds with invalid timestamps
                remaining_wounds.append(wound)

        # Update character if any wounds healed
        if healed_wounds:
            update_expression = "SET Wounds = :wounds, UpdatedAt = :timestamp"
            expression_values = {
                ":wounds": remaining_wounds,
                ":timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Check for consciousness recovery
            current_state = character.get("CharState", "standing")
            if current_state == "unconscious":
                # Calculate current health after healing
                max_health = character.get("MaxHealth", 10)
                current_health = max_health - len(remaining_wounds)

                if current_health > 0:
                    # Character regains consciousness
                    update_expression += ", CharState = :state"
                    expression_values[":state"] = "standing"

                    logger.info(
                        "Character will regain consciousness",
                        extra={
                            "character_id": character_id,
                            "health": current_health,
                            "max_health": max_health,
                            "wounds_remaining": len(remaining_wounds),
                        },
                    )

            dynamo.update_item(
                TableName.CHARACTERS,
                Key={"CharacterID": character_id},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values,
            )

            logger.info(
                "Healed expired wounds",
                extra={
                    "character_id": character_id,
                    "healed_count": len(healed_wounds),
                    "remaining_count": len(remaining_wounds),
                    "healed_types": [w.get("DamageType") for w in healed_wounds],
                    "consciousness_recovered": expression_values.get(":state") == "standing",
                },
            )

        return {"healed_count": len(healed_wounds), "remaining_wounds": remaining_wounds, "error": None}

    except ClientError as err:
        logger.error("Failed to heal wounds", extra={"character_id": character_id, "error": str(err)}, exc_info=True)
        raise RuntimeError(f"Failed to heal wounds: {str(err)}")


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
        raise RuntimeError(f"Failed to apply death/unconscious state: {str(err)}")


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
            raise RuntimeError(f"Failed to apply character updates: {str(err)}")
