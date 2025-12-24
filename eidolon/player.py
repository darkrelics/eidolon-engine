"""
Player management utilities for Lambda functions.

Provides functions for player authentication and validation.
"""

from datetime import datetime, timezone

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger
from eidolon.player_character import delete_character, delete_character_history


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

    try:
        player = dynamo.get_item(
            TableName.PLAYERS,
            {"PlayerID": player_id},
            ProjectionExpression="CharacterList",
        )
    except ClientError as err:
        logger.error(f"Failed to retrieve character list for {player_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to retrieve character list: {err}") from err

    if not player:
        logger.warning(f"Player not found for {player_id}")
        raise ValueError(f"Player {player_id} not found")

    character_list: dict = player.get("CharacterList", {})

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

    return characters


def character_contains_item(character: dict, item_id: str, *, character_id=None) -> bool:
    """
    Determine whether the provided character owns the supplied item ID.

    Inspects inventory slots, equipped hand slots, and recursively traverses container contents.
    """
    if not character or not item_id:
        return False

    top_level_items: list[str] = []

    inventory = character.get("Inventory", {})
    for slot_data in inventory.values():
        if slot_data and isinstance(slot_data, dict):
            slot_item_id = slot_data.get("ItemID")
            if slot_item_id:
                if slot_item_id == item_id:
                    return True
                top_level_items.append(slot_item_id)

    left_id = character.get("LeftHandID")
    if left_id:
        if left_id == item_id:
            return True
        top_level_items.append(left_id)

    right_id = character.get("RightHandID")
    if right_id:
        if right_id == item_id:
            return True
        top_level_items.append(right_id)

    processed: set[str] = set()
    items_to_process = list(top_level_items)

    while items_to_process:
        current_id = items_to_process.pop()
        if not current_id or current_id in processed:
            continue

        processed.add(current_id)

        try:
            item_record = dynamo.get_item(
                TableName.ITEMS,
                {"ItemID": current_id},
                ProjectionExpression="Container, Contents",
            )
        except ClientError as err:
            logger.error(
                "Failed to inspect item %s for ownership check (character=%s) Error: %s",
                current_id,
                character_id,
                err,
                exc_info=True,
            )
            raise RuntimeError(f"Failed to verify item ownership: {err}") from err

        if not item_record or not item_record.get("Container"):
            continue

        contents = item_record.get("Contents", [])
        for nested_id in contents:
            if not nested_id:
                continue
            if nested_id == item_id:
                return True
            if nested_id not in processed:
                items_to_process.append(nested_id)

    return False


def player_owns_item(player_id: str, item_id: str) -> bool:
    """
    Verify that the specified item ID belongs to one of the player's characters.

    Raises:
        ValueError: If the player record cannot be found
        RuntimeError: If ownership verification fails due to a database error
    """
    if not player_id or not item_id:
        return False

    try:
        player = dynamo.get_item(
            TableName.PLAYERS,
            {"PlayerID": player_id},
            ProjectionExpression="CharacterList",
        )
    except ClientError as err:
        logger.error(
            "Failed to load player %s while verifying item ownership Error: %s",
            player_id,
            err,
            exc_info=True,
        )
        raise RuntimeError(f"Failed to verify item ownership: {err}") from err

    if not player:
        logger.warning(f"Player not found for ownership check: {player_id}")
        raise ValueError(f"Player {player_id} not found")

    character_list = player.get("CharacterList", {})
    for char_info in character_list.values():
        char_id = char_info.get("UUID")
        if not char_id:
            continue

        try:
            character = dynamo.get_item(
                TableName.CHARACTERS,
                {"CharacterID": char_id},
                ProjectionExpression="Inventory, LeftHandID, RightHandID",
            )
        except ClientError as err:
            logger.error(
                "Failed to load character %s while verifying item ownership Error: %s",
                char_id,
                err,
                exc_info=True,
            )
            raise RuntimeError(f"Failed to verify item ownership: {err}") from err

        if not character:
            continue

        if character_contains_item(character, item_id, character_id=char_id):
            return True

    return False


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
        player = dynamo.get_item(
            TableName.PLAYERS,
            {"PlayerID": player_id},
            ProjectionExpression="CharacterList",
        )

        if not player:
            logger.warning(f"Player not found for ownership check: {player_id}")
            raise ValueError(f"Player {player_id} not found")

        # Check if character_id exists in player's character list
        character_list = player.get("CharacterList", {})

        for char_info in character_list.values():
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
        "CharactersDeleted": 0,
        "ItemsDeleted": 0,
        "ActiveSegmentsDeleted": 0,
        "HistoryDeleted": 0,
        "Errors": [],
    }

    try:
        player = dynamo.get_item(
            TableName.PLAYERS,
            {"PlayerID": player_id},
            ProjectionExpression="CharacterList",
        )

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

                    if deletion_result.get("CharacterDeleted"):
                        results["CharactersDeleted"] += 1
                    results["ItemsDeleted"] += deletion_result.get("ItemsDeleted", 0)
                    results["ActiveSegmentsDeleted"] += deletion_result.get("ActiveSegmentsDeleted", 0)
                    results["HistoryDeleted"] += deletion_result.get("HistoryDeleted", 0)

                    if deletion_result.get("Errors"):
                        results["Errors"].extend(deletion_result.get("Errors", []))

                    logger.info(f"Processed character deletion for {character_name}")
                except Exception as err:
                    logger.error(f"Failed to delete character for {character_name} Error: {err}", exc_info=True)
                    results["Errors"].append(f"Failed to delete character {character_name} ({character_id}): {err}")

        logger.info(f"Completed deleting all characters for {player_id}")
        return results

    except ClientError as err:
        logger.error(f"Database error in delete_all_characters for {player_id} Error: {err}", exc_info=True)
        results["Errors"].append(f"Database error: {err}")
        return results
    except Exception as err:
        logger.error(f"Error in delete_all_characters Error: {err}", exc_info=True)
        results["Errors"].append(f"General error: {err}")
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
        player = dynamo.get_item(
            TableName.PLAYERS,
            {"PlayerID": player_id},
            ProjectionExpression="CharacterList",
        )
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
                    ProjectionExpression="ActiveSegmentID",
                )

                # Batch delete for efficiency
                delete_keys = []
                for item in items:  # type: ignore
                    seg_id = item.get("ActiveSegmentID")
                    if seg_id:
                        delete_keys.append({"ActiveSegmentID": seg_id})

                if delete_keys:
                    try:
                        failed = dynamo.batch_write_with_retries(
                            TableName.ACTIVE_SEGMENTS,
                            delete_keys,
                            operation="delete",
                        )
                        deleted_count += len(delete_keys) - len(failed)
                        for f in failed:
                            logger.error(f"Failed to delete active segment {f.get('ActiveSegmentID')} after retries")
                    except Exception as err:
                        logger.error(f"Batch delete failed for active segments: {err}")
                        # Fallback to individual deletes
                        for key in delete_keys:
                            try:
                                dynamo.delete_item(TableName.ACTIVE_SEGMENTS, Key=key)
                                deleted_count += 1
                            except ClientError as err:
                                logger.error(f"Failed to delete active segment {key.get('ActiveSegmentID')}: {err}")

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
    Delete all segment and story history records for the player's characters.

    Since history tables use CharacterID as the partition key (not PlayerID),
    we need to:
    1. Get the player's character list
    2. Delete segment history for each character
    3. Delete story history for each character via helper

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
        player = dynamo.get_item(
            TableName.PLAYERS,
            {"PlayerID": player_id},
            ProjectionExpression="CharacterList",
        )
        if not player:
            logger.warning(f"Player not found: {player_id}")
            return 0

        character_list = player.get("CharacterList", {})

        # For each character, delete their segment history and story history
        for _, char_info in character_list.items():
            character_id = char_info.get("UUID")
            if not character_id:
                continue

            # Delete segment history records for this character
            try:
                items = dynamo.query(
                    TableName.SEGMENT_HISTORY,
                    KeyConditionExpression="CharacterID = :cid",
                    ExpressionAttributeValues={":cid": character_id},
                    ProjectionExpression="ActiveSegmentID",
                )

                delete_keys = []
                for item in items:  # type: ignore
                    seg_id = item.get("ActiveSegmentID")
                    if seg_id:
                        delete_keys.append({"CharacterID": character_id, "ActiveSegmentID": seg_id})

                if delete_keys:
                    try:
                        failed = dynamo.batch_write_with_retries(
                            TableName.SEGMENT_HISTORY,
                            delete_keys,
                            operation="delete",
                        )
                        deleted_count += len(delete_keys) - len(failed)
                        for f in failed:
                            logger.error(f"Failed to delete segment history for {f.get('ActiveSegmentID')} after retries")
                    except Exception as err:
                        logger.error(f"Batch delete failed for segment history: {err}")
                        for key in delete_keys:
                            try:
                                dynamo.delete_item(TableName.SEGMENT_HISTORY, Key=key)
                                deleted_count += 1
                            except ClientError as err:
                                logger.error(f"Failed to delete segment history for {key.get('ActiveSegmentID')}: {err}")
            except ClientError as err:
                logger.error(f"Error querying segment history for character {character_id}: {err}")

            # Delete story history using shared helper
            try:
                history_result = delete_character_history(character_id)
                deleted_count += history_result.get("DeletedCount", 0)
            except Exception as err:
                logger.error(f"Failed to delete story history via helper for {character_id}: {err}")

        logger.info(f"Deleted {deleted_count} history records for player {player_id}")
        return deleted_count

    except Exception as err:
        logger.error(
            f"Error deleting character history for player {player_id}: {err}",
            exc_info=True,
        )
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
        "PlayerID": player_id,
        "Timestamp": datetime.now(timezone.utc).isoformat(),
        "Deletions": {
            "PlayerRecord": False,
            "Characters": 0,
            "Items": 0,
            "ActiveSegments": 0,
            "CharacterHistory": 0,
            "StoryHistory": 0,
        },
        "Errors": [],
    }

    # Delete player record first
    try:
        delete_player_record(player_id)
        results["Deletions"]["PlayerRecord"] = True
    except RuntimeError as err:
        logger.error(f"Failed to delete player record for {player_id} Error: {err}")
        results["Errors"].append(f"Player record: {err}")
    except Exception as err:
        logger.error(f"Unexpected error deleting player record Error: {err}", exc_info=True)
        results["Errors"].append(f"Player record: {err}")

    # Delete all characters and their associated data
    try:
        char_deletion_results = delete_all_characters_for_player(player_id)
        results["Deletions"]["Characters"] = char_deletion_results.get("CharactersDeleted", 0)
        results["Deletions"]["Items"] = char_deletion_results.get("ItemsDeleted", 0)
        results["Deletions"]["ActiveSegments"] += char_deletion_results.get("ActiveSegmentsDeleted", 0)
        results["Deletions"]["StoryHistory"] = char_deletion_results.get("HistoryDeleted", 0)
        if char_deletion_results.get("Errors"):
            results["Errors"].extend(char_deletion_results.get("Errors", []))
    except Exception as err:
        logger.error(f"Unexpected error deleting characters Error: {err}", exc_info=True)
        results["Errors"].append(f"Characters: {err}")

    # Delete any remaining active segments
    try:
        # Additional active segments not covered by character deletion
        # (e.g., segments with PlayerID but no CharacterID)
        additional_segments = delete_player_active_segments(player_id)
        results["Deletions"]["ActiveSegments"] += additional_segments
    except Exception as err:
        logger.error(f"Unexpected error deleting active segments Error: {err}", exc_info=True)
        results["Errors"].append(f"Active segments: {err}")

    # Delete character history
    try:
        # Additional character history not covered by character deletion
        additional_history = delete_player_character_history(player_id)
        results["Deletions"]["CharacterHistory"] = additional_history
    except Exception as err:
        logger.error(f"Unexpected error deleting character history Error: {err}", exc_info=True)
        results["Errors"].append(f"Character history: {err}")

    # Log summary
    logger.info(f"Deletion complete for {player_id}")

    return results
