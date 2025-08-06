"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to get the status of an active segment.
Returns segment completion status and any available results.
"""

import time

from eidolon.character import character_get
from eidolon.cors import cors_handler
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import extract_player_id, validate_player
from eidolon.requests import get_query_parameter_flexible
from eidolon.responses import lambda_error, lambda_response
from eidolon.story import get_active_story_segment_with_player_check


def get_segment_status_business_logic(character_id: str, player_id: str) -> dict:
    """
    Business logic for getting segment status.

    Args:
        character_id: Character UUID
        player_id: Authenticated player ID

    Returns:
        Response data dict with segment status

    Raises:
        ValueError: If character not found or not owned
        RuntimeError: If database operations fail
    """
    # Verify character ownership
    # TODO - Read Player Record instead.
    character: dict = character_get(character_id, player_id)

    # Get active segment
    active_segment = get_active_story_segment_with_player_check(character_id, player_id)

    # Calculate status
    current_time = int(time.time())
    end_time = int(active_segment.get("EndTime", 0))
    is_complete = current_time >= end_time
    time_remaining = max(0, end_time - current_time)

    response = {
        "ActiveSegmentID": active_segment.get("ActiveSegmentID"),
        "StoryID": active_segment.get("StoryID"),
        "SegmentID": active_segment.get("SegmentID"),
        "Status": active_segment.get("Status", "active"),
        "IsComplete": is_complete,
        "TimeRemaining": time_remaining,
        "EndTime": end_time,
    }

    # Include results if segment is complete
    if is_complete:
        response["ChallengeResults"] = active_segment.get("ChallengeResults", [])
        response["Outcome"] = active_segment.get("Outcome")
        response["Decision"] = active_segment.get("Decision")
        response["CombatState"] = active_segment.get("CombatState")
        response["HealingApplied"] = active_segment.get("HealingApplied")

    logger.info(f"Segment status retrieved for {character_id}")

    return response


def lambda_handler(event: dict, context: object) -> dict:
    """
    Get status of active segment.

    Lambda function to check the status of a character's active segment.
    Used by clients to poll for segment completion and retrieve results.

    Query Parameters:
        characterId: Character ID to check (supports both CharacterID and characterId)

    Returns:
        200: Segment status data
        404: No active segment found
        400: Missing parameters or invalid request
        401: Unauthorized
        500: Internal error
    """
    # Log invocation
    log_lambda_statistics(event, context)

    # Handle preflight
    preflight_response: dict = cors_handler.handle_preflight(event)
    if preflight_response:
        return preflight_response

    try:
        # Extract player ID from JWT
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

    # Get character ID from query parameters (flexible: CharacterID or characterId)
    character_id = get_query_parameter_flexible(event, "CharacterID", "characterId")
    if not character_id:
        return lambda_response(400, {"Error": "Missing CharacterID parameter"}, event)

    # Call business logic
    try:
        response_data = get_segment_status_business_logic(character_id, player_id)  # type: ignore
        return lambda_response(200, response_data, event)
    except ValueError as err:
        logger.warning(f"Invalid request or not found for {character_id} Error: {err}")
        error_msg = str(err).lower()
        if "no active" in error_msg:
            return lambda_response(404, {"Error": "No active segment found"}, event)
        elif "not found" in error_msg:
            return lambda_response(404, {"Error": "Character not found"}, event)
        return lambda_response(400, {"Error": str(err)}, event)
    except RuntimeError as err:
        logger.error(
            f"Failed to get segment status for {character_id} Error: {err}",
            exc_info=True,
        )
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)
