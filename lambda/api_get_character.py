"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to get a character for the incremental game.
Returns the full character data including active segments if any.
"""

from botocore.exceptions import ClientError

from eidolon.character import get_character_with_ownership
from eidolon.dynamo import decimal_to_float
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

# Configure logging
logger = get_logger(__name__)


def get_character_business_logic(character_id: str, player_id: str) -> dict:
    """
    Business logic for getting character data.

    Args:
        character_id: Character UUID from query parameter
        player_id: Authenticated player ID

    Returns:
        Response data dict

    Raises:
        ValueError: If character ID invalid or character not found
        RuntimeError: If database operations fail
    """
    # Validate character ID format
    if not character_id:
        raise ValueError("Missing required parameter: characterId")

    if not validate_uuid(character_id):
        raise ValueError("Invalid character ID format")

    # Get character with ownership check (raises exceptions if not found)
    character = get_character_with_ownership(character_id, player_id)

    # Check for active segments
    active_segment = None
    try:
        active_segments = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="CharacterID-index",
            KeyConditionExpression="CharacterID = :cid",
            FilterExpression="PlayerID = :pid AND #status = :status",
            ExpressionAttributeValues={":cid": character_id, ":pid": player_id, ":status": "active"},
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
    except ClientError as err:
        logger.error(
            "Error querying active segments",
            extra={
                "error": str(err),
                "character_id": character_id,
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
        )
        # Continue without active segment data - not critical for response

    # Build response data
    response_data = {"character": decimal_to_float(character)}

    # Add active segment if found
    if active_segment:
        response_data["activeSegment"] = decimal_to_float(active_segment)

    return response_data


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
        character_id, param_error = get_query_parameter(event, "characterId", required=True)  # type: ignore
        if param_error:
            return build_lambda_response(400, {"error": param_error}, event)

        # Call business logic
        try:
            response_data = get_character_business_logic(character_id, player_id)
            # Return success response
            return build_lambda_response(200, response_data, event)
        except ValueError as err:
            logger.warning(
                "Character not found or invalid request",
                extra={"character_id": character_id, "error": str(err)},
            )
            if "not found" in str(err).lower():
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
                "Failed to get character",
                extra={"character_id": character_id, "error": str(err)},
            )
            return build_lambda_response(
                500,
                {"error": "Failed to retrieve character data"},
                event,
            )

    except Exception as err:
        return handle_lambda_error(err, context, event)
