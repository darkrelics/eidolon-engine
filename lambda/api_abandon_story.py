"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to abandon an active story.
Updates character state, marks active segments as abandoned, and updates history.
"""

from eidolon.character import get_character_with_ownership
from eidolon.character import reset_character_game_mode
from eidolon.cors import cors_handler
from eidolon.logger import get_logger
from eidolon.requests import extract_player_id
from eidolon.requests import get_query_parameter
from eidolon.responses import create_response
from eidolon.responses import error_response
from eidolon.story import add_story_to_abandoned_list
from eidolon.story import get_active_story_segment
from eidolon.story import mark_segment_as_abandoned
from eidolon.story import record_story_abandonment
from eidolon.validation import validate_uuid

logger = get_logger(__name__)


def abandon_story_business_logic(character_id: str, player_id: str) -> dict:
    """
    Business logic for abandoning an active story.

    This orchestrates the story abandonment process:
    1. Verify character ownership
    2. Check if character is in a story
    3. Get active story segment
    4. Add story to abandoned list
    5. Mark segment as abandoned
    6. Record in history
    7. Reset character state

    Args:
        character_id: Character UUID
        player_id: Player ID for ownership verification

    Returns:
        Dict with response data for successful abandonment

    Raises:
        ValueError: If character not found, not owned, or not in a story
        RuntimeError: If database operations fail
    """
    character = get_character_with_ownership(character_id, player_id)

    game_mode = character.get("GameMode", "None")
    if game_mode != "Incremental":
        logger.warning(
            "Character not in Incremental mode",
            extra={"character_id": character_id, "game_mode": game_mode},
        )
        raise ValueError("Character not in a story")

    active_segment = get_active_story_segment(character_id)
    active_segment_id = active_segment.get("ActiveSegmentID")
    story_id = active_segment.get("StoryID")
    story_title = active_segment.get("StoryTitle", "Unknown Story")

    try:
        add_story_to_abandoned_list(character_id, story_id) # type: ignore
    except (ValueError, RuntimeError) as err:
        logger.error(
            "Failed to add story to abandoned list but continuing",
            extra={"character_id": character_id, "story_id": story_id, "error": str(err)},
        )

    try:
        mark_segment_as_abandoned(active_segment_id) # type: ignore
    except (ValueError, RuntimeError) as err:
        logger.error(
            "Failed to mark segment as abandoned but continuing",
            extra={"active_segment_id": active_segment_id, "error": str(err)},
        )

    try:
        record_story_abandonment(character_id, story_id) # type: ignore
    except (ValueError, RuntimeError) as err:
        logger.error(
            "Failed to update history but continuing",
            extra={"character_id": character_id, "story_id": story_id, "error": str(err)},
        )

    reset_character_game_mode(character_id)
    response_data = {
        "characterId": character_id,
        "storyId": story_id,
        "storyTitle": story_title,
        "abandoned": True,
        "message": "Story abandoned successfully",
    }

    logger.info(
        "Story abandoned successfully",
        extra={
            "character_id": character_id,
            "story_id": story_id,
            "active_segment_id": active_segment_id,
        },
    )

    return response_data


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to abandon an active story.

    Args:
        event: API Gateway Lambda proxy event
        context: Lambda context

    Returns:
        API Gateway Lambda proxy response
    """
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

    if event.get("httpMethod") == "OPTIONS":
        return cors_handler.handle_preflight(event)

    try:
        player_id = extract_player_id(event)
        logger.info("Player authenticated", extra={"player_id": player_id})

        character_id = get_query_parameter(event, "characterId")
        if not character_id:
            return cors_handler.add_cors_headers(
                error_response("Missing characterId parameter", status_code=400), event
            )

        if not validate_uuid(character_id):
            return cors_handler.add_cors_headers(
                error_response("Invalid character ID format", status_code=400), event
            )

        logger.info(
            "Abandoning story",
            extra={"character_id": character_id},
        )

        result = abandon_story_business_logic(character_id, player_id)

        logger.info("Lambda response", extra={"status_code": 200})
        return cors_handler.add_cors_headers(
            create_response(200, result), event
        )

    except ValueError as err:
        logger.error("Business logic error", extra={"error": str(err)})
        return cors_handler.add_cors_headers(
            error_response(str(err), status_code=400), event
        )
    except RuntimeError as err:
        logger.error("Database error", extra={"error": str(err)}, exc_info=True)
        return cors_handler.add_cors_headers(
            error_response("Internal server error", status_code=500), event
        )

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
