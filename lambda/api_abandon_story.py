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


Lambda function to abandon an active story.
Updates character state, marks active segments as abandoned, and updates history.
"""

from datetime import datetime, timezone

from eidolon.cors import cors_handler
from eidolon.dynamo import get_item, get_table, update_item
from eidolon.environment import ACTIVE_SEGMENTS_TABLE, CHARACTERS_TABLE, HISTORY_TABLE
from eidolon.logger import get_logger
from eidolon.requests import extract_player_id, get_required_field, parse_json_body
from eidolon.responses import create_response, error_response, not_found_response
from eidolon.validation import validate_uuid

# Configure logging
logger = get_logger(__name__)


def get_character_and_verify_ownership(character_id: str, player_id: str) -> object:
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


def get_active_story_for_character(character_id: str) -> object:
    """
    Get the active story segment for a character.

    Args:
        character_id: Character UUID

    Returns:
        Active segment data or None if not found
    """
    active_segments_table = get_table(ACTIVE_SEGMENTS_TABLE)

    # Query by CharacterID index
    response = active_segments_table.query(
        IndexName="CharacterID-index",
        KeyConditionExpression="CharacterID = :cid",
        FilterExpression="#status = :status",
        ExpressionAttributeNames={"#status": "Status"},
        ExpressionAttributeValues={":cid": character_id, ":status": "active"},
    )

    items = response.get("Items", [])

    if not items:
        return None

    # Should only be one active segment per character
    return items[0]


def update_character_game_mode(character_id: str) -> None:
    """
    Update character's GameMode back to None.

    Args:
        character_id: Character UUID
    """
    characters_table = get_table(CHARACTERS_TABLE)

    update_item(
        characters_table,
        {"CharacterID": character_id},
        "SET GameMode = :none",
        {},
        {":none": "None"},
    )


def mark_segment_abandoned(active_segment_id: str) -> None:
    """
    Mark an active segment as abandoned.

    Args:
        active_segment_id: Active segment UUID
    """
    active_segments_table = get_table(ACTIVE_SEGMENTS_TABLE)

    update_item(
        active_segments_table,
        {"ActiveSegmentID": active_segment_id},
        "SET #status = :status",
        {"#status": "Status"},
        {":status": "abandoned"},
    )


def update_history_abandoned(character_id: str, story_id: str) -> None:
    """
    Update history to mark story as abandoned.

    Args:
        character_id: Character UUID
        story_id: Story UUID
    """
    history_table = get_table(HISTORY_TABLE)

    # Get existing history entry
    history = get_item(history_table, {"CharacterID": character_id, "StoryID": story_id})

    if history:
        # Increment abandoned count and set finished time
        abandoned_count = history.get("AbandonedCount", 0) + 1

        update_item(
            history_table,
            {"CharacterID": character_id, "StoryID": story_id},
            "SET FinishedAt = :finished, AbandonedCount = :count, FinalOutcome = :outcome",
            {},
            {
                ":finished": datetime.now(timezone.utc).isoformat(),
                ":count": abandoned_count,
                ":outcome": "abandoned",
            },
        )


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to abandon an active story.

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
                "request_id": context.aws_request_id,  # type: ignore
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

        # Parse request body
        body, parse_error = parse_json_body(event)
        if parse_error:
            return cors_handler.add_cors_headers(parse_error, event)

        # Get required fields
        character_id, char_error = get_required_field(body, "characterId")
        if char_error:
            return cors_handler.add_cors_headers(error_response(char_error, status_code=400), event)

        # Validate UUID
        if character_id and not validate_uuid(character_id):
            return cors_handler.add_cors_headers(error_response("Invalid character ID format", status_code=400), event)

        logger.info(
            "Abandoning story",
            extra={"character_id": character_id},
        )

        # Get character and verify ownership
        character: dict = get_character_and_verify_ownership(character_id, player_id)  # type: ignore
        if not character:
            return cors_handler.add_cors_headers(not_found_response("Character"), event)

        # Check if character is in Incremental mode
        game_mode = character.get("GameMode", "None")
        if game_mode != "Incremental":
            logger.warning(
                "Character not in Incremental mode",
                extra={"character_id": character_id, "game_mode": game_mode},
            )
            return cors_handler.add_cors_headers(error_response("Character not in a story", status_code=409), event)

        # Get active story segment
        active_segment: dict = get_active_story_for_character(character_id)  # type: ignore
        if not active_segment:
            logger.warning(
                "No active story found",
                extra={"character_id": character_id},
            )
            return cors_handler.add_cors_headers(error_response("No active story to abandon", status_code=404), event)

        active_segment_id: str = active_segment.get("ActiveSegmentID")  # type: ignore
        story_id = active_segment.get("StoryID")
        story_title = active_segment.get("StoryTitle", "Unknown Story")

        # Update character GameMode back to None
        update_character_game_mode(character_id)  # type: ignore

        # Mark segment as abandoned
        mark_segment_abandoned(active_segment_id)

        # Update history
        update_history_abandoned(character_id, story_id)  # type: ignore

        # Build response
        response_data = {
            "characterId": character_id,
            "storyId": story_id,
            "storyTitle": story_title,
            "status": "abandoned",
            "message": "Story abandoned successfully",
        }

        logger.info(
            "Story abandoned successfully",
            extra={
                "status_code": 200,
                "character_id": character_id,
                "story_id": story_id,
                "active_segment_id": active_segment_id,
            },
        )

        return cors_handler.add_cors_headers(create_response(200, response_data), event)

    except Exception as err:
        logger.error(
            "Unexpected error in lambda_handler",
            extra={"error": str(err)},
            exc_info=True,
        )
        logger.info("Lambda response", extra={"status_code": 500})
        return cors_handler.add_cors_headers(error_response("Internal server error", status_code=500), event)
