"""
Eidolon Engine - Player Deletion Handler

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


Lambda function to handle complete player deletion including all associated
game data from both MUD and Incremental game tables. This ensures GDPR
compliance by removing all traces of user data.
"""

import json
import os
from datetime import datetime, timezone

import boto3

from eidolon.dynamo import get_table, delete_item, scan_all_items
from eidolon.logger import get_logger
from eidolon.requests import extract_player_id, parse_json_body
from eidolon.responses import create_response, error_response

# Configure logging
logger = get_logger(__name__)

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb")

# Table name configuration from environment variables with defaults
TABLES_CONFIG: dict = {
    "players": os.environ.get("PLAYERS_TABLE", "players"),
    "characters": os.environ.get("CHARACTERS_TABLE", "characters"),
    "active_segments": os.environ.get("ACTIVE_SEGMENTS_TABLE", "active_segments"),
    "character_history": os.environ.get("CHARACTER_HISTORY_TABLE", "character_history"),
}


def delete_player_record(player_id: str) -> bool:
    """
    Delete player record from players table.

    Args:
        player_id: Cognito user ID

    Returns:
        bool: True if deleted or not found, False on error
    """
    table = get_table(TABLES_CONFIG["players"])
    if delete_item(table, {"PlayerID": player_id}):
        logger.info("Deleted player record", extra={"player_id": player_id})
        return True
    return False


def delete_all_characters(player_id: str) -> int:
    """
    Delete all characters (both MUD and Incremental) owned by the player.

    Args:
        player_id: Cognito user ID

    Returns:
        int: Number of characters deleted
    """
    deleted_count = 0
    try:
        table = get_table(TABLES_CONFIG["characters"])

        # Scan for all characters owned by this player
        success, result = scan_all_items(table, filter_expression="PlayerID = :pid", expression_values={":pid": player_id})

        if not success:
            logger.error("Failed to scan characters", extra={"error": result})
            return 0

        items = result if isinstance(result, list) else []

        # Delete each character found
        for item in items:
            if delete_item(table, {"CharacterID": item["CharacterID"]}):
                deleted_count += 1
                game_mode = item.get("GameMode", "Unknown")
                logger.info(
                    "Deleted character",
                    extra={
                        "game_mode": game_mode,
                        "character_name": item.get("CharacterName", "Unknown"),
                        "character_id": item["CharacterID"],
                    },
                )

        return deleted_count

    except Exception as err:
        logger.error("Error in delete_all_characters", extra={"error": str(err)}, exc_info=True)
        return deleted_count


# Note: Incremental characters are now handled by delete_all_characters since they share the same table


def delete_active_segments(player_id: str) -> bool:
    """
    Delete any active game segments for the player.

    Args:
        player_id: Cognito user ID

    Returns:
        bool: True if deleted or not found, False on error
    """
    table = get_table(TABLES_CONFIG["active_segments"])
    if delete_item(table, {"PlayerID": player_id}):
        logger.info("Deleted active segments", extra={"player_id": player_id})
        return True
    return False


def delete_character_history(player_id: str) -> int:
    """
    Delete all character history records for the player.

    Args:
        player_id: Cognito user ID

    Returns:
        int: Number of history records deleted
    """
    deleted_count = 0
    try:
        table = get_table(TABLES_CONFIG["character_history"])

        # Query all history records for this player
        response = table.query(KeyConditionExpression="PlayerID = :pid", ExpressionAttributeValues={":pid": player_id})

        # Delete each history record
        for item in response.get("Items", []):
            if delete_item(table, {"PlayerID": player_id, "Timestamp": item["Timestamp"]}):
                deleted_count += 1

        # Handle pagination
        while "LastEvaluatedKey" in response:
            response = table.query(
                KeyConditionExpression="PlayerID = :pid",
                ExpressionAttributeValues={":pid": player_id},
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )

            for item in response.get("Items", []):
                if delete_item(table, {"PlayerID": player_id, "Timestamp": item["Timestamp"]}):
                    deleted_count += 1

        logger.info("Deleted history records", extra={"count": deleted_count, "player_id": player_id})
        return deleted_count

    except Exception as err:
        logger.error("Error in delete_character_history", extra={"error": str(err)}, exc_info=True)
        return deleted_count


def lambda_handler(event, context):
    """
    Lambda handler for complete player data deletion.

    Can be triggered by:
    1. Direct invocation with player_id in body
    2. CloudWatch Events from Cognito user deletion
    3. API Gateway with authenticated request

    Args:
        event: Lambda event
        context: Lambda context

    Returns:
        Response with deletion summary
    """
    # Log Lambda invocation
    if hasattr(context, "aws_request_id"):
        logger.info(
            "Lambda invocation",
            extra={
                "request_id": context.aws_request_id,
                "function_name": getattr(context, "function_name", "unknown"),
            },
        )

    try:
        player_id = None

        # Extract player ID based on event source
        if "detail" in event and "requestParameters" in event.get("detail", {}):
            # CloudWatch Events from Cognito
            player_id = event["detail"]["requestParameters"].get("username")
        elif "body" in event:
            # API Gateway or direct invocation
            body, _ = parse_json_body(event) if isinstance(event.get("body"), str) else (event.get("body", {}), None)
            player_id = body.get("player_id") if body else None
        elif "player_id" in event:
            # Direct invocation
            player_id = event["player_id"]
        elif "requestContext" in event and "authorizer" in event["requestContext"]:
            # API Gateway with Cognito authorizer
            player_id, _ = extract_player_id(event)

        if not player_id:
            logger.error("No player ID provided in request")
            if "requestContext" in event:
                return create_response(400, {"error": "Player ID required"})
            return {"statusCode": 400, "body": json.dumps({"error": "Player ID required"})}

        logger.info("Starting deletion process", extra={"player_id": player_id})

        # Track deletion results
        results: dict = {
            "player_id": player_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "deletions": {
                "player_record": False,
                "all_characters": 0,
                "active_segments": False,
                "character_history": 0,
            },
            "errors": [],
        }

        # Delete from each table
        try:
            results["deletions"]["player_record"] = delete_player_record(player_id)
        except Exception as err:
            logger.error("Unexpected error deleting player record", extra={"error": str(err)}, exc_info=True)
            results["errors"].append(f"Player record: {str(err)}")

        try:
            results["deletions"]["all_characters"] = delete_all_characters(player_id)
        except Exception as err:
            logger.error("Unexpected error deleting characters", extra={"error": str(err)}, exc_info=True)
            results["errors"].append(f"Characters: {str(err)}")

        try:
            results["deletions"]["active_segments"] = delete_active_segments(player_id)
        except Exception as err:
            logger.error("Unexpected error deleting active segments", extra={"error": str(err)}, exc_info=True)
            results["errors"].append(f"Active segments: {str(err)}")

        try:
            results["deletions"]["character_history"] = delete_character_history(player_id)
        except Exception as err:
            logger.error("Unexpected error deleting character history", extra={"error": str(err)}, exc_info=True)
            results["errors"].append(f"Character history: {str(err)}")

        # Log summary
        logger.info("Deletion complete", extra={"player_id": player_id, "summary": results})

        # Return appropriate response based on event source
        if "requestContext" in event:
            # API Gateway response format
            status_code = 200 if not results["errors"] else 207
            logger.info("Lambda response", extra={"status_code": status_code})
            return create_response(status_code, results)
        else:
            # Direct invocation response
            return results

    except Exception as err:
        logger.error("Unexpected error in lambda_handler", extra={"error": str(err)}, exc_info=True)
        logger.info("Lambda response", extra={"status_code": 500})

        if "requestContext" in event:
            return error_response("Internal server error", status_code=500)
        else:
            raise
