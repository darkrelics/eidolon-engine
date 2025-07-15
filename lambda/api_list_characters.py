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

import json
import os

import boto3
from botocore.exceptions import ClientError

from eidolon.cors import cors_handler
from eidolon.logger import get_logger

# Configure logging
logger = get_logger(__name__)

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb")
players_table: str = os.environ.get("PLAYERS_TABLE", "players")

players_table = dynamodb.Table(players_table)  # type: ignore


def lambda_handler(event, _):
    """
    Lambda handler for listing player characters.

    Args:
        event: API Gateway event with Cognito authorizer
        _: Lambda context (unused)

    Returns:
        API Gateway response
    """
    try:
        # Extract player ID from Cognito authorizer
        player_id = event.get("requestContext", {}).get("authorizer", {}).get("claims", {}).get("sub")
        if not player_id:
            return {
                "statusCode": 401,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Unauthorized"}),
            }

        # Get player data from players table
        response = players_table.get_item(Key={"PlayerID": player_id})  # type: ignore

        if "Item" not in response:
            return {
                "statusCode": 404,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Player not found"}),
            }

        player_data = response["Item"]
        character_list = player_data.get("CharacterList", {})

        # Build character list with name and death status
        characters: list = []
        for char_name, char_info in character_list.items():
            characters.append({"name": char_name, "dead": char_info.get("Dead", False)})

        # Sort by name for consistent ordering
        characters.sort(key=lambda x: x["name"])

        response: dict = {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
            },
            "body": json.dumps({"characters": characters}),
        }
        return cors_handler.add_cors_headers(response, event)

    except ClientError as err:
        logger.error(f"DynamoDB error: {err}")
        response = {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Database error"}),
        }
        return cors_handler.add_cors_headers(response, event)
    except Exception as err:
        logger.error(f"Unexpected error: {err}")
        response = {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Internal server error"}),
        }
        return cors_handler.add_cors_headers(response, event)
