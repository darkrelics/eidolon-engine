"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason Robinson

Lambda function to abandon an active story.
Updates character state, marks active segments as abandoned, and updates history.
"""

from eidolon.character import get_character_with_ownership
from eidolon.character import reset_character_game_mode
from eidolon.cors import cors_handler
from eidolon.logger import get_logger
from eidolon.requests import extract_player_id
from eidolon.requests import get_required_field
from eidolon.requests import parse_json_body
from eidolon.responses import create_response
from eidolon.responses import error_response
from eidolon.story import add_story_to_abandoned_list
from eidolon.story import get_active_story_segment
from eidolon.story import mark_segment_as_abandoned
from eidolon.story import record_story_abandonment
from eidolon.validation import validate_uuid

# Configure logging
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
        Dict with:
            - success: bool
            - data: Response data (if success)
            - error: Error message (if failed)
            - statusCode: HTTP status code
    """
    # Step 1: Verify character ownership
    character, error_msg = get_character_with_ownership(character_id, player_id)
    if error_msg:
        logger.warning(
            "Character not found or not owned",
            extra={
                "character_id": character_id,
                "player_id": player_id,
                "error": error_msg,
            },
        )
        return {
            "success": False,
            "error": "Character not found",
            "statusCode": 404,
        }

    # Step 2: Check if character is in a story
    game_mode = character.get("GameMode", "None")
    if game_mode != "Incremental":
        logger.warning(
            "Character not in Incremental mode",
            extra={"character_id": character_id, "game_mode": game_mode},
        )
        return {
            "success": False,
            "error": "Character not in a story",
            "statusCode": 409,
        }

    # Step 3: Get active story segment
    segment_result = get_active_story_segment(character_id)
    if not segment_result["success"]:
        return {
            "success": False,
            "error": segment_result["error"],
            "statusCode": 404,
        }

    active_segment = segment_result["data"]
    active_segment_id = active_segment.get("ActiveSegmentID")
    story_id = active_segment.get("StoryID")
    story_title = active_segment.get("StoryTitle", "Unknown Story")

    # Step 4: Add story to abandoned list
    abandoned_list_result = add_story_to_abandoned_list(character_id, story_id)
    if not abandoned_list_result["success"]:
        logger.error(
            "Failed to add story to abandoned list but continuing",
            extra={"character_id": character_id, "story_id": story_id},
        )

    # Step 5: Mark segment as abandoned
    abandon_result = mark_segment_as_abandoned(active_segment_id)
    if not abandon_result["success"]:
        logger.error(
            "Failed to mark segment as abandoned but continuing",
            extra={"active_segment_id": active_segment_id},
        )

    # Step 6: Record in history
    history_result = record_story_abandonment(character_id, story_id)
    if not history_result["success"]:
        logger.error(
            "Failed to update history but continuing",
            extra={"character_id": character_id, "story_id": story_id},
        )

    # Step 7: Reset character game mode
    reset_result = reset_character_game_mode(character_id)
    if not reset_result["success"]:
        return {
            "success": False,
            "error": reset_result["error"],
            "statusCode": 500,
        }

    # Build success response
    response_data = {
        "characterId": character_id,
        "storyId": story_id,
        "storyTitle": story_title,
        "status": "abandoned",
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

    return {
        "success": True,
        "data": response_data,
        "statusCode": 200,
    }


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to abandon an active story.

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
        player_id, auth_error = extract_player_id(event)
        if auth_error:
            logger.error("Authentication failed", extra={"error": auth_error})
            return cors_handler.add_cors_headers(
                error_response(auth_error, status_code=401), event
            )

        logger.info("Player authenticated", extra={"player_id": player_id})

        body, parse_error = parse_json_body(event)
        if parse_error:
            return cors_handler.add_cors_headers(parse_error, event)

        character_id, char_error = get_required_field(body, "characterId")
        if char_error:
            return cors_handler.add_cors_headers(
                error_response(char_error, status_code=400), event
            )

        if character_id and not validate_uuid(character_id):
            return cors_handler.add_cors_headers(
                error_response("Invalid character ID format", status_code=400), event
            )

        logger.info(
            "Abandoning story",
            extra={"character_id": character_id},
        )

        result = abandon_story_business_logic(character_id, player_id)  # type: ignore

        if not result["success"]:
            return cors_handler.add_cors_headers(
                error_response(result["error"], status_code=result["statusCode"]), event
            )

        logger.info("Lambda response", extra={"status_code": 200})
        return cors_handler.add_cors_headers(
            create_response(200, result["data"]), event
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
