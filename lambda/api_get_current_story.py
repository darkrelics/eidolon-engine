"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to get the current active story and segment for a character.
Returns story metadata and segment details for the client to display.
"""

from eidolon.character import get_character, validate_character_ownership
from eidolon.cors import cors_handler
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import extract_player_id, validate_player_exists
from eidolon.requests import get_query_parameter_flexible
from eidolon.responses import lambda_response, lambda_error
from eidolon.story import (
    format_story_segment_response,
    get_active_story_segment_with_player_check,
    get_story_metadata,
    get_story_segment,
)
from eidolon.validation import validate_uuid


def get_current_story_business_logic(character_id: str, player_id: str) -> dict:
    """
    Business logic for getting current active story and segment.

    Args:
        character_id: Character UUID
        player_id: Authenticated player ID

    Returns:
        Response data dict with story and segment information

    Raises:
        ValueError: If character not found, not owned, or no active story
        RuntimeError: If database operations fail
    """
    # Validate character ID format
    if not validate_uuid(character_id):
        raise ValueError("Invalid character ID format")

    # Verify character ownership
    character = get_character(character_id)
    validate_character_ownership(character, player_id)

    # Get active segment
    active_segment = get_active_story_segment_with_player_check(character_id, player_id)
    story_id = active_segment.get("StoryID")
    segment_id = active_segment.get("SegmentID")

    if not story_id or not segment_id:
        raise ValueError("Invalid active segment data")

    # Get story and segment metadata
    story_metadata = get_story_metadata(story_id)
    segment_data = get_story_segment(story_id, segment_id)

    # Format response using eidolon library function
    response_data = format_story_segment_response(
        active_segment=active_segment,
        story_metadata=story_metadata,
        segment_data=segment_data,
    )

    # Add the raw active segment data for client compatibility
    response_data["ActiveSegment"] = active_segment

    logger.info(
        "Current story retrieved successfully",
        extra={
            "character_id": character_id,
            "story_id": story_id,
            "segment_type": segment_data.get("SegmentType"),
            "segment_id": segment_id,
        },
    )

    return response_data


def lambda_handler(event: dict, context: object) -> dict:
    """
    Get current active story and segment for a character.

    Lambda function to get the current active story segment for a character.
    This function retrieves the current active segment if a character is in a story,
    along with relevant story metadata and segment details.

    Query Parameters:
        characterId: Character ID to check (supports both CharacterID and characterId)

    Returns:
        200: Current story and segment data
        404: No active story or character not found
        400: Missing parameters or invalid request
        401: Unauthorized
        500: Internal error
    """
    # Log invocation
    log_lambda_statistics(event, context)

    # Handle preflight
    preflight_response: dict = cors_handler.handle_preflight(event)
    if preflight_response:
        return preflight_response

    try:
        # Extract player ID from JWT
        player_id = extract_player_id(event)
    except ValueError as err:
        logger.error("Authentication failed", extra={"error": str(err)}, exc_info=True)
        return lambda_response(401, {"Error": "Unauthorized"}, event)
    except Exception as err:
        return lambda_error(event, err)

    # Validate player exists
    try:
        if not validate_player_exists(player_id):
            logger.error("Player not found in database", extra={"player_id": player_id})
            return lambda_response(401, {"Error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error("Failed to validate player", extra={"error": str(err)}, exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)

    # Get character ID from query parameters (flexible: CharacterID or characterId)
    character_id = get_query_parameter_flexible(event, "CharacterID", "characterId")
    if not character_id:
        return lambda_response(400, {"Error": "Missing CharacterID parameter"}, event)

    # Call business logic
    try:
        response_data = get_current_story_business_logic(character_id, player_id)  # type: ignore
        logger.info("Lambda response", extra={"status_code": 200})
        return lambda_response(200, response_data, event)
    except ValueError as err:
        logger.warning(
            "Invalid request or not found",
            extra={"character_id": character_id, "error": str(err)},
        )
        error_msg = str(err).lower()
        if "no active story" in error_msg:
            return lambda_response(404, {"Error": "No active story found"}, event)
        elif "not found" in error_msg:
            return lambda_response(404, {"Error": "Character not found"}, event)
        return lambda_response(400, {"Error": str(err)}, event)
    except RuntimeError as err:
        logger.error(
            "Failed to get current story",
            extra={"character_id": character_id, "error": str(err)},
            exc_info=True,
        )
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)
