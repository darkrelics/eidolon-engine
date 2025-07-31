"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to submit a decision for a story segment.
Updates the active segment with the player's choice and returns the next segment.
"""

from eidolon.logger import get_logger
from eidolon.player import extract_player_id_from_event, validate_player_exists
from eidolon.requests import get_required_field_flexible, parse_json_body
from eidolon.story import submit_decision_for_character
from eidolon.utilities import (
    build_lambda_response_pascal,
    handle_lambda_error_pascal,
    handle_preflight_if_options,
    log_lambda_invocation,
)

# Configure logging
logger = get_logger(__name__)


def submit_decision_business_logic(character_id: str, decision_id: str, player_id: str) -> dict:
    """
    Business logic for submitting a decision.

    Args:
        character_id: Character UUID
        decision_id: Decision ID chosen by player
        player_id: Authenticated player ID

    Returns:
        Response data with accepted status and optional next segment time

    Raises:
        ValueError: If validation fails
        RuntimeError: If database operations fail
    """
    # Submit the decision using the eidolon library
    return submit_decision_for_character(character_id, decision_id, player_id)


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to submit a decision for a story segment.

    Args:
        event: API Gateway Lambda proxy event
        context: Lambda context

    Returns:
        API Gateway Lambda proxy response
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
        logger.error("Authentication failed", extra={"error": str(err)}, exc_info=True)
        return build_lambda_response_pascal(401, {"Error": "Unauthorized"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)

    # Validate player exists
    try:
        if not validate_player_exists(player_id):
            logger.error("Player not found in database", extra={"player_id": player_id}, exc_info=True)
            return build_lambda_response_pascal(401, {"Error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error("Failed to validate player", extra={"error": str(err)}, exc_info=True)
        return build_lambda_response_pascal(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)

    # Parse request body with flexible field names
    try:
        body = parse_json_body(event)
        character_id = get_required_field_flexible(body, "CharacterID", "characterID")
        decision_id = get_required_field_flexible(body, "Decision", "decision")
    except ValueError as err:
        return build_lambda_response_pascal(400, {"Error": str(err)}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)

    # Call business logic
    try:
        response_data = submit_decision_business_logic(character_id, decision_id, player_id)  # type: ignore
        logger.info("Lambda response", extra={"status_code": 200})
        return build_lambda_response_pascal(200, response_data, event)
    except ValueError as err:
        logger.warning(
            "Invalid request",
            extra={"character_id": character_id, "decision_id": decision_id, "error": str(err)},
        )
        error_msg = str(err)
        if "not found" in error_msg.lower():
            return build_lambda_response_pascal(404, {"Error": error_msg}, event)
        elif "already submitted" in error_msg.lower():
            return build_lambda_response_pascal(409, {"Error": error_msg}, event)
        return build_lambda_response_pascal(400, {"Error": error_msg}, event)
    except RuntimeError as err:
        logger.error(
            "Failed to submit decision",
            extra={"character_id": character_id, "decision_id": decision_id, "error": str(err)},
            exc_info=True,
        )
        return build_lambda_response_pascal(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)
