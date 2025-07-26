"""
Eidolon Engine - Player Deletion Handler

Copyright 2024-2025 Jason E. Robinson

Lambda function to handle complete player deletion including all associated
game data from both MUD and Incremental game tables. This ensures GDPR
compliance by removing all traces of user data.
"""

import json
from datetime import datetime
from datetime import timezone

from eidolon.character import delete_character
from eidolon.dynamo import dynamo
from eidolon.dynamo import TableName
from eidolon.logger import get_logger
from eidolon.requests import extract_player_id
from eidolon.requests import parse_json_body
from eidolon.responses import create_response
from eidolon.responses import error_response

# Configure logging
logger = get_logger(__name__)


def delete_player_record(player_id: str) -> bool:
    """
    Delete player record from players table.

    Args:
        player_id: Cognito user ID

    Returns:
        bool: True if deleted or not found, False on error
    """
    try:
        dynamo.delete_item(TableName.PLAYERS, Key={"PlayerID": player_id})
        logger.info("Deleted player record", extra={"player_id": player_id})
        return True
    except Exception as err:
        logger.error(
            "Failed to delete player record",
            extra={"error": str(err), "player_id": player_id},
        )
        return False


def delete_all_characters(player_id: str) -> dict:
    """
    Delete all characters (both MUD and Incremental) owned by the player.

    Args:
        player_id: Cognito user ID

    Returns:
        dict: Summary of deletion results
    """
    results = {
        "characters_deleted": 0,
        "items_deleted": 0,
        "active_segments_deleted": 0,
        "history_deleted": 0,
        "errors": [],
    }

    try:
        player = dynamo.get_item(TableName.PLAYERS, {"PlayerID": player_id})

        if not player:
            logger.warning(
                "Player not found for character deletion",
                extra={"player_id": player_id},
            )
            return results

        character_list = player.get("CharacterList", {})

        for character_name, character_info in character_list.items():
            character_id = character_info.get("UUID")
            if character_id:
                try:
                    # No need to verify ownership here since we're getting characters from player's own list
                    deletion_result = delete_character(
                        character_id, remove_from_player_list=False
                    )

                    if deletion_result["character_deleted"]:
                        results["characters_deleted"] += 1
                    results["items_deleted"] += deletion_result["items_deleted"]
                    results["active_segments_deleted"] += deletion_result[
                        "active_segments_deleted"
                    ]
                    results["history_deleted"] += deletion_result["history_deleted"]

                    if deletion_result["errors"]:
                        results["errors"].extend(deletion_result["errors"])

                    logger.info(
                        "Processed character deletion",
                        extra={
                            "character_name": character_name,
                            "character_id": character_id,
                            "game_mode": character_info.get("GameMode", "Unknown"),
                            "deletion_result": deletion_result,
                        },
                    )
                except Exception as err:
                    logger.error(
                        "Failed to delete character",
                        extra={
                            "error": str(err),
                            "character_id": character_id,
                            "character_name": character_name,
                        },
                    )
                    results["errors"].append(
                        f"Failed to delete character {character_name} ({character_id}): {str(err)}"
                    )

        logger.info(
            "Completed deleting all characters",
            extra={"player_id": player_id, "results": results},
        )
        return results

    except Exception as err:
        logger.error(
            "Error in delete_all_characters", extra={"error": str(err)}, exc_info=True
        )
        results["errors"].append(f"General error: {str(err)}")
        return results


def delete_active_segments(player_id: str) -> int:
    """
    Delete any active game segments for the player.

    Args:
        player_id: Cognito user ID

    Returns:
        int: Number of segments deleted
    """
    deleted_count = 0
    try:
        items = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            KeyConditionExpression="PlayerID = :pid",
            ExpressionAttributeValues={":pid": player_id},
        )

        for item in items:  # type: ignore
            try:
                dynamo.delete_item(
                    TableName.ACTIVE_SEGMENTS,
                    Key={"ActiveSegmentID": item["ActiveSegmentID"]},
                )
                deleted_count += 1
            except Exception as err:
                logger.error(
                    "Failed to delete active segment",
                    extra={"error": str(err), "segment_id": item["ActiveSegmentID"]},
                )

        logger.info(
            "Deleted active segments",
            extra={"player_id": player_id, "count": deleted_count},
        )
        return deleted_count
    except Exception as err:
        logger.error(
            "Error deleting active segments",
            extra={"error": str(err), "player_id": player_id},
        )
        return deleted_count


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
        items = dynamo.query(
            TableName.CHARACTER_HISTORY,
            KeyConditionExpression="PlayerID = :pid",
            ExpressionAttributeValues={":pid": player_id},
        )

        for item in items:  # type: ignore
            try:
                dynamo.delete_item(
                    TableName.CHARACTER_HISTORY,
                    Key={"PlayerID": player_id, "Timestamp": item["Timestamp"]},
                )
                deleted_count += 1
            except Exception as err:
                logger.error(
                    "Failed to delete history record",
                    extra={"error": str(err), "timestamp": item["Timestamp"]},
                )

        logger.info(
            "Deleted history records",
            extra={"count": deleted_count, "player_id": player_id},
        )
        return deleted_count

    except Exception as err:
        logger.error(
            "Error in delete_character_history",
            extra={"error": str(err)},
            exc_info=True,
        )
        return deleted_count


def lambda_handler(event: dict, context: object) -> dict:
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
                "request_id": context.aws_request_id,  # type: ignore
                "function_name": getattr(context, "function_name", "unknown"),
            },
        )

    try:
        player_id = None

        if "detail" in event and "requestParameters" in event.get("detail", {}):
            # CloudWatch Events from Cognito
            player_id = event["detail"]["requestParameters"].get("username")
        elif "body" in event:
            # API Gateway or direct invocation
            body, _ = (
                parse_json_body(event)
                if isinstance(event.get("body"), str)
                else (event.get("body", {}), None)
            )
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
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Player ID required"}),
            }

        logger.info("Starting deletion process", extra={"player_id": player_id})

        # Track deletion results
        results: dict = {
            "player_id": player_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "deletions": {
                "player_record": False,
                "characters": 0,
                "items": 0,
                "active_segments": 0,
                "character_history": 0,
                "story_history": 0,
            },
            "errors": [],
        }

        try:
            results["deletions"]["player_record"] = delete_player_record(player_id)
        except Exception as err:
            logger.error(
                "Unexpected error deleting player record",
                extra={"error": str(err)},
                exc_info=True,
            )
            results["errors"].append(f"Player record: {str(err)}")

        try:
            char_deletion_results = delete_all_characters(player_id)
            results["deletions"]["characters"] = char_deletion_results[
                "characters_deleted"
            ]
            results["deletions"]["items"] = char_deletion_results["items_deleted"]
            results["deletions"]["active_segments"] += char_deletion_results[
                "active_segments_deleted"
            ]
            results["deletions"]["story_history"] = char_deletion_results[
                "history_deleted"
            ]
            if char_deletion_results["errors"]:
                results["errors"].extend(char_deletion_results["errors"])
        except Exception as err:
            logger.error(
                "Unexpected error deleting characters",
                extra={"error": str(err)},
                exc_info=True,
            )
            results["errors"].append(f"Characters: {str(err)}")

        try:
            # Additional active segments not covered by character deletion
            # (e.g., segments with PlayerID but no CharacterID)
            additional_segments = delete_active_segments(player_id)
            results["deletions"]["active_segments"] += additional_segments
        except Exception as err:
            logger.error(
                "Unexpected error deleting active segments",
                extra={"error": str(err)},
                exc_info=True,
            )
            results["errors"].append(f"Active segments: {str(err)}")

        try:
            # Additional character history not covered by character deletion
            additional_history = delete_character_history(player_id)
            results["deletions"]["character_history"] = additional_history
        except Exception as err:
            logger.error(
                "Unexpected error deleting character history",
                extra={"error": str(err)},
                exc_info=True,
            )
            results["errors"].append(f"Character history: {str(err)}")

        # Log summary
        logger.info(
            "Deletion complete", extra={"player_id": player_id, "summary": results}
        )

        # Return appropriate response based on event source
        if "requestContext" in event:
            # API Gateway response format
            status_code = 200 if not results["errors"] else 207
            logger.info("Lambda response", extra={"status_code": status_code})
            return create_response(status_code, results)
        return results

    except Exception as err:
        logger.error(
            "Unexpected error in lambda_handler",
            extra={"error": str(err)},
            exc_info=True,
        )
        logger.info("Lambda response", extra={"status_code": 500})

        if "requestContext" in event:
            return error_response("Internal server error", status_code=500)
        raise
