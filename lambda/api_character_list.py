"""
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

Lambda function to list character names for an authenticated player.
Returns only character names and death status from the player table.
"""

from eidolon.cors import cors_handler
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import extract_player_id, get_character_list, validate_player
from eidolon.responses import lambda_error, lambda_response


def list_characters(player_id: str) -> dict:
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
    characters: list = get_character_list(player_id)

    logger.debug(f"Characters retreived: {characters}")

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
        player_id: str = extract_player_id(event)
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

    # Call business logic
    try:
        response_data: dict = list_characters(player_id)
        logger.info("Lambda response for status 200")
        return lambda_response(200, response_data, event)
    except ValueError as err:
        logger.warning(f"Player not found for {player_id} Error: {err}")
        return lambda_response(
            404,
            {"Error": "Player not found"},
            event,
        )
    except RuntimeError as err:
        logger.error(f"Failed to list characters for {player_id} Error: {err}", exc_info=True)
        return lambda_response(
            500,
            {"Error": "Internal server error"},
            event,
        )
    except Exception as err:
        return lambda_error(event, err)
