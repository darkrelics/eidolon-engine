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
"""

import time

from eidolon.cors import cors_handler
from eidolon.dynamo import TableName, dynamo
from eidolon.logger import get_logger
from eidolon.requests import extract_player_id, get_query_parameter
from eidolon.responses import create_response, error_response, not_found_response
from eidolon.validation import validate_uuid

logger = get_logger(__name__)


def lambda_handler(event: dict, context: object) -> dict:
    """Get current active story and segment for a character.

    Lambda function to get the current active story segment for a character.
    This function retrieves the current active segment if a character is in a story,
    along with relevant story metadata and segment details.

    Query Parameters:
        characterId: Character ID to check

    Returns:
        200: Current story and segment data
        404: No active story
        400: Missing parameters
        401: Unauthorized
        500: Internal error
    """
    logger.info(
        "Lambda invoked",
        extra={
            "request_id": getattr(context, "aws_request_id", "unknown"),
            "function_name": getattr(context, "function_name", "unknown"),
            "http_method": event.get("httpMethod"),
            "path": event.get("path"),
            "query_params": event.get("queryStringParameters"),
        },
    )

    # Handle preflight requests
    if event.get("httpMethod") == "OPTIONS":
        return cors_handler.handle_preflight(event)

    # Validate authentication
    player_id, error = extract_player_id(event)
    if error:
        logger.warning("Auth failed", extra={"error": error})
        return cors_handler.add_cors_headers(error_response(error, status_code=401), event)

    # Get parameters
    character_id, error = get_query_parameter(event, "characterId", required=True)
    if error:
        return cors_handler.add_cors_headers(error_response(error, status_code=400), event)

    # Validate character ID format
    if not validate_uuid(character_id):
        logger.warning("Invalid character ID format", extra={"character_id": character_id})
        return cors_handler.add_cors_headers(error_response("Invalid character ID format", status_code=400), event)

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

        if not items:
            logger.info("No active story found", extra={"character_id": character_id})
            return cors_handler.add_cors_headers(not_found_response("No active story"), event)

        # Get the active segment (should only be one)
        active_segment = items[0]
        story_id = active_segment.get("StoryID")
        segment_id = active_segment.get("SegmentID")

        # Get story metadata
        story_item = dynamo.get_item(TableName.STORY, {"StoryID": story_id})
        if not story_item:
            logger.error("Story not found", extra={"story_id": story_id})
            return cors_handler.add_cors_headers(error_response("Story data missing", status_code=500), event)

        # Get the current segment from Segments table
        current_segment = dynamo.get_item(TableName.SEGMENTS, {"StoryID": story_id, "SegmentID": segment_id})
        if not current_segment:
            logger.error(
                "Segment not found",
                extra={"segment_id": segment_id, "story_id": story_id},
            )
            return cors_handler.add_cors_headers(error_response("Segment data missing", status_code=500), event)

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
                "narrative": (current_segment.get("Narrative", "") if current_segment.get("SegmentType") != "decision" else ""),
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
            response_data["segment"]["decisionText"] = current_segment.get("DecisionText", "")
            # Format options from DecisionOptions map
            decision_options = current_segment.get("DecisionOptions", {})
            options = []
            for option_id, _ in decision_options.items():
                options.append({"id": option_id, "text": option_id.replace("-", " ").title()})
            response_data["segment"]["options"] = options
            response_data["segment"]["decision"] = active_segment.get("Decision")

        # Add challenge info if this is a narrative segment
        if current_segment.get("SegmentType") == "narrative":
            response_data["segment"]["challenges"] = current_segment.get("Challenges", [])
            response_data["segment"]["challengeResults"] = active_segment.get("ChallengeResults", [])
            response_data["segment"]["outcome"] = active_segment.get("Outcome")

        # Add combat info if this is a combat segment
        if current_segment.get("SegmentType") == "combat":
            response_data["segment"]["combat"] = current_segment.get("Combat", {})
            response_data["segment"]["combatState"] = active_segment.get("CombatState", {})

        logger.info(
            "Current story retrieved successfully",
            extra={
                "status_code": 200,
                "character_id": character_id,
                "story_id": story_id,
                "segment_type": current_segment.get("SegmentType"),
                "segment_id": active_segment.get("SegmentID"),
            },
        )
        return cors_handler.add_cors_headers(create_response(200, response_data), event)

    except Exception as err:
        logger.error("Failed to get current story", extra={"error": str(err)}, exc_info=True)
        logger.info("Lambda response", extra={"status_code": 500})
        return cors_handler.add_cors_headers(error_response("Internal server error", status_code=500), event)
