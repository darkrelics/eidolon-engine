"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to get the outcome of a completed segment.
Returns the narrative text and any rewards/effects for the outcome.
"""

from eidolon.character import get_character
from eidolon.character import validate_character_ownership
from eidolon.logger import get_logger
from eidolon.player import extract_player_id_from_event
from eidolon.player import validate_player_exists
from eidolon.requests import get_query_parameter_flexible
from eidolon.story import get_completed_segment_for_character
from eidolon.story import get_story_segment
from eidolon.utilities import build_lambda_response_pascal
from eidolon.utilities import handle_lambda_error_pascal
from eidolon.utilities import handle_preflight_if_options
from eidolon.utilities import log_lambda_invocation
from eidolon.validation import validate_uuid

# Configure logging
logger = get_logger(__name__)


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
    # Validate UUID formats
    if not validate_uuid(character_id):
        raise ValueError("Invalid character ID format")

    if not validate_uuid(segment_id):
        raise ValueError("Invalid segment ID format")

    # Verify character ownership
    character = get_character(character_id)
    validate_character_ownership(character, player_id)

    # Get the completed segment
    active_segment = get_completed_segment_for_character(character_id, player_id, segment_id)
    active_segment_id = active_segment.get("ActiveSegmentID")
    segment_type = active_segment.get("SegmentType")
    story_id = active_segment.get("StoryID")

    # Get segment definition from Segments table
    segment = get_story_segment(story_id, segment_id)  # type: ignore

    # Build outcome data based on segment type
    outcome_data = {
        "segmentType": segment_type,
        "status": "completed",  # We already verified it's completed
    }

    if segment_type == "decision":
        # For decision segments, return the decision made
        decision = active_segment.get("Decision")
        decision_options = segment.get("DecisionOptions", {})

        outcome_data["decision"] = decision
        outcome_data["nextSegmentId"] = decision_options.get(decision) if decision else None
        # Decision segments don't have narrative/effects in the response
        outcome_data["outcome"] = "normal"
        outcome_data["narrative"] = ""
        outcome_data["effects"] = {}

    elif segment_type in ["narrative", "combat"]:
        # Get the outcome from the active segment
        outcome = active_segment.get("Outcome", "normal")

        # Get results from segment definition
        results = segment.get("Results", {})
        outcome_result = results.get(outcome, {})

        outcome_data["outcome"] = outcome
        outcome_data["narrative"] = outcome_result.get("narrative", "")
        outcome_data["effects"] = outcome_result.get("effects", {})

        # Add challenge results for narrative segments
        if segment_type == "narrative":
            outcome_data["challengeResults"] = active_segment.get("ChallengeResults", [])

        # Add combat state for combat segments
        if segment_type == "combat":
            outcome_data["combatState"] = active_segment.get("CombatState", {})

        # Get next segment for non-terminal outcomes
        if outcome not in ["death", "failure"]:
            outcome_data["nextSegmentId"] = segment.get("NextSegmentID")

    logger.info(
        "Segment outcome retrieved successfully",
        extra={
            "active_segment_id": active_segment_id,
            "segment_type": segment_type,
            "outcome": outcome_data.get("outcome"),
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
        return build_lambda_response_pascal(401, {"error": "Unauthorized"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)

    # Validate player exists
    try:
        if not validate_player_exists(player_id):
            logger.error("Player not found in database", extra={"player_id": player_id})
            return build_lambda_response_pascal(401, {"error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error("Failed to validate player", extra={"error": str(err)})
        return build_lambda_response_pascal(500, {"error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)

    # Get parameters from query (flexible: PascalCase or camelCase)
    character_id = get_query_parameter_flexible(event, "CharacterId", "characterId")
    if not character_id:
        return build_lambda_response_pascal(400, {"error": "Missing CharacterId parameter"}, event)

    segment_id = get_query_parameter_flexible(event, "SegmentId", "segmentId")
    if not segment_id:
        return build_lambda_response_pascal(400, {"error": "Missing SegmentId parameter"}, event)

    # Call business logic
    try:
        outcome_data = get_segment_outcome_business_logic(character_id, segment_id, player_id)  # type: ignore

        # Build response per API documentation with PascalCase
        response_data = {
            "Outcome": outcome_data.get("outcome", "normal"),
            "Narrative": outcome_data.get("narrative", ""),
            "Effects": outcome_data.get("effects", {}),
        }

        return build_lambda_response_pascal(200, response_data, event)

    except ValueError as err:
        logger.warning(
            "Invalid request",
            extra={"character_id": character_id, "segment_id": segment_id, "error": str(err)},
        )
        error_msg = str(err)
        if "not found" in error_msg.lower():
            return build_lambda_response_pascal(
                404,
                {"error": error_msg},
                event,
            )
        elif "not yet completed" in error_msg.lower():
            return build_lambda_response_pascal(
                409,
                {"error": error_msg},
                event,
            )
        return build_lambda_response_pascal(
            400,
            {"error": error_msg},
            event,
        )
    except RuntimeError as err:
        logger.error(
            "Failed to get segment outcome",
            extra={"character_id": character_id, "segment_id": segment_id, "error": str(err)},
        )
        return build_lambda_response_pascal(
            500,
            {"error": "Internal server error"},
            event,
        )

    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)
