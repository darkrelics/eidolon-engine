"""
Character management utilities for Lambda functions.

Provides common functions for character creation and management.
"""

import uuid

from botocore.exceptions import ClientError

from eidolon.dynamo import get_item, get_table
from eidolon.environment import ACTIVE_SEGMENTS_TABLE, ARCHETYPES_TABLE, CHARACTERS_TABLE, MAX_CHARACTERS_PER_PLAYER, PLAYERS_TABLE
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
        archetypes_table = get_table(ARCHETYPES_TABLE)
        response = archetypes_table.get_item(Key={"ArchetypeName": archetype_name})

        if "Item" not in response:
            logger.warning("Archetype not found", extra={"archetype_name": archetype_name})
            return None

        archetype = response["Item"]

        # Check if archetype is available to players
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
        # Get player record
        players_table = get_table(PLAYERS_TABLE)
        response = players_table.get_item(Key={"PlayerID": player_id})

        if "Item" not in response:
            logger.error("Player not found", extra={"player_id": player_id})
            return False, 0

        player = response["Item"]
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
    # Validate character ID format
    if not validate_uuid(character_id):
        logger.warning("Invalid character ID format", extra={"character_id": character_id})
        return None, "Invalid character ID format"

    # Get character from database
    characters_table = get_table(CHARACTERS_TABLE)
    character = get_item(characters_table, {"CharacterID": character_id})

    if not character:
        logger.warning("Character not found", extra={"character_id": character_id})
        return None, "Character not found"

    # Verify ownership
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
        return None, "Character not found"  # Don't reveal ownership info

    logger.info(
        "Character retrieved successfully",
        extra={
            "character_id": character_id,
            "character_name": character.get("CharacterName"),
            "game_mode": character.get("GameMode"),
        },
    )

    return character, None


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
    active_segments_table = get_table(ACTIVE_SEGMENTS_TABLE)

    # Query by CharacterID using GSI
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

    # Add segment type filter if specified
    if segment_type:
        query_params["FilterExpression"] += " AND SegmentType = :type"
        query_params["ExpressionAttributeValues"][":type"] = segment_type

    try:
        response = active_segments_table.query(**query_params)
        items = response.get("Items", [])

        if not items:
            logger.info(
                "No active segment found",
                extra={"character_id": character_id, "segment_type": segment_type},
            )
            return None, "No active segment found"

        # Return first active segment (should only be one)
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
    # First get player record to find character UUID
    players_table = get_table(PLAYERS_TABLE)
    player = get_item(players_table, {"PlayerID": player_id})

    if not player:
        logger.warning("Player not found", extra={"player_id": player_id})
        return None, "Player not found"

    # Get character UUID from player's character list
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

    # Get character details
    characters_table = get_table(CHARACTERS_TABLE)
    character = get_item(characters_table, {"CharacterID": character_id})

    if not character:
        logger.error(
            "Character not found in characters table",
            extra={"character_id": character_id, "character_name": character_name},
        )
        return None, "Character not found"

    return character, None
