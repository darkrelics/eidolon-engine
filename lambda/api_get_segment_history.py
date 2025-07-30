"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to retrieve segment history for a character.
Returns completed segment results from the character's story history.
"""

from eidolon.character import get_character, validate_character_ownership
from eidolon.logger import get_logger
from eidolon.player import extract_player_id_from_event, validate_player_exists
from eidolon.requests import get_query_parameter_flexible
from eidolon.story import get_story_history
from eidolon.utilities import (
    build_lambda_response_pascal,
    handle_lambda_error_pascal,
    handle_preflight_if_options,
    log_lambda_invocation,
)
from eidolon.validation import validate_uuid

logger = get_logger(__name__)


def get_segment_history_business_logic(character_id: str, player_id: str) -> dict:
    """
    Business logic for retrieving segment history.

    Args:
        character_id: Character UUID
        player_id: Authenticated player ID

    Returns:
        Response data dict with segment history

    Raises:
        ValueError: If character not found or not owned
        RuntimeError: If database operations fail
    """
    # Validate character ID format
    if not validate_uuid(character_id):
        raise ValueError("Invalid character ID format")

    # Verify character ownership
    character = get_character(character_id)
    validate_character_ownership(character, player_id)

    # Get current story ID from character
    story_id = character.get("ActiveStoryID")
    if not story_id:
        # No active story, return empty history
        logger.info(
            "No active story for character",
            extra={"character_id": character_id},
        )
        return {
            "CharacterID": character_id,
            "StoryID": None,
            "Segments": [],
        }

    # Get story history
    try:
        history = get_story_history(character_id, story_id)
    except RuntimeError as err:
        logger.error(
            "Failed to get story history",
            extra={
                "character_id": character_id,
                "story_id": story_id,
                "error": str(err),
            },
        )
        raise

    # Extract segment history
    segment_history = history.get("SegmentHistory", [])

    # Format segments for response
    formatted_segments = []
    for segment in segment_history:
        formatted_segment = {
            "SegmentID": segment.get("SegmentID"),
            "SegmentType": segment.get("SegmentType"),
            "CompletedAt": segment.get("CompletedAt"),
            "Outcome": segment.get("Outcome"),
        }

        # Add optional fields if present
        if segment.get("Decision"):
            formatted_segment["Decision"] = segment.get("Decision")

        if segment.get("ChallengeResults"):
            formatted_segment["ChallengeResults"] = segment.get("ChallengeResults")

        if segment.get("SkillXPAwarded"):
            formatted_segment["SkillXPAwarded"] = segment.get("SkillXPAwarded")

        if segment.get("AttributeXPAwarded"):
            formatted_segment["AttributeXPAwarded"] = segment.get("AttributeXPAwarded")

        if segment.get("CombatState"):
            formatted_segment["CombatState"] = segment.get("CombatState")

        formatted_segments.append(formatted_segment)

    # Sort by completion time, newest first
    formatted_segments.sort(key=lambda x: x.get("CompletedAt", ""), reverse=True)

    response = {
        "CharacterID": character_id,
        "StoryID": story_id,
        "Segments": formatted_segments,
    }

    logger.info(
        "Segment history retrieved",
        extra={
            "character_id": character_id,
            "story_id": story_id,
            "segment_count": len(formatted_segments),
        },
    )

    return response


def lambda_handler(event: dict, context: object) -> dict:
    """
    Get segment history for a character.

    Lambda function to retrieve completed segment history for a character's
    active story. Used by clients to display past outcomes and decisions.

    Query Parameters:
        characterId: Character ID to get history for (supports both CharacterID and characterId)

    Returns:
        200: Segment history data
        404: Character not found
        400: Missing parameters or invalid request
        401: Unauthorized
        500: Internal error
    """
    # Log invocation
    log_lambda_invocation(context, event)

    # Handle preflight
    preflight_response = handle_preflight_if_options(event)
    if preflight_response:
        return preflight_response

    try:
        # Extract player ID from JWT
        player_id = extract_player_id_from_event(event)
    except ValueError as err:
        logger.error("Authentication failed", extra={"error": str(err)}, exc_info=True)
        return build_lambda_response_pascal(401, {"Error": "Unauthorized"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)

    # Validate player exists
    try:
        if not validate_player_exists(player_id):
            logger.error("Player not found in database", extra={"player_id": player_id}, exc_info=True)
            return build_lambda_response_pascal(401, {"Error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error("Failed to validate player", extra={"error": str(err)}, exc_info=True)
        return build_lambda_response_pascal(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)

    # Get character ID from query parameters (flexible: CharacterID or characterId)
    character_id = get_query_parameter_flexible(event, "CharacterID", "characterId")
    if not character_id:
        return build_lambda_response_pascal(400, {"Error": "Missing CharacterID parameter"}, event)

    # Call business logic
    try:
        response_data = get_segment_history_business_logic(character_id, player_id)  # type: ignore
        logger.info("Lambda response", extra={"status_code": 200})
        return build_lambda_response_pascal(200, response_data, event)
    except ValueError as err:
        logger.warning(
            "Invalid request",
            extra={"character_id": character_id, "error": str(err)},
        )
        if "not found" in str(err).lower():
            return build_lambda_response_pascal(404, {"Error": "Character not found"}, event)
        return build_lambda_response_pascal(400, {"Error": str(err)}, event)
    except RuntimeError as err:
        logger.error(
            "Failed to get segment history",
            extra={"character_id": character_id, "error": str(err)},
            exc_info=True,
        )
        return build_lambda_response_pascal(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)
