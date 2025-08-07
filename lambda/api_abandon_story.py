"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to abandon an active story.
Updates character state, marks active segments as abandoned, and updates history.
"""

from eidolon.character_data import character_get
from eidolon.character_story import reset_character_game_mode
from eidolon.cors import cors_handler
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import extract_player_id, validate_player
from eidolon.requests import get_query_parameter_flexible
from eidolon.responses import lambda_error, lambda_response
from eidolon.segment import delete_active_segment, record_abandoned_segment_history
from eidolon.story import add_story_to_abandoned_list, get_active_story_segment, mark_segment_as_abandoned, record_story_abandonment
from eidolon.validation import validate_uuid


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
    character: dict = character_get(character_id, player_id)

    if character.get("GameMode", "None") != "Incremental":
        logger.warning(f"Character not in Incremental mode for {character_id}")
        raise ValueError("Character not in a story")

    active_segment = get_active_story_segment(character_id)
    active_segment_id = active_segment.get("ActiveSegmentID")
    story_id = active_segment.get("StoryID")
    story_title = active_segment.get("StoryTitle", "Unknown Story")

    if not active_segment_id or not story_id:
        logger.error(f"Active segment missing required fields for {character_id}")
        raise ValueError("Invalid active segment data")

    # Reset character game mode first to immediately free the character
    reset_character_game_mode(character_id)

    # Add story to abandoned list
    try:
        add_story_to_abandoned_list(character_id, story_id)
    except (ValueError, RuntimeError) as err:
        logger.error(f"Failed to add story to abandoned list but continuing for {character_id} Error: {err}")

    # Record story abandonment in story history
    try:
        record_story_abandonment(character_id, story_id)
    except (ValueError, RuntimeError) as err:
        logger.error(f"Failed to update story history but continuing for {character_id} Error: {err}")

    # Mark segment as abandoned
    try:
        mark_segment_as_abandoned(active_segment_id)
    except (ValueError, RuntimeError) as err:
        logger.error(f"Failed to mark segment as abandoned but continuing for {active_segment_id} Error: {err}")

    # Record abandoned segment in history
    try:
        record_abandoned_segment_history(character_id, story_id, active_segment)
    except RuntimeError as err:
        logger.error(f"Failed to record segment history but continuing for {character_id} Error: {err}")

    # Delete the active segment after recording history
    try:
        delete_active_segment(active_segment_id)
    except ValueError as err:
        logger.error(f"Failed to delete active segment - invalid ID for {active_segment_id} Error: {err}")

    logger.info(f"Story abandoned successfully for {character_id}")

    return {
        "CharacterID": character_id,
        "StoryID": story_id,
        "StoryTitle": story_title,
        "Abandoned": True,
        "Message": "Story abandoned successfully",
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

    # Get character ID from query parameters (flexible: CharacterID or characterId)
    character_id = get_query_parameter_flexible(event, "CharacterID", "characterId")
    if not character_id:
        return lambda_response(400, {"Error": "Missing CharacterID parameter"}, event)

    if not validate_uuid(character_id):
        return lambda_response(400, {"Error": "Invalid character ID format"}, event)

    # Call business logic
    try:
        logger.info(f"Abandoning story for {character_id}")
        result: dict = abandon_story_business_logic(character_id, player_id)
        logger.info("Lambda response for status 200")
        return lambda_response(200, result, event)
    except ValueError as err:
        logger.warning(f"Business logic error Error: {err}")
        return lambda_response(400, {"Error": str(err)}, event)
    except RuntimeError as err:
        logger.error(f"Database error Error: {err}", exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)
