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


Lambda function to get a character for the incremental game.
Returns the full character data including active segments if any.
"""

import os

from eidolon.cors import cors_handler
from eidolon.dynamo import decimal_to_float, get_item, get_table
from eidolon.logger import get_logger
from eidolon.requests import extract_player_id, get_query_parameter
from eidolon.responses import create_response, error_response, not_found_response

# Configure logging
logger = get_logger(__name__)

# Get table names from environment
CHARACTERS_TABLE = os.environ.get("CHARACTERS_TABLE", "characters")
ACTIVE_SEGMENTS_TABLE = os.environ.get("ACTIVE_SEGMENTS_TABLE", "active_segments")


def get_character_by_id(character_id, player_id):
    """
    Get character by UUID and verify ownership.

    Args:
        character_id: Character UUID
        player_id: Cognito user ID for ownership verification

    Returns:
        Character data or None if not found or not owned by player
    """
    logger.info("Getting character by ID", extra={"character_id": character_id, "player_id": player_id})

    characters_table = get_table(CHARACTERS_TABLE)
    character = get_item(characters_table, {"CharacterID": character_id})

    if not character:
        logger.warning("Character not found", extra={"character_id": character_id})
        return None

    # Verify ownership
    character_owner = character.get("PlayerID")
    if character_owner != player_id:
        logger.warning(
            "Character ownership mismatch",
            extra={"character_id": character_id, "player_id": player_id, "character_owner": character_owner},
        )
        return None

    logger.info(
        "Character retrieved successfully",
        extra={
            "character_id": character_id,
            "character_name": character.get("CharacterName"),
            "game_mode": character.get("GameMode"),
        },
    )
    return character


def get_active_segment(player_id):
    """
    Get active segment for a player if any.

    Args:
        player_id: Cognito user ID

    Returns:
        Active segment data or None
    """
    logger.info("Checking for active segment", extra={"player_id": player_id})

    active_segments_table = get_table(ACTIVE_SEGMENTS_TABLE)
    active_segment = get_item(active_segments_table, {"PlayerID": player_id})

    if active_segment:
        logger.info(
            "Active segment found",
            extra={
                "player_id": player_id,
                "segment_id": active_segment.get("SegmentID"),
                "story_id": active_segment.get("StoryID"),
            },
        )
    else:
        logger.info("No active segment for player", extra={"player_id": player_id})

    return active_segment


def lambda_handler(event, context) -> dict:
    """
    Lambda handler for getting incremental character data.

    Args:
        event: API Gateway event with Cognito authorizer
        context: Lambda context

    Returns:
        API Gateway response
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
        # Extract player ID from Cognito authorizer
        player_id, auth_error = extract_player_id(event)
        if auth_error:
            logger.error("Authentication failed", extra={"error": auth_error})
            return cors_handler.add_cors_headers(error_response(auth_error, status_code=401), event)

        # Get character ID from query parameters
        character_id, error_msg = get_query_parameter(event, "characterId", required=True)
        if error_msg:
            return cors_handler.add_cors_headers(error_response(error_msg), event)

        logger.info("Extracting character ID from query parameters", extra={"character_id": character_id})

        # Get character data
        character = get_character_by_id(character_id, player_id)

        if not character:
            logger.warning("Character not found or access denied", extra={"character_id": character_id, "player_id": player_id})
            return cors_handler.add_cors_headers(not_found_response("Character"), event)

        # Get active segment if any
        active_segment = get_active_segment(player_id)

        # Prepare response data
        response_data: dict = {
            "character": decimal_to_float(character),
            "activeSegment": decimal_to_float(active_segment) if active_segment else None,
        }

        # Return success response
        logger.info(
            "Character data retrieved successfully",
            extra={
                "status_code": 200,
                "character_id": character_id,
                "character_name": character.get("CharacterName"),
                "has_active_segment": active_segment is not None,
            },
        )
        return cors_handler.add_cors_headers(create_response(200, response_data), event)

    except Exception as err:
        logger.error("Unexpected error in lambda_handler", extra={"error": str(err)}, exc_info=True)
        logger.info("Lambda response", extra={"status_code": 500})
        return cors_handler.add_cors_headers(error_response("Internal server error", status_code=500), event)
