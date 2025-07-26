"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson
"""

import time

from botocore.exceptions import ClientError

from eidolon.character import get_character_with_ownership
from eidolon.dynamo import dynamo
from eidolon.dynamo import TableName
from eidolon.logger import get_logger
from eidolon.requests import get_query_parameter
from eidolon.utilities import build_lambda_response
from eidolon.utilities import extract_and_validate_player_id
from eidolon.utilities import handle_lambda_error
from eidolon.utilities import handle_preflight_if_options
from eidolon.utilities import log_lambda_invocation
from eidolon.validation import validate_uuid

logger = get_logger(__name__)


def get_current_story_business_logic(character_id: str, player_id: str) -> dict:
    """
    Business logic for getting current active story and segment.

    Args:
        character_id: Character UUID
        player_id: Authenticated player ID

    Returns:
        Response data dict with story and segment information

    Raises:
        ValueError: If character not found, not owned, or no active story
        RuntimeError: If database operations fail
    """
    # Validate character ID format
    if not validate_uuid(character_id):
        raise ValueError("Invalid character ID format")

    # Verify character ownership
    get_character_with_ownership(character_id, player_id)

    try:
        # Get active segment for character using GSI query
        items = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="CharacterID-index",
            KeyConditionExpression="CharacterID = :cid",
            FilterExpression="PlayerID = :pid AND #status = :status",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={
                ":cid": character_id,
                ":pid": player_id,
                ":status": "active",
            },
        )
    except ClientError as err:
        logger.error(
            "Failed to query active segments",
            extra={
                "error": str(err),
                "character_id": character_id,
                "error_code": err.response.get("Error", {}).get("Code", "Unknown")
            },
            exc_info=True
        )
        raise RuntimeError(f"Failed to query active segments: {str(err)}")

    if not items:
        logger.info("No active story found", extra={"character_id": character_id})
        raise ValueError("No active story found")

    # Get the active segment (should only be one)
    active_segment = items[0]
    story_id = active_segment.get("StoryID")
    segment_id = active_segment.get("SegmentID")

    # Get story metadata
    try:
        story_item = dynamo.get_item(TableName.STORY, {"StoryID": story_id})
        if not story_item:
            logger.error("Story not found", extra={"story_id": story_id})
            raise RuntimeError("Story data missing")
    except ClientError as err:
        logger.error(
            "Failed to get story",
            extra={"error": str(err), "story_id": story_id},
            exc_info=True
        )
        raise RuntimeError(f"Failed to get story: {str(err)}")

    # Get the current segment from Segments table
    try:
        current_segment = dynamo.get_item(
            TableName.SEGMENTS, {"StoryID": story_id, "SegmentID": segment_id}
        )
        if not current_segment:
            logger.error(
                "Segment not found",
                extra={"segment_id": segment_id, "story_id": story_id},
            )
            raise RuntimeError("Segment data missing")
    except ClientError as err:
        logger.error(
            "Failed to get segment",
            extra={"error": str(err), "segment_id": segment_id},
            exc_info=True
        )
        raise RuntimeError(f"Failed to get segment: {str(err)}")

    total_segments = story_item.get("TotalSegments", 1)
    current_segment_index = current_segment.get("SegmentIndex", 0)

    # Calculate time remaining
    end_time = int(active_segment.get("EndTime", 0))
    current_time = int(time.time())
    time_remaining = max(0, end_time - current_time)

    # Build response
    response_data = {
        "story": {
            "storyId": story_id,
            "title": story_item.get("Title", ""),
            "type": story_item.get("StoryType", ""),
            "totalSegments": total_segments,
            "currentSegmentIndex": current_segment_index,
        },
        "segment": {
            "segmentId": segment_id,
            "segmentType": current_segment.get("SegmentType", ""),
            "shortStatus": current_segment.get("ShortStatus", ""),
            "narrative": (
                current_segment.get("Narrative", "")
                if current_segment.get("SegmentType") != "decision"
                else ""
            ),
            "duration": current_segment.get("SegmentDuration", 0),
            "timeRemaining": time_remaining,
            "startTime": active_segment.get("StartTime", 0),
            "endTime": end_time,
        },
        "activeSegmentId": active_segment.get("ActiveSegmentID", ""),
        "status": active_segment.get("Status", ""),
    }

    # Add decision options if this is a decision segment
    if current_segment.get("SegmentType") == "decision":
        response_data["segment"]["decisionText"] = current_segment.get(
            "DecisionText", ""
        )
        # Format options from DecisionOptions map
        decision_options = current_segment.get("DecisionOptions", {})
        options = []
        for option_id, _ in decision_options.items():
            options.append(
                {"id": option_id, "text": option_id.replace("-", " ").title()}
            )
        response_data["segment"]["options"] = options
        response_data["segment"]["decision"] = active_segment.get("Decision")

    # Add challenge info if this is a narrative segment
    if current_segment.get("SegmentType") == "narrative":
        response_data["segment"]["challenges"] = current_segment.get(
            "Challenges", []
        )
        response_data["segment"]["challengeResults"] = active_segment.get(
            "ChallengeResults", []
        )
        response_data["segment"]["outcome"] = active_segment.get("Outcome")

    # Add combat info if this is a combat segment
    if current_segment.get("SegmentType") == "combat":
        response_data["segment"]["combat"] = current_segment.get("Combat", {})
        response_data["segment"]["combatState"] = active_segment.get(
            "CombatState", {}
        )

    logger.info(
        "Current story retrieved successfully",
        extra={
            "character_id": character_id,
            "story_id": story_id,
            "segment_type": current_segment.get("SegmentType"),
            "segment_id": active_segment.get("SegmentID"),
        },
    )

    return response_data


def lambda_handler(event: dict, context: object) -> dict:
    """Get current active story and segment for a character.

    Lambda function to get the current active story segment for a character.
    This function retrieves the current active segment if a character is in a story,
    along with relevant story metadata and segment details.

    Query Parameters:
        characterId: Character ID to check

    Returns:
        200: Current story and segment data
        404: No active story or character not found
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
        # Extract and validate player ID
        player_id, auth_error = extract_and_validate_player_id(event)
        if auth_error:
            return auth_error

        # Get character ID from query parameters
        character_id, param_error = get_query_parameter(
            event, "characterId", required=True
        ) # type: ignore
        if param_error:
            return build_lambda_response(400, {"error": param_error}, event)

        # Call business logic
        try:
            response_data = get_current_story_business_logic(character_id, player_id)
            return build_lambda_response(200, response_data, event)
        except ValueError as err:
            logger.warning(
                "Invalid request or not found",
                extra={"character_id": character_id, "error": str(err)},
            )
            if "no active story" in str(err).lower():
                return build_lambda_response(
                    404,
                    {"error": "No active story found"},
                    event,
                )
            elif "not found" in str(err).lower():
                return build_lambda_response(
                    404,
                    {"error": "Character not found"},
                    event,
                )
            return build_lambda_response(
                400,
                {"error": str(err)},
                event,
            )
        except RuntimeError as err:
            logger.error(
                "Failed to get current story",
                extra={"character_id": character_id, "error": str(err)},
            )
            return build_lambda_response(
                500,
                {"error": "Failed to retrieve story data"},
                event,
            )

    except Exception as err:
        return handle_lambda_error(err, context, event)
