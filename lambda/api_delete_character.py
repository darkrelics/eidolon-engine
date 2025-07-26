"""
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

Lambda function to delete a character for an authenticated player.
Ensures the character belongs to the player before deletion.
"""

from eidolon.character import delete_character as delete_character_lib
from eidolon.cors import cors_handler
from eidolon.dynamo import dynamo
from eidolon.dynamo import TableName
from eidolon.logger import get_logger
from eidolon.requests import extract_player_id
from eidolon.requests import get_query_parameter
from eidolon.responses import create_response
from eidolon.responses import error_response

# Configure logging
logger = get_logger(__name__)


def get_character_name_by_id(player_id: str, character_id: str) -> str:
    """
    Get character name by ID and verify ownership.

    Args:
        player_id: Cognito user ID
        character_id: Character UUID

    Returns:
        Character name if owned by player, empty string otherwise
    """
    # Get player record
    player_data = dynamo.get_item(TableName.PLAYERS, {"PlayerID": player_id})

    if not player_data:
        logger.warning("Player not found", extra={"player_id": player_id})
        return ""

    character_list = player_data.get("CharacterList", {})

    # Find character by UUID
    for char_name, char_info in character_list.items():
        if char_info.get("UUID") == character_id:
            return char_name

    logger.warning(
        "Character not found for player",
        extra={"character_id": character_id, "player_id": player_id},
    )
    return ""


def verify_character_ownership(player_id: str, character_name: str) -> tuple:
    """
    Verify that a character belongs to the specified player.

    Args:
        player_id: Cognito user ID
        character_name: Name of the character to verify

    Returns:
        tuple: (is_owner, character_uuid)
    """
    # Get player record
    player_data = dynamo.get_item(TableName.PLAYERS, {"PlayerID": player_id})

    if not player_data:
        logger.warning("Player not found", extra={"player_id": player_id})
        return False, None
    character_list = player_data.get("CharacterList", {})

    # Check if character exists in player's list
    if character_name not in character_list:
        logger.warning(
            "Character not found for player",
            extra={"character_name": character_name, "player_id": player_id},
        )
        return False, None

    character_info = character_list[character_name]
    character_uuid = character_info.get("UUID")

    # Double-check character record ownership
    character_data = dynamo.get_item(
        TableName.CHARACTERS, {"CharacterID": character_uuid}
    )

    if character_data and character_data.get("PlayerID") != player_id:
        logger.warning(
            "Character does not belong to player",
            extra={"character_id": character_uuid, "player_id": player_id},
        )
        return False, None

    return True, character_uuid


def delete_character_handler(
    player_id: str, character_name: str, character_id: str
) -> dict:
    """
    Handle character deletion with ownership verification.

    Args:
        player_id: Cognito user ID
        character_name: Name of the character
        character_id: UUID of the character

    Returns:
        dict: Results of the deletion operation
    """
    try:
        # Verify ownership by checking the character record
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})

        if not character:
            logger.error("Character not found", extra={"character_id": character_id})
            return {
                "character_deleted": False,
                "character_removed_from_player": False,
                "items_deleted": 0,
                "active_segments_deleted": 0,
                "history_deleted": 0,
                "errors": ["Character not found"],
            }

        # Verify the character belongs to the player
        if character.get("PlayerID") != player_id:
            logger.error(
                "Character does not belong to player",
                extra={"character_id": character_id, "player_id": player_id},
            )
            return {
                "character_deleted": False,
                "character_removed_from_player": False,
                "items_deleted": 0,
                "active_segments_deleted": 0,
                "history_deleted": 0,
                "errors": ["Character does not belong to player"],
            }

        # Use the library function to delete the character
        results = delete_character_lib(character_id, remove_from_player_list=True)

        logger.info(
            "Character deletion completed",
            extra={
                "character_name": character_name,
                "character_id": character_id,
                "player_id": player_id,
                "results": results,
            },
        )

        return results

    except Exception as err:
        logger.error(
            "Error deleting character", extra={"error": str(err)}, exc_info=True
        )
        return {
            "character_deleted": False,
            "character_removed_from_player": False,
            "items_deleted": 0,
            "active_segments_deleted": 0,
            "history_deleted": 0,
            "errors": [f"Unexpected error: {str(err)}"],
        }


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler for character deletion API.

    Args:
        event: API Gateway event with Cognito authorizer
        context: Lambda context

    Returns:
        API Gateway response
    """
    # Log Lambda invocation
    if hasattr(context, "aws_request_id"):
        logger.info(
            "Lambda invocation",
            extra={
                "request_id": context.aws_request_id,  # type: ignore
                "function_name": getattr(context, "function_name", "unknown"),
                "http_method": event.get("httpMethod"),
                "path": event.get("path"),
            },
        )

    # Handle preflight requests
    if event.get("httpMethod") == "OPTIONS":
        return cors_handler.handle_preflight(event)

    try:
        # Extract player ID from Cognito authorizer
        player_id, auth_error = extract_player_id(event)
        if auth_error:
            logger.error("Authentication failed", extra={"error": auth_error})
            return cors_handler.add_cors_headers(
                error_response(auth_error, status_code=401), event
            )

        # Get character ID from query parameters
        character_id, error_msg = get_query_parameter(
            event, "characterId", required=True
        )
        if error_msg:
            return cors_handler.add_cors_headers(error_response(error_msg), event)

        # Get character name and verify ownership
        character_name = get_character_name_by_id(player_id, character_id)
        if not character_name:
            return cors_handler.add_cors_headers(
                error_response("Character not found or access denied", status_code=404),
                event,
            )

        # Delete the character
        deletion_result = delete_character_handler(
            player_id, character_name, character_id
        )

        # Check if deletion was successful
        if not deletion_result["character_deleted"]:
            error_msg = "Failed to delete character"
            if deletion_result["errors"]:
                error_msg = deletion_result["errors"][0]
            return cors_handler.add_cors_headers(
                error_response(error_msg, status_code=500), event
            )

        # Return success response with details
        logger.info("Lambda response", extra={"status_code": 200})
        return cors_handler.add_cors_headers(
            create_response(
                200,
                {
                    "message": "Character deleted successfully",
                    "characterName": character_name,
                    "itemsDeleted": deletion_result["items_deleted"],
                    "activeSegmentsDeleted": deletion_result["active_segments_deleted"],
                    "historyDeleted": deletion_result["history_deleted"],
                },
            ),
            event,
        )

    except Exception as err:
        logger.error(
            "Unexpected error in lambda_handler",
            extra={"error": str(err)},
            exc_info=True,
        )
        logger.info("Lambda response", extra={"status_code": 500})
        return cors_handler.add_cors_headers(
            error_response("Internal server error", status_code=500), event
        )
