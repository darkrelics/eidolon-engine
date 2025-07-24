"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason Robinson

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.


Lambda function to get available stories for a character.
Returns stories the character can participate in, checking prerequisites and cooldowns.
"""

import os
from datetime import datetime, timezone

from eidolon.cors import cors_handler
from eidolon.dynamo import decimal_to_float, get_item, get_table
from eidolon.logger import get_logger
from eidolon.requests import extract_player_id, get_query_parameter
from eidolon.responses import create_response, error_response, not_found_response
from eidolon.validation_utils import validate_uuid

# Configure logging
logger = get_logger(__name__)

# Get table names from environment
CHARACTERS_TABLE = os.environ.get("CHARACTERS_TABLE", "characters")
STORY_TABLE = os.environ.get("STORY_TABLE", "story")
HISTORY_TABLE = os.environ.get("HISTORY_TABLE", "history")


def get_character_and_verify_ownership(character_id, player_id):
    """
    Get character by UUID and verify ownership.

    Args:
        character_id: Character UUID
        player_id: Cognito user ID for ownership verification

    Returns:
        Character data or None if not found or not owned by player
    """
    characters_table = get_table(CHARACTERS_TABLE)
    character = get_item(characters_table, {"CharacterID": character_id})

    if not character:
        logger.warning("Character not found", extra={"character_id": character_id})
        return None

    # Verify ownership
    if character.get("PlayerID") != player_id:
        logger.warning(
            "Character ownership mismatch",
            extra={"character_id": character_id, "player_id": player_id},
        )
        return None

    return character


def get_story_cooldown(character_id, story_id, story_type):
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
    history_table = get_table(HISTORY_TABLE)
    try:
        response = history_table.get_item(Key={"CharacterID": character_id, "StoryID": story_id})
        history = response.get("Item")

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
            finished_at = datetime.fromisoformat(history["FinishedAt"].replace("Z", "+00:00"))
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


def check_prerequisites(character, prerequisites):
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
        # TODO: Implement room visit tracking
        # For now, we'll skip this check
        pass

    return True


def lambda_handler(event, context):
    """
    Lambda handler to get available stories for a character.

    Args:
        event: API Gateway Lambda proxy event
        context: Lambda context

    Returns:
        API Gateway Lambda proxy response
    """
    # Log Lambda invocation
    if hasattr(context, "aws_request_id"):
        logger.info(
            "Lambda invocation",
            extra={
                "request_id": context.aws_request_id,
                "function_name": getattr(context, "function_name", "unknown"),
                "http_method": event.get("httpMethod"),
                "path": event.get("path"),
            },
        )

    # Handle preflight requests
    if event.get("httpMethod") == "OPTIONS":
        return cors_handler.handle_preflight(event)

    try:
        # Extract player ID from authorizer
        player_id, auth_error = extract_player_id(event)
        if auth_error:
            logger.error("Authentication failed", extra={"error": auth_error})
            return cors_handler.add_cors_headers(error_response(auth_error, status_code=401), event)

        logger.info("Player authenticated", extra={"player_id": player_id})

        # Get character ID from query parameters
        character_id, param_error = get_query_parameter(event, "characterId", required=True)
        if param_error:
            return cors_handler.add_cors_headers(
                error_response(param_error, status_code=400), event
            )

        # Validate character ID format
        if not validate_uuid(character_id):
            return cors_handler.add_cors_headers(
                error_response("Invalid character ID format", status_code=400), event
            )

        # Get character and verify ownership
        character = get_character_and_verify_ownership(character_id, player_id)
        if not character:
            return cors_handler.add_cors_headers(not_found_response("Character"), event)

        # Check if character is in a valid state for stories
        game_mode = character.get("GameMode", "None")
        if game_mode not in ["None", "Incremental"]:
            return cors_handler.add_cors_headers(
                error_response(f"Character is currently in {game_mode} mode", status_code=409), event
            )

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
            return cors_handler.add_cors_headers(
                create_response(200, {"stories": []}), event
            )

        # Load story details from Story table
        story_table = get_table(STORY_TABLE)
        stories = []

        for story_id in available_story_ids:
            try:
                story = get_item(story_table, {"StoryID": story_id})
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
                    "estimatedDuration": int(story.get("EstimatedDuration", 0))
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

            except Exception as err:
                logger.error("Error loading story", extra={"story_id": story_id, "error": str(err)})
                continue

        # Sort stories by availability and title
        stories.sort(key=lambda s: (not s["available"], s["title"]))

        logger.info(
            "Stories retrieved successfully",
            extra={
                "status_code": 200,
                "character_id": character_id,
                "total_stories": len(stories),
                "available_stories": sum(1 for s in stories if s["available"]),
            },
        )

        response_dict = {"stories": stories}
        # decimal_to_float preserves dict structure, just converts Decimal to float
        response_data = decimal_to_float(response_dict)
        # Type assertion - we know response_data is a dict because we passed a dict
        return cors_handler.add_cors_headers(create_response(200, response_data), event)  # type: ignore

    except Exception as err:
        logger.error("Unexpected error in lambda_handler", extra={"error": str(err)}, exc_info=True)
        logger.info("Lambda response", extra={"status_code": 500})
        return cors_handler.add_cors_headers(
            error_response("Internal server error", status_code=500), event
        )