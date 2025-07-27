"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to get available stories for a character.
Returns stories the character can participate in, checking prerequisites and cooldowns.
"""

from eidolon.character import get_character
from eidolon.character import validate_character_ownership
from eidolon.logger import get_logger
from eidolon.player import extract_player_id_from_event
from eidolon.player import validate_player_exists
from eidolon.requests import get_query_parameter_flexible
from eidolon.story import get_stories_for_character
from eidolon.utilities import build_lambda_response_pascal
from eidolon.utilities import handle_lambda_error_pascal
from eidolon.utilities import handle_preflight_if_options
from eidolon.utilities import log_lambda_invocation
from eidolon.validation import validate_uuid

# Configure logging
logger = get_logger(__name__)


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

    # Get character ID from query parameters (flexible: CharacterID or characterId)
    character_id = get_query_parameter_flexible(event, "CharacterID", "characterId")
    if not character_id:
        return build_lambda_response_pascal(400, {"error": "Missing CharacterID parameter"}, event)

    # Call business logic
    try:
        response_data = get_available_stories_business_logic(character_id, player_id)  # type: ignore
        return build_lambda_response_pascal(200, response_data, event)
    except ValueError as err:
        logger.warning(
            "Invalid request",
            extra={"character_id": character_id, "error": str(err)},
        )
        error_msg = str(err)
        if "not found" in error_msg.lower():
            return build_lambda_response_pascal(
                404,
                {"error": "Character not found"},
                event,
            )
        elif "mode" in error_msg.lower():
            return build_lambda_response_pascal(
                409,
                {"error": error_msg},
                event,
            )
        return build_lambda_response_pascal(
            400,
            {"error": error_msg},
            event,
        )
    except RuntimeError as err:
        logger.error(
            "Failed to get stories",
            extra={"character_id": character_id, "error": str(err)},
        )
        return build_lambda_response_pascal(
            500,
            {"error": "Internal server error"},
            event,
        )
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)
