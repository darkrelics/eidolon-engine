"""
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

Lambda function to list character names for an authenticated player.
Returns only character names and death status from the player table.
"""

from eidolon.logger import get_logger
from eidolon.player import extract_player_id_from_event
from eidolon.player import get_formatted_character_list
from eidolon.player import validate_player_exists
from eidolon.utilities import build_lambda_response
from eidolon.utilities import handle_lambda_error
from eidolon.utilities import handle_preflight_if_options
from eidolon.utilities import log_lambda_invocation

# Configure logging
logger = get_logger(__name__)


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
    return {"characters": characters}


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
        return build_lambda_response(401, {"error": "Unauthorized"}, event)
    except Exception as err:
        return handle_lambda_error(err, context, event)
    
    # Validate player exists
    try:
        if not validate_player_exists(player_id):
            logger.error("Player not found in database", extra={"player_id": player_id})
            return build_lambda_response(401, {"error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error("Failed to validate player", extra={"error": str(err)})
        return build_lambda_response(500, {"error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error(err, context, event)

    # Call business logic
    try:
        response_data = list_characters_business_logic(player_id)
        return build_lambda_response(200, response_data, event)
    except ValueError as err:
        logger.warning(
            "Player not found",
            extra={"player_id": player_id, "error": str(err)},
        )
        return build_lambda_response(
            404,
            {"error": "Player not found"},
            event,
        )
    except RuntimeError as err:
        logger.error(
            "Failed to list characters",
            extra={"player_id": player_id, "error": str(err)},
        )
        return build_lambda_response(
            500,
            {"error": "Internal server error"},
            event,
        )
    except Exception as err:
        return handle_lambda_error(err, context, event)
