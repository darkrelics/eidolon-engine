"""
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

Lambda function to delete a character for an authenticated player.
Ensures the character belongs to the player before deletion.
"""

from eidolon.character import delete_character
from eidolon.character import get_character
from eidolon.character import validate_character_ownership
from eidolon.logger import get_logger
from eidolon.player import extract_player_id_from_event
from eidolon.player import validate_player_exists
from eidolon.requests import get_query_parameter_flexible
from eidolon.utilities import build_lambda_response_pascal
from eidolon.utilities import handle_lambda_error_pascal
from eidolon.utilities import handle_preflight_if_options
from eidolon.utilities import log_lambda_invocation
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
    character = get_character(character_id)
    validate_character_ownership(character, player_id)
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
    # Log invocation
    log_lambda_invocation(context, event)

    # Handle preflight
    preflight_response = handle_preflight_if_options(event)
    if preflight_response:
        return preflight_response

    # Extract player ID from JWT
    try:
        player_id = extract_player_id_from_event(event)
    except ValueError as err:
        logger.error("Authentication failed", extra={"error": str(err)})
        return build_lambda_response_pascal(401, {"error": "Unauthorized"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)

    # Validate player exists
    try:
        if not validate_player_exists(player_id):
            logger.error("Player not found in database", extra={"player_id": player_id})
            return build_lambda_response_pascal(401, {"error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error("Failed to validate player", extra={"error": str(err)})
        return build_lambda_response_pascal(500, {"error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)

    # Get character ID from query parameters (flexible: CharacterId or characterId)
    character_id = get_query_parameter_flexible(event, "CharacterId", "characterId")
    if not character_id:
        return build_lambda_response_pascal(400, {"error": "Missing CharacterId parameter"}, event)

    # Validate character ID format
    if not validate_uuid(character_id):  # type: ignore
        return build_lambda_response_pascal(400, {"error": "Invalid character ID format"}, event)

    # Call business logic
    try:
        result = handle_character_deletion(player_id, character_id)  # type: ignore
        return build_lambda_response_pascal(
            200,
            {
                "Message": "Character deleted successfully",
                "CharacterID": character_id,
                "CharacterName": result["character_name"],
                "ItemsDeleted": result["deletion_result"]["items_deleted"],
                "ActiveSegmentsDeleted": result["deletion_result"]["active_segments_deleted"],
                "HistoryDeleted": result["deletion_result"]["history_deleted"],
            },
            event,
        )
    except ValueError as err:
        # Character not found or not owned by player
        logger.warning(
            "Character deletion validation failed",
            extra={"character_id": character_id, "player_id": player_id, "error": str(err)},
        )
        return build_lambda_response_pascal(404, {"error": "Character not found or access denied"}, event)
    except RuntimeError as err:
        # Database or deletion failures
        logger.error(
            "Character deletion system error",
            extra={"character_id": character_id, "error": str(err)},
            exc_info=True,
        )
        return build_lambda_response_pascal(500, {"error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)
