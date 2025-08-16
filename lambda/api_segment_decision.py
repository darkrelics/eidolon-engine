"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to submit a decision for a story segment.
Updates the active segment with the player's choice and returns the next segment.
"""

from eidolon.cognito import extract_player_id
from eidolon.cors import cors_handler
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import validate_player
from eidolon.responses import lambda_error, lambda_response
from eidolon.story import submit_decision_for_character


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
            logger.error(f"Player not found in database for {player_id}", exc_info=True)
            return lambda_response(401, {"Error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error(f"Failed to validate player Error: {err}", exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)

    # Parse request body with flexible field names
    try:
        body: dict = event.get("body", {})
        character_id: str = body.get("character_id") or body.get("CharacterID")  # type: ignore
        decision_id: str = body.get("decision") or body.get("Decision")  # type: ignore

    except ValueError as err:
        return lambda_response(400, {"Error": str(err)}, event)
    except Exception as err:
        return lambda_error(event, err)

    # Call business logic
    try:
        response_data = submit_decision_business_logic(character_id, decision_id, player_id)  # type: ignore
        return lambda_response(200, response_data, event)
    except ValueError as err:
        logger.warning(f"Invalid request for {character_id} Error: {err}")
        error_msg = str(err)
        if "not found" in error_msg.lower():
            return lambda_response(404, {"Error": error_msg}, event)
        elif "already submitted" in error_msg.lower():
            return lambda_response(409, {"Error": error_msg}, event)
        return lambda_response(400, {"Error": error_msg}, event)
    except RuntimeError as err:
        logger.error(
            f"Failed to submit decision for {character_id} Error: {err}",
            exc_info=True,
        )
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)
