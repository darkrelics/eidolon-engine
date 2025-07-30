"""Lambda function for character rest endpoint."""

import time
from uuid_extension import uuid7

from eidolon.character import get_character_with_ownership
from eidolon.logger import get_logger
from eidolon.player import extract_player_id_from_event, validate_player_exists
from eidolon.requests import get_required_field_flexible, parse_json_body
from eidolon.segment import create_next_active_segment
from eidolon.story import get_story_metadata
from eidolon.utilities import (
    build_lambda_response_pascal,
    handle_lambda_error_pascal,
    handle_preflight_if_options,
    log_lambda_invocation,
)

# Configure logging
logger = get_logger(__name__)

# Rest segment configuration
REST_SEGMENT_DURATION = 900  # 15 minutes (time to heal a bashing wound)


def handle_character_rest(player_id: str, character_id: str) -> dict:
    """Handle the business logic for character rest.

    Args:
        player_id: Cognito user ID
        character_id: Character ID to rest

    Returns:
        Dict containing rest segment information

    Raises:
        ValueError: If character validation fails
        RuntimeError: If database operations fail
    """
    # Get and validate character ownership
    character = get_character_with_ownership(character_id, player_id)

    # Check game mode
    game_mode = character.get("GameMode", "None")
    if game_mode != "Incremental":
        logger.warning(
            "Character not in Incremental mode",
            extra={"character_id": character_id, "game_mode": game_mode},
        )
        raise ValueError(f"Character is in {game_mode} mode, must be in Incremental mode")

    # Check if character has active story
    active_story_id = character.get("ActiveStoryID")
    if not active_story_id:
        logger.warning("Character has no active story", extra={"character_id": character_id})
        raise ValueError("No active story")

    # Check for existing active segment
    active_segment_id = character.get("ActiveSegmentID")
    if active_segment_id:
        logger.warning(
            "Character already has active segment",
            extra={
                "character_id": character_id,
                "segment_id": active_segment_id,
            },
        )
        raise ValueError("Character already has an active segment")

    # Create rest segment
    result = create_rest_segment(character, active_story_id)

    logger.info(
        "Rest initiated successfully",
        extra={
            "character_id": character_id,
            "segment_id": result.get("segment", {}).get("activeSegmentId"),
            "wounds": len(character.get("Wounds", [])),
        },
    )

    return result


def create_rest_segment(character: dict, story_id: str) -> dict:
    """Create a rest segment for the character.

    Args:
        character: Character data
        story_id: Active story ID

    Returns:
        Dict with segment creation result

    Raises:
        RuntimeError: If database operations fail
    """
    character_id = character.get("CharacterID")
    player_id = character.get("PlayerID")

    # Get story title
    story_title = "Unknown Story"
    try:
        story = get_story_metadata(story_id)
        story_title = story.get("Title", "Unknown Story")
    except (ValueError, RuntimeError):
        # Use default if story lookup fails
        pass

    # Create rest segment definition
    rest_segment_def = {
        "SegmentID": str(uuid7()),  # Generate unique ID for this rest segment
        "SegmentType": "rest",
        "SegmentDuration": REST_SEGMENT_DURATION,
        "ShortStatus": "Resting to heal wounds",
        "DefaultStatus": "Resting to heal wounds",
        "RestBenefit": {
            "bashingHeal": 1,  # Heal 1 bashing wound
            "lethalHeal": 0,   # No lethal healing in standard rest
        },
        "NextSegmentID": None,  # Rest segments typically end the story or continue based on story logic
    }

    # Use the eidolon library to create the active segment
    try:
        active_segment_id = create_next_active_segment(
            character_id=character_id, # type: ignore
            player_id=player_id, # type: ignore
            story_id=story_id,
            segment=rest_segment_def,
            story_title=story_title
        )
    except RuntimeError as err:
        logger.error("Failed to create rest segment", extra={"error": str(err)}, exc_info=True)
        raise

    # Calculate times for response
    current_time = int(time.time())
    end_time = current_time + REST_SEGMENT_DURATION

    # Return segment info for client
    return {
        "success": True,
        "segment": {
            "activeSegmentId": active_segment_id,
            "segmentType": "rest",
            "startTime": current_time,
            "endTime": end_time,
            "shortStatus": "Resting to heal wounds",
            "duration": REST_SEGMENT_DURATION,
        },
    }


def lambda_handler(event: dict, context: object) -> dict:
    """Lambda handler for character rest API."""
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
        logger.error("Authentication failed", extra={"error": str(err)}, exc_info=True)
        return build_lambda_response_pascal(401, {"Error": "Unauthorized"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)

    # Validate player exists
    try:
        if not validate_player_exists(player_id):
            logger.error("Player not found in database", extra={"player_id": player_id})
            return build_lambda_response_pascal(401, {"Error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error("Failed to validate player", extra={"error": str(err)}, exc_info=True)
        return build_lambda_response_pascal(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)

    # Parse request body
    try:
        body = parse_json_body(event)
    except ValueError as err:
        return build_lambda_response_pascal(400, {"Error": str(err)}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)

    # Extract and validate required fields
    try:
        character_id = get_required_field_flexible(body, "CharacterID", "characterId")
    except ValueError as err:
        return build_lambda_response_pascal(400, {"Error": str(err)}, event)

    logger.info(
        "Character rest request received",
        extra={
            "player_id": player_id,
            "character_id": character_id,
        },
    )

    # Call business logic
    try:
        result = handle_character_rest(player_id, character_id)  # type: ignore
        logger.info("Lambda response", extra={"status_code": 200})
        return build_lambda_response_pascal(
            200,
            {
                "Success": True,
                "Segment": {
                    "ActiveSegmentId": result.get("segment", {}).get("activeSegmentId"),
                    "SegmentType": result.get("segment", {}).get("segmentType"),
                    "StartTime": result.get("segment", {}).get("startTime"),
                    "EndTime": result.get("segment", {}).get("endTime"),
                    "ShortStatus": result.get("segment", {}).get("shortStatus"),
                    "Duration": result.get("segment", {}).get("duration"),
                },
            },
            event,
        )
    except ValueError as err:
        # Business logic errors
        logger.warning("Character rest validation failed", extra={"error": str(err)})
        status_code = 403 if "not owned by player" in str(err) else 400
        return build_lambda_response_pascal(status_code, {"Error": str(err)}, event)
    except RuntimeError as err:
        # System errors
        logger.error("Character rest system error", extra={"error": str(err)}, exc_info=True)
        return build_lambda_response_pascal(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)
