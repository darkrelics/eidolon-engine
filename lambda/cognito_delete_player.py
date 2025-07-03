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
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

from eidolon.logger import get_logger

# Configure logging
logger = get_logger(__name__)

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb")

# Table name configuration from environment variables with defaults
TABLES_CONFIG = {
    "players": os.environ.get("PLAYERS_TABLE", "players"),
    "mud_characters": os.environ.get("MUD_CHARACTERS_TABLE", "characters"),
    "incremental_characters": os.environ.get("INCREMENTAL_CHARACTERS_TABLE", "incremental_characters"),
    "active_segments": os.environ.get("ACTIVE_SEGMENTS_TABLE", "active_segments"),
    "character_history": os.environ.get("CHARACTER_HISTORY_TABLE", "character_history"),
}


def delete_player_record(player_id):
    """
    Delete player record from players table.

    Args:
        player_id: Cognito user ID

    Returns:
        bool: True if deleted or not found, False on error
    """
    try:
        table = dynamodb.Table(TABLES_CONFIG["players"])
        table.delete_item(Key={"PlayerID": player_id})
        logger.info("Deleted player record", player_id=player_id)
        return True
    except ClientError as err:
        if err.response["Error"]["Code"] == "ResourceNotFoundException":
            logger.warning(f"Players table not found: {TABLES_CONFIG['players']}")
            return True
        logger.error(f"Error deleting player record: {err}")
        return False


def delete_mud_characters(player_id):
    """
    Delete all MUD characters owned by the player.

    Args:
        player_id: Cognito user ID

    Returns:
        int: Number of characters deleted
    """
    deleted_count = 0
    try:
        table = dynamodb.Table(TABLES_CONFIG["mud_characters"])

        # Scan for all characters owned by this player
        response = table.scan(FilterExpression="PlayerID = :pid", ExpressionAttributeValues={":pid": player_id})

        # Delete each character found
        for item in response.get("Items", []):
            try:
                table.delete_item(Key={"CharacterID": item["CharacterID"]})
                deleted_count += 1
                logger.info(f"Deleted MUD character {item.get('CharacterName', 'Unknown')} ({item['CharacterID']})")
            except ClientError as err:
                logger.error(f"Error deleting MUD character {item['CharacterID']}: {err}")

        # Handle pagination
        while "LastEvaluatedKey" in response:
            response = table.scan(
                FilterExpression="PlayerID = :pid",
                ExpressionAttributeValues={":pid": player_id},
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )

            for item in response.get("Items", []):
                try:
                    table.delete_item(Key={"CharacterID": item["CharacterID"]})
                    deleted_count += 1
                    logger.info(f"Deleted MUD character {item.get('CharacterName', 'Unknown')} ({item['CharacterID']})")
                except ClientError as err:
                    logger.error(f"Error deleting MUD character {item['CharacterID']}: {err}")

        return deleted_count

    except ClientError as err:
        if err.response["Error"]["Code"] == "ResourceNotFoundException":
            logger.warning(f"MUD characters table not found: {TABLES_CONFIG['mud_characters']}")
            return 0
        logger.error(f"Error scanning MUD characters: {err}")
        return deleted_count


def delete_incremental_characters(player_id):
    """
    Delete incremental game character for the player.

    Args:
        player_id: Cognito user ID

    Returns:
        bool: True if deleted or not found, False on error
    """
    try:
        table = dynamodb.Table(TABLES_CONFIG["incremental_characters"])

        # Get character to log its name
        response = table.get_item(Key={"PlayerID": player_id})
        if "Item" in response:
            char_name = response["Item"].get("CharacterName", "Unknown")
            logger.info(f"Deleting incremental character {char_name} for player {player_id}")

        # Delete the character
        table.delete_item(Key={"PlayerID": player_id})
        return True

    except ClientError as err:
        if err.response["Error"]["Code"] == "ResourceNotFoundException":
            logger.warning(f"Incremental characters table not found: {TABLES_CONFIG['incremental_characters']}")
            return True
        logger.error(f"Error deleting incremental character: {err}")
        return False


def delete_active_segments(player_id):
    """
    Delete any active game segments for the player.

    Args:
        player_id: Cognito user ID

    Returns:
        bool: True if deleted or not found, False on error
    """
    try:
        table = dynamodb.Table(TABLES_CONFIG["active_segments"])
        table.delete_item(Key={"PlayerID": player_id})
        logger.info(f"Deleted active segments for {player_id}")
        return True
    except ClientError as err:
        if err.response["Error"]["Code"] == "ResourceNotFoundException":
            logger.warning(f"Active segments table not found: {TABLES_CONFIG['active_segments']}")
            return True
        logger.error(f"Error deleting active segments: {err}")
        return False


def delete_character_history(player_id):
    """
    Delete all character history records for the player.

    Args:
        player_id: Cognito user ID

    Returns:
        int: Number of history records deleted
    """
    deleted_count = 0
    try:
        table = dynamodb.Table(TABLES_CONFIG["character_history"])

        # Query all history records for this player
        response = table.query(KeyConditionExpression="PlayerID = :pid", ExpressionAttributeValues={":pid": player_id})

        # Delete each history record
        for item in response.get("Items", []):
            try:
                table.delete_item(Key={"PlayerID": player_id, "Timestamp": item["Timestamp"]})
                deleted_count += 1
            except ClientError as err:
                logger.error("Error deleting history record", error=err)

        # Handle pagination
        while "LastEvaluatedKey" in response:
            response = table.query(
                KeyConditionExpression="PlayerID = :pid",
                ExpressionAttributeValues={":pid": player_id},
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )

            for item in response.get("Items", []):
                try:
                    table.delete_item(Key={"PlayerID": player_id, "Timestamp": item["Timestamp"]})
                    deleted_count += 1
                except ClientError as err:
                    logger.error("Error deleting history record", error=err)

        logger.info("Deleted history records", count=deleted_count, player_id=player_id)
        return deleted_count

    except ClientError as err:
        if err.response["Error"]["Code"] == "ResourceNotFoundException":
            logger.warning("Character history table not found", table_name=TABLES_CONFIG["character_history"])
            return 0
        logger.error("Error querying character history", error=err)
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
    try:
        player_id = None

        # Extract player ID based on event source
        if "detail" in event and "requestParameters" in event.get("detail", {}):
            # CloudWatch Events from Cognito
            player_id = event["detail"]["requestParameters"].get("username")
        elif "body" in event:
            # API Gateway or direct invocation
            body = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]
            player_id = body.get("player_id")
        elif "player_id" in event:
            # Direct invocation
            player_id = event["player_id"]
        elif "requestContext" in event and "authorizer" in event["requestContext"]:
            # API Gateway with Cognito authorizer
            claims = event["requestContext"]["authorizer"].get("claims", {})
            player_id = claims.get("sub")

        if not player_id:
            logger.error("No player ID provided in request")
            return {"statusCode": 400, "body": json.dumps({"error": "Player ID required"})}

        logger.info(f"Starting deletion process for player {player_id}")

        # Track deletion results
        results = {
            "player_id": player_id,
            "timestamp": datetime.utcnow().isoformat(),
            "deletions": {
                "player_record": False,
                "mud_characters": 0,
                "incremental_character": False,
                "active_segments": False,
                "character_history": 0,
            },
            "errors": [],
        }

        # Delete from each table
        try:
            results["deletions"]["player_record"] = delete_player_record(player_id)
        except Exception as err:
            logger.error(f"Unexpected error deleting player record: {err}")
            results["errors"].append(f"Player record: {str(err)}")

        try:
            results["deletions"]["mud_characters"] = delete_mud_characters(player_id)
        except Exception as err:
            logger.error(f"Unexpected error deleting MUD characters: {err}")
            results["errors"].append(f"MUD characters: {str(err)}")

        try:
            results["deletions"]["incremental_character"] = delete_incremental_characters(player_id)
        except Exception as err:
            logger.error(f"Unexpected error deleting incremental character: {err}")
            results["errors"].append(f"Incremental character: {str(err)}")

        try:
            results["deletions"]["active_segments"] = delete_active_segments(player_id)
        except Exception as err:
            logger.error(f"Unexpected error deleting active segments: {err}")
            results["errors"].append(f"Active segments: {str(err)}")

        try:
            results["deletions"]["character_history"] = delete_character_history(player_id)
        except Exception as err:
            logger.error(f"Unexpected error deleting character history: {err}")
            results["errors"].append(f"Character history: {str(err)}")

        # Log summary
        logger.info(f"Deletion summary for {player_id}: {json.dumps(results)}")

        # Return appropriate response based on event source
        if "requestContext" in event:
            # API Gateway response format
            return {
                "statusCode": 200 if not results["errors"] else 207,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps(results),
            }
        else:
            # Direct invocation response
            return results

    except Exception as err:
        logger.error(f"Unexpected error in lambda_handler: {err}")

        if "requestContext" in event:
            return {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Internal server error"}),
            }
        else:
            raise
