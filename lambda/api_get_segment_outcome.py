"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason Robinson

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.


Lambda function to get the outcome of a completed segment.
Returns the narrative text and any rewards/effects for the outcome.
"""

from eidolon.cors import cors_handler
from eidolon.dynamo import get_item, get_table
from eidolon.environment import ACTIVE_SEGMENTS_TABLE, SEGMENTS_TABLE
from eidolon.logger import get_logger
from eidolon.requests import extract_player_id, get_query_parameter
from eidolon.responses import create_response, error_response, not_found_response
from eidolon.validation import validate_uuid

# Configure logging
logger = get_logger(__name__)


def get_completed_segment_for_character(character_id: str, segment_id: str, player_id: str) -> object:
    """
    Get completed segment for a character and verify ownership.

    Args:
        character_id: Character UUID
        segment_id: Segment UUID
        player_id: Cognito user ID for ownership verification

    Returns:
        Active segment data or None if not found or not owned by player
    """
    active_segments_table = get_table(ACTIVE_SEGMENTS_TABLE)

    # Query by CharacterID to find the segment
    response = active_segments_table.query(
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

    items = response.get("Items", [])
    if not items:
        logger.warning(
            "Completed segment not found",
            extra={"character_id": character_id, "segment_id": segment_id},
        )
        return None

    active_segment = items[0]

    # Ownership already verified in query

    return active_segment


def get_segment_outcome(active_segment: dict) -> object:
    """
    Get the outcome details for a completed segment.

    Args:
        active_segment: Active segment data

    Returns:
        Outcome details including narrative and effects
    """
    segment_type = active_segment.get("SegmentType")
    story_id = active_segment.get("StoryID")
    segment_id = active_segment.get("SegmentID")

    # Get segment definition from Segments table
    segments_table = get_table(SEGMENTS_TABLE)
    segment = get_item(segments_table, {"StoryID": story_id, "SegmentID": segment_id})

    if not segment:
        logger.error("Segment not found", extra={"story_id": story_id, "segment_id": segment_id})
        return None

    outcome_data = {
        "segmentType": segment_type,
        "status": active_segment.get("Status", ""),
    }

    if segment_type == "decision":
        # For decision segments, return the decision made and next segment
        decision = active_segment.get("Decision")
        decision_options = segment.get("DecisionOptions", {})

        outcome_data["decision"] = decision
        outcome_data["nextSegmentId"] = decision_options.get(decision) if decision else None

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

    return outcome_data


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to get the outcome of a completed segment.

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
            return cors_handler.add_cors_headers(error_response(auth_error, status_code=401), event)

        logger.info("Player authenticated", extra={"player_id": player_id})

        # Get parameters from query
        character_id, char_error = get_query_parameter(event, "characterId", required=True)
        if char_error:
            return cors_handler.add_cors_headers(error_response(char_error, status_code=400), event)

        segment_id, seg_error = get_query_parameter(event, "segmentId", required=True)
        if seg_error:
            return cors_handler.add_cors_headers(error_response(seg_error, status_code=400), event)

        # Validate UUIDs
        if character_id and not validate_uuid(character_id):
            return cors_handler.add_cors_headers(error_response("Invalid character ID format", status_code=400), event)

        if segment_id and not validate_uuid(segment_id):
            return cors_handler.add_cors_headers(error_response("Invalid segment ID format", status_code=400), event)

        logger.info(
            "Getting segment outcome",
            extra={"character_id": character_id, "segment_id": segment_id},
        )

        # Get completed segment for character and verify ownership
        active_segment: dict = get_completed_segment_for_character(character_id, segment_id, player_id)  # type: ignore
        if not active_segment:
            return cors_handler.add_cors_headers(not_found_response("Completed segment"), event)

        active_segment_id = active_segment.get("ActiveSegmentID")

        # Check if segment is completed
        status = active_segment.get("Status")
        if status != "completed":
            logger.warning(
                "Segment not completed",
                extra={"active_segment_id": active_segment_id, "status": status},
            )
            return cors_handler.add_cors_headers(error_response("Segment not yet completed", status_code=409), event)

        # Get outcome details
        outcome_data: dict = get_segment_outcome(active_segment)  # type: ignore
        if not outcome_data:
            return cors_handler.add_cors_headers(error_response("Failed to get outcome data", status_code=500), event)

        # Build response per documentation
        response_data = {
            "outcome": outcome_data.get("outcome", "normal"),
            "narrative": outcome_data.get("narrative", ""),
            "effects": outcome_data.get("effects", {}),
        }

        logger.info(
            "Segment outcome retrieved successfully",
            extra={
                "status_code": 200,
                "active_segment_id": active_segment_id,
                "segment_type": outcome_data.get("segmentType"),
                "outcome": outcome_data.get("outcome"),
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
        return cors_handler.add_cors_headers(error_response("Internal server error", status_code=500), event)
