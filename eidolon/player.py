"""
Player management utilities for Lambda functions.

Provides functions for player authentication and validation.
"""

from datetime import datetime, timezone

from botocore.exceptions import ClientError

from eidolon.character import delete_character
from eidolon.dynamo import TableName, dynamo
from eidolon.logger import get_logger

logger = get_logger(__name__)


def create_player_record(user_uuid: str, email: str) -> None:
    """
    Create a new player record in DynamoDB.

    Args:
        user_uuid: Cognito user UUID (sub)
        email: User's email address

    Raises:
        ValueError: If user_uuid or email is missing
        RuntimeError: If database operations fail
    """
    if not user_uuid or not email:
        raise ValueError("Missing required user attributes (sub or email)")

    # Check if player already exists
    logger.debug("Checking for existing player", extra={"user_id": user_uuid})

    try:
        existing_player = dynamo.get_item(TableName.PLAYERS, {"PlayerID": user_uuid})

        if existing_player:
            logger.info("Player already exists", extra={"user_id": user_uuid})
            return

    except ClientError as err:
        logger.error(
            "Failed to check for existing player",
            extra={"user_id": user_uuid, "error": str(err), "error_code": err.response.get("Error", {}).get("Code", "Unknown")},
            exc_info=True,
        )
        raise RuntimeError(f"Failed to check for existing player: {str(err)}")

    # Create new player entry
    timestamp: str = datetime.now(timezone.utc).isoformat()

    player_item: dict = {
        "PlayerID": user_uuid,
        "Email": email,
        "CharacterList": {},
        "SeenMotD": [],
        "CreatedAt": timestamp,
        "UpdatedAt": timestamp,
    }

    # Write to DynamoDB
    try:
        dynamo.put_item(TableName.PLAYERS, player_item)
        logger.info(
            "Created new player record",
            extra={"email": email, "user_id": user_uuid},
        )
    except ClientError as err:
        logger.error(
            "Failed to create player record",
            extra={
                "email": email,
                "user_id": user_uuid,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to create player record: {str(err)}")


def extract_player_id_from_event(event: dict) -> str:
    """
    Extract player ID from Cognito authorizer claims in API Gateway event.

    Args:
        event: API Gateway event with Cognito authorizer

    Returns:
        Player ID (sub claim) from JWT token

    Raises:
        ValueError: If player ID is not found in claims (unauthorized)
    """
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    player_id = claims.get("sub")

    if not player_id:
        logger.warning("No player ID found in request claims")
        raise ValueError("Unauthorized - No player ID in token")

    logger.debug("Extracted player ID from claims", extra={"player_id": player_id})
    return player_id


def validate_player_exists(player_id: str) -> bool:
    """
    Validate that a player exists in the database.

    Args:
        player_id: Cognito user ID to validate

    Returns:
        True if player exists, False otherwise

    Raises:
        RuntimeError: If database query fails
    """
    try:
        player = dynamo.get_item(TableName.PLAYERS, {"PlayerID": player_id})

        if not player:
            logger.warning("Player not found in database", extra={"player_id": player_id})
            return False

        logger.debug("Player validation successful", extra={"player_id": player_id})
        return True

    except ClientError as err:
        logger.error("Failed to validate player existence", extra={"player_id": player_id, "error": str(err)}, exc_info=True)
        raise RuntimeError(f"Failed to validate player: {str(err)}")


def get_player_data(player_id: str) -> dict:
    """
    Retrieve player data from DynamoDB.

    Args:
        player_id: Cognito user ID

    Returns:
        Player data dict

    Raises:
        ValueError: If player not found
        RuntimeError: If database query fails
    """
    try:
        player = dynamo.get_item(TableName.PLAYERS, {"PlayerID": player_id})

        if not player:
            logger.warning("Player not found", extra={"player_id": player_id})
            raise ValueError(f"Player {player_id} not found")

        logger.info(
            "Player data retrieved", extra={"player_id": player_id, "character_count": len(player.get("CharacterList", {}))}
        )
        return player

    except ClientError as err:
        logger.error("Failed to retrieve player data", extra={"player_id": player_id, "error": str(err)}, exc_info=True)
        raise RuntimeError(f"Failed to retrieve player data: {str(err)}")


def get_player_characters(player_id: str) -> dict:
    """
    Get character list for a player.

    Args:
        player_id: Cognito user ID

    Returns:
        Dictionary of character names to character info

    Raises:
        ValueError: If player not found
        RuntimeError: If database query fails
    """
    player = get_player_data(player_id)
    return player.get("CharacterList", {})


def update_player_timestamp(player_id: str, timestamp: str) -> None:
    """
    Update player's UpdatedAt timestamp.

    Args:
        player_id: Cognito user ID
        timestamp: ISO format timestamp

    Raises:
        RuntimeError: If database update fails
    """
    try:
        dynamo.update_item(
            TableName.PLAYERS,
            Key={"PlayerID": player_id},
            UpdateExpression="SET UpdatedAt = :timestamp",
            ExpressionAttributeValues={":timestamp": timestamp},
        )
        logger.debug("Updated player timestamp", extra={"player_id": player_id})

    except ClientError as err:
        logger.error("Failed to update player timestamp", extra={"player_id": player_id, "error": str(err)}, exc_info=True)
        raise RuntimeError(f"Failed to update player timestamp: {str(err)}")


def get_formatted_character_list(player_id: str) -> list:
    """
    Get formatted character list for a player.

    Args:
        player_id: Cognito user ID

    Returns:
        List of character dicts with CharacterName, CharacterID, and Dead fields

    Raises:
        ValueError: If player not found
        RuntimeError: If database query fails
    """
    player_data = get_player_data(player_id)
    character_list = player_data.get("CharacterList", {})

    logger.info(
        "Player data retrieved",
        extra={"player_id": player_id, "character_count": len(character_list)},
    )

    # Build character list with proper field names
    characters = []
    for char_name, char_info in character_list.items():
        char_data = {
            "CharacterName": char_name,
            "CharacterID": char_info.get("UUID", ""),
            "Dead": char_info.get("Dead", False),
        }
        characters.append(char_data)

        logger.debug(
            "Processing character",
            extra={
                "character_name": char_name,
                "character_id": char_data.get("CharacterID"),
                "is_dead": char_data.get("Dead"),
            },
        )

    # Sort by name for consistent ordering
    characters.sort(key=lambda x: x.get("CharacterName", ""))

    logger.info(
        "Character list prepared successfully",
        extra={
            "player_id": player_id,
            "character_count": len(characters),
            "character_names": [c.get("CharacterName", "") for c in characters],
        },
    )

    return characters


def delete_player_record(player_id: str) -> None:
    """
    Delete player record from players table.

    Args:
        player_id: Cognito user ID

    Raises:
        RuntimeError: If database operation fails
    """
    try:
        dynamo.delete_item(TableName.PLAYERS, Key={"PlayerID": player_id})
        logger.info("Deleted player record", extra={"player_id": player_id})
    except ClientError as err:
        logger.error(
            "Failed to delete player record",
            extra={"error": str(err), "player_id": player_id, "error_code": err.response.get("Error", {}).get("Code", "Unknown")},
            exc_info=True,
        )
        raise RuntimeError(f"Failed to delete player record: {str(err)}")


def delete_all_characters_for_player(player_id: str) -> dict:
    """
    Delete all characters (both MUD and Incremental) owned by the player.

    Args:
        player_id: Cognito user ID

    Returns:
        dict: Summary of deletion results

    Raises:
        RuntimeError: If critical database operations fail
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
                    deletion_result = delete_character(character_id, remove_from_player_list=False)

                    if deletion_result.get("character_deleted"):
                        results["characters_deleted"] += 1
                    results["items_deleted"] += deletion_result.get("items_deleted", 0)
                    results["active_segments_deleted"] += deletion_result.get("active_segments_deleted", 0)
                    results["history_deleted"] += deletion_result.get("history_deleted", 0)

                    if deletion_result.get("errors"):
                        results["errors"].extend(deletion_result.get("errors", []))

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
                        exc_info=True,
                    )
                    results["errors"].append(f"Failed to delete character {character_name} ({character_id}): {str(err)}")

        logger.info(
            "Completed deleting all characters",
            extra={"player_id": player_id, "results": results},
        )
        return results

    except ClientError as err:
        logger.error(
            "Database error in delete_all_characters",
            extra={"error": str(err), "player_id": player_id, "error_code": err.response.get("Error", {}).get("Code", "Unknown")},
            exc_info=True,
        )
        results["errors"].append(f"Database error: {str(err)}")
        return results
    except Exception as err:
        logger.error("Error in delete_all_characters", extra={"error": str(err)}, exc_info=True)
        results["errors"].append(f"General error: {str(err)}")
        return results


def delete_player_active_segments(player_id: str) -> int:
    """
    Delete any active game segments for the player.

    Args:
        player_id: Cognito user ID

    Returns:
        int: Number of segments deleted

    Raises:
        RuntimeError: If query fails (but continues deletion attempts)
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
                    Key={"ActiveSegmentID": item.get("ActiveSegmentID")},
                )
                deleted_count += 1
            except ClientError as err:
                logger.error(
                    "Failed to delete active segment",
                    extra={
                        "error": str(err),
                        "segment_id": item.get("ActiveSegmentID"),
                        "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
                    },
                )

        logger.info(
            "Deleted active segments",
            extra={"player_id": player_id, "count": deleted_count},
        )
        return deleted_count
    except ClientError as err:
        logger.error(
            "Error querying active segments",
            extra={"error": str(err), "player_id": player_id, "error_code": err.response.get("Error", {}).get("Code", "Unknown")},
            exc_info=True,
        )
        return deleted_count
    except Exception as err:
        logger.error("Error deleting active segments", extra={"error": str(err), "player_id": player_id}, exc_info=True)
        return deleted_count


def delete_player_character_history(player_id: str) -> int:
    """
    Delete all character history records for the player.

    Args:
        player_id: Cognito user ID

    Returns:
        int: Number of history records deleted

    Raises:
        RuntimeError: If query fails (but continues deletion attempts)
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
                    Key={"PlayerID": player_id, "Timestamp": item.get("Timestamp")},
                )
                deleted_count += 1
            except ClientError as err:
                logger.error(
                    "Failed to delete history record",
                    extra={
                        "error": str(err),
                        "timestamp": item.get("Timestamp"),
                        "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
                    },
                )

        logger.info(
            "Deleted history records",
            extra={"count": deleted_count, "player_id": player_id},
        )
        return deleted_count

    except ClientError as err:
        logger.error(
            "Error querying character history",
            extra={"error": str(err), "player_id": player_id, "error_code": err.response.get("Error", {}).get("Code", "Unknown")},
            exc_info=True,
        )
        return deleted_count
    except Exception as err:
        logger.error(
            "Error in delete_character_history",
            extra={"error": str(err)},
            exc_info=True,
        )
        return deleted_count


def delete_player_data_completely(player_id: str) -> dict:
    """
    Delete all player data including characters, items, segments, and history.

    This is the main orchestration function that handles complete player deletion.

    Args:
        player_id: Cognito user ID

    Returns:
        dict: Complete deletion results with counts and any errors

    Raises:
        ValueError: If player_id is empty
    """

    if not player_id:
        raise ValueError("Player ID cannot be empty")

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

    # Delete player record first
    try:
        delete_player_record(player_id)
        results["deletions"]["player_record"] = True
    except RuntimeError as err:
        logger.error(
            "Failed to delete player record",
            extra={"error": str(err), "player_id": player_id},
        )
        results["errors"].append(f"Player record: {str(err)}")
    except Exception as err:
        logger.error(
            "Unexpected error deleting player record",
            extra={"error": str(err)},
            exc_info=True,
        )
        results["errors"].append(f"Player record: {str(err)}")

    # Delete all characters and their associated data
    try:
        char_deletion_results = delete_all_characters_for_player(player_id)
        results["deletions"]["characters"] = char_deletion_results.get("characters_deleted", 0)
        results["deletions"]["items"] = char_deletion_results.get("items_deleted", 0)
        results["deletions"]["active_segments"] += char_deletion_results.get("active_segments_deleted", 0)
        results["deletions"]["story_history"] = char_deletion_results.get("history_deleted", 0)
        if char_deletion_results.get("errors"):
            results["errors"].extend(char_deletion_results.get("errors", []))
    except Exception as err:
        logger.error(
            "Unexpected error deleting characters",
            extra={"error": str(err)},
            exc_info=True,
        )
        results["errors"].append(f"Characters: {str(err)}")

    # Delete any remaining active segments
    try:
        # Additional active segments not covered by character deletion
        # (e.g., segments with PlayerID but no CharacterID)
        additional_segments = delete_player_active_segments(player_id)
        results["deletions"]["active_segments"] += additional_segments
    except Exception as err:
        logger.error(
            "Unexpected error deleting active segments",
            extra={"error": str(err)},
            exc_info=True,
        )
        results["errors"].append(f"Active segments: {str(err)}")

    # Delete character history
    try:
        # Additional character history not covered by character deletion
        additional_history = delete_player_character_history(player_id)
        results["deletions"]["character_history"] = additional_history
    except Exception as err:
        logger.error(
            "Unexpected error deleting character history",
            extra={"error": str(err)},
            exc_info=True,
        )
        results["errors"].append(f"Character history: {str(err)}")

    # Log summary
    logger.info("Deletion complete", extra={"player_id": player_id, "summary": results})

    return results
