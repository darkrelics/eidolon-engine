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
import logging
import os

import boto3
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb")
players_table_name = os.environ.get("PLAYERS_TABLE_NAME", "players")

players_table = dynamodb.Table(players_table_name)


def get_player_data(player_id):
    """
    Get player data including character list and death status.
    
    Args:
        player_id: Cognito user ID
        
    Returns:
        tuple: (character_list, dead_characters)
    """
    try:
        response = players_table.get_item(
            Key={"PlayerID": player_id}
        )
        
        if "Item" not in response:
            logger.warning(f"Player not found: {player_id}")
            return {}, []
        
        player = response["Item"]
        character_list = player.get("CharacterList", {})
        dead_characters = player.get("DeadCharacters", [])
        
        return character_list, dead_characters
        
    except ClientError as err:
        logger.error(f"Error getting player data: {err}")
        return {}, []


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
                "body": json.dumps({"error": "Unauthorized"})
            }
        
        # Get player's character list
        character_list = get_player_characters(player_id)
        
        if not character_list:
            # Return empty list if no characters
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({
                    "characters": [],
                    "count": 0,
                    "message": "No characters found"
                })
            }
        
        # Get details for each character
        characters = []
        for character_name, character_id in character_list.items():
            character_details = get_character_details(character_id)
            if character_details:
                characters.append(character_details)
            else:
                # Include placeholder for missing characters
                characters.append({
                    "characterId": character_id,
                    "characterName": character_name,
                    "error": "Character data not found"
                })
        
        # Sort by last played date (most recent first)
        characters.sort(
            key=lambda x: x.get("lastPlayed", ""),
            reverse=True
        )
        
        # Convert any Decimal values to float for JSON serialization
        characters = decimal_to_float(characters)
        
        # Return character list
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({
                "characters": characters,
                "count": len(characters),
                "playerId": player_id
            })
        }
        
    except Exception as err:
        logger.error(f"Unexpected error in lambda_handler: {err}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Internal server error"})
        }