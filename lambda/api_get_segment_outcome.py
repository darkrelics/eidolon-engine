"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to get the outcome of a completed segment.
Returns the narrative text and any rewards/effects for the outcome.
"""

from eidolon.character import character_get
from eidolon.cors import cors_handler
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import extract_player_id, validate_player
from eidolon.requests import get_query_parameter_flexible
from eidolon.responses import lambda_error, lambda_response
from eidolon.segment import validate_segment_outcome_results
from eidolon.story import get_completed_segment_for_character, get_story_segment


def get_segment_outcome_business_logic(character_id: str, segment_id: str, player_id: str) -> dict:
    """
    Business logic for getting the outcome of a completed segment.

    Args:
        character_id: Character UUID
        segment_id: Segment UUID
        player_id: Authenticated player ID

    Returns:
        Outcome data dict with narrative and effects

    Raises:
        ValueError: If character not found, segment not found, or segment not completed
        RuntimeError: If database operations fail
    """

    # Verify character ownership
    # TODO - Read Player Record instead.
    character: dict = character_get(character_id, player_id)

    # Get the completed segment
    active_segment = get_completed_segment_for_character(character_id, player_id, segment_id)
    active_segment_id = active_segment.get("ActiveSegmentID")
    segment_type = active_segment.get("SegmentType")
    story_id = active_segment.get("StoryID")

    # Get segment definition from Segments table
    segment = get_story_segment(story_id, segment_id)  # type: ignore

    # Build outcome data based on segment type
    outcome_data = {
        "SegmentType": segment_type,
        "Status": "completed",  # We already verified it's completed
    }

    if segment_type == "decision":
        # For decision segments, return the decision made
        decision = active_segment.get("Decision")
        decision_options = segment.get("DecisionOptions", {})

        outcome_data["Decision"] = decision
        outcome_data["NextSegmentID"] = decision_options.get(decision) if decision else None
        # Decision segments don't have narrative/effects in the response
        outcome_data["Outcome"] = "normal"
        outcome_data["Narrative"] = ""
        outcome_data["Effects"] = {}

    elif segment_type == "mechanical":
        # Get the outcome from the active segment
        outcome = active_segment.get("Outcome", "normal")

        # Validate and extract outcome results
        validated_result = validate_segment_outcome_results(segment, outcome)

        outcome_data["Outcome"] = outcome
        outcome_data["Narrative"] = validated_result["narrative"]
        outcome_data["Effects"] = validated_result["effects"]

        # Add challenge results for mechanical segments
        outcome_data["ChallengeResults"] = active_segment.get("ChallengeResults", [])
        # Add combat state if present
        if active_segment.get("CombatState"):
            outcome_data["CombatState"] = active_segment.get("CombatState", {})

        # Get next segment for non-terminal outcomes
        if outcome not in ["death", "failure"]:
            outcome_data["NextSegmentID"] = segment.get("NextSegmentID")

    elif segment_type == "rest":
        # Rest segments have simple completion
        outcome_data["Outcome"] = "normal"
        outcome_data["Narrative"] = "You have rested and recovered."
        outcome_data["Effects"] = {}
        outcome_data["NextSegmentID"] = segment.get("NextSegmentID")

    else:
        # Unknown segment type
        logger.warning(f"Unknown segment type: {segment_type}")
        outcome_data["Outcome"] = "normal"
        outcome_data["Narrative"] = ""
        outcome_data["Effects"] = {}

    logger.info(
        "Segment outcome retrieved successfully",
        extra={
            "active_segment_id": active_segment_id,
            "segment_type": segment_type,
            "outcome": outcome_data.get("Outcome"),
        },
    )

    return outcome_data


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to get the outcome of a completed segment.

    Query Parameters:
        characterId: Character UUID
        segmentId: Segment UUID

    Returns:
        200: Outcome data with narrative and effects
        404: Character or segment not found
        400: Invalid parameters
        401: Unauthorized
        409: Segment not yet completed
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
        if not validate_player(player_id):
            logger.error("Player not found in database", extra={"player_id": player_id}, exc_info=True)
            return lambda_response(401, {"Error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error("Failed to validate player", extra={"error": str(err)}, exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)

    # Get parameters from query (flexible: PascalCase or camelCase)
    character_id = get_query_parameter_flexible(event, "CharacterID", "characterId")
    if not character_id:
        return lambda_response(400, {"Error": "Missing CharacterID parameter"}, event)

    segment_id = get_query_parameter_flexible(event, "SegmentID", "segmentId")
    if not segment_id:
        return lambda_response(400, {"Error": "Missing SegmentID parameter"}, event)

    # Call business logic
    try:
        outcome_data = get_segment_outcome_business_logic(character_id, segment_id, player_id)  # type: ignore

        # Build response per API documentation with PascalCase
        response_data = {
            "Outcome": outcome_data.get("Outcome", "normal"),
            "Narrative": outcome_data.get("Narrative", ""),
            "Effects": outcome_data.get("Effects", {}),
        }

        # Add optional fields based on what's available
        if "NextSegmentID" in outcome_data:
            response_data["NextSegmentID"] = outcome_data["NextSegmentID"]

        if "Decision" in outcome_data:
            response_data["Decision"] = outcome_data["Decision"]

        if "ChallengeResults" in outcome_data:
            response_data["ChallengeResults"] = outcome_data["ChallengeResults"]

        if "CombatState" in outcome_data:
            response_data["CombatState"] = outcome_data["CombatState"]

        logger.info("Lambda response", extra={"status_code": 200})
        return lambda_response(200, response_data, event)

    except ValueError as err:
        logger.warning(
            "Invalid request",
            extra={"character_id": character_id, "segment_id": segment_id, "error": str(err)},
        )
        error_msg = str(err)
        if "not found" in error_msg.lower():
            return lambda_response(
                404,
                {"Error": error_msg},
                event,
            )
        elif "not yet completed" in error_msg.lower():
            return lambda_response(
                409,
                {"Error": error_msg},
                event,
            )
        return lambda_response(
            400,
            {"Error": error_msg},
            event,
        )
    except RuntimeError as err:
        logger.error(
            "Failed to get segment outcome",
            extra={"character_id": character_id, "segment_id": segment_id, "error": str(err)},
            exc_info=True,
        )
        return lambda_response(
            500,
            {"Error": "Internal server error"},
            event,
        )

    except Exception as err:
        return lambda_error(event, err)
