"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to start a story for a character.
Validates character state, creates active segment, and returns first segment details.
"""

from eidolon.cors import cors_handler
from eidolon.environment import SEGMENT_QUEUE_URL
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import extract_player_id, validate_player
from eidolon.polling import ensure_polling_enabled
from eidolon.responses import lambda_error, lambda_response
from eidolon.sqs import send_message
from eidolon.story import start_story_for_character
from eidolon.validation import validate_uuid


def format_start_story_response(active_segment: dict, segment: dict) -> dict:
    """
    Format response per API documentation.

    Args:
        active_segment: Active segment record from database
        segment: Segment definition from Segments table

    Returns:
        Dict with success and segment data
    """
    return {
        "Success": True,
        "Segment": {
            "ActiveSegmentID": active_segment.get("ActiveSegmentID", ""),
            "SegmentType": segment.get("SegmentType", "mechanical"),
            "StartTime": active_segment.get("StartTime", 0),
            "EndTime": active_segment.get("EndTime", 0),
            "ShortStatus": segment.get("ShortStatus", "Starting your adventure..."),
            "Duration": active_segment.get("EndTime", 0) - active_segment.get("StartTime", 0),
        },
    }


def queue_mechanical_segment_for_processing(active_segment: dict) -> None:
    """
    Queue mechanical segment to SQS for processing.

    Args:
        active_segment: Active segment record containing segment details
    """
    if not SEGMENT_QUEUE_URL:
        logger.warning("SEGMENT_QUEUE_URL not configured")
        return

    message_body = {
        "ActiveSegmentID": active_segment.get("ActiveSegmentID", ""),
        "CharacterID": active_segment.get("CharacterID", ""),
        "StoryID": active_segment.get("StoryID", ""),
        "SegmentID": active_segment.get("SegmentID", ""),
        "SegmentType": "mechanical",
    }

    try:
        send_message(SEGMENT_QUEUE_URL, message_body)
        logger.info(
            "Queued mechanical segment for processing", extra={"active_segment_id": active_segment.get("ActiveSegmentID", "")}
        )
    except RuntimeError as err:
        # Non-critical failure - log but don't block story start
        logger.warning(
            "Failed to queue segment for processing",
            extra={"active_segment_id": active_segment.get("ActiveSegmentID", ""), "error": str(err)},
        )


def start_story_business_logic(character_id: str, story_id: str, player_id: str) -> dict:
    """
    Business logic for starting a story.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        player_id: Authenticated player ID

    Returns:
        Dict with success and segment data

    Raises:
        ValueError: If validation fails
        RuntimeError: If critical operations fail
    """
    # Start the story (critical - can raise)
    result = start_story_for_character(character_id, story_id, player_id)

    active_segment = result.get("active_segment", {})
    segment = result.get("segment", {})

    # Queue mechanical segments (non-critical)
    if segment.get("SegmentType") == "mechanical":
        queue_mechanical_segment_for_processing(active_segment)

    # Enable polling (non-critical)
    ensure_polling_enabled()

    # Format response
    return format_start_story_response(active_segment, segment)


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to start a story for a character.

    Validates character ownership and game mode, then creates an active
    segment for the story. Queues mechanical segments for processing and
    enables the polling system if needed.

    Args:
        event: API Gateway Lambda proxy event containing:
            - httpMethod: POST
            - body: JSON with CharacterID and StoryID
            - requestContext.authorizer.claims.sub: Player ID from JWT
        context: Lambda context with request ID and function name

    Returns:
        API Gateway Lambda proxy response with:
            - 200: Success with segment details
            - 400: Invalid request parameters
            - 401: Unauthorized (no JWT or invalid player)
            - 403: Story not available to character
            - 404: Character or story not found
            - 409: Character already in a game mode
            - 500: Internal server error
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
            logger.error("Player not found in database", extra={"player_id": player_id})
            return lambda_response(401, {"Error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error("Failed to validate player", extra={"error": str(err)}, exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)

    # Parse request body with flexible field names
    try:
        body: dict = event.get("body", {})
        character_id: str = body.get("character_id") or body.get("CharacterID")  # type: ignore
        story_id: str = body.get("story_id") or body.get("StoryID")  # type: ignore

    except ValueError as err:
        return lambda_response(400, {"Error": str(err)}, event)
    except Exception as err:
        return lambda_error(event, err)

    # Validate UUIDs
    if character_id and not validate_uuid(character_id):  # type: ignore
        return lambda_response(400, {"Error": "Invalid character ID format"}, event)

    if story_id and not validate_uuid(story_id):  # type: ignore
        return lambda_response(400, {"Error": "Invalid story ID format"}, event)

    logger.info(
        "Starting story",
        extra={"character_id": character_id, "story_id": story_id},
    )

    # Call business logic
    try:
        response_data = start_story_business_logic(character_id, story_id, player_id)  # type: ignore
        logger.info("Lambda response", extra={"status_code": 200})
        return lambda_response(200, response_data, event)
    except ValueError as err:
        logger.warning(
            "Invalid request",
            extra={"character_id": character_id, "story_id": story_id, "error": str(err)},
        )
        error_msg = str(err)
        if "not found" in error_msg.lower():
            return lambda_response(404, {"Error": error_msg}, event)
        elif "already in" in error_msg.lower() and "mode" in error_msg.lower():
            return lambda_response(409, {"Error": error_msg}, event)
        elif "not available" in error_msg.lower():
            return lambda_response(403, {"Error": error_msg}, event)
        return lambda_response(400, {"Error": error_msg}, event)
    except RuntimeError as err:
        logger.error(
            "Failed to start story",
            extra={"character_id": character_id, "story_id": story_id, "error": str(err)},
            exc_info=True,
        )
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)
