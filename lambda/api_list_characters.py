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

import boto3

from eidolon.cors import cors_handler
from eidolon.dynamo import get_item_safe
from eidolon.logger import get_logger
from eidolon.requests import extract_player_id
from eidolon.responses import create_response, error_response, not_found_response

# Configure logging
logger = get_logger(__name__)

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb")
players_table: str = os.environ.get("PLAYERS_TABLE", "players")

players_table = dynamodb.Table(players_table)  # type: ignore


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
    logger.log_lambda_event(event, context)

    try:
        # Extract player ID from Cognito authorizer
        player_id, auth_error = extract_player_id(event)
        if auth_error:
            return auth_error

        # Get player data from players table
        success, result = get_item_safe(players_table, {"PlayerID": player_id}, error_context="getting player data")

        if not success:
            return cors_handler.add_cors_headers(error_response("Database error", status_code=500), event)

        if result == "Item not found":
            return cors_handler.add_cors_headers(not_found_response("Player"), event)

        player_data = result
        character_list = player_data.get("CharacterList", {})

        # Build character list with name and death status
        characters: list = []
        for char_name, char_info in character_list.items():
            characters.append({"name": char_name, "dead": char_info.get("Dead", False)})

        # Sort by name for consistent ordering
        characters.sort(key=lambda x: x["name"])

        # Return success response
        logger.log_response(200)
        return cors_handler.add_cors_headers(create_response(200, {"characters": characters}), event)

    except Exception as err:
        logger.error("Unexpected error in lambda_handler", error=err)
        logger.log_response(500)
        return cors_handler.add_cors_headers(error_response("Internal server error", status_code=500), event)
