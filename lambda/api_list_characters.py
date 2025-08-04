"""
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

Lambda function to list character names for an authenticated player.
Returns only character names and death status from the player table.
"""

from eidolon.cors import cors_handler
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import extract_player_id, get_formatted_character_list, validate_player_exists
from eidolon.responses import lambda_error, lambda_response


def list_characters_business_logic(player_id: str) -> dict:
    """
    Business logic for listing player's characters.

    Args:
        player_id: Authenticated player ID

    Returns:
        Dict with characters list

    Raises:
        ValueError: If player not found
        RuntimeError: If database operations fail
    """
    # Get formatted character list from eidolon library
    characters = get_formatted_character_list(player_id)
    return {"Characters": characters}


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler for listing player characters.

    Args:
        event: API Gateway event with Cognito authorizer
        context: Lambda context

    Returns:
        API Gateway response with:
            200: List of characters
            404: Player not found
            401: Unauthorized
            500: Internal error
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
        logger.error("Authentication failed", extra={"error": str(err)}, exc_info=True)
        return lambda_response(401, {"Error": "Unauthorized"}, event)
    except Exception as err:
        return lambda_error(event, err)

    # Validate player exists
    try:
        if not validate_player_exists(player_id):
            logger.error("Player not found in database", extra={"player_id": player_id})
            return lambda_response(401, {"Error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error("Failed to validate player", extra={"error": str(err)}, exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)

    # Call business logic
    try:
        response_data = list_characters_business_logic(player_id)
        logger.info("Lambda response", extra={"status_code": 200})
        return lambda_response(200, response_data, event)
    except ValueError as err:
        logger.warning(
            "Player not found",
            extra={"player_id": player_id, "error": str(err)},
        )
        return lambda_response(
            404,
            {"Error": "Player not found"},
            event,
        )
    except RuntimeError as err:
        logger.error(
            "Failed to list characters",
            extra={"player_id": player_id, "error": str(err)},
            exc_info=True,
        )
        return lambda_response(
            500,
            {"Error": "Internal server error"},
            event,
        )
    except Exception as err:
        return lambda_error(event, err)
