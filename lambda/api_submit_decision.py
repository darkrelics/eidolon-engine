"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason Robinson

Lambda function to submit a decision for a story segment.
Updates the active segment with the player's choice and returns the next segment.
"""

from eidolon.cors import cors_handler
from eidolon.dynamo import dynamo
from eidolon.dynamo import TableName
from eidolon.logger import get_logger
from eidolon.requests import extract_player_id
from eidolon.requests import get_required_field
from eidolon.requests import parse_json_body
from eidolon.responses import create_response
from eidolon.responses import error_response
from eidolon.responses import not_found_response
from eidolon.validation import validate_uuid

# Configure logging
logger = get_logger(__name__)


def get_active_segment_for_character(character_id: str, player_id: str) -> dict:
    """
    Get active segment for a character and verify ownership.

    Args:
        character_id: Character UUID
        player_id: Cognito user ID for ownership verification

    Returns:
        Active segment data or None if not found or not owned by player
    """
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
    if not items:
        logger.warning(
            "No active decision segment found", extra={"character_id": character_id}
        )
        return {}

    active_segment = items[0]

    if not active_segment:
        logger.warning("Active segment not found", extra={"character_id": character_id})
        return {}

    # Verify ownership
    if active_segment.get("PlayerID") != player_id:
        logger.warning(
            "Active segment ownership mismatch",
            extra={
                "active_segment_id": active_segment.get("ActiveSegmentID"),
                "player_id": player_id,
            },
        )
        return {}

    # Verify it's still active
    if active_segment.get("Status") != "active":
        logger.warning(
            "Segment not active",
            extra={
                "active_segment_id": active_segment.get("ActiveSegmentID"),
                "status": active_segment.get("Status"),
            },
        )
        return {}

    # Verify it's a decision segment
    if active_segment.get("SegmentType") != "decision":
        logger.warning(
            "Not a decision segment",
            extra={
                "active_segment_id": active_segment.get("ActiveSegmentID"),
                "type": active_segment.get("SegmentType"),
            },
        )
        return {}

    return active_segment


def validate_decision(active_segment: dict, decision_id: str) -> bool:
    """
    Validate that the decision is valid for this segment.

    Args:
        active_segment: Active segment data
        decision_id: Decision ID submitted by player

    Returns:
        True if valid, False otherwise
    """
    decision_options = active_segment.get("DecisionOptions", {})
    return decision_id in decision_options


def update_active_segment_decision(active_segment_id: str, decision_id: str) -> dict:
    """
    Update the active segment with the player's decision.

    Args:
        active_segment_id: Active segment UUID
        decision_id: Decision ID chosen by player

    Returns:
        Updated active segment data
    """
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


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to submit a decision for a story segment.

    Args:
        event: API Gateway Lambda proxy event
        context: Lambda context

    Returns:
        API Gateway Lambda proxy response
    """
    # Log Lambda invocation
    if hasattr(context, "aws_request_id"):
        logger.info(
            "Lambda invocation",
            extra={
                "request_id": context.aws_request_id,  # type: ignore
                "function_name": getattr(context, "function_name", "unknown"),
                "http_method": event.get("httpMethod"),
                "path": event.get("path"),
            },
        )

    # Handle preflight requests
    if event.get("httpMethod") == "OPTIONS":
        return cors_handler.handle_preflight(event)

    try:
        # Extract player ID from authorizer
        player_id, auth_error = extract_player_id(event)
        if auth_error:
            logger.error("Authentication failed", extra={"error": auth_error})
            return cors_handler.add_cors_headers(
                error_response(auth_error, status_code=401), event
            )

        logger.info("Player authenticated", extra={"player_id": player_id})

        # Parse request body
        body, parse_error = parse_json_body(event)
        if parse_error:
            return cors_handler.add_cors_headers(parse_error, event)

        # Get required fields
        character_id, char_error = get_required_field(body, "characterId")
        if char_error:
            return cors_handler.add_cors_headers(
                error_response(char_error, status_code=400), event
            )

        decision_id, decision_error = get_required_field(body, "decision")
        if decision_error:
            return cors_handler.add_cors_headers(
                error_response(decision_error, status_code=400), event
            )

        # Validate UUIDs
        if character_id and not validate_uuid(character_id):
            return cors_handler.add_cors_headers(
                error_response("Invalid character ID format", status_code=400), event
            )

        logger.info(
            "Submitting decision",
            extra={"character_id": character_id, "decision": decision_id},
        )

        # Get active segment for character and verify ownership
        active_segment = get_active_segment_for_character(character_id, player_id)  # type: ignore
        if not active_segment:
            return cors_handler.add_cors_headers(
                not_found_response("Active segment"), event
            )

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
            return cors_handler.add_cors_headers(
                error_response("Decision already submitted", status_code=409), event
            )

        # Validate decision is valid for this segment
        if not validate_decision(active_segment, decision_id):  # type: ignore
            logger.warning(
                "Invalid decision for segment",
                extra={
                    "active_segment_id": active_segment_id,
                    "decision_id": decision_id,
                },
            )
            return cors_handler.add_cors_headers(
                error_response("Invalid decision option", status_code=400), event
            )

        # Update active segment with decision
        update_active_segment_decision(active_segment_id, decision_id)  # type: ignore

        # Get next segment ID based on decision
        next_segment_id = get_next_segment_id(active_segment, decision_id)  # type: ignore

        # Build response per documentation
        response_data = {
            "accepted": True,
            "nextSegmentTime": None,
        }

        if next_segment_id:
            # Calculate next segment completion time
            story_id = active_segment.get("StoryID")
            next_segment = dynamo.get_item(
                TableName.SEGMENTS, {"StoryID": story_id, "SegmentID": next_segment_id}
            )

            if next_segment:
                # Next segment will start after processing completes
                # Add segment duration to get completion time
                duration = int(next_segment.get("SegmentDuration", 300))
                import time

                response_data["nextSegmentTime"] = int(time.time()) + duration

        # Remove nextSegmentTime if not set
        if response_data["nextSegmentTime"] is None:
            del response_data["nextSegmentTime"]

        logger.info(
            "Decision submitted successfully",
            extra={
                "status_code": 200,
                "active_segment_id": active_segment_id,
                "decision_id": decision_id,
                "next_segment_id": next_segment_id,
            },
        )

        return cors_handler.add_cors_headers(create_response(200, response_data), event)

    except Exception as err:
        logger.error(
            "Unexpected error in lambda_handler",
            extra={"error": str(err)},
            exc_info=True,
        )
        logger.info("Lambda response", extra={"status_code": 500})
        return cors_handler.add_cors_headers(
            error_response("Internal server error", status_code=500), event
        )
