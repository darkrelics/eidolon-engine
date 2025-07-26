"""
Character management utilities for Lambda functions.

Provides common functions for character creation and management.
"""

import pickle
import uuid
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from eidolon.dynamo import dynamo
from eidolon.dynamo import TableName
from eidolon.environment import MAX_CHARACTERS_PER_PLAYER, DEFAULT_HEALTH, DEFAULT_ESSENCE
from eidolon.logger import get_logger
from eidolon.validation import validate_uuid
from eidolon.items import create_items_from_prototypes

logger = get_logger(__name__)


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


def get_character_with_ownership(character_id: str, player_id: str) -> dict:
    """
    Get character by ID and verify ownership.

    Args:
        character_id: Character UUID
        player_id: Player ID for ownership verification

    Returns:
        Character dict

    Raises:
        ValueError: If character ID invalid, not found, or not owned by player
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

    character_owner = character.get("PlayerID")
    if character_owner != player_id:
        logger.warning(
            "Character ownership mismatch",
            extra={
                "character_id": character_id,
                "player_id": player_id,
                "character_owner": character_owner,
            },
        )
        raise ValueError("Character not found")

    logger.info(
        "Character retrieved successfully",
        extra={
            "character_id": character_id,
            "character_name": character.get("CharacterName"),
            "game_mode": character.get("GameMode"),
        },
    )

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

    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})

        if character:
            character_name = character.get("CharacterName")
            player_id = character.get("PlayerID")

            if remove_from_player_list and player_id and character_name:
                try:
                    dynamo.update_item(
                        TableName.PLAYERS,
                        Key={"PlayerID": player_id},
                        UpdateExpression="REMOVE CharacterList.#name",
                        ConditionExpression="attribute_exists(CharacterList.#name)",
                        ExpressionAttributeNames={"#name": character_name},
                    )
                    results["character_removed_from_player"] = True
                    logger.info(
                        "Removed character from player list",
                        extra={
                            "character_name": character_name,
                            "player_id": player_id,
                        },
                    )
                except ClientError as err:
                    logger.error(
                        "Failed to remove character from player list",
                        extra={"error": str(err), "character_name": character_name},
                    )
                    results["errors"].append(f"Failed to remove character from player list: {str(err)}")

            inventory = character.get("Inventory", {})
            for slot, item_id in inventory.items():
                if item_id:
                    try:
                        dynamo.delete_item(TableName.ITEMS, Key={"ItemID": item_id})
                        results["items_deleted"] += 1
                    except ClientError as err:
                        logger.error(
                            "Failed to delete item",
                            extra={"item_id": item_id, "error": str(err)},
                        )
                        results["errors"].append(f"Failed to delete item {item_id}: {str(err)}")

            left_hand_id = character.get("LeftHandID")
            right_hand_id = character.get("RightHandID")

            if left_hand_id:
                try:
                    dynamo.delete_item(TableName.ITEMS, Key={"ItemID": left_hand_id})
                    results["items_deleted"] += 1
                except ClientError as err:
                    logger.error(
                        "Failed to delete left hand item",
                        extra={"item_id": left_hand_id, "error": str(err)},
                    )
                    results["errors"].append(f"Failed to delete left hand item: {str(err)}")

            if right_hand_id:
                try:
                    dynamo.delete_item(TableName.ITEMS, Key={"ItemID": right_hand_id})
                    results["items_deleted"] += 1
                except ClientError as err:
                    logger.error(
                        "Failed to delete right hand item",
                        extra={"item_id": right_hand_id, "error": str(err)},
                    )
                    results["errors"].append(f"Failed to delete right hand item: {str(err)}")

            try:
                dynamo.delete_item(TableName.CHARACTERS, Key={"CharacterID": character_id})
                results["character_deleted"] = True
                logger.info(
                    "Deleted character",
                    extra={
                        "character_id": character_id,
                        "character_name": character.get("CharacterName", "Unknown"),
                        "game_mode": character.get("GameMode", "Unknown"),
                        "player_id": character.get("PlayerID"),
                    },
                )
            except ClientError as err:
                logger.error(
                    "Failed to delete character",
                    extra={"error": str(err), "character_id": character_id},
                )
                results["errors"].append(f"Failed to delete character: {str(err)}")

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
                    results["active_segments_deleted"] += 1
                except ClientError as err:
                    logger.error(
                        "Failed to delete active segment",
                        extra={
                            "error": str(err),
                            "segment_id": segment["ActiveSegmentID"],
                        },
                    )
                    results["errors"].append(f"Failed to delete active segment {segment['ActiveSegmentID']}: {str(err)}")

        except ClientError as err:
            logger.error(
                "Failed to query active segments",
                extra={"error": str(err), "character_id": character_id},
            )
            results["errors"].append(f"Failed to query active segments: {str(err)}")

        try:
            history_records = dynamo.query(
                TableName.HISTORY,
                KeyConditionExpression="CharacterID = :cid",
                ExpressionAttributeValues={":cid": character_id},
            )

            for record in history_records:  # type: ignore
                try:
                    dynamo.delete_item(
                        TableName.HISTORY,
                        Key={"CharacterID": character_id, "StoryID": record["StoryID"]},
                    )
                    results["history_deleted"] += 1
                except ClientError as err:
                    logger.error(
                        "Failed to delete history record",
                        extra={"error": str(err), "story_id": record["StoryID"]},
                    )
                    results["errors"].append(f"Failed to delete history record for story {record['StoryID']}: {str(err)}")

        except ClientError as err:
            logger.error(
                "Failed to query history",
                extra={"error": str(err), "character_id": character_id},
            )
            results["errors"].append(f"Failed to query history: {str(err)}")

    except ValueError as err:
        logger.error(
            "Value error in delete_character",
            extra={"error": str(err), "character_id": character_id},
            exc_info=True,
        )
        results["errors"].append(f"Value error: {str(err)}")
    except KeyError as err:
        logger.error(
            "Key error in delete_character",
            extra={"error": str(err), "character_id": character_id},
            exc_info=True,
        )
        results["errors"].append(f"Key error: {str(err)}")
    except AttributeError as err:
        logger.error(
            "Attribute error in delete_character",
            extra={"error": str(err), "character_id": character_id},
            exc_info=True,
        )
        results["errors"].append(f"Attribute error: {str(err)}")

    return results


def create_character(player_id: str, character_name: str, archetype_name: str, archetype_data: dict) -> tuple[str, str]:
    """Create a new incremental character in DynamoDB.

    Args:
        player_id: Cognito user ID
        character_name: Name of the character
        archetype_name: Name of the archetype
        archetype_data: Archetype data from DynamoDB

    Returns:
        Tuple of (character_id, error_message)
        - If successful: (character_id, None)
        - If failed: (None, error_message)
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

    # Build character record
    character_item = {
        "CharacterID": character_id,
        "PlayerID": player_id,
        "CharacterName": character_name,
        "Archetype": archetype_name,
        "Attributes": archetype_data.get("Attributes", {}),
        "Skills": archetype_data.get("Skills", {}),
        "Health": archetype_data.get("Health", DEFAULT_HEALTH),
        "MaxHealth": archetype_data.get("Health", DEFAULT_HEALTH),
        "Essence": archetype_data.get("Essence", DEFAULT_ESSENCE),
        "MaxEssence": archetype_data.get("Essence", DEFAULT_ESSENCE),
        "Wounds": [],
        "RoomID": archetype_data.get("StartRoom", 0),  # Use archetype's StartRoom or default to 0
        "Inventory": {},  # Will be populated with starting items below
        "Resources": {},
        "Progress": {},  # Track story progress flags and achievements
        # Incremental game story tracking fields
        "AvailableStories": archetype_data.get("AvailableStories", []),  # Stories the character can start
        "AbandonedStories": [],  # Stories started but not finished
        "CompletedStories": [],  # Stories successfully completed
        "ActiveStoryID": None,  # Currently active story
        "ActiveSegmentID": None,  # Currently active segment
        "Hidden": False,
        "CharState": "Standing",
        "GameMode": "Incremental",  # Mark as Incremental game character
        "CreatedAt": timestamp,
        "UpdatedAt": timestamp,
        "LastPlayed": timestamp,
    }

    # Process starting items from archetype
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

        # Create items from prototypes and get inventory mapping
        inventory = create_items_from_prototypes(starting_items, character_id)

        # Update character item with the inventory
        character_item["Inventory"] = inventory

        logger.info(
            "Starting items created",
            extra={"character_id": character_id, "inventory_slots": len(inventory)},
        )

    try:

        # First, check if character name already exists using GSI
        logger.info(
            "Checking if character name is available",
            extra={"character_name": character_name},
        )

        # Use query to check for existing character name
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
                    extra={"character_name": character_name, "player_id": player_id},
                )
                return None, "Character name is already taken"
        except Exception as err:
            logger.error(
                "Error checking character name availability",
                extra={"error": str(err), "character_name": character_name},
            )
            return None, "Failed to check character name availability"

        # Character name is available, create the character record
        logger.info(
            "Character name available, creating character record",
            extra={"character_id": character_id},
        )

        try:
            dynamo.put_item(TableName.CHARACTERS, character_item)
        except ClientError as err:
            logger.error(
                "Failed to create character record",
                extra={"character_name": character_name, "error": str(err)},
            )
            return None, "Failed to create character"

        logger.info(
            "Character record created successfully",
            extra={"character_id": character_id},
        )

        # Update player's character list
        character_info = {
            "UUID": character_id,
            "Dead": False,
            "GameMode": "Incremental",
        }

        logger.info(
            "Updating player character list",
            extra={
                "player_id": player_id,
                "character_name": character_name,
                "character_info": character_info,
            },
        )

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

        logger.info(
            "Character creation completed successfully",
            extra={
                "character_name": character_name,
                "character_id": character_id,
                "player_id": player_id,
                "archetype": archetype_name,
            },
        )
        return character_id, None

    except ClientError as err:
        logger.error(
            "Error creating character",
            extra={
                "error": str(err),
                "character_name": character_name,
                "player_id": player_id,
            },
        )
        # Attempt to rollback character creation if player update failed
        try:
            dynamo.delete_item(TableName.CHARACTERS, Key={"CharacterID": character_id})
        except ClientError as rollback_err:
            logger.error(
                "Failed to rollback character creation",
                extra={"error": str(rollback_err), "character_id": character_id},
            )
        return None, "Failed to create character"
