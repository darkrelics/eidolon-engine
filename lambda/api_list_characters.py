"""
Eidolon Engine

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


Lambda function to list character names for an authenticated player.
Returns only character names and death status from the player table.
"""

import os

from eidolon.cors import cors_handler
from eidolon.dynamo import get_item, get_table
from eidolon.logger import get_logger
from eidolon.requests import extract_player_id
from eidolon.responses import create_response, error_response, not_found_response

# Configure logging
logger = get_logger(__name__)

# Get table name from environment
PLAYERS_TABLE = os.environ.get("PLAYERS_TABLE", "players")


def lambda_handler(event, context):
    """
    Lambda handler for listing player characters.

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

    # Log auth details
    headers = event.get("headers", {})
    auth_header = headers.get("Authorization", headers.get("authorization", "NOT PROVIDED"))
    logger.info(f"Authorization header present: {'Bearer' in auth_header}")

    # Log request context authorizer
    request_context = event.get("requestContext", {})
    authorizer = request_context.get("authorizer", {})
    logger.info(f"Authorizer claims: {authorizer.get('claims', 'NO CLAIMS')}")

    # Handle preflight requests
    if event.get("httpMethod") == "OPTIONS":
        return cors_handler.handle_preflight(event)

    try:
        # Extract player ID from Cognito authorizer
        player_id, auth_error = extract_player_id(event)
        if auth_error:
            logger.error("Authentication failed", extra={"error": auth_error})
            return cors_handler.add_cors_headers(error_response(auth_error, status_code=401), event)

        logger.info("Player authenticated", extra={"player_id": player_id})

        # Get player data from players table
        players_table = get_table(PLAYERS_TABLE)
        player_data = get_item(players_table, {"PlayerID": player_id})

        if not player_data:
            logger.warning("Player not found in database", extra={"player_id": player_id})
            return cors_handler.add_cors_headers(not_found_response("Player"), event)
        
        character_list = player_data.get("CharacterList", {})
        logger.info(
            "Player data retrieved", 
            extra={
                "player_id": player_id,
                "character_count": len(character_list)
            }
        )

        # Build character list with name, id, and death status
        characters: list = []
        for char_name, char_info in character_list.items():
            char_data = {
                "name": char_name,
                "id": char_info.get("UUID", ""),
                "dead": char_info.get("Dead", False)
            }
            characters.append(char_data)
            logger.debug(
                "Processing character", 
                extra={
                    "character_name": char_name,
                    "character_id": char_data["id"],
                    "is_dead": char_data["dead"]
                }
            )

        # Sort by name for consistent ordering
        characters.sort(key=lambda x: x["name"])

        # Return success response
        logger.info(
            "Character list prepared successfully", 
            extra={
                "status_code": 200,
                "player_id": player_id,
                "character_count": len(characters),
                "character_names": [c["name"] for c in characters]
            }
        )
        return cors_handler.add_cors_headers(create_response(200, {"characters": characters}), event)

    except Exception as err:
        logger.error("Unexpected error in lambda_handler", extra={"error": str(err)}, exc_info=True)
        logger.info("Lambda response", extra={"status_code": 500})
        return cors_handler.add_cors_headers(error_response("Internal server error", status_code=500), event)
