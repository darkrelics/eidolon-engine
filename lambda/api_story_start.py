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
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import validate_player
from eidolon.polling import ensure_polling_enabled
from eidolon.requests import parse_event_body
from eidolon.responses import lambda_error, lambda_response
from eidolon.segment_response import new_segment_response
from eidolon.sqs import queue_segment_for_processing
from eidolon.story_active import story_update_character
from eidolon.story_history import create_story_history_entry
from eidolon.story_retrieval import get_story_and_first_segment
from eidolon.story_segment import create_active_segment
from eidolon.story_validation import story_eligability, validate_story_available
from eidolon.validation import validate_uuid


def start_story(character_id: str, story_id: str, player_id: str) -> dict:
    """
    Business logic for starting a story - orchestrates the complete process.

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
    logger.debug(f"start_story called - char: {character_id}, story: {story_id}, player: {player_id}")

    # Get character and verify ownership
    logger.debug(f"Getting character {character_id} for player {player_id}")
    character = character_get(character_id, player_id)
    logger.debug(f"Character retrieved: {character.get('CharacterName', 'unknown')}, Mode: {character.get('GameMode', 'None')}")

    # Check if character can start a story
    if not story_eligability(character):
        game_mode = character.get("GameMode", "None")
        logger.warning(f"Character {character_id} in {game_mode} mode, cannot start new story")
        raise ValueError(f"Character is currently in {game_mode} mode with an active story")

    # Validate story is available
    logger.debug(f"Validating story {story_id} is available for character")
    validate_story_available(character, story_id)

    # Get story and first segment
    logger.debug(f"Getting story {story_id} and first segment")
    story, first_segment = get_story_and_first_segment(story_id)
    logger.debug(f"Story: {story.get('Title', 'Unknown')}, First segment: {first_segment.get('SegmentID', 'unknown')}")

    # Create story instance
    logger.info(f"Creating story history entry for '{story.get('Title', 'Unknown Story')}'")
    story_instance_id = create_story_history_entry(character_id, story_id, story)

    # Create initial segment
    logger.info(f"Creating active segment for story")
    active_segment = create_active_segment(character_id, player_id, story_id, first_segment, story_instance_id)
    logger.info(f"Active segment created: {active_segment.get('ActiveSegmentID', 'unknown')}")

    # Update character state
    active_segment_id = active_segment.get("ActiveSegmentID")
    if not active_segment_id:
        raise RuntimeError("Active segment creation failed - no ActiveSegmentID")

    try:
        response = story_update_character(character_id, story_id, active_segment_id)
        logger.debug(f"Character state updated successfully, response metadata: {response.get('ResponseMetadata', {})}")
    except (ValueError, RuntimeError) as err:
        # Let ops_segment_poller handle cleanup of orphaned segments
        logger.error(f"Failed to update character state, segment {active_segment_id} will be cleaned up by poller: {err}")
        raise

    # Queue mechanical segments
    if first_segment.get("SegmentType") == "mechanical":
        queue_segment_for_processing(active_segment_id)

    # Enable polling
    ensure_polling_enabled()

    logger.info(f"Story started successfully for {character_id}")

    # Format response
    return new_segment_response(active_segment, first_segment)


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
        body = parse_event_body(event)
        logger.debug(f"Parsed body: {body}")
        character_id: str = body.get("CharacterID", "")  # type: ignore
        story_id: str = body.get("StoryID", "")  # type: ignore
        logger.info(f"Request parameters - CharacterID: {character_id}, StoryID: {story_id}")

    except ValueError as err:
        logger.error(f"Failed to parse request body Error: {err}", exc_info=True)
        return lambda_response(400, {"Error": "Improper request body"}, event)
    except Exception as err:
        logger.error(f"Unexpected error occurred: {err}", exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)

    # Validate required parameters
    if not character_id:
        logger.error("Missing required parameter: CharacterID")
        return lambda_response(400, {"Error": "CharacterID is required"}, event)

    if not story_id:
        logger.error("Missing required parameter: StoryID")
        return lambda_response(400, {"Error": "StoryID is required"}, event)

    # Validate UUIDs
    if not validate_uuid(character_id):  # type: ignore
        logger.error(f"Invalid character ID format: {character_id}")
        return lambda_response(400, {"Error": "Invalid character ID format"}, event)

    if not validate_uuid(story_id):  # type: ignore
        logger.error(f"Invalid story ID format: {story_id}")
        return lambda_response(400, {"Error": "Invalid story ID format"}, event)

    logger.info(f"Starting story {story_id} for character {character_id} owned by {player_id}")

    # Call business logic
    try:
        response_data = start_story(character_id, story_id, player_id)  # type: ignore
        logger.info(f"Story started successfully for {character_id}")
        return lambda_response(200, response_data, event)
    except ValueError as err:
        error_msg = str(err)
        logger.warning(f"Invalid request for character={character_id}, story={story_id}: {error_msg}")
        if "not found" in error_msg.lower():
            return lambda_response(404, {"Error": error_msg}, event)
        elif "already in" in error_msg.lower() and "mode" in error_msg.lower():
            return lambda_response(409, {"Error": error_msg}, event)
        elif "not available" in error_msg.lower():
            return lambda_response(403, {"Error": error_msg}, event)
        return lambda_response(400, {"Error": error_msg}, event)
    except RuntimeError as err:
        logger.error(
            f"Runtime error starting story={story_id} for character={character_id}: {err}",
            exc_info=True,
        )
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)
