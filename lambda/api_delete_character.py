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


Lambda function to delete a character for an authenticated player.
Ensures the character belongs to the player before deletion.
"""

import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

from eidolon.cors import cors_handler

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb")
players_table = os.environ.get("PLAYERS_TABLE", "players")
characters_table = os.environ.get("CHARACTERS_TABLE", "characters")
items_table = os.environ.get("ITEMS_TABLE", "items")

players_table = dynamodb.Table(players_table)
characters_table = dynamodb.Table(characters_table)
items_table = dynamodb.Table(items_table)


def verify_character_ownership(player_id, character_name):
    """
    Verify that a character belongs to the specified player.

    Args:
        player_id: Cognito user ID
        character_name: Name of the character to verify

    Returns:
        tuple: (is_owner, character_uuid)
    """
    try:
        # Get player record
        response = players_table.get_item(Key={"PlayerID": player_id})

        if "Item" not in response:
            logger.warning(f"Player not found: {player_id}")
            return False, None

        player_data = response["Item"]
        character_list = player_data.get("CharacterList", {})

        # Check if character exists in player's list
        if character_name not in character_list:
            logger.warning(f"Character {character_name} not found for player {player_id}")
            return False, None

        character_info = character_list[character_name]
        character_uuid = character_info.get("UUID")

        # Double-check character record ownership
        char_response = characters_table.get_item(Key={"CharacterID": character_uuid})
        if "Item" in char_response:
            character_data = char_response["Item"]
            if character_data.get("PlayerID") != player_id:
                logger.warning(f"Character {character_uuid} does not belong to player {player_id}")
                return False, None

        return True, character_uuid

    except ClientError as err:
        logger.error(f"Error verifying ownership: {err}")
        return False, None


def delete_character_items(character_id):
    """
    Delete all items belonging to a character.

    Args:
        character_id: Character UUID

    Returns:
        int: Number of items deleted
    """
    deleted_count = 0

    try:
        # Get character record to find inventory
        char_response = characters_table.get_item(Key={"CharacterID": character_id})

        if "Item" not in char_response:
            return 0

        character_data = char_response["Item"]
        inventory = character_data.get("Inventory", [])

        # Delete each item
        for item_id in inventory:
            try:
                items_table.delete_item(Key={"ItemID": item_id})
                deleted_count += 1
            except ClientError as err:
                logger.error(f"Error deleting item {item_id}: {err}")

        # Also check for hand items
        left_hand_id = character_data.get("LeftHandID")
        right_hand_id = character_data.get("RightHandID")

        if left_hand_id:
            try:
                items_table.delete_item(Key={"ItemID": left_hand_id})
                deleted_count += 1
            except ClientError:
                pass

        if right_hand_id:
            try:
                items_table.delete_item(Key={"ItemID": right_hand_id})
                deleted_count += 1
            except ClientError:
                pass

        return deleted_count

    except ClientError as err:
        logger.error(f"Error getting character inventory: {err}")
        return deleted_count


def delete_character(player_id, character_name, character_id):
    """
    Delete a character from the database.

    Args:
        player_id: Cognito user ID
        character_name: Name of the character
        character_id: UUID of the character

    Returns:
        bool: True if successful
    """
    try:
        # Delete character items first
        items_deleted = delete_character_items(character_id)
        logger.info(f"Deleted {items_deleted} items for character {character_id}")

        # Delete character from characters table
        try:
            characters_table.delete_item(
                Key={"CharacterID": character_id},
                ConditionExpression="PlayerID = :player_id",
                ExpressionAttributeValues={":player_id": player_id},
            )
        except ClientError as err:
            if err.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.error(f"Character {character_id} does not belong to player {player_id}")
                return False
            raise

        # Remove character from player's character list
        players_table.update_item(
            Key={"PlayerID": player_id},
            UpdateExpression="REMOVE CharacterList.#name",
            ExpressionAttributeNames={"#name": character_name},
            ConditionExpression="attribute_exists(CharacterList.#name)",
            ReturnValues="ALL_NEW",
        )

        logger.info(f"Deleted character {character_name} ({character_id}) for player {player_id}")
        return True

    except ClientError as err:
        logger.error(f"Error deleting character: {err}")
        return False


def lambda_handler(event, _):
    """
    Lambda handler for character deletion API.

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

        # Parse request body
        try:
            body = json.loads(event.get("body", "{}"))
        except json.JSONDecodeError:
            response = {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Invalid JSON"}),
            }
            return cors_handler.add_cors_headers(response, event)

        # Extract character name
        character_name = body.get("characterName", "").strip()

        if not character_name:
            response = {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Missing character name"}),
            }
            return cors_handler.add_cors_headers(response, event)

        # Verify ownership
        is_owner, character_id = verify_character_ownership(player_id, character_name)

        if not is_owner:
            response = {
                "statusCode": 403,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Character not found or access denied"}),
            }
            return cors_handler.add_cors_headers(response, event)

        # Delete the character
        if not delete_character(player_id, character_name, character_id):
            response = {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Failed to delete character"}),
            }
            return cors_handler.add_cors_headers(response, event)

        # Return success response
        response = {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
            },
            "body": json.dumps({"message": "Character deleted successfully", "characterName": character_name}),
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
