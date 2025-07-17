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
from eidolon.dynamo import decimal_to_float, get_table, get_item
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
    characters_table = get_table(CHARACTERS_TABLE)
    character = get_item(characters_table, {"CharacterID": character_id})

    if not character:
        return None

    # Verify ownership
    if character.get("PlayerID") != player_id:
        logger.warning("Character ownership mismatch", extra={"character_id": character_id, "player_id": player_id})
        return None

    return character


def get_active_segment(player_id):
    """
    Get active segment for a player if any.

    Args:
        player_id: Cognito user ID

    Returns:
        Active segment data or None
    """
    active_segments_table = get_table(ACTIVE_SEGMENTS_TABLE)
    return get_item(active_segments_table, {"PlayerID": player_id})


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
            return auth_error

        # Get character ID from query parameters
        character_id, error_msg = get_query_parameter(event, "characterId", required=True)
        if error_msg:
            return cors_handler.add_cors_headers(error_response(error_msg), event)

        # Get character data
        character = get_character_by_id(character_id, player_id)

        if not character:
            return cors_handler.add_cors_headers(not_found_response("Character"), event)

        # Get active segment if any
        active_segment = get_active_segment(player_id)

        # Prepare response data
        response_data: dict = {
            "character": decimal_to_float(character),
            "activeSegment": decimal_to_float(active_segment) if active_segment else None,
        }

        # Return success response
        logger.info("Lambda response", extra={"status_code": 200})
        return cors_handler.add_cors_headers(create_response(200, response_data), event)

    except Exception as err:
        logger.error("Unexpected error in lambda_handler", extra={"error": str(err)}, exc_info=True)
        logger.info("Lambda response", extra={"status_code": 500})
        return cors_handler.add_cors_headers(error_response("Internal server error", status_code=500), event)
