"""
Character management utilities for Lambda functions.

Provides common functions for character creation and management.
"""

import uuid

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.environment import MAX_CHARACTERS_PER_PLAYER
from eidolon.logger import get_logger
from eidolon.validation import validate_uuid

logger = get_logger(__name__)


def generate_character_id() -> str:
    """
    Generate a UUID v4 for the character ID.

    Returns:
        A UUID string for the character ID.
    """
    return str(uuid.uuid4())


def get_archetype(archetype_name: str):
    """
    Retrieve and validate an archetype from DynamoDB.

    Args:
        archetype_name: Name of the archetype.

    Returns:
        Archetype data or None if not found/not player-available.
    """
    try:
        archetype = dynamo.get_item(TableName.ARCHETYPES, {"ArchetypeName": archetype_name})

        if not archetype:
            logger.warning("Archetype not found", extra={"archetype_name": archetype_name})
            return None

        if not archetype.get("Player", False):
            logger.warning(
                "Archetype not available to players",
                extra={"archetype_name": archetype_name},
            )
            return None

        return archetype

    except ClientError as err:
        logger.error(
            "Error retrieving archetype",
            extra={"error": str(err), "archetype_name": archetype_name},
        )
        return None


def check_character_limit(player_id: str) -> tuple:
    """
    Check if player has reached character limit.

    Args:
        player_id: Cognito user ID.

    Returns:
        Tuple of (can_create, current_count).
    """
    try:
        player = dynamo.get_item(TableName.PLAYERS, {"PlayerID": player_id})

        if not player:
            logger.error("Player not found", extra={"player_id": player_id})
            return False, 0
        character_list = player.get("CharacterList", {})
        current_count = len(character_list)

        return current_count < MAX_CHARACTERS_PER_PLAYER, current_count

    except ClientError as err:
        logger.error(
            "Error checking character limit",
            extra={"error": str(err), "player_id": player_id},
        )
        return False, 0


def get_character_with_ownership(character_id: str, player_id: str) -> tuple:
    """
    Get character by ID and verify ownership.

    Args:
        character_id: Character UUID
        player_id: Player ID for ownership verification

    Returns:
        Tuple of (character_dict, error_message)
        If successful: (character, None)
        If failed: (None, error_message)
    """
    if not validate_uuid(character_id):
        logger.warning("Invalid character ID format", extra={"character_id": character_id})
        return None, "Invalid character ID format"

    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})

        if not character:
            logger.warning("Character not found", extra={"character_id": character_id})
            return None, "Character not found"
    except ClientError as err:
        logger.error(
            "Error retrieving character",
            extra={"error": str(err), "character_id": character_id},
        )
        return None, "Failed to retrieve character"

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
        return None, "Character not found"

    logger.info(
        "Character retrieved successfully",
        extra={
            "character_id": character_id,
            "character_name": character.get("CharacterName"),
            "game_mode": character.get("GameMode"),
        },
    )

    return character, None


def reset_character_game_mode(character_id: str) -> dict:
    """
    Reset character's GameMode back to None.

    Args:
        character_id: Character UUID

    Returns:
        Dict with:
            - success: bool
            - error: Error message (if failed)
    """
    try:
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET GameMode = :none",
            ExpressionAttributeValues={":none": "None"},
        )
        logger.info("Reset character game mode", extra={"character_id": character_id})
        return {"success": True}

    except Exception as err:
        logger.error(
            "Failed to reset character game mode",
            extra={"character_id": character_id, "error": str(err)},
        )
        return {"success": False, "error": "Failed to update character"}


def get_active_segment_for_character(character_id: str, player_id: str, segment_type=None) -> tuple:
    """
    Get active segment for a character with ownership verification.

    Args:
        character_id: Character UUID
        player_id: Player ID for ownership verification
        segment_type: Optional segment type filter (e.g., "decision")

    Returns:
        Tuple of (active_segment_dict, error_message)
        If successful: (active_segment, None)
        If failed: (None, error_message)
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
            return None, "No active segment found"

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

        return active_segment, None

    except Exception as err:
        logger.error(
            "Error querying active segments",
            extra={"error": str(err), "character_id": character_id},
        )
        return None, "Failed to retrieve active segment"


def verify_character_in_game_mode(character: dict, expected_mode: str = "Incremental") -> tuple:
    """
    Verify character is in the expected game mode.

    Args:
        character: Character dict
        expected_mode: Expected game mode

    Returns:
        Tuple of (is_valid, error_message)
        If valid: (True, None)
        If invalid: (False, error_message)
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
        return False, f"Character is not in {expected_mode} mode"

    return True, None


def get_character_by_name(player_id: str, character_name: str) -> tuple:
    """
    Get character by name for a specific player.

    Args:
        player_id: Player ID
        character_name: Character name

    Returns:
        Tuple of (character_dict, error_message)
        If successful: (character, None)
        If failed: (None, error_message)
    """
    try:
        player = dynamo.get_item(TableName.PLAYERS, {"PlayerID": player_id})

        if not player:
            logger.warning("Player not found", extra={"player_id": player_id})
            return None, "Player not found"

        character_list = player.get("CharacterList", {})
        character_info = character_list.get(character_name)

        if not character_info:
            logger.warning(
                "Character not found in player list",
                extra={"player_id": player_id, "character_name": character_name},
            )
            return None, "Character not found"

        character_id = character_info.get("UUID")
        if not character_id:
            logger.error(
                "Character UUID missing",
                extra={"player_id": player_id, "character_name": character_name},
            )
            return None, "Character data corrupted"

        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})

        if not character:
            logger.error(
                "Character not found in characters table",
                extra={"character_id": character_id, "character_name": character_name},
            )
            return None, "Character not found"

        return character, None

    except ClientError as err:
        logger.error(
            "Error retrieving character by name",
            extra={"error": str(err), "player_id": player_id, "character_name": character_name},
        )
        return None, "Failed to retrieve character"


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
        "errors": []
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
                    logger.info("Removed character from player list",
                               extra={"character_name": character_name, "player_id": player_id})
                except Exception as err:
                    logger.error("Failed to remove character from player list",
                                extra={"error": str(err), "character_name": character_name})
                    results["errors"].append(f"Failed to remove character from player list: {str(err)}")

            inventory = character.get("Inventory", {})
            for slot, item_id in inventory.items():
                if item_id:
                    try:
                        dynamo.delete_item(TableName.ITEMS, Key={"ItemID": item_id})
                        results["items_deleted"] += 1
                    except Exception as err:
                        logger.error(f"Failed to delete item {item_id}", extra={"error": str(err)})
                        results["errors"].append(f"Failed to delete item {item_id}: {str(err)}")

            left_hand_id = character.get("LeftHandID")
            right_hand_id = character.get("RightHandID")

            if left_hand_id:
                try:
                    dynamo.delete_item(TableName.ITEMS, Key={"ItemID": left_hand_id})
                    results["items_deleted"] += 1
                except Exception as err:
                    logger.error(f"Failed to delete left hand item {left_hand_id}", extra={"error": str(err)})
                    results["errors"].append(f"Failed to delete left hand item: {str(err)}")

            if right_hand_id:
                try:
                    dynamo.delete_item(TableName.ITEMS, Key={"ItemID": right_hand_id})
                    results["items_deleted"] += 1
                except Exception as err:
                    logger.error(f"Failed to delete right hand item {right_hand_id}", extra={"error": str(err)})
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
                        "player_id": character.get("PlayerID")
                    }
                )
            except Exception as err:
                logger.error("Failed to delete character", extra={"error": str(err), "character_id": character_id})
                results["errors"].append(f"Failed to delete character: {str(err)}")

        try:
            active_segments = dynamo.query(
                TableName.ACTIVE_SEGMENTS,
                IndexName="CharacterID-index",
                KeyConditionExpression="CharacterID = :cid",
                ExpressionAttributeValues={":cid": character_id}
            )

            for segment in active_segments: # type: ignore
                try:
                    dynamo.delete_item(TableName.ACTIVE_SEGMENTS, Key={"ActiveSegmentID": segment["ActiveSegmentID"]})
                    results["active_segments_deleted"] += 1
                except Exception as err:
                    logger.error("Failed to delete active segment", extra={"error": str(err), "segment_id": segment["ActiveSegmentID"]})
                    results["errors"].append(f"Failed to delete active segment {segment['ActiveSegmentID']}: {str(err)}")

        except Exception as err:
            logger.error("Failed to query active segments", extra={"error": str(err), "character_id": character_id})
            results["errors"].append(f"Failed to query active segments: {str(err)}")

        try:
            history_records = dynamo.query(
                TableName.HISTORY,
                KeyConditionExpression="CharacterID = :cid",
                ExpressionAttributeValues={":cid": character_id}
            )

            for record in history_records: # type: ignore
                try:
                    dynamo.delete_item(
                        TableName.HISTORY,
                        Key={"CharacterID": character_id, "StoryID": record["StoryID"]}
                    )
                    results["history_deleted"] += 1
                except Exception as err:
                    logger.error("Failed to delete history record", extra={"error": str(err), "story_id": record["StoryID"]})
                    results["errors"].append(f"Failed to delete history record for story {record['StoryID']}: {str(err)}")

        except Exception as err:
            logger.error("Failed to query history", extra={"error": str(err), "character_id": character_id})
            results["errors"].append(f"Failed to query history: {str(err)}")

    except Exception as err:
        logger.error("Error in delete_character", extra={"error": str(err), "character_id": character_id}, exc_info=True)
        results["errors"].append(f"General error: {str(err)}")

    return results
