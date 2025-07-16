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

import os

import boto3

from eidolon.cors import cors_handler
from eidolon.dynamo import get_table, get_item, delete_item, update_item_with_condition
from eidolon.logger import get_logger
from eidolon.requests import extract_player_id, parse_json_body, validate_required_fields
from eidolon.responses import error_response, success_response

# Configure logging
logger = get_logger(__name__)

# Get table names from environment
PLAYERS_TABLE = os.environ.get("PLAYERS_TABLE", "players")
CHARACTERS_TABLE = os.environ.get("CHARACTERS_TABLE", "characters")
ITEMS_TABLE = os.environ.get("ITEMS_TABLE", "items")


def verify_character_ownership(player_id, character_name) -> tuple:
    """
    Verify that a character belongs to the specified player.

    Args:
        player_id: Cognito user ID
        character_name: Name of the character to verify

    Returns:
        tuple: (is_owner, character_uuid)
    """
    # Get player record
    players_table = get_table(PLAYERS_TABLE)
    player_data = get_item(players_table, {"PlayerID": player_id})

    if not player_data:
        logger.warning("Player not found", extra={"player_id": player_id})
        return False, None
    character_list = player_data.get("CharacterList", {})

    # Check if character exists in player's list
    if character_name not in character_list:
        logger.warning("Character not found for player", extra={"character_name": character_name, "player_id": player_id})
        return False, None

    character_info = character_list[character_name]
    character_uuid = character_info.get("UUID")

    # Double-check character record ownership
    characters_table = get_table(CHARACTERS_TABLE)
    character_data = get_item(characters_table, {"CharacterID": character_uuid})

    if character_data and character_data.get("PlayerID") != player_id:
        logger.warning("Character does not belong to player", extra={"character_id": character_uuid, "player_id": player_id})
        return False, None

    return True, character_uuid


def delete_character_items(character_id) -> int:
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
        characters_table = get_table(CHARACTERS_TABLE)
        character_data = get_item(characters_table, {"CharacterID": character_id})

        if not character_data:
            return 0
        inventory = character_data.get("Inventory", {})

        # Delete each item
        items_table = get_table(ITEMS_TABLE)
        for slot, item_id in inventory.items():
            if delete_item(items_table, {"ItemID": item_id}):
                deleted_count += 1

        # Also check for hand items
        left_hand_id = character_data.get("LeftHandID")
        right_hand_id = character_data.get("RightHandID")

        if left_hand_id:
            if delete_item(items_table, {"ItemID": left_hand_id}):
                deleted_count += 1

        if right_hand_id:
            if delete_item(items_table, {"ItemID": right_hand_id}):
                deleted_count += 1

        return deleted_count

    except Exception as err:
        logger.error("Error processing character items", extra={"error": str(err)})
        return deleted_count


def delete_character(player_id, character_name, character_id) -> bool:
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
        logger.info("Deleted items for character", extra={"items_deleted": items_deleted, "character_id": character_id})

        # Delete character from characters table
        characters_table = get_table(CHARACTERS_TABLE)
        if not delete_item(characters_table, {"CharacterID": character_id}):
            return False

        # Remove character from player's character list
        players_table = get_table(PLAYERS_TABLE)
        success, error_msg = update_item_with_condition(
            players_table,
            {"PlayerID": player_id},
            "REMOVE CharacterList.#name",
            {},
            "attribute_exists(CharacterList.#name)",
            {"#name": character_name},
        )

        if not success:
            logger.error("Failed to remove character from player list", extra={"error": error_msg})
            return False

        logger.info(
            "Deleted character", extra={"character_name": character_name, "character_id": character_id, "player_id": player_id}
        )
        return True

    except Exception as err:
        logger.error("Error deleting character", extra={"error": str(err)})
        return False


def lambda_handler(event, context) -> dict:
    """
    Lambda handler for character deletion API.

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

    # Handle preflight requests
    if event.get("httpMethod") == "OPTIONS":
        return cors_handler.handle_preflight(event)

    try:
        # Extract player ID from Cognito authorizer
        player_id, auth_error = extract_player_id(event)
        if auth_error:
            return auth_error

        # Parse request body
        body, parse_error = parse_json_body(event)
        if parse_error:
            return cors_handler.add_cors_headers(parse_error, event)

        # Validate required fields
        is_valid, error_msg = validate_required_fields(body, ["characterName"])
        if not is_valid:
            return cors_handler.add_cors_headers(error_response(error_msg), event)

        character_name = body["characterName"].strip()

        # Verify ownership
        is_owner, character_id = verify_character_ownership(player_id, character_name)

        if not is_owner:
            return cors_handler.add_cors_headers(error_response("Character not found or access denied", status_code=403), event)

        # Delete the character
        if not delete_character(player_id, character_name, character_id):
            return cors_handler.add_cors_headers(error_response("Failed to delete character", status_code=500), event)

        # Return success response
        logger.info("Lambda response", extra={"status_code": 200})
        return cors_handler.add_cors_headers(
            success_response({"message": "Character deleted successfully", "characterName": character_name}), event
        )

    except Exception as err:
        logger.error("Unexpected error in lambda_handler", extra={"error": str(err)}, exc_info=True)
        logger.info("Lambda response", extra={"status_code": 500})
        return cors_handler.add_cors_headers(error_response("Internal server error", status_code=500), event)
