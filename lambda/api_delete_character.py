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
from eidolon.player import extract_player_id_from_event
from eidolon.requests import get_query_parameter
from eidolon.responses import create_response
from eidolon.responses import error_response
from eidolon.validation import validate_uuid

# Configure logging
logger = get_logger(__name__)


def handle_character_deletion(player_id: str, character_id: str) -> dict:
    """
    Handle the business logic for character deletion.

    This function orchestrates the character deletion process without
    performing any AWS-specific operations.

    Args:
        player_id: Cognito user ID
        character_id: Character UUID

    Returns:
        Dict containing:
            - success: bool - Whether deletion was successful
            - character_name: str - Name of deleted character
            - deletion_result: dict - Detailed deletion results

    Raises:
        ValueError: If character not found, invalid ID, or not owned by player
        RuntimeError: If database operations fail
    """
    # Verify ownership
    character = get_character_with_ownership(character_id, player_id)
    character_name = character.get("CharacterName", "Unknown")

    logger.info(
        "Character ownership verified, proceeding with deletion",
        extra={
            "character_id": character_id,
            "character_name": character_name,
            "player_id": player_id,
        },
    )

    # Delete the character
    deletion_result = delete_character(character_id, remove_from_player_list=True)

    logger.info(
        "Character deletion completed",
        extra={
            "character_name": character_name,
            "character_id": character_id,
            "player_id": player_id,
            "results": deletion_result,
        },
    )

    # Check if deletion was successful
    if not deletion_result["character_deleted"]:
        error_msg = "Failed to delete character"
        if deletion_result["errors"]:
            error_msg = deletion_result["errors"][0]
        raise RuntimeError(error_msg)

    return {"success": True, "character_name": character_name, "deletion_result": deletion_result}


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
        try:
            player_id = extract_player_id_from_event(event)
        except ValueError as err:
            logger.error("Authentication failed", extra={"error": str(err)})
            return cors_handler.add_cors_headers(error_response("Unauthorized", status_code=401), event)

        # Get character ID from query parameters
        try:
            character_id = get_query_parameter(event, "characterId", required=True)
        except ValueError as err:
            return cors_handler.add_cors_headers(error_response(str(err), status_code=400), event)

        # Validate character ID format
        if not validate_uuid(character_id):  # type: ignore
            return cors_handler.add_cors_headers(error_response("Invalid character ID format", status_code=400), event)

        # Handle character deletion through business logic function
        try:
            result = handle_character_deletion(player_id, character_id)  # type: ignore

            # Return success response with details
            logger.info("Lambda response", extra={"status_code": 200})
            return cors_handler.add_cors_headers(
                create_response(
                    200,
                    {
                        "message": "Character deleted successfully",
                        "characterId": character_id,
                        "characterName": result["character_name"],
                        "itemsDeleted": result["deletion_result"]["items_deleted"],
                        "activeSegmentsDeleted": result["deletion_result"]["active_segments_deleted"],
                        "historyDeleted": result["deletion_result"]["history_deleted"],
                    },
                ),
                event,
            )
        except ValueError as err:
            # Character not found or not owned by player
            logger.warning(
                "Character deletion validation failed",
                extra={"character_id": character_id, "player_id": player_id, "error": str(err)},
            )
            return cors_handler.add_cors_headers(
                error_response("Character not found or access denied", status_code=404),
                event,
            )
        except RuntimeError as err:
            # Database or deletion failures
            logger.error(
                "Character deletion system error",
                extra={"character_id": character_id, "error": str(err)},
                exc_info=True,
            )
            return cors_handler.add_cors_headers(
                error_response(str(err), status_code=500),
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
