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


Lambda function to list incremental characters for an authenticated player.
Returns character names and UUIDs from the player's character list in the
players table.
"""

import json
import os

import boto3
from botocore.exceptions import ClientError

from eidolon.cors_handler import cors_handler
from eidolon.logger import get_logger

# Configure logging
logger = get_logger(__name__)

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb")
players_table = os.environ.get("PLAYERS_TABLE", "players")

players_table = dynamodb.Table(players_table)


def get_player_characters(player_id):
    """
    Get incremental character list from player record.

    Args:
        player_id: Cognito user ID

    Returns:
        List of character names and UUIDs only
    """
    try:
        # Get player data from players table
        response = players_table.get_item(Key={"PlayerID": player_id})

        if "Item" not in response:
            logger.info("No player record found", player_id=player_id)
            return []

        player_data = response["Item"]
        character_list = player_data.get("CharacterList", {})

        if not character_list:
            return []

        # Build list of characters with just name and UUID
        characters = []
        for char_name, char_info in character_list.items():
            # Only include characters that aren't dead for incremental game
            if not char_info.get("Dead", False):
                characters.append({"characterId": char_info.get("UUID"), "characterName": char_name})

        # Sort by character name for consistent ordering
        characters.sort(key=lambda x: x["characterName"])

        return characters

    except ClientError as err:
        logger.error("Error listing characters", error=err)
        raise


def lambda_handler(event, context):
    """
    Lambda handler for listing incremental characters.

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
        claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
        player_id = claims.get("sub")

        if not player_id:
            return cors_handler.add_cors_headers(
                {
                    "statusCode": 401,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": "Unauthorized"}),
                },
                event,
            )

        # Get player's characters
        characters = get_player_characters(player_id)

        logger.log_response(200)
        return cors_handler.add_cors_headers(
            {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                },
                "body": json.dumps({"characters": characters, "count": len(characters)}),
            },
            event,
        )

    except Exception as err:
        logger.error("Unexpected error in lambda_handler", error=err)
        logger.log_response(500)
        return cors_handler.add_cors_headers(
            {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Internal server error"}),
            },
            event,
        )
