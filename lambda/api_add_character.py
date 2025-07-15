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


Lambda function to add a new character for the incremental game.
Simplified version without name collision checks since incremental
allows duplicate names.
"""

import json
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from eidolon.character import (
    check_character_limit,
    generate_character_id,
    get_archetype,
)
from eidolon.dynamo import convert_to_decimal
from eidolon.cors import cors_handler
from eidolon.logger import get_logger
from eidolon.validation_utils import validate_character_name

# Configure logging
logger = get_logger(__name__)

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb")
players_table = os.environ.get("PLAYERS_TABLE", "players")
characters_table = os.environ.get("CHARACTERS_TABLE", "characters")
ARCHETYPES_TABLE = os.environ.get("ARCHETYPES_TABLE", "archetypes")

players_table = dynamodb.Table(players_table)  # type: ignore
characters_table = dynamodb.Table(characters_table)  # type: ignore
archetypes_table = dynamodb.Table(ARCHETYPES_TABLE)  # type: ignore





def create_character(player_id, character_name, archetype_name, archetype_data):
    """
    Create a new incremental character in DynamoDB.

    Args:
        player_id: Cognito user ID
        character_name: Name of the character
        archetype_name: Name of the archetype
        archetype_data: Archetype data from DynamoDB

    Returns:
        Character ID if successful, None otherwise
    """
    character_id = generate_character_id()
    timestamp = datetime.now(timezone.utc).isoformat()


    # Build character record
    character_item: dict = {
        "CharacterID": character_id,
        "PlayerID": player_id,
        "CharacterName": character_name,
        "Archetype": archetype_name,
        "Attributes": convert_to_decimal(archetype_data.get("Attributes", {})),
        "Skills": convert_to_decimal(archetype_data.get("Skills", {})),
        "Health": archetype_data.get("Health", 10),
        "MaxHealth": archetype_data.get("Health", 10),
        "Essence": convert_to_decimal(archetype_data.get("Essence", 3)),
        "MaxEssence": convert_to_decimal(archetype_data.get("Essence", 3)),
        "Wounds": [],
        "RoomID": 0,  # Always room 0 for incremental
        "Inventory": {},  # Use MUD inventory structure (slot -> itemID)
        "Resources": {},
        "Progress": {},  # Track story progress flags and achievements
        "StoryState": {  # Track current position in stories
            "currentStoryId": None,
            "currentPassageId": None,
            "startTime": None,
            "abandoned": False,
        },
        "Hidden": False,
        "CharState": "Standing",
        "GameMode": "Incremental",  # Mark as Incremental game character
        "CreatedAt": timestamp,
        "UpdatedAt": timestamp,
        "LastPlayed": timestamp,
    }

    try:
        # Update player's character list
        character_info: dict = {"UUID": character_id, "Dead": False, "GameMode": "Incremental"}

        players_table.update_item(  # type: ignore
            Key={"PlayerID": player_id},
            UpdateExpression="SET CharacterList.#name = :info, UpdatedAt = :timestamp",
            ExpressionAttributeNames={"#name": character_name},
            ExpressionAttributeValues={":info": character_info, ":timestamp": timestamp},
        )

        # Create character record
        characters_table.put_item(Item=character_item)  # type: ignore

        logger.info("Created incremental character", character_name=character_name, character_id=character_id, player_id=player_id)
        return character_id

    except ClientError as err:
        logger.error("Error creating character", error=err, character_name=character_name, player_id=player_id)
        # Attempt to rollback player update
        try:
            players_table.update_item(  # type: ignore
                Key={"PlayerID": player_id},
                UpdateExpression="REMOVE CharacterList.#name",
                ExpressionAttributeNames={"#name": character_name},
            )
        except ClientError as rollback_err:
            logger.error("Failed to rollback player update", error=rollback_err, character_name=character_name)
        return None


def lambda_handler(event, context):
    """
    Lambda handler for incremental character creation API.

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

        # Parse request body
        try:
            body = json.loads(event.get("body", "{}"))
        except json.JSONDecodeError:
            return cors_handler.add_cors_headers(
                {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": "Invalid JSON"}),
                },
                event,
            )

        # Extract and validate required fields
        character_name = body.get("characterName", "").strip()
        archetype_name = body.get("archetype", "").strip()

        if not character_name or not archetype_name:
            return cors_handler.add_cors_headers(
                {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": "Missing required fields"}),
                },
                event,
            )

        # Validate character name format
        is_valid, error_msg = validate_character_name(character_name)
        if not is_valid:
            return cors_handler.add_cors_headers(
                {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": f"Invalid character name: {error_msg}"}),
                },
                event,
            )

        # Check character limit
        can_create, current_count = check_character_limit(player_id, players_table)
        if not can_create:
            return cors_handler.add_cors_headers(
                {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": f"Character limit reached ({current_count})", "currentCount": current_count}),
                },
                event,
            )

        # Validate archetype
        archetype_data = get_archetype(archetype_name, archetypes_table)
        if not archetype_data:
            return cors_handler.add_cors_headers(
                {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": "Invalid or unavailable archetype"}),
                },
                event,
            )

        # Create the character
        character_id = create_character(player_id, character_name, archetype_name, archetype_data)
        if not character_id:
            return cors_handler.add_cors_headers(
                {
                    "statusCode": 500,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": "Failed to create character"}),
                },
                event,
            )

        # Return success response
        logger.log_response(201)
        return cors_handler.add_cors_headers(
            {
                "statusCode": 201,
                "headers": {
                    "Content-Type": "application/json",
                },
                "body": json.dumps(
                    {
                        "characterId": character_id,
                        "characterName": character_name,
                        "archetype": archetype_name,
                        "message": "Character created successfully",
                    }
                ),
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
