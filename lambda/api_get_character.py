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

import boto3

from eidolon.cors import cors_handler
from eidolon.dynamo import decimal_to_float, get_item_safe
from eidolon.logger import get_logger
from eidolon.requests import extract_player_id, get_query_parameter
from eidolon.responses import create_response, error_response, not_found_response

# Configure logging
logger = get_logger(__name__)

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb")
characters_table = os.environ.get("CHARACTERS_TABLE", "characters")
active_segments_table = os.environ.get("ACTIVE_SEGMENTS_TABLE", "active_segments")

characters_table = dynamodb.Table(characters_table)  # type: ignore
active_segments_table = dynamodb.Table(active_segments_table)  # type: ignore




def get_character_by_id(character_id, player_id):
    """
    Get character by UUID and verify ownership.

    Args:
        character_id: Character UUID
        player_id: Cognito user ID for ownership verification

    Returns:
        Character data or None if not found or not owned by player
    """
    success, result = get_item_safe(
        characters_table,
        {"CharacterID": character_id},
        error_context="getting character"
    )

    if not success:
        return None

    if result == "Item not found":
        return None

    character = result

    # Verify ownership
    if character.get("PlayerID") != player_id:
        logger.warning("Character ownership mismatch", character_id=character_id, player_id=player_id)
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
    success, result = get_item_safe(
        active_segments_table,
        {"PlayerID": player_id},
        error_context="getting active segment"
    )

    if not success or result == "Item not found":
        return None

    return result


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
    logger.log_lambda_event(event, context)

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
            return cors_handler.add_cors_headers(
                error_response(error_msg),
                event
            )

        # Get character data
        character = get_character_by_id(character_id, player_id)

        if not character:
            return cors_handler.add_cors_headers(
                not_found_response("Character"),
                event
            )

        # Get active segment if any
        active_segment = get_active_segment(player_id)

        # Prepare response data
        response_data: dict = {
            "character": decimal_to_float(character),
            "activeSegment": decimal_to_float(active_segment) if active_segment else None,
        }

        # Return success response
        logger.log_response(200)
        return cors_handler.add_cors_headers(
            create_response(200, response_data),
            event
        )

    except Exception as err:
        logger.error("Unexpected error in lambda_handler", error=err)
        logger.log_response(500)
        return cors_handler.add_cors_headers(
            error_response("Internal server error", status_code=500),
            event
        )
