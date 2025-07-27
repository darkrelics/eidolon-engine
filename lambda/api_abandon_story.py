"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to abandon an active story.
Updates character state, marks active segments as abandoned, and updates history.
"""

from eidolon.character import get_character
from eidolon.character import reset_character_game_mode
from eidolon.character import validate_character_ownership
from eidolon.logger import get_logger
from eidolon.player import extract_player_id_from_event
from eidolon.player import validate_player_exists
from eidolon.requests import get_query_parameter
from eidolon.story import add_story_to_abandoned_list, get_active_story_segment, mark_segment_as_abandoned, record_story_abandonment
from eidolon.utilities import build_lambda_response
from eidolon.utilities import handle_lambda_error
from eidolon.utilities import handle_preflight_if_options
from eidolon.utilities import log_lambda_invocation
from eidolon.validation import validate_uuid

logger = get_logger(__name__)


def abandon_story_business_logic(character_id: str, player_id: str) -> dict:
    """Business logic for abandoning an active story.

    Args:
        character_id: Character UUID
        player_id: Player ID for ownership verification

    Returns:
        Dict with response data for successful abandonment

    Raises:
        ValueError: If character not found, not owned, or not in a story
        RuntimeError: If database operations fail
    """
    character = get_character(character_id)
    validate_character_ownership(character, player_id)

    if character.get("GameMode", "None") != "Incremental":
        logger.warning(
            "Character not in Incremental mode", extra={"character_id": character_id, "game_mode": character.get("GameMode")}
        )
        raise ValueError("Character not in a story")

    active_segment = get_active_story_segment(character_id)
    active_segment_id = active_segment.get("ActiveSegmentID")
    story_id = active_segment.get("StoryID")
    story_title = active_segment.get("StoryTitle", "Unknown Story")

    try:
        add_story_to_abandoned_list(character_id, story_id)  # type: ignore
    except (ValueError, RuntimeError) as err:
        logger.error(
            "Failed to add story to abandoned list but continuing",
            extra={"character_id": character_id, "story_id": story_id, "error": str(err)},
        )

    try:
        mark_segment_as_abandoned(active_segment_id)  # type: ignore
    except (ValueError, RuntimeError) as err:
        logger.error(
            "Failed to mark segment as abandoned but continuing", extra={"active_segment_id": active_segment_id, "error": str(err)}
        )

    try:
        record_story_abandonment(character_id, story_id)  # type: ignore
    except (ValueError, RuntimeError) as err:
        logger.error(
            "Failed to update history but continuing", extra={"character_id": character_id, "story_id": story_id, "error": str(err)}
        )

    reset_character_game_mode(character_id)

    logger.info(
        "Story abandoned successfully",
        extra={"character_id": character_id, "story_id": story_id, "active_segment_id": active_segment_id},
    )

    return {
        "characterId": character_id,
        "storyId": story_id,
        "storyTitle": story_title,
        "abandoned": True,
        "message": "Story abandoned successfully",
    }


def lambda_handler(event: dict, context: object) -> dict:
    """Lambda handler to abandon an active story.

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
        return build_lambda_response(401, {"error": "Unauthorized"}, event)
    except Exception as err:
        return handle_lambda_error(err, context, event)
    
    # Validate player exists
    try:
        if not validate_player_exists(player_id):
            logger.error("Player not found in database", extra={"player_id": player_id})
            return build_lambda_response(401, {"error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error("Failed to validate player", extra={"error": str(err)})
        return build_lambda_response(500, {"error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error(err, context, event)

    # Get character ID from query parameters
    character_id = get_query_parameter(event, "characterId")
    if not character_id:
        return build_lambda_response(400, {"error": "Missing characterId parameter"}, event)

    if not validate_uuid(character_id):
        return build_lambda_response(400, {"error": "Invalid character ID format"}, event)

    # Call business logic
    try:
        logger.info("Abandoning story", extra={"character_id": character_id})
        result = abandon_story_business_logic(character_id, player_id)
        return build_lambda_response(200, result, event)
    except ValueError as err:
        logger.warning("Business logic error", extra={"error": str(err)})
        return build_lambda_response(400, {"error": str(err)}, event)
    except RuntimeError as err:
        logger.error("Database error", extra={"error": str(err)}, exc_info=True)
        return build_lambda_response(500, {"error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error(err, context, event)
