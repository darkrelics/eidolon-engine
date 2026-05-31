"""
Eidolon Engine - Incremental Game

Copyright 2024-2026 Jason E. Robinson

Lambda function to start a story for a character.
Validates character state, creates active segment, and returns first segment details.

Endpoint: POST /story/start
Authentication: Cognito (required)
"""

from uuid_extension import uuid7

from eidolon.character_data import character_get
from eidolon.constants import CharState
from eidolon.dynamo import TableName, dynamo
from eidolon.errors import ConflictError, NotFoundError
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.polling import ensure_polling_enabled
from eidolon.requests import parse_event_body
from eidolon.segment_response import new_segment_response
from eidolon.sqs import queue_segment_for_processing
from eidolon.story_active import story_update_character
from eidolon.story_completion import complete_story_for_character
from eidolon.story_history import create_story_history_entry
from eidolon.story_retrieval import get_story_and_first_segment
from eidolon.story_segment import create_active_segment
from eidolon.story_validation import story_eligibility, validate_story_available
from eidolon.validation import validate_uuid


def remove_invalid_story_from_character(character: dict, character_id: str, story_id: str) -> None:
    """Remove a story that no longer exists from a character's available stories. Non-fatal on failure.

    Args:
        character: Character data dict
        character_id: Character UUID
        story_id: Story UUID to remove
    """
    try:
        available_stories = set(character.get("AvailableStories", []))
        if story_id in available_stories:
            available_stories.remove(story_id)
            dynamo.update_item(
                TableName.CHARACTERS,
                Key={"CharacterID": character_id},
                UpdateExpression="SET AvailableStories = :stories",
                ExpressionAttributeValues={":stories": list(available_stories)},
            )
            logger.info(f"Removed invalid story {story_id} from character {character_id}")
    except Exception as err:
        logger.error(f"Failed to remove invalid story from character: {err}")


def start_story(character_id: str, story_id: str, player_id: str) -> dict:
    """
    Business logic for starting a story - orchestrates the complete process.

    Uses lock-first pattern: atomically claims the character via conditional write
    BEFORE creating any records, preventing race conditions where two concurrent
    requests both pass eligibility checks.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        player_id: Authenticated player ID

    Returns:
        Dict with segment data

    Raises:
        ValueError: If validation fails (with status code prefix)
        RuntimeError: If critical operations fail
    """
    # Get character and verify ownership
    character = character_get(character_id, player_id)

    # Check if character can start a story
    if not story_eligibility(character):
        # Check specifically for dead character
        char_state = character.get("CharState")
        if char_state == CharState.DEAD.value:
            logger.warning(f"Character {character_id} is dead, cannot start new story")
            raise ValueError("Dead characters cannot start new stories")

        # Existing game mode error handling
        game_mode = character.get("GameMode", "None")
        logger.warning(f"Character {character_id} in {game_mode} mode, cannot start new story")
        raise ConflictError(f"Character is currently in {game_mode} mode with an active story")

    # Validate story is available
    validate_story_available(character, story_id)

    # Get story and first segment - handle case where story no longer exists
    try:
        story, first_segment = get_story_and_first_segment(story_id)
    except ValueError as err:
        logger.warning(f"Story {story_id} not found in database, removing from character's available stories")
        remove_invalid_story_from_character(character, character_id, story_id)
        raise NotFoundError("Story no longer exists") from err

    # Pre-generate IDs so the atomic lock can reference them
    story_instance_id = str(uuid7())
    active_segment_id = str(uuid7())

    # LOCK FIRST: Atomically claim the character via conditional write
    # This prevents two concurrent requests from both passing eligibility
    try:
        story_update_character(character_id, story_id, active_segment_id, story_instance_id)
    except ValueError as err:
        logger.warning(f"Character {character_id} already locked by another request: {err}")
        raise ConflictError("Character is currently starting another story") from err
    except RuntimeError as err:
        logger.error(f"Failed to lock character {character_id} for story start: {err}")
        raise err

    # Character is now locked (GameMode=Incremental) - create records
    # If creation fails, roll back the character state
    try:
        # Create story instance
        create_story_history_entry(character_id, story_id, story, story_instance_id)

        # Create initial segment
        active_segment = create_active_segment(
            character_id, player_id, story_id, first_segment, story_instance_id, active_segment_id
        )
    except Exception as err:
        # Roll back character state since records couldn't be created
        logger.error(f"Failed to create story records after locking character {character_id}: {err}")
        try:
            complete_story_for_character(character_id)
            logger.info(f"Rolled back character {character_id} state after creation failure")
        except Exception as rollback_err:
            logger.error(f"Failed to roll back character {character_id} state: {rollback_err}")
        raise RuntimeError(f"Failed to create story records: {err}") from err

    # Queue mechanical segments - critical for game to work
    if first_segment.get("SegmentType") == "mechanical":
        try:
            queue_segment_for_processing(active_segment_id)
        except RuntimeError as err:
            logger.error(f"Failed to queue segment {active_segment_id}: {err}")
            raise ValueError("Unable to start story - processing queue unavailable. Please try again later.") from err

    # Enable polling
    ensure_polling_enabled()

    logger.info(f"Story started successfully for {character_id}")

    # Format response
    return new_segment_response(active_segment, first_segment)


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """
    Lambda handler to start a story for a character.

    Validates character ownership and game mode, then creates an active
    segment for the story. Queues mechanical segments for processing and
    enables the polling system if needed.

    Args:
        event: API Gateway Lambda proxy event
        context: Lambda context
        player_id: Authenticated player ID

    Returns:
        Dict with status_code and body
    """
    # Parse request body with flexible field names
    body = parse_event_body(event)
    character_id = body.get("CharacterID", "")
    story_id = body.get("StoryID", "")

    # Validate required parameters
    if not character_id:
        logger.error("Missing required parameter: CharacterID")
        raise ValueError("CharacterID is required")

    if not story_id:
        logger.error("Missing required parameter: StoryID")
        raise ValueError("StoryID is required")

    # Validate UUIDs
    if not validate_uuid(character_id):
        logger.error(f"Invalid character ID format: {character_id}")
        raise ValueError("Invalid character ID format")

    if not validate_uuid(story_id):
        logger.error(f"Invalid story ID format: {story_id}")
        raise ValueError("Invalid story ID format")

    logger.info(f"Starting story {story_id} for character {character_id} owned by {player_id}")

    # Call business logic
    response_data = start_story(character_id, story_id, player_id)
    return {"status_code": 200, "body": response_data}
