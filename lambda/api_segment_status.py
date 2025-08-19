"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to get the status of an active segment.
Returns segment completion status and any available results.
"""

import time

from eidolon.api_models import SegmentStatusResponse
from eidolon.cognito import extract_player_id
from eidolon.cors import cors_handler
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import validate_player, verify_character_ownership
from eidolon.requests import get_query_parameter_flexible
from eidolon.responses import lambda_error, lambda_response
from eidolon.story import get_active_story_segment_with_player_check
from eidolon.time_utils import from_unix


def get_segment_status_business_logic(character_id: str, player_id: str) -> SegmentStatusResponse:
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
    # Verify character ownership using player record
    if not verify_character_ownership(character_id, player_id):
        raise ValueError("Character not owned by player")

    # Get active segment
    active_segment = get_active_story_segment_with_player_check(character_id, player_id)

    # Convert Unix timestamps to ISO 8601 for API response
    end_time_unix = active_segment.get("EndTime", 0)
    end_time = from_unix(end_time_unix) if end_time_unix else ""

    # Calculate status using Unix timestamps
    import time

    now = time.time()
    is_complete = end_time_unix <= now if end_time_unix else False
    time_remaining = max(0, int(end_time_unix - now)) if end_time_unix else 0

    processing_status = active_segment.get("ProcessingStatus", "")

    response = {
        "ActiveSegmentID": active_segment.get("ActiveSegmentID"),
        "StoryID": active_segment.get("StoryID"),
        "SegmentID": active_segment.get("SegmentID"),
        "Status": active_segment.get("Status", "active"),
        "IsComplete": is_complete,
        "TimeRemaining": time_remaining,
        "EndTime": end_time,
        "ProcessingStatus": processing_status,
        "SegmentType": active_segment.get("SegmentType"),
    }

    # Only include narrative data if segment is processed or if it's not a mechanical segment
    # Mechanical segments need processing before narrative is available
    segment_type = active_segment.get("SegmentType", "").lower()

    if segment_type != "mechanical" or processing_status == "processed":
        # Include narrative and events for display
        response["DefaultStatus"] = active_segment.get("DefaultStatus")
        response["ClientEvents"] = active_segment.get("ClientEvents", [])
        response["ChallengeResults"] = active_segment.get("ChallengeResults", [])
        response["Outcome"] = active_segment.get("Outcome")
        response["CombatState"] = active_segment.get("CombatState")
    else:
        # Segment is still processing - just return basic status
        response["DefaultStatus"] = "Processing..."

    # Include decision-specific data
    if segment_type == "decision":
        response["Decision"] = active_segment.get("Decision")
        response["DecisionOptions"] = active_segment.get("DecisionOptions")

    # Include healing data for rest segments
    if segment_type == "rest":
        response["HealingApplied"] = active_segment.get("HealingApplied")

    logger.info(f"Segment status retrieved for {character_id}")

    return SegmentStatusResponse.model_validate(response)


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
        return lambda_response(200, response_data.model_dump(by_alias=True), event)
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
