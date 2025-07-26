"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to get available stories for a character.
Returns stories the character can participate in, checking prerequisites and cooldowns.
"""

from datetime import datetime
from datetime import timezone

from botocore.exceptions import ClientError

from eidolon.character import get_character_with_ownership
from eidolon.dynamo import dynamo
from eidolon.dynamo import TableName
from eidolon.logger import get_logger
from eidolon.requests import get_query_parameter
from eidolon.utilities import build_lambda_response
from eidolon.utilities import extract_and_validate_player_id
from eidolon.utilities import handle_lambda_error
from eidolon.utilities import handle_preflight_if_options
from eidolon.utilities import log_lambda_invocation
from eidolon.validation import validate_uuid

# Configure logging
logger = get_logger(__name__)


def get_story_cooldown(character_id: str, story_id: str, story_type: str):
    """
    Calculate cooldown remaining for a story based on its type and last completion.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        story_type: Type of story (one-time, daily, repeatable)

    Returns:
        Seconds remaining on cooldown, 0 if playable
    """
    if story_type == "repeatable":
        return 0

    # Query history table for last completion
    try:
        history = dynamo.get_item(
            TableName.HISTORY, {"CharacterID": character_id, "StoryID": story_id}
        )

        if not history:
            return 0  # Never played

        # Check if story was completed or abandoned
        if not history.get("FinishedAt"):
            return 0  # Abandoned stories can be retried

        if story_type == "one-time":
            # Check if it was completed successfully
            outcome = history.get("FinalOutcome", "")
            if outcome in ["normal", "exceptional", "minimal"]:
                return -1  # Permanently unavailable
            return 0  # Failed/died, can retry

        if story_type == "daily":
            # Calculate time until midnight UTC
            finished_at = datetime.fromisoformat(
                history["FinishedAt"].replace("Z", "+00:00")
            )
            now = datetime.now(timezone.utc)

            # Check if completion was today
            if finished_at.date() == now.date():
                # Calculate seconds until midnight
                midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
                midnight = midnight.replace(day=midnight.day + 1)
                return int((midnight - now).total_seconds())

            return 0  # Completed on a previous day

    except Exception as err:
        logger.error("Error checking story cooldown", extra={"error": str(err)})
        return 0


def check_prerequisites(character: dict, prerequisites: dict) -> bool:
    """
    Check if character meets story prerequisites.

    Args:
        character: Character data
        prerequisites: Story prerequisite requirements

    Returns:
        True if all prerequisites are met
    """
    # Check minimum skills
    min_skills = prerequisites.get("minSkills", {})
    character_skills = character.get("Skills", {})

    for skill, min_value in min_skills.items():
        if character_skills.get(skill, 0) < min_value:
            return False

    # Check required items
    required_items = prerequisites.get("requiredItems", [])
    if required_items:
        inventory = character.get("Inventory", {})
        inventory_items = list(inventory.values())
        for item_id in required_items:
            if item_id not in inventory_items:
                return False

    # Check required rooms visited
    required_rooms = prerequisites.get("requiredRooms", [])
    if required_rooms:
        pass

    return True


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
    character = get_character_with_ownership(character_id, player_id)

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

    if not available_story_ids:
        return {"stories": []}

    # Load story details from Story table
    stories = []

    for story_id in available_story_ids:
        try:
            story = dynamo.get_item(TableName.STORY, {"StoryID": story_id})
            if not story:
                logger.warning("Story not found", extra={"story_id": story_id})
                continue

            # Check prerequisites
            prerequisites = story.get("Prerequisites", {})
            if not check_prerequisites(character, prerequisites):
                continue

            # Check cooldown
            story_type = story.get("StoryType", "repeatable")
            cooldown = get_story_cooldown(character_id, story_id, story_type)

            if cooldown == -1:  # Permanently unavailable
                continue

            # Format story for response
            story_data = {
                "storyId": story_id,
                "title": story.get("Title", "Unknown Story"),
                "description": story.get("Description", ""),
                "type": story_type,
                "available": cooldown == 0,
                "cooldownRemaining": max(0, cooldown) if cooldown is not None else 0,
                "estimatedDuration": int(story.get("EstimatedDuration", 0)),
            }

            stories.append(story_data)
            logger.debug(
                "Story processed",
                extra={
                    "story_id": story_id,
                    "story_type": story_type,
                    "available": story_data["available"],
                    "cooldown": cooldown,
                },
            )

        except ClientError as err:
            logger.error(
                "Error loading story",
                extra={
                    "story_id": story_id,
                    "error": str(err),
                    "error_code": err.response.get("Error", {}).get("Code", "Unknown")
                },
            )
            continue

    # Sort stories by availability and title
    stories.sort(key=lambda s: (not s["available"], s["title"]))

    logger.info(
        "Stories retrieved successfully",
        extra={
            "character_id": character_id,
            "total_stories": len(stories),
            "available_stories": sum(1 for s in stories if s["available"]),
        },
    )

    return {"stories": stories}


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

    try:
        # Extract and validate player ID
        player_id, auth_error = extract_and_validate_player_id(event)
        if auth_error:
            return auth_error

        # Get character ID from query parameters
        character_id, param_error = get_query_parameter(
            event, "characterId", required=True
        ) # type: ignore
        if param_error:
            return build_lambda_response(400, {"error": param_error}, event)

        # Call business logic
        try:
            response_data = get_available_stories_business_logic(character_id, player_id)
            return build_lambda_response(200, response_data, event)
        except ValueError as err:
            logger.warning(
                "Invalid request",
                extra={"character_id": character_id, "error": str(err)},
            )
            error_msg = str(err)
            if "not found" in error_msg.lower():
                return build_lambda_response(
                    404,
                    {"error": "Character not found"},
                    event,
                )
            elif "mode" in error_msg.lower():
                return build_lambda_response(
                    409,
                    {"error": error_msg},
                    event,
                )
            return build_lambda_response(
                400,
                {"error": error_msg},
                event,
            )
        except RuntimeError as err:
            logger.error(
                "Failed to get stories",
                extra={"character_id": character_id, "error": str(err)},
            )
            return build_lambda_response(
                500,
                {"error": "Failed to retrieve stories"},
                event,
            )

    except Exception as err:
        return handle_lambda_error(err, context, event)
