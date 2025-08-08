"""
Player management utilities for Lambda functions.

Provides functions for player authentication and validation.
"""

from datetime import datetime, timezone

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger
from eidolon.player_character import delete_character


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
    logger.debug(f"Checking for existing player for {user_uuid}")

    try:
        existing_player = dynamo.get_item(TableName.PLAYERS, {"PlayerID": user_uuid})

        if existing_player:
            logger.info(f"Player already exists for {user_uuid}")
            raise ValueError(f"Player {user_uuid} already exists")

    except ClientError as err:
        logger.error(
            f"Failed to check for existing player: user_id {user_uuid} error: {err} error_code: {err.response.get('Error')}"
        )
        raise RuntimeError(f"Failed to check for existing player: {err}") from err

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
        logger.debug(f"Created new player record. PlayerID: {user_uuid}, Email: {email}")
    except ClientError as err:
        logger.error(
            f"Failed to create player record. PlayerID: {user_uuid}, Email: {email}",
            exc_info=True,
        )
        raise RuntimeError(f"Failed to create player record: {err}") from err


def validate_player(player_id: str) -> bool:
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
            logger.warning(f"Player not found in database for {player_id}")
            return False

        logger.debug(f"Player validation successful for {player_id}")
        return True

    except ClientError as err:
        logger.error(f"Failed to validate player existence for {player_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to validate player: {err}") from err


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
            logger.warning(f"Player not found for {player_id}")
            raise ValueError(f"Player {player_id} not found")

        logger.info(f"Player data retrieved for {player_id}")
        return player

    except ClientError as err:
        logger.error(f"Failed to retrieve player data for {player_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to retrieve player data: {err}") from err


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
    player: dict = get_player_data(player_id)
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
        logger.debug(f"Updated player timestamp for {player_id}")

    except ClientError as err:
        logger.error(f"Failed to update player timestamp for {player_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to update player timestamp: {err}") from err


def get_character_list(player_id: str) -> list:
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
    player_data: dict = get_player_data(player_id)
    character_list: dict = player_data.get("CharacterList", {})

    logger.debug(f"Player data retrieved: {player_data}")

    # Build character list with proper field names
    characters: list = []
    for char_name, char_info in character_list.items():
        char_data: dict = {
            "CharacterName": char_name,
            "CharacterID": char_info.get("UUID", ""),
            "Dead": char_info.get("Dead", False),
        }
        characters.append(char_data)

        logger.debug(f"Processing character for {char_name}")

    # Sort by name for consistent ordering
    characters.sort(key=lambda x: x.get("CharacterName", ""))

    logger.info(
        "Character list prepared successfully",
    )

    return characters


def verify_character_ownership(character_id: str, player_id: str) -> bool:
    """
    Verify that a character belongs to a player by checking the player record.

    This is more efficient than fetching the full character record since the
    player record is smaller and the players table is accessed less frequently.

    Args:
        character_id: Character UUID to verify
        player_id: Cognito user ID (player UUID)

    Returns:
        True if the character belongs to the player, False otherwise

    Raises:
        ValueError: If player not found
        RuntimeError: If database query fails
    """
    try:
        player = dynamo.get_item(TableName.PLAYERS, {"PlayerID": player_id})

        if not player:
            logger.warning(f"Player not found for ownership check: {player_id}")
            raise ValueError(f"Player {player_id} not found")

        # Check if character_id exists in player's character list
        character_list = player.get("CharacterList", {})

        for char_name, char_info in character_list.items():
            if char_info.get("UUID") == character_id:
                logger.debug(f"Character ownership verified: {character_id} belongs to {player_id}")
                return True

        logger.warning(f"Character ownership failed: {character_id} not owned by {player_id}")
        return False

    except ClientError as err:
        logger.error(f"Failed to verify character ownership for {character_id}, {player_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to verify character ownership: {err}") from err


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
        logger.info(f"Deleted player record for {player_id}")
    except ClientError as err:
        logger.error(f"Failed to delete player record for {player_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to delete player record: {err}") from err


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
            logger.warning(f"Player not found for character deletion for {player_id}")
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

                    logger.info(f"Processed character deletion for {character_name}")
                except Exception as err:
                    logger.error(f"Failed to delete character for {character_name} Error: {err}", exc_info=True)
                    results["errors"].append(f"Failed to delete character {character_name} ({character_id}): {err}")

        logger.info(f"Completed deleting all characters for {player_id}")
        return results

    except ClientError as err:
        logger.error(f"Database error in delete_all_characters for {player_id} Error: {err}", exc_info=True)
        results["errors"].append(f"Database error: {err}")
        return results
    except Exception as err:
        logger.error(f"Error in delete_all_characters Error: {err}", exc_info=True)
        results["errors"].append(f"General error: {err}")
        return results


def delete_player_active_segments(player_id: str) -> int:
    """
    Delete any active game segments for the player.
    
    Since there's no PlayerID GSI on the active_segments table, we need to:
    1. Get the player's character list
    2. Query active segments for each character using CharacterID-index GSI
    3. Delete the found segments

    Args:
        player_id: Cognito user ID

    Returns:
        int: Number of segments deleted

    Raises:
        RuntimeError: If query fails (but continues deletion attempts)
    """
    deleted_count = 0
    
    try:
        # First get the player's characters
        player = dynamo.get_item(TableName.PLAYERS, {"PlayerID": player_id})
        if not player:
            logger.warning(f"Player not found: {player_id}")
            return 0
            
        character_list = player.get("CharacterList", {})
        
        # For each character, query and delete their active segments
        for _, char_info in character_list.items():
            character_id = char_info.get("UUID")
            if not character_id:
                continue
                
            try:
                # Query using CharacterID-index GSI
                items = dynamo.query(
                    TableName.ACTIVE_SEGMENTS,
                    IndexName="CharacterID-index",
                    KeyConditionExpression="CharacterID = :cid",
                    ExpressionAttributeValues={":cid": character_id},
                )
                
                for item in items:  # type: ignore
                    try:
                        dynamo.delete_item(
                            TableName.ACTIVE_SEGMENTS,
                            Key={"ActiveSegmentID": item.get("ActiveSegmentID")},
                        )
                        deleted_count += 1
                    except ClientError as err:
                        logger.error(f"Failed to delete active segment {item.get('ActiveSegmentID')}: {err}")
                        
            except ClientError as err:
                logger.error(f"Error querying active segments for character {character_id}: {err}")
                continue
        
        logger.info(f"Deleted {deleted_count} active segments for player {player_id}")
        return deleted_count
        
    except Exception as err:
        logger.error(f"Error deleting active segments for player {player_id}: {err}", exc_info=True)
        return deleted_count


def delete_player_character_history(player_id: str) -> int:
    """
    Delete all segment history records for the player's characters.
    
    Since the segment_history table uses CharacterID as partition key (not PlayerID),
    we need to:
    1. Get the player's character list  
    2. Query segment history for each character
    3. Delete the found records

    Args:
        player_id: Cognito user ID

    Returns:
        int: Number of history records deleted

    Raises:
        RuntimeError: If query fails (but continues deletion attempts)
    """
    deleted_count = 0
    
    try:
        # First get the player's characters
        player = dynamo.get_item(TableName.PLAYERS, {"PlayerID": player_id})
        if not player:
            logger.warning(f"Player not found: {player_id}")
            return 0
            
        character_list = player.get("CharacterList", {})
        
        # For each character, query and delete their segment history
        for _, char_info in character_list.items():
            character_id = char_info.get("UUID")
            if not character_id:
                continue
                
            try:
                # Query segment_history table with CharacterID as partition key
                items = dynamo.query(
                    TableName.SEGMENT_HISTORY,
                    KeyConditionExpression="CharacterID = :cid",
                    ExpressionAttributeValues={":cid": character_id},
                )
                
                for item in items:  # type: ignore
                    try:
                        # Delete using composite key: CharacterID + ActiveSegmentID
                        dynamo.delete_item(
                            TableName.SEGMENT_HISTORY,
                            Key={
                                "CharacterID": character_id,
                                "ActiveSegmentID": item.get("ActiveSegmentID")
                            },
                        )
                        deleted_count += 1
                    except ClientError as err:
                        logger.error(f"Failed to delete segment history for {item.get('ActiveSegmentID')}: {err}")
                        
            except ClientError as err:
                logger.error(f"Error querying segment history for character {character_id}: {err}")
                continue
                
        # Also delete from story_history table
        for _, char_info in character_list.items():
            character_id = char_info.get("UUID")
            if not character_id:
                continue
                
            try:
                # Query story_history table with CharacterID as partition key
                items = dynamo.query(
                    TableName.STORY_HISTORY,
                    KeyConditionExpression="CharacterID = :cid",
                    ExpressionAttributeValues={":cid": character_id},
                )
                
                for item in items:  # type: ignore
                    try:
                        # Delete using composite key: CharacterID + StoryID
                        dynamo.delete_item(
                            TableName.STORY_HISTORY,
                            Key={
                                "CharacterID": character_id,
                                "StoryID": item.get("StoryID")
                            },
                        )
                        deleted_count += 1
                    except ClientError as err:
                        logger.error(f"Failed to delete story history for {item.get('StoryID')}: {err}")
                        
            except ClientError as err:
                logger.error(f"Error querying story history for character {character_id}: {err}")
                continue
        
        logger.info(f"Deleted {deleted_count} history records for player {player_id}")
        return deleted_count
        
    except Exception as err:
        logger.error(f"Error deleting character history for player {player_id}: {err}", exc_info=True)
        return deleted_count


def delete_player_data(player_id: str) -> dict:
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

    logger.info(f"Starting deletion process for {player_id}")

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
        logger.error(f"Failed to delete player record for {player_id} Error: {err}")
        results["errors"].append(f"Player record: {err}")
    except Exception as err:
        logger.error(f"Unexpected error deleting player record Error: {err}", exc_info=True)
        results["errors"].append(f"Player record: {err}")

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
        logger.error(f"Unexpected error deleting characters Error: {err}", exc_info=True)
        results["errors"].append(f"Characters: {err}")

    # Delete any remaining active segments
    try:
        # Additional active segments not covered by character deletion
        # (e.g., segments with PlayerID but no CharacterID)
        additional_segments = delete_player_active_segments(player_id)
        results["deletions"]["active_segments"] += additional_segments
    except Exception as err:
        logger.error(f"Unexpected error deleting active segments Error: {err}", exc_info=True)
        results["errors"].append(f"Active segments: {err}")

    # Delete character history
    try:
        # Additional character history not covered by character deletion
        additional_history = delete_player_character_history(player_id)
        results["deletions"]["character_history"] = additional_history
    except Exception as err:
        logger.error(f"Unexpected error deleting character history Error: {err}", exc_info=True)
        results["errors"].append(f"Character history: {err}")

    # Log summary
    logger.info(f"Deletion complete for {player_id}")

    return results
