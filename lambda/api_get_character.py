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


Lambda function to get a character for the incremental game.
Returns the full character data including active segments if any.
"""

from eidolon.character import get_character_with_ownership
from eidolon.dynamo import TableName, dynamo, decimal_to_float
from eidolon.logger import get_logger
from eidolon.requests import get_query_parameter
from eidolon.responses import error_response, not_found_response
from eidolon.utilities import (
    build_lambda_response,
    extract_and_validate_player_id,
    handle_lambda_error,
    handle_preflight_if_options,
    log_lambda_invocation,
)
from eidolon.validation import validate_uuid

# Configure logging
logger = get_logger(__name__)


def get_character_business_logic(character_id: str, player_id: str) -> tuple:
    """
    Business logic for getting character data.

    Args:
        character_id: Character UUID from query parameter
        player_id: Authenticated player ID

    Returns:
        Tuple of (response_data, error_response)
        If successful: (data_dict, None)
        If failed: (None, error_response_dict)
    """
    # Validate character ID format
    if not character_id:
        return None, error_response("Missing required parameter: characterId", status_code=400)

    if not validate_uuid(character_id):
        return None, error_response("Invalid character ID format", status_code=400)

    # Get character with ownership check
    character, error_msg = get_character_with_ownership(character_id, player_id)
    if error_msg:
        return None, not_found_response("Character")

    # Check for active segments
    active_segment = None
    try:
        active_segments = dynamo.query_by_gsi(
            TableName.ACTIVE_SEGMENTS,
            "CharacterID-index",
            {"CharacterID": character_id},
            FilterExpression="PlayerID = :pid AND #status = :status",
            ExpressionAttributeValues={":pid": player_id, ":status": "active"},
            ExpressionAttributeNames={"#status": "Status"},
        )

        if active_segments:
            active_segment = active_segments[0]
            logger.info(
                "Active segment found for character",
                extra={
                    "character_id": character_id,
                    "segment_type": active_segment.get("SegmentType"),
                    "story_id": active_segment.get("StoryID"),
                },
            )
    except Exception as err:
        logger.error(
            "Error querying active segments",
            extra={"error": str(err), "character_id": character_id},
        )
        # Continue without active segment data

    # Build response data
    response_data = {"character": decimal_to_float(character)}

    # Add active segment if found
    if active_segment:
        response_data["activeSegment"] = decimal_to_float(active_segment)

    return response_data, None


def lambda_handler(event: dict, context: object):
    """
    Lambda handler for getting incremental character data.

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

    try:
        # Extract and validate player ID
        player_id, auth_error = extract_and_validate_player_id(event)
        if auth_error:
            return auth_error

        # Get character ID from query parameters
        character_id, param_error = get_query_parameter(event, "characterId", required=True)
        if param_error:
            return build_lambda_response(400, {"error": param_error}, event)

        # Call business logic
        response_data, error_response_obj = get_character_business_logic(character_id, player_id)

        if error_response_obj:
            return build_lambda_response(
                error_response_obj.get("statusCode", 500),
                error_response_obj.get("body", {"error": "Unknown error"}),
                event,
            )

        # Return success response
        return build_lambda_response(200, response_data, event)

    except Exception as err:
        return handle_lambda_error(err, context, event)
