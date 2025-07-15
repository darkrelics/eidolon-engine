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


Lambda function to get a character for the incremental game.
Returns the full character data including active segments if any.
"""

import json
import os
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

from eidolon.cors import cors_handler
from eidolon.logger import get_logger

# Configure logging
logger = get_logger(__name__)

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb")
characters_table = os.environ.get("CHARACTERS_TABLE", "characters")
active_segments_table = os.environ.get("ACTIVE_SEGMENTS_TABLE", "active_segments")

characters_table = dynamodb.Table(characters_table) # type: ignore
active_segments_table = dynamodb.Table(active_segments_table) # type: ignore


def decimal_to_float(obj):
    """
    Convert DynamoDB Decimal types to Python float for JSON serialization.

    Args:
        obj: Object to convert

    Returns:
        Converted object
    """
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(v) for v in obj]
    return obj


def get_character_by_id(character_id, player_id):
    """
    Get character by UUID and verify ownership.

    Args:
        character_id: Character UUID
        player_id: Cognito user ID for ownership verification

    Returns:
        Character data or None if not found or not owned by player
    """
    try:
        response = characters_table.get_item(Key={"CharacterID": character_id}) # type: ignore

        if "Item" not in response:
            return None

        character = response["Item"]

        # Verify ownership
        if character.get("PlayerID") != player_id:
            logger.warning("Character ownership mismatch", character_id=character_id, player_id=player_id)
            return None

        return character

    except ClientError as err:
        logger.error("Error getting character", error=err, character_id=character_id)
        return None


def get_active_segment(player_id):
    """
    Get active segment for a player if any.

    Args:
        player_id: Cognito user ID

    Returns:
        Active segment data or None
    """
    try:
        response = active_segments_table.get_item(Key={"PlayerID": player_id}) # type: ignore

        if "Item" in response:
            return response["Item"]

        return None

    except ClientError as err:
        logger.error("Error getting active segment", error=err, player_id=player_id)
        return None


def lambda_handler(event, context) -> dict:
    """
    Lambda handler for getting incremental character data.

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

        # Get character ID from query parameters
        character_id = event.get("queryStringParameters", {}).get("characterId", "").strip()

        if not character_id:
            return cors_handler.add_cors_headers(
                {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": "Missing character ID"}),
                },
                event,
            )

        # Get character data
        character = get_character_by_id(character_id, player_id)

        if not character:
            return cors_handler.add_cors_headers(
                {
                    "statusCode": 404,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": "Character not found"}),
                },
                event,
            )

        # Get active segment if any
        active_segment = get_active_segment(player_id)

        # Prepare response data
        response_data: dict = {
            "character": decimal_to_float(character),
            "activeSegment": decimal_to_float(active_segment) if active_segment else None,
        }

        # Return success response
        logger.log_response(200)
        return cors_handler.add_cors_headers(
            {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                },
                "body": json.dumps(response_data),
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
