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
from eidolon.player import verify_character_ownership
from eidolon.requests import get_query_parameter
from eidolon.responses import lambda_error, lambda_response
from eidolon.schema import normalize_segment_definition
from eidolon.segment_core import validate_segment_outcome_results
from eidolon.story_active import get_active_story_segment_with_player_check
from eidolon.story_retrieval import get_story_segment
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

    # Try to get active segment
    try:
        active_segment = get_active_story_segment_with_player_check(character_id, player_id)
    except ValueError as err:
        if "No active story found" in str(err):
            # Return a friendly response when no active segment exists
            # This can happen after a rollback or when no story is active
            logger.info(f"No active segment for character {character_id} - likely rolled back or not started")
            raise ValueError("No active story. Please select a story to begin your adventure.") from err
        raise

    # Convert Unix timestamps to ISO 8601 for API response
    end_time_unix = active_segment.get("EndTime", 0)
    end_time = from_unix(end_time_unix) if end_time_unix else ""

    # Calculate status using Unix timestamps
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
    story_id = active_segment.get("StoryID")
    segment_id = active_segment.get("SegmentID")

    if segment_type != "mechanical" or processing_status == "processed":
        # Include narrative and events for display
        response["DefaultStatus"] = active_segment.get("DefaultStatus")
        response["ClientEvents"] = active_segment.get("ClientEvents", [])
        response["ChallengeResults"] = active_segment.get("ChallengeResults", [])
        response["Outcome"] = active_segment.get("Outcome")
        response["CombatState"] = active_segment.get("CombatState")

        # If segment is processed/completed, include full narrative data
        if processing_status == "processed" or active_segment.get("Status") == "completed":
            try:
                # Get segment definition for narrative text
                segment_def = get_story_segment(story_id, segment_id)  # type: ignore
                segment_def = normalize_segment_definition(segment_def)

                if segment_type == "mechanical":
                    outcome = active_segment.get("Outcome", "normal")
                    validated_result = validate_segment_outcome_results(segment_def, outcome)
                    response["Narrative"] = validated_result.get("Narrative", "")
                    response["Effects"] = validated_result.get("Effects", {})

                    # Get next segment based on outcome
                    results = segment_def.get("Results", {}) or {}
                    next_segment_id = None
                    if isinstance(results, dict):
                        outcome_map = {
                            "death": "Death",
                            "failure": "Failure",
                            "minimal": "Minimal",
                            "normal": "Normal",
                            "exceptional": "Exceptional",
                        }
                        outcome_key = outcome_map.get(str(outcome).lower())
                        if outcome_key and isinstance(results.get(outcome_key), dict):
                            outcome_block = results.get(outcome_key, {})
                            if isinstance(outcome_block, dict) and "NextSegmentID" in outcome_block:
                                next_segment_id = outcome_block.get("NextSegmentID")

                    if next_segment_id is None and "NextSegmentID" in segment_def:
                        next_segment_id = segment_def.get("NextSegmentID")

                    response["NextSegmentID"] = next_segment_id

                elif segment_type == "rest":
                    # Get rest segment results
                    rest_results = segment_def.get("Results", {})
                    if isinstance(rest_results, dict) and "normal" in rest_results:
                        normal_result = rest_results["normal"]
                        response["Narrative"] = normal_result.get("Narrative", "")
                        response["Effects"] = normal_result.get("Effects", {})
                        response["NextSegmentID"] = normal_result.get("NextSegmentID")
                    else:
                        response["Narrative"] = ""
                        response["Effects"] = {}
                        response["NextSegmentID"] = segment_def.get("NextSegmentID")

                elif segment_type == "decision":
                    decision = active_segment.get("Decision")
                    decision_options = segment_def.get("DecisionOptions", {})
                    response["NextSegmentID"] = decision_options.get(decision) if decision else None
                    response["Narrative"] = ""
                    response["Effects"] = {}

            except Exception as err:
                logger.warning(
                    f"Failed to get narrative data for segment_id={segment_id}, character_id={character_id}: {err.__class__.__name__}: {err}"
                )
                # Continue without narrative - not critical
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

    logger.debug(f"Segment status retrieved for {character_id}")

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

    # Get character ID from query parameters
    character_id = get_query_parameter(event, "CharacterID")
    if not character_id:
        return lambda_response(400, {"Error": "Missing CharacterID parameter"}, event)

    # Call business logic
    try:
        response_data = get_segment_status_business_logic(character_id, player_id)  # type: ignore
        return lambda_response(200, response_data.model_dump(by_alias=True), event)
    except ValueError as err:
        logger.warning(f"Invalid request or not found for {character_id} Error: {err}")
        error_msg = str(err)
        # Return consistent 404 for no active segment/story
        if "no active" in error_msg.lower() or "Please select" in error_msg:
            return lambda_response(404, {"Error": "No active segment found"}, event)
        elif "not found" in error_msg.lower():
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
