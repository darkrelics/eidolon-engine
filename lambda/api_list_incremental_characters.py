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
Returns character names and UUIDs from the incremental_characters table.
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
characters_table_name = os.environ.get("CHARACTERS_TABLE_NAME", "incremental_characters")

characters_table = dynamodb.Table(characters_table_name)


def get_player_characters(player_id):
    """
    Get all incremental characters for a player.
    
    Args:
        player_id: Cognito user ID
        
    Returns:
        List of character summaries (name, uuid, archetype)
    """
    try:
        # Query characters by PlayerID
        # Consider adding a GSI on PlayerID for better performance
        response = characters_table.scan(
            FilterExpression="PlayerID = :pid",
            ExpressionAttributeValues={":pid": player_id},
            ProjectionExpression="CharacterID, CharacterName, Archetype, #h, MaxHealth",
            ExpressionAttributeNames={"#h": "Health"}  # Health is a reserved word
        )
        
        items = response.get("Items", [])
        
        # Handle pagination
        while "LastEvaluatedKey" in response:
            response = characters_table.scan(
                FilterExpression="PlayerID = :pid",
                ExpressionAttributeValues={":pid": player_id},
                ProjectionExpression="CharacterID, CharacterName, Archetype, #h, MaxHealth",
                ExpressionAttributeNames={"#h": "Health"},
                ExclusiveStartKey=response["LastEvaluatedKey"]
            )
            items.extend(response.get("Items", []))
        
        # Build character list
        characters = []
        for item in items:
            characters.append({
                "characterId": item.get("CharacterID"),
                "characterName": item.get("CharacterName"),
                "archetype": item.get("Archetype"),
                "health": float(item.get("Health", 0)),
                "maxHealth": float(item.get("MaxHealth", 0))
            })
        
        # Sort by character name for consistent ordering
        characters.sort(key=lambda x: x["characterName"])
        
        return characters
        
    except ClientError as err:
        logger.error(f"Error listing characters: {err}")
        raise


def lambda_handler(event, _):
    """
    Lambda handler for listing incremental characters.
    
    Args:
        event: API Gateway event with Cognito authorizer
        _: Lambda context (unused)
        
    Returns:
        API Gateway response
    """
    try:
        # Extract player ID from Cognito authorizer
        claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
        player_id = claims.get("sub")
        
        if not player_id:
            return {
                "statusCode": 401,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Unauthorized"}),
            }
        
        # Get player's characters
        characters = get_player_characters(player_id)
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({
                "characters": characters,
                "count": len(characters)
            })
        }
        
    except Exception as err:
        logger.error(f"Unexpected error in lambda_handler: {err}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Internal server error"}),
        }