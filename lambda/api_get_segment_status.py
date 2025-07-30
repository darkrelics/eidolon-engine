"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to get the status of an active segment.
Returns segment completion status and any available results.
"""

import time

from eidolon.character import get_character, validate_character_ownership
from eidolon.logger import get_logger
from eidolon.player import extract_player_id_from_event, validate_player_exists
from eidolon.requests import get_query_parameter_flexible
from eidolon.story import get_active_story_segment_with_player_check
from eidolon.utilities import (
    build_lambda_response_pascal,
    handle_lambda_error_pascal,
    handle_preflight_if_options,
    log_lambda_invocation,
)
from eidolon.validation import validate_uuid

logger = get_logger(__name__)


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
    # Validate character ID format
    if not validate_uuid(character_id):
        raise ValueError("Invalid character ID format")

    # Verify character ownership
    character = get_character(character_id)
    validate_character_ownership(character, player_id)

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
    
    logger.info(
        "Segment status retrieved",
        extra={
            "character_id": character_id,
            "active_segment_id": active_segment.get("ActiveSegmentID"),
            "is_complete": is_complete,
            "time_remaining": time_remaining,
        },
    )
    
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
    log_lambda_invocation(context, event)

    # Handle preflight
    preflight_response = handle_preflight_if_options(event)
    if preflight_response:
        return preflight_response

    try:
        # Extract player ID from JWT
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

    # Get character ID from query parameters (flexible: CharacterID or characterId)
    character_id = get_query_parameter_flexible(event, "CharacterID", "characterId")
    if not character_id:
        return build_lambda_response_pascal(400, {"Error": "Missing CharacterID parameter"}, event)

    # Call business logic
    try:
        response_data = get_segment_status_business_logic(character_id, player_id)  # type: ignore
        logger.info("Lambda response", extra={"status_code": 200})
        return build_lambda_response_pascal(200, response_data, event)
    except ValueError as err:
        logger.warning(
            "Invalid request or not found",
            extra={"character_id": character_id, "error": str(err)},
        )
        error_msg = str(err).lower()
        if "no active" in error_msg:
            return build_lambda_response_pascal(404, {"Error": "No active segment found"}, event)
        elif "not found" in error_msg:
            return build_lambda_response_pascal(404, {"Error": "Character not found"}, event)
        return build_lambda_response_pascal(400, {"Error": str(err)}, event)
    except RuntimeError as err:
        logger.error(
            "Failed to get segment status",
            extra={"character_id": character_id, "error": str(err)},
            exc_info=True,
        )
        return build_lambda_response_pascal(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)