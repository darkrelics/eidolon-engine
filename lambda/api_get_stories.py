"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to get available stories for a character.
Returns stories the character can participate in, checking prerequisites and cooldowns.
"""

from eidolon.character import get_character, validate_character_ownership
from eidolon.cors import cors_handler
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import extract_player_id, validate_player
from eidolon.requests import get_query_parameter_flexible
from eidolon.responses import lambda_error, lambda_response
from eidolon.story import get_stories_for_character
from eidolon.validation import validate_uuid


def get_available_stories_business_logic(character_id: str, player_id: str) -> dict:
    """
    Business logic for getting available stories for a character.

    Args:
        character_id: Character UUID
        player_id: Authenticated player ID

    Returns:
        Dict with stories list

    Raises:
        ValueError: If character not found or in invalid state
        RuntimeError: If database operations fail
    """
    # Validate character ID format
    if not validate_uuid(character_id):
        raise ValueError("Invalid character ID format")

    # Get character and verify ownership
    character = get_character(character_id)
    validate_character_ownership(character, player_id)

    # Check if character is in a valid state for stories
    game_mode = character.get("GameMode", "None")
    if game_mode not in ["None", "Incremental"]:
        raise ValueError(f"Character is currently in {game_mode} mode")

    # Get available stories from character
    available_story_ids = character.get("AvailableStories", [])
    logger.info(
        "Available stories for character",
        extra={
            "character_id": character_id,
            "story_count": len(available_story_ids),
            "story_ids": available_story_ids,
        },
    )

    # Get story details with prerequisite and cooldown checking
    stories = get_stories_for_character(character_id, available_story_ids)

    # Sort stories by availability and title
    stories.sort(key=lambda s: (not s["Available"], s["Title"]))

    logger.info(
        "Stories retrieved successfully",
        extra={
            "character_id": character_id,
            "total_stories": len(stories),
            "available_stories": sum(1 for s in stories if s["Available"]),
        },
    )

    return {"Stories": stories}


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to get available stories for a character.

    Query Parameters:
        characterId: Character UUID

    Returns:
        200: List of available stories
        404: Character not found
        400: Invalid parameters
        401: Unauthorized
        409: Character in invalid state
        500: Internal error
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
        logger.error("Authentication failed", extra={"error": str(err)}, exc_info=True)
        return lambda_response(401, {"Error": "Unauthorized"}, event)
    except Exception as err:
        return lambda_error(event, err)

    # Validate player exists
    try:
        if not validate_player(player_id):
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
        response_data = get_available_stories_business_logic(character_id, player_id)  # type: ignore
        logger.info("Lambda response", extra={"status_code": 200})
        return lambda_response(200, response_data, event)
    except ValueError as err:
        logger.warning(
            "Invalid request",
            extra={"character_id": character_id, "error": str(err)},
        )
        error_msg = str(err)
        if "not found" in error_msg.lower():
            return lambda_response(
                404,
                {"Error": "Character not found"},
                event,
            )
        elif "mode" in error_msg.lower():
            return lambda_response(
                409,
                {"Error": error_msg},
                event,
            )
        return lambda_response(
            400,
            {"Error": error_msg},
            event,
        )
    except RuntimeError as err:
        logger.error(
            "Failed to get stories",
            extra={"character_id": character_id, "error": str(err)},
            exc_info=True,
        )
        return lambda_response(
            500,
            {"Error": "Internal server error"},
            event,
        )
    except Exception as err:
        return lambda_error(event, err)
