"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to start a story for a character.
Validates character state, creates active segment, and returns first segment details.
"""

from botocore.exceptions import ClientError

from eidolon.character_data import character_get
from eidolon.cognito import extract_player_id
from eidolon.cors import cors_handler
from eidolon.dynamo import TableName, dynamo
from eidolon.environment import SEGMENT_QUEUE_URL
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import validate_player
from eidolon.polling import ensure_polling_enabled
from eidolon.responses import lambda_error, lambda_response
from eidolon.sqs import send_message
from eidolon.story import create_active_segment, create_story_history_entry, get_story_and_first_segment, validate_story_available
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
        logger.info(f"Queued mechanical segment for processing for {active_segment.get('ActiveSegmentID', '')}")
    except RuntimeError as err:
        # Non-critical failure - log but don't block story start
        logger.warning(f"Failed to queue segment for processing for {active_segment.get('ActiveSegmentID', '')} Error: {err}")


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


def start_story_for_character(character_id: str, story_id: str, player_id: str) -> dict:
    """
    Start a story for a character with atomic state updates.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        player_id: Player UUID

    Returns:
        Dict with active_segment data

    Raises:
        ValueError: If validation fails
        RuntimeError: If database operations fail
    """

    # Get character and verify ownership
    character: dict = character_get(character_id, player_id)

    # Check if character is already in a game mode
    game_mode = character.get("GameMode", "None")
    if game_mode != "None":
        logger.warning(f"Character already in game mode for {character_id}")
        raise ValueError(f"Character is currently in {game_mode} mode")

    # Validate story is available
    validate_story_available(character, story_id)

    # Get story and first segment
    story, first_segment = get_story_and_first_segment(story_id)

    # Create active segment first to get the segment ID
    story_title = story.get("Title", "Unknown Story")
    active_segment = create_active_segment(character_id, player_id, story_id, story_title, first_segment)

    # Atomically update character to set GameMode, ActiveStoryID, ActiveSegmentID and remove from available list
    try:
        # Build update expression to set GameMode and remove from AvailableStories
        available_stories = character.get("AvailableStories", [])
        if story_id in available_stories:
            story_index = available_stories.index(story_id)
            update_expression = (
                "SET GameMode = :mode, ActiveStoryID = :story_id, ActiveSegmentID = :segment_id "
                f"REMOVE AvailableStories[{story_index}]"
            )
        else:
            # Story not in list anymore (race condition), just update the mode
            update_expression = "SET GameMode = :mode, ActiveStoryID = :story_id, ActiveSegmentID = :segment_id"

        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues={
                ":mode": "Incremental",
                ":none": "None",
                ":story_id": story_id,
                ":segment_id": active_segment.get("ActiveSegmentID"),
            },
            ConditionExpression="GameMode = :none",
        )

    except ClientError as err:
        # Rollback: Delete the active segment we just created
        try:
            dynamo.delete_item(
                TableName.ACTIVE_SEGMENTS,
                Key={"ActiveSegmentID": active_segment.get("ActiveSegmentID")},
            )
        except Exception as rollback_err:
            logger.error(f"Failed to rollback active segment for {active_segment.get('ActiveSegmentID')} Error: {rollback_err}")

        if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.warning(f"Character state changed during story start for {character_id}")
            raise ValueError("Character state conflict") from err

        logger.error(f"Failed to update character state for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to update character state: {err}") from err

    # Create history entry
    story_type = story.get("StoryType", "repeatable")
    create_story_history_entry(character_id, story_id, story_title, story_type)

    logger.info(f"Story started successfully for {character_id}")

    return {"active_segment": active_segment, "segment": first_segment, "story": story}


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
        logger.error(f"Authentication failed Error: {err}", exc_info=True)
        return lambda_response(401, {"Error": "Unauthorized"}, event)
    except Exception as err:
        return lambda_error(event, err)

    # Validate player exists
    try:
        if not validate_player(player_id):
            logger.error(f"Player not found in database for {player_id}")
            return lambda_response(401, {"Error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error(f"Failed to validate player Error: {err}", exc_info=True)
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

    logger.info(f"Starting story for {character_id}")

    # Call business logic
    try:
        response_data = start_story_business_logic(character_id, story_id, player_id)  # type: ignore
        return lambda_response(200, response_data, event)
    except ValueError as err:
        logger.warning(f"Invalid request for {character_id} Error: {err}")
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
            f"Failed to start story for {character_id} Error: {err}",
            exc_info=True,
        )
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)
