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
import logging
import os
import re
import uuid
from datetime import datetime
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

from cors_handler import cors_handler

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb")
players_table = os.environ.get("PLAYERS_TABLE", "players")
characters_table = os.environ.get("CHARACTERS_TABLE", "incremental_characters")
ARCHETYPES_TABLE = os.environ.get("ARCHETYPES_TABLE", "archetypes")

players_table = dynamodb.Table(players_table)
characters_table = dynamodb.Table(characters_table)
archetypes_table = dynamodb.Table(ARCHETYPES_TABLE)

# Character name validation regex (same as server)
NAME_PATTERN = re.compile(r"^[a-zA-Z'-]+$")
MIN_NAME_LENGTH = 4
MAX_NAME_LENGTH = 20


def validate_character_name(name):
    """
    Validate character name according to game rules.

    Args:
        name: Character name to validate

    Returns:
        tuple: (is_valid, error_message)
    """
    if not name:
        return False, "Name cannot be empty"

    if len(name) < MIN_NAME_LENGTH:
        return False, f"Name must be at least {MIN_NAME_LENGTH} characters"

    if len(name) > MAX_NAME_LENGTH:
        return False, f"Name must be {MAX_NAME_LENGTH} characters or fewer"

    if not NAME_PATTERN.match(name):
        return False, "Name must contain only letters, hyphens, and apostrophes"

    # Check for special characters at start/end
    if name[0] in "-'" or name[-1] in "-'":
        return False, "Name cannot start or end with special characters"

    # Check for consecutive special characters
    for i in range(len(name) - 1):
        if name[i] in "-'" and name[i + 1] in "-'":
            return False, "Name cannot have consecutive special characters"

    # Check for excessive repetition
    for i in range(len(name) - 2):
        if name[i] == name[i + 1] == name[i + 2]:
            return False, "Name cannot have more than 2 consecutive identical characters"

    # Check letter ratio for short names with special chars
    if len(name) <= 3 and any(c in "-'" for c in name):
        return False, "Short names cannot contain special characters"

    # Ensure reasonable letter-to-special-character ratio
    letter_count = sum(1 for c in name if c.isalpha())
    if letter_count / len(name) < 0.5:
        return False, "Name must be primarily letters"

    return True, None


def generate_character_id():
    """Generate a UUID v4 for the character ID."""
    return str(uuid.uuid4())


def get_archetype(archetype_name):
    """
    Retrieve and validate an archetype from DynamoDB.

    Args:
        archetype_name: Name of the archetype

    Returns:
        Archetype data or None if not found/not player-available
    """
    try:
        response = archetypes_table.get_item(Key={"ArchetypeName": archetype_name})

        if "Item" not in response:
            logger.warning(f"Archetype not found: {archetype_name}")
            return None

        archetype = response["Item"]

        # Check if archetype is available to players
        if not archetype.get("Player", False):
            logger.warning(f"Archetype not available to players: {archetype_name}")
            return None

        return archetype

    except ClientError as err:
        logger.error(f"Error retrieving archetype: {err}")
        return None


def check_character_limit(player_id):
    """
    Check if player has reached character limit.

    Args:
        player_id: Cognito user ID

    Returns:
        tuple: (can_create, current_count)
    """
    max_characters = int(os.environ.get("MAX_CHARACTERS_PER_PLAYER", "10"))

    try:
        # Get player record
        response = players_table.get_item(Key={"PlayerID": player_id})

        if "Item" not in response:
            logger.error(f"Player not found: {player_id}")
            return False, 0

        player = response["Item"]
        character_list = player.get("CharacterList", {})
        current_count = len(character_list)

        return current_count < max_characters, current_count

    except ClientError as err:
        logger.error(f"Error checking character limit: {err}")
        return False, 0


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
    timestamp = datetime.utcnow().isoformat()

    # Convert float values to Decimal for DynamoDB
    def convert_to_decimal(obj):
        if isinstance(obj, float):
            return Decimal(str(obj))
        elif isinstance(obj, dict):
            return {k: convert_to_decimal(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_to_decimal(v) for v in obj]
        return obj

    # Build character record
    character_item = {
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
        "Inventory": [],
        "Resources": {"gold": 0, "supplies": 10, "reputation": 0},
        "Hidden": False,
        "CharState": "Standing",
        "CreatedAt": timestamp,
        "UpdatedAt": timestamp,
        "LastPlayed": timestamp,
    }

    try:
        # Update player's character list
        character_info = {"UUID": character_id, "Dead": False}

        players_table.update_item(
            Key={"PlayerID": player_id},
            UpdateExpression="SET CharacterList.#name = :info, UpdatedAt = :timestamp",
            ExpressionAttributeNames={"#name": character_name},
            ExpressionAttributeValues={":info": character_info, ":timestamp": timestamp},
        )

        # Create character record
        characters_table.put_item(Item=character_item)

        logger.info(f"Created incremental character {character_name} ({character_id}) for player {player_id}")
        return character_id

    except ClientError as err:
        logger.error(f"Error creating character: {err}")
        # Attempt to rollback player update
        try:
            players_table.update_item(
                Key={"PlayerID": player_id},
                UpdateExpression="REMOVE CharacterList.#name",
                ExpressionAttributeNames={"#name": character_name},
            )
        except ClientError as rollback_err:
            logger.error(f"Failed to rollback player update: {rollback_err}")
        return None


def lambda_handler(event, _):
    """
    Lambda handler for incremental character creation API.

    Args:
        event: API Gateway event with Cognito authorizer
        _: Lambda context (unused)

    Returns:
        API Gateway response
    """
    # Handle preflight requests
    if event.get('httpMethod') == 'OPTIONS':
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
                event
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
                event
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
                event
            )

        # Validate character name
        is_valid, error_msg = validate_character_name(character_name)
        if not is_valid:
            return cors_handler.add_cors_headers(
                {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": f"Invalid character name: {error_msg}"}),
                },
                event
            )

        # Check character limit
        can_create, current_count = check_character_limit(player_id)
        if not can_create:
            return cors_handler.add_cors_headers(
                {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": f"Character limit reached ({current_count})", "currentCount": current_count}),
                },
                event
            )

        # Validate archetype
        archetype_data = get_archetype(archetype_name)
        if not archetype_data:
            return cors_handler.add_cors_headers(
                {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": "Invalid or unavailable archetype"}),
                },
                event
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
                event
            )

        # Return success response
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
            event
        )

    except Exception as err:
        logger.error(f"Unexpected error in lambda_handler: {err}")
        return cors_handler.add_cors_headers(
            {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Internal server error"}),
            },
            event
        )
