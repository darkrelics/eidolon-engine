"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to get the outcome of a completed segment.
Returns the narrative text and any rewards/effects for the outcome.
"""

from botocore.exceptions import ClientError

from eidolon.character import get_character
from eidolon.character import validate_character_ownership
from eidolon.dynamo import dynamo
from eidolon.dynamo import TableName
from eidolon.logger import get_logger
from eidolon.requests import get_query_parameter
from eidolon.utilities import build_lambda_response
from eidolon.player import extract_player_id_from_event
from eidolon.player import validate_player_exists
from eidolon.utilities import handle_lambda_error
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

    # Query for the completed segment
    try:
        items = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="CharacterID-index",
            KeyConditionExpression="CharacterID = :cid",
            FilterExpression="PlayerID = :pid AND SegmentID = :sid AND #status = :status",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={
                ":cid": character_id,
                ":pid": player_id,
                ":sid": segment_id,
                ":status": "completed",
            },
        )
    except ClientError as err:
        logger.error(
            "Failed to query active segments",
            extra={
                "error": str(err),
                "character_id": character_id,
                "segment_id": segment_id,
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to query segments: {str(err)}")

    if not items:
        logger.warning(
            "Completed segment not found",
            extra={"character_id": character_id, "segment_id": segment_id},
        )
        raise ValueError("Completed segment not found")

    active_segment = items[0]
    active_segment_id = active_segment.get("ActiveSegmentID")

    # Double-check segment is completed
    status = active_segment.get("Status")
    if status != "completed":
        logger.warning(
            "Segment not completed",
            extra={"active_segment_id": active_segment_id, "status": status},
        )
        raise ValueError("Segment not yet completed")

    segment_type = active_segment.get("SegmentType")
    story_id = active_segment.get("StoryID")

    # Get segment definition from Segments table
    try:
        segment = dynamo.get_item(TableName.SEGMENTS, {"StoryID": story_id, "SegmentID": segment_id})
        if not segment:
            logger.error("Segment not found", extra={"story_id": story_id, "segment_id": segment_id})
            raise RuntimeError("Segment definition not found")
    except ClientError as err:
        logger.error("Failed to get segment", extra={"error": str(err), "segment_id": segment_id}, exc_info=True)
        raise RuntimeError(f"Failed to get segment: {str(err)}")

    # Build outcome data based on segment type
    outcome_data = {
        "segmentType": segment_type,
        "status": status,
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

    # Get parameters from query
    character_id, char_error = get_query_parameter(event, "characterId", required=True)  # type: ignore
    if char_error:
        return build_lambda_response(400, {"error": char_error}, event)

    segment_id, seg_error = get_query_parameter(event, "segmentId", required=True)  # type: ignore
    if seg_error:
        return build_lambda_response(400, {"error": seg_error}, event)

    # Call business logic
    try:
        outcome_data = get_segment_outcome_business_logic(character_id, segment_id, player_id)

        # Build response per API documentation
        response_data = {
            "outcome": outcome_data.get("outcome", "normal"),
            "narrative": outcome_data.get("narrative", ""),
            "effects": outcome_data.get("effects", {}),
        }

        return build_lambda_response(200, response_data, event)

    except ValueError as err:
        logger.warning(
            "Invalid request",
            extra={"character_id": character_id, "segment_id": segment_id, "error": str(err)},
        )
        error_msg = str(err)
        if "not found" in error_msg.lower():
            return build_lambda_response(
                404,
                {"error": error_msg},
                event,
            )
        elif "not yet completed" in error_msg.lower():
            return build_lambda_response(
                409,
                {"error": error_msg},
                event,
            )
        return build_lambda_response(
            400,
            {"error": error_msg},
            event,
        )
    except RuntimeError as err:
        logger.error(
            "Failed to get segment outcome",
            extra={"character_id": character_id, "segment_id": segment_id, "error": str(err)},
        )
        return build_lambda_response(
            500,
            {"error": "Failed to retrieve outcome data"},
            event,
        )

    except Exception as err:
        return handle_lambda_error(err, context, event)
