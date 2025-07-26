"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to submit a decision for a story segment.
Updates the active segment with the player's choice and returns the next segment.
"""

import time

from botocore.exceptions import ClientError

from eidolon.character import get_character
from eidolon.character import validate_character_ownership
from eidolon.dynamo import dynamo
from eidolon.dynamo import TableName
from eidolon.logger import get_logger
from eidolon.requests import get_required_field
from eidolon.requests import parse_json_body
from eidolon.utilities import build_lambda_response
from eidolon.player import extract_player_id_from_event
from eidolon.player import validate_player_exists
from eidolon.utilities import handle_lambda_error
from eidolon.utilities import handle_preflight_if_options
from eidolon.utilities import log_lambda_invocation
from eidolon.validation import validate_uuid

# Configure logging
logger = get_logger(__name__)


def get_active_decision_segment(character_id: str, player_id: str) -> dict:
    """
    Get active decision segment for a character and verify ownership.

    Args:
        character_id: Character UUID
        player_id: Cognito user ID for ownership verification

    Returns:
        Active segment data

    Raises:
        ValueError: If no active decision segment found or validation fails
        RuntimeError: If database query fails
    """
    try:
        # Query by CharacterID to find active segment
        items = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="CharacterID-index",
            KeyConditionExpression="CharacterID = :cid",
            FilterExpression="PlayerID = :pid AND #status = :status AND SegmentType = :type",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={
                ":cid": character_id,
                ":pid": player_id,
                ":status": "active",
                ":type": "decision",
            },
        )
    except ClientError as err:
        logger.error(
            "Failed to query active segments",
            extra={
                "error": str(err),
                "character_id": character_id,
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to query active segments: {str(err)}")

    if not items:
        logger.warning("No active decision segment found", extra={"character_id": character_id})
        raise ValueError("No active decision segment found")

    active_segment = items[0]

    # Verify ownership (should already be verified by query)
    if active_segment.get("PlayerID") != player_id:
        logger.warning(
            "Active segment ownership mismatch",
            extra={
                "active_segment_id": active_segment.get("ActiveSegmentID"),
                "player_id": player_id,
            },
        )
        raise ValueError("Active segment not found")

    # Verify it's still active (should already be verified by query)
    if active_segment.get("Status") != "active":
        logger.warning(
            "Segment not active",
            extra={
                "active_segment_id": active_segment.get("ActiveSegmentID"),
                "status": active_segment.get("Status"),
            },
        )
        raise ValueError("Segment not active")

    # Verify it's a decision segment (should already be verified by query)
    if active_segment.get("SegmentType") != "decision":
        logger.warning(
            "Not a decision segment",
            extra={
                "active_segment_id": active_segment.get("ActiveSegmentID"),
                "type": active_segment.get("SegmentType"),
            },
        )
        raise ValueError("Not a decision segment")

    return active_segment


def validate_decision(active_segment: dict, decision_id: str) -> None:
    """
    Validate that the decision is valid for this segment.

    Args:
        active_segment: Active segment data
        decision_id: Decision ID submitted by player

    Raises:
        ValueError: If decision is not valid for this segment
    """
    decision_options = active_segment.get("DecisionOptions", {})
    if decision_id not in decision_options:
        raise ValueError("Invalid decision option")


def update_active_segment_decision(active_segment_id: str, decision_id: str) -> dict:
    """
    Update the active segment with the player's decision.

    Args:
        active_segment_id: Active segment UUID
        decision_id: Decision ID chosen by player

    Returns:
        Updated active segment data

    Raises:
        RuntimeError: If database update fails
    """
    try:
        # Update the decision field
        dynamo.update_item(
            TableName.ACTIVE_SEGMENTS,
            Key={"ActiveSegmentID": active_segment_id},
            UpdateExpression="SET #decision = :decision, #status = :status",
            ExpressionAttributeNames={"#decision": "Decision", "#status": "Status"},
            ExpressionAttributeValues={":decision": decision_id, ":status": "completed"},
        )

        # Get updated item
        return dynamo.get_item(TableName.ACTIVE_SEGMENTS, {"ActiveSegmentID": active_segment_id})  # type: ignore
    except ClientError as err:
        logger.error(
            "Failed to update active segment",
            extra={
                "active_segment_id": active_segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to update active segment: {str(err)}")


def get_next_segment_id(active_segment: dict, decision_id: str) -> str:
    """
    Get the next segment ID based on the decision.

    Args:
        active_segment: Active segment data
        decision_id: Decision ID chosen by player

    Returns:
        Next segment ID or None
    """
    decision_options = active_segment.get("DecisionOptions", {})
    return decision_options.get(decision_id)


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
    # Validate character ID format
    if not validate_uuid(character_id):
        raise ValueError("Invalid character ID format")

    # Verify character ownership
    character = get_character(character_id)
    validate_character_ownership(character, player_id)

    logger.info(
        "Submitting decision",
        extra={"character_id": character_id, "decision": decision_id},
    )

    # Get active segment for character and verify ownership
    active_segment = get_active_decision_segment(character_id, player_id)
    active_segment_id = active_segment.get("ActiveSegmentID")

    # Check if decision was already made
    if active_segment.get("Decision"):
        logger.warning(
            "Decision already submitted",
            extra={
                "active_segment_id": active_segment_id,
                "existing_decision": active_segment.get("Decision"),
            },
        )
        raise ValueError("Decision already submitted")

    # Validate decision is valid for this segment
    validate_decision(active_segment, decision_id)

    # Update active segment with decision
    update_active_segment_decision(active_segment_id, decision_id)  # type: ignore

    # Get next segment ID based on decision
    next_segment_id = get_next_segment_id(active_segment, decision_id)

    # Build response per documentation
    response_data: dict = {
        "accepted": True,
    }

    if next_segment_id:
        try:
            # Calculate next segment completion time
            story_id = active_segment.get("StoryID")
            next_segment = dynamo.get_item(TableName.SEGMENTS, {"StoryID": story_id, "SegmentID": next_segment_id})

            if next_segment:
                # Next segment will start after processing completes
                # Add segment duration to get completion time
                duration = int(next_segment.get("SegmentDuration", 300))
                response_data["nextSegmentTime"] = int(time.time()) + duration
        except ClientError as err:
            logger.error(
                "Failed to get next segment",
                extra={
                    "story_id": story_id,  # type: ignore
                    "segment_id": next_segment_id,
                    "error": str(err),
                },
            )
            # Continue without next segment time

    logger.info(
        "Decision submitted successfully",
        extra={
            "active_segment_id": active_segment_id,
            "decision_id": decision_id,
            "next_segment_id": next_segment_id,
        },
    )

    return response_data


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

    # Parse request body
    body, parse_error = parse_json_body(event)
    if parse_error:
        return build_lambda_response(400, {"error": str(parse_error)}, event)

    # Get required fields
    character_id, char_error = get_required_field(body, "characterId")
    if char_error:
        return build_lambda_response(400, {"error": char_error}, event)

    decision_id, decision_error = get_required_field(body, "decision")
    if decision_error:
        return build_lambda_response(400, {"error": decision_error}, event)

    # Call business logic
    try:
        response_data = submit_decision_business_logic(character_id, decision_id, player_id)
        return build_lambda_response(200, response_data, event)
    except ValueError as err:
        logger.warning(
            "Invalid request",
            extra={"character_id": character_id, "decision_id": decision_id, "error": str(err)},
        )
        error_msg = str(err)
        if "not found" in error_msg.lower():
            return build_lambda_response(404, {"error": error_msg}, event)
        elif "already submitted" in error_msg.lower():
            return build_lambda_response(409, {"error": error_msg}, event)
        return build_lambda_response(400, {"error": error_msg}, event)
    except RuntimeError as err:
        logger.error(
            "Failed to submit decision",
            extra={"character_id": character_id, "decision_id": decision_id, "error": str(err)},
        )
        return build_lambda_response(500, {"error": "Failed to submit decision"}, event)
    except Exception as err:
        return handle_lambda_error(err, context, event)
