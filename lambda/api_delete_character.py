"""
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

Lambda function to delete a character for an authenticated player.
Ensures the character belongs to the player before deletion.
"""

from eidolon.character import delete_character
from eidolon.character import get_character_with_ownership
from eidolon.cors import cors_handler
from eidolon.logger import get_logger
from eidolon.requests import extract_player_id
from eidolon.requests import get_query_parameter
from eidolon.responses import create_response
from eidolon.responses import error_response
from eidolon.validation import validate_uuid

# Configure logging
logger = get_logger(__name__)


def delete_character_with_ownership_check(player_id: str, character_id: str) -> dict:
    """
    Delete a character after verifying ownership.

    Args:
        player_id: Cognito user ID
        character_id: Character UUID

    Returns:
        dict: Results of the deletion operation

    Raises:
        ValueError: If character not found or not owned by player
        RuntimeError: If database operations fail
    """
    # Verify ownership and get character
    character = get_character_with_ownership(character_id, player_id)
    character_name = character.get("CharacterName", "Unknown")

    logger.info(
        "Deleting character",
        extra={
            "character_id": character_id,
            "character_name": character_name,
            "player_id": player_id,
        },
    )

    # Delete the character
    results = delete_character(character_id, remove_from_player_list=True)

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
            return cors_handler.add_cors_headers(error_response(auth_error, status_code=401), event)

        # Get character ID from query parameters
        character_id, error_msg = get_query_parameter(event, "characterId", required=True)  # type: ignore
        if error_msg:
            return cors_handler.add_cors_headers(error_response(error_msg), event)

        # Validate character ID format
        if not validate_uuid(character_id):
            return cors_handler.add_cors_headers(error_response("Invalid character ID format", status_code=400), event)

        # Delete the character with ownership verification
        try:
            deletion_result = delete_character_with_ownership_check(player_id, character_id)
        except ValueError as err:
            logger.warning(
                "Character not found or not owned",
                extra={"character_id": character_id, "player_id": player_id, "error": str(err)},
            )
            return cors_handler.add_cors_headers(
                error_response("Character not found or access denied", status_code=404),
                event,
            )
        except RuntimeError as err:
            logger.error(
                "Failed to delete character",
                extra={"character_id": character_id, "error": str(err)},
            )
            return cors_handler.add_cors_headers(
                error_response("Failed to delete character", status_code=500),
                event,
            )

        # Check if deletion was successful
        if not deletion_result["character_deleted"]:
            error_msg = "Failed to delete character"
            if deletion_result["errors"]:
                error_msg = deletion_result["errors"][0]
            return cors_handler.add_cors_headers(error_response(error_msg, status_code=500), event)

        # Return success response with details
        logger.info("Lambda response", extra={"status_code": 200})
        return cors_handler.add_cors_headers(
            create_response(
                200,
                {
                    "message": "Character deleted successfully",
                    "characterId": character_id,
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
        return cors_handler.add_cors_headers(error_response("Internal server error", status_code=500), event)
