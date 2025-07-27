"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to start a story for a character.
Validates character state, creates active segment, and returns first segment details.
"""

from eidolon.logger import get_logger
from eidolon.player import extract_player_id_from_event, validate_player_exists
from eidolon.requests import get_required_field_flexible, parse_json_body
from eidolon.story import format_segment_response, start_story_for_character
from eidolon.utilities import (
    build_lambda_response_pascal,
    handle_lambda_error_pascal,
    handle_preflight_if_options,
    log_lambda_invocation,
)
from eidolon.validation import validate_uuid

# Configure logging
logger = get_logger(__name__)


def start_story_business_logic(character_id: str, story_id: str, player_id: str) -> dict:
    """
    Business logic for starting a story.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        player_id: Authenticated player ID

    Returns:
        Response data with segment information

    Raises:
        ValueError: If validation fails
        RuntimeError: If database operations fail
    """
    # Start the story using the eidolon library
    result = start_story_for_character(character_id, story_id, player_id)

    # Format response
    segment_data = format_segment_response(result["segment"], result["active_segment"])

    return {"Segment": segment_data}


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to start a story for a character.

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

    # Extract player ID from JWT
    try:
        player_id = extract_player_id_from_event(event)
    except ValueError as err:
        logger.error("Authentication failed", extra={"error": str(err)})
        return build_lambda_response_pascal(401, {"error": "Unauthorized"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)

    # Validate player exists
    try:
        if not validate_player_exists(player_id):
            logger.error("Player not found in database", extra={"player_id": player_id})
            return build_lambda_response_pascal(401, {"error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error("Failed to validate player", extra={"error": str(err)})
        return build_lambda_response_pascal(500, {"error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)

    # Parse request body with flexible field names
    try:
        body = parse_json_body(event)
        character_id = get_required_field_flexible(body, "CharacterID", "characterID")
        story_id = get_required_field_flexible(body, "StoryID", "storyID")
    except ValueError as err:
        return build_lambda_response_pascal(400, {"error": str(err)}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)

    # Validate UUIDs
    if character_id and not validate_uuid(character_id):  # type: ignore
        return build_lambda_response_pascal(400, {"error": "Invalid character ID format"}, event)

    if story_id and not validate_uuid(story_id):  # type: ignore
        return build_lambda_response_pascal(400, {"error": "Invalid story ID format"}, event)

    logger.info(
        "Starting story",
        extra={"character_id": character_id, "story_id": story_id},
    )

    # Call business logic
    try:
        response_data = start_story_business_logic(character_id, story_id, player_id)  # type: ignore
        return build_lambda_response_pascal(200, response_data, event)
    except ValueError as err:
        logger.warning(
            "Invalid request",
            extra={"character_id": character_id, "story_id": story_id, "error": str(err)},
        )
        error_msg = str(err)
        if "not found" in error_msg.lower():
            return build_lambda_response_pascal(404, {"error": error_msg}, event)
        elif "already in" in error_msg.lower() and "mode" in error_msg.lower():
            return build_lambda_response_pascal(409, {"error": error_msg}, event)
        elif "not available" in error_msg.lower():
            return build_lambda_response_pascal(403, {"error": error_msg}, event)
        return build_lambda_response_pascal(400, {"error": error_msg}, event)
    except RuntimeError as err:
        logger.error(
            "Failed to start story",
            extra={"character_id": character_id, "story_id": story_id, "error": str(err)},
        )
        return build_lambda_response_pascal(500, {"error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)
