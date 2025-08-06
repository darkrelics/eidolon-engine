"""Lambda function for character rest endpoint."""

import time

from eidolon.character import character_get
from eidolon.cors import cors_handler
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import extract_player_id, validate_player
from eidolon.responses import lambda_error, lambda_response
from eidolon.segment import get_active_segment_info, insert_rest_segment

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
    character = character_get(character_id, player_id)

    # Check game mode
    game_mode = character.get("GameMode", "None")
    if game_mode != "Incremental":
        logger.warning(f"Character not in Incremental mode for {character_id}")
        raise ValueError(f"Character is in {game_mode} mode, must be in Incremental mode")

    # Check if character has active story
    active_story_id = character.get("ActiveStoryID")
    if not active_story_id:
        logger.warning(f"Character has no active story for {character_id}")
        raise ValueError("No active story")

    # Get active segment - character MUST have one to insert rest
    active_segment_id = character.get("ActiveSegmentID")
    if not active_segment_id:
        logger.warning(f"Character has no active segment for {character_id}")
        raise ValueError("Character must have an active segment to rest")

    # Get active segment info to find current segment ID
    try:
        active_segment = get_active_segment_info(active_segment_id)
        current_segment_id = active_segment.get("SegmentID")
        if not current_segment_id:
            raise ValueError("Active segment missing SegmentID")
    except (ValueError, RuntimeError) as err:
        logger.error(f"Failed to get active segment info for {active_segment_id} Error: {err}", exc_info=True)
        raise

    # Calculate time remaining on current segment
    current_time = int(time.time())
    end_time = active_segment.get("EndTime", 0)
    time_remaining = max(0, end_time - current_time)

    logger.info(f"Current segment timing for {current_segment_id}")

    # Insert rest segment into story flow
    try:
        rest_segment_id = insert_rest_segment(
            story_id=active_story_id,
            current_segment_id=current_segment_id,
            rest_duration=REST_SEGMENT_DURATION,
            time_remaining=time_remaining,
        )
    except (ValueError, RuntimeError) as err:
        logger.error(f"Failed to insert rest segment for {active_story_id} Error: {err}", exc_info=True)
        raise

    logger.info(f"Rest segment inserted successfully for {character_id}")

    return {"rest_segment_id": rest_segment_id, "current_segment_id": current_segment_id, "active_segment_id": active_segment_id}


def lambda_handler(event: dict, context: object) -> dict:
    """Lambda handler for character rest API."""
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

    # Parse request body
    try:
        body: dict = event.get("body", {})
    except ValueError as err:
        return lambda_response(400, {"Error": str(err)}, event)
    except Exception as err:
        return lambda_error(event, err)

    # Extract and validate required fields
    try:
        character_id: str = body.get("character_id") or body.get("CharacterID")  # type: ignore

    except ValueError as err:
        return lambda_response(400, {"Error": str(err)}, event)

    logger.info(f"Character rest request received for {character_id}")

    # Call business logic
    try:
        result = handle_character_rest(player_id, character_id)  # type: ignore
        logger.info("Lambda response for status 200")
        return lambda_response(
            200,
            {
                "Success": True,
                "RestSegmentId": result.get("rest_segment_id"),
                "InsertedAfter": result.get("current_segment_id"),
                "Message": "Rest segment inserted into story flow. It will be processed after the current segment completes.",
            },
            event,
        )
    except ValueError as err:
        # Business logic errors
        logger.warning(f"Character rest validation failed Error: {err}")
        error_msg = str(err)

        # Check for specific error cases
        if "not owned by player" in error_msg:
            status_code = 403
        elif "Cannot insert rest segment" in error_msg:
            # Early return cases - not enough time or at end of story
            status_code = 422  # Unprocessable Entity
        else:
            status_code = 400

        return lambda_response(status_code, {"Error": error_msg}, event)
    except RuntimeError as err:
        # System errors
        logger.error(f"Character rest system error Error: {err}", exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)
