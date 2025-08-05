"""
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

Lambda function to delete a character for an authenticated player.
Ensures the character belongs to the player before deletion.
"""

from eidolon.character import delete_character, character_get
from eidolon.cors import cors_handler
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import extract_player_id, validate_player
from eidolon.requests import get_query_parameter_flexible
from eidolon.responses import lambda_error, lambda_response
from eidolon.validation import validate_uuid


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
    character: dict = character_get(character_id, player_id)
    character_name = character.get("CharacterName", "Unknown")

    logger.info(f"Character ownership verified, proceeding with deletion for {character_id}")

    # Delete the character
    deletion_result = delete_character(character_id, remove_from_player_list=True)

    logger.info(f"Character deletion completed for {character_id}")

    # Check if deletion was successful
    if not deletion_result.get("character_deleted", False):
        error_msg = "Failed to delete character"
        errors = deletion_result.get("errors", [])
        if errors:
            error_msg = errors[0]
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
    log_lambda_statistics(event, context)

    # Handle preflight
    preflight_response: dict = cors_handler.handle_preflight(event)
    if preflight_response:
        return preflight_response

    # Extract player ID from JWT
    try:
        player_id = extract_player_id(event)
    except ValueError as err:
        logger.error(f"Authentication failed Error: {err}", exc_info=True)
        return lambda_response(401, {"Error": "Unauthorized"}, event)
    except Exception as err:
        return lambda_error(event, err)

    # Validate player exists
    try:
        if not validate_player(player_id):
            logger.error(f"Player not found in database for {player_id}")
            return lambda_response(401, {"Error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error(f"Failed to validate player Error: {err}", exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)

    # Get character ID from query parameters (flexible: CharacterID or characterId)
    character_id = get_query_parameter_flexible(event, "CharacterID", "characterId")
    if not character_id:
        return lambda_response(400, {"Error": "Missing CharacterID parameter"}, event)

    # Validate character ID format
    if not validate_uuid(character_id):  # type: ignore
        return lambda_response(400, {"Error": "Invalid character ID format"}, event)

    # Call business logic
    try:
        result = handle_character_deletion(player_id, character_id)  # type: ignore
        logger.info(f"Lambda response")
        return lambda_response(
            200,
            {
                "Message": "Character deleted successfully",
                "CharacterID": character_id,
                "CharacterName": result.get("character_name", "Unknown"),
                "ItemsDeleted": result.get("deletion_result", {}).get("items_deleted", 0),
                "ActiveSegmentsDeleted": result.get("deletion_result", {}).get("active_segments_deleted", 0),
                "HistoryDeleted": result.get("deletion_result", {}).get("history_deleted", 0),
            },
            event,
        )
    except ValueError as err:
        # Character not found or not owned by player
        logger.warning(f"Character deletion validation failed for {character_id} Error: {err}")
        error_msg = str(err).lower()
        if "not found" in error_msg:
            return lambda_response(404, {"Error": "Character not found"}, event)
        elif "not owned" in error_msg or "ownership" in error_msg:
            return lambda_response(403, {"Error": "Access denied"}, event)
        else:
            return lambda_response(400, {"Error": str(err)}, event)
    except RuntimeError as err:
        # Database or deletion failures
        logger.error(
            f"Character deletion system error for {character_id} Error: {err}",
            exc_info=True,
        )
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)
