"""
Player-Character relationship management utilities.

Handles operations that involve both player and character tables,
breaking circular dependencies between player.py and character_data.py.
"""

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger


def add_character_to_player_list(player_id: str, character_name: str, character_id: str, timestamp: str) -> bool:
    """
    Add character to player's character list.

    Args:
        player_id: Player UUID
        character_name: Character name
        character_id: Character UUID
        timestamp: ISO format timestamp

    Returns:
        True if added successfully

    Raises:
        RuntimeError: If database operation fails
    """
    character_info = {
        "UUID": character_id,
        "Dead": False,
        "GameMode": "None",
    }

    logger.info(f"Adding character to player list for {character_name}")

    try:
        dynamo.update_item(
            TableName.PLAYERS,
            Key={"PlayerID": player_id},
            UpdateExpression="SET CharacterList.#name = :info, UpdatedAt = :timestamp",
            ExpressionAttributeNames={"#name": character_name},
            ExpressionAttributeValues={
                ":info": character_info,
                ":timestamp": timestamp,
            },
        )
        return True
    except ClientError as err:
        logger.error(f"Failed to add character to player list for {character_name} Error: {err}")
        raise RuntimeError(f"Failed to add character to player list: {err}") from err


def remove_character_from_player_list(player_id: str, character_name: str) -> dict:
    """
    Remove a character from the player's CharacterList.

    Args:
        player_id: Player UUID
        character_name: Name of the character to remove

    Returns:
        Dict with:
            - Removed: bool - Whether the character was removed
            - Error: str - Error message if removal failed (None if successful)
    """
    result = {"Removed": False, "Error": None}

    if not player_id or not character_name:
        return result

    try:
        dynamo.update_item(
            TableName.PLAYERS,
            Key={"PlayerID": player_id},
            UpdateExpression="REMOVE CharacterList.#name",
            ConditionExpression="attribute_exists(CharacterList.#name)",
            ExpressionAttributeNames={"#name": character_name},
        )
        result["Removed"] = True
        logger.info(f"Removed character from player list for {character_name}")
    except ClientError as err:
        if err.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            logger.error(f"Failed to remove character from player list for {character_name} Error: {err}")
            result["Error"] = f"Failed to remove character from player list: {err}"

    return result


def delete_character_items(character: dict) -> dict:
    """
    Delete all items belonging to a character, including items inside containers.

    Args:
        character: Character dict containing inventory and equipped items

    Returns:
        Dict with:
            - DeletedCount: int - Number of items deleted
            - Errors: list - List of error messages
    """
    result = {"DeletedCount": 0, "Errors": []}

    # Collect all top-level item IDs
    top_level_items = []

    # Inventory items
    inventory = character.get("Inventory", {})
    for _, item_data in inventory.items():
        if item_data and isinstance(item_data, dict):
            item_id = item_data.get("ItemID")
            if item_id:
                top_level_items.append(item_id)

    # Equipped items
    left_id = character.get("LeftHandID")
    if left_id:
        top_level_items.append(left_id)
    right_id = character.get("RightHandID")
    if right_id:
        top_level_items.append(right_id)

    # Recursively collect all item IDs including contents
    all_item_ids = set()
    items_to_process = list(top_level_items)

    while items_to_process:
        item_id = items_to_process.pop()

        # Skip if already processed
        if item_id in all_item_ids:
            continue

        all_item_ids.add(item_id)

        # Check if this item is a container and has contents
        try:
            item = dynamo.get_item(
                TableName.ITEMS,
                {"ItemID": item_id},
                ProjectionExpression="Container, Contents",
            )
            if item and item.get("Container"):
                # Add contents to process list
                contents = item.get("Contents", [])
                for content_id in contents:
                    if content_id and content_id not in all_item_ids:
                        items_to_process.append(content_id)
        except ClientError as err:
            logger.error(f"Failed to check container contents for {item_id} Error: {err}")
            result["Errors"].append(f"Failed to check item {item_id}: {err}")

    # Batch delete all items using DynamoDB's batch writer with automatic retries
    if all_item_ids:
        # Convert item IDs to Key format for batch delete
        delete_keys = [{"ItemID": item_id} for item_id in all_item_ids]

        try:
            # Use the existing batch_write_with_retries method that handles:
            # - Automatic batching (25 items per batch)
            # - Automatic retry of unprocessed items
            # - Exponential backoff for throttling
            failed_items = dynamo.batch_write_with_retries(TableName.ITEMS, delete_keys, operation="delete")

            # Count successful deletes
            result["DeletedCount"] = len(all_item_ids) - len(failed_items)

            # Log failed items
            for failed_key in failed_items:
                item_id = failed_key.get("ItemID")
                logger.error(f"Failed to delete item {item_id} after retries")
                result["Errors"].append(f"Failed to delete item {item_id}")

        except Exception as err:
            logger.error(f"Batch delete operation failed: {err}")
            result["Errors"].append(f"Batch delete failed: {err}")

            # Fall back to individual deletes for all items
            for item_id in all_item_ids:
                try:
                    dynamo.delete_item(TableName.ITEMS, Key={"ItemID": item_id})
                    result["DeletedCount"] += 1
                except ClientError as err:
                    logger.error(f"Failed to delete item {item_id} Error: {err}")
                    result["Errors"].append(f"Failed to delete item {item_id}: {err}")

    return result


def delete_character_active_segments(character_id: str) -> dict:
    """
    Delete all active segments for a character.

    Args:
        character_id: Character UUID

    Returns:
        Dict with:
            - DeletedCount: int - Number of segments deleted
            - Errors: list - List of error messages
    """
    result = {"DeletedCount": 0, "Errors": []}

    try:
        active_segments = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="CharacterID-index",
            KeyConditionExpression="CharacterID = :cid",
            ExpressionAttributeValues={":cid": character_id},
            ProjectionExpression="ActiveSegmentID",
        )

        if active_segments:
            # Prepare keys for batch deletion
            delete_keys = []
            for segment in active_segments:
                seg_id = segment.get("ActiveSegmentID")
                if seg_id:
                    delete_keys.append({"ActiveSegmentID": seg_id})

            try:
                # Batch delete all segments with automatic retries
                failed_items = dynamo.batch_write_with_retries(TableName.ACTIVE_SEGMENTS, delete_keys, operation="delete")

                # Count successful deletes
                result["DeletedCount"] = len(delete_keys) - len(failed_items)

                # Log failed items
                for failed_key in failed_items:
                    segment_id = failed_key.get("ActiveSegmentID")
                    logger.error(f"Failed to delete active segment {segment_id} after retries")
                    result["Errors"].append(f"Failed to delete active segment {segment_id}")

            except Exception as err:
                logger.error(f"Batch delete of segments failed: {err}")
                # Fall back to individual deletes
                for segment in active_segments:
                    seg_id = segment.get("ActiveSegmentID")
                    if not seg_id:
                        continue
                    try:
                        dynamo.delete_item(
                            TableName.ACTIVE_SEGMENTS,
                            Key={"ActiveSegmentID": seg_id},
                        )
                        result["DeletedCount"] += 1
                    except ClientError as err:
                        logger.error(f"Failed to delete active segment {seg_id} Error: {err}")
                        result["Errors"].append(f"Failed to delete active segment {seg_id}: {err}")

    except ClientError as err:
        logger.error(f"Failed to query active segments for {character_id} Error: {err}")
        result["Errors"].append(f"Failed to query active segments: {err}")

    return result


def delete_character_segment_history(character_id: str) -> dict:
    """
    Delete all segment history records for a character.

    Args:
        character_id: Character UUID

    Returns:
        Dict with:
            - DeletedCount: int - Number of segment history records deleted
            - Errors: list - List of error messages
    """
    result = {"DeletedCount": 0, "Errors": []}

    try:
        history_records = dynamo.query(
            TableName.SEGMENT_HISTORY,
            KeyConditionExpression="CharacterID = :cid",
            ExpressionAttributeValues={":cid": character_id},
            ProjectionExpression="ActiveSegmentID",
        )

        if history_records:
            delete_keys = []
            for record in history_records:
                active_segment_id = record.get("ActiveSegmentID")
                if active_segment_id:
                    delete_keys.append({"CharacterID": character_id, "ActiveSegmentID": active_segment_id})

            try:
                failed_items = dynamo.batch_write_with_retries(TableName.SEGMENT_HISTORY, delete_keys, operation="delete")

                result["DeletedCount"] = len(delete_keys) - len(failed_items)

                for failed_key in failed_items:
                    seg_id = failed_key.get("ActiveSegmentID")
                    logger.error(f"Failed to delete segment history record for active segment {seg_id} after retries")
                    result["Errors"].append(f"Failed to delete segment history record for active segment {seg_id}")

            except Exception as err:
                logger.error(f"Batch delete of segment history failed: {err}")
                # Fall back to individual deletes
                for record in history_records:
                    seg_id = record.get("ActiveSegmentID")
                    if not seg_id:
                        result["Errors"].append(
                            "Segment history record missing ActiveSegmentID; cannot delete this record individually"
                        )
                        continue
                    try:
                        dynamo.delete_item(
                            TableName.SEGMENT_HISTORY,
                            Key={"CharacterID": character_id, "ActiveSegmentID": seg_id},
                        )
                        result["DeletedCount"] += 1
                    except ClientError as err:
                        logger.error(f"Failed to delete segment history record for ActiveSegmentID {seg_id} Error: {err}")
                        result["Errors"].append(f"Failed to delete segment history record for active segment {seg_id}: {err}")

    except ClientError as err:
        logger.error(f"Failed to query segment history for {character_id} Error: {err}")
        result["Errors"].append(f"Failed to query segment history: {err}")

    return result


def delete_character_history(character_id: str) -> dict:
    """
    Delete all history records for a character.

    Args:
        character_id: Character UUID

    Returns:
        Dict with:
            - DeletedCount: int - Number of history records deleted
            - Errors: list - List of error messages
    """
    result = {"DeletedCount": 0, "Errors": []}

    try:
        history_records = dynamo.query(
            TableName.STORY_HISTORY,
            KeyConditionExpression="CharacterID = :cid",
            ExpressionAttributeValues={":cid": character_id},
            ProjectionExpression="StoryInstanceID",
        )

        if history_records:
            # Prepare composite keys for batch deletion using CharacterID + StoryInstanceID
            delete_keys = []
            for record in history_records:
                story_instance_id = record.get("StoryInstanceID")
                if story_instance_id:
                    delete_keys.append({"CharacterID": character_id, "StoryInstanceID": story_instance_id})
                else:
                    logger.warning(
                        f"History record missing StoryInstanceID for character {character_id}; skipping batch delete for this record"
                    )

            try:
                # Batch delete all history records with automatic retries
                failed_items = dynamo.batch_write_with_retries(TableName.STORY_HISTORY, delete_keys, operation="delete")

                # Count successful deletes
                result["DeletedCount"] = len(delete_keys) - len(failed_items)

                # Log failed items
                for failed_key in failed_items:
                    story_instance_id = failed_key.get("StoryInstanceID")
                    logger.error(f"Failed to delete history record for story instance {story_instance_id} after retries")
                    result["Errors"].append(f"Failed to delete history record for story instance {story_instance_id}")

            except Exception as err:
                logger.error(f"Batch delete of history records failed: {err}")
                # Fall back to individual deletes
                for record in history_records:
                    story_instance_id = record.get("StoryInstanceID")
                    if not story_instance_id:
                        result["Errors"].append("History record missing StoryInstanceID; cannot delete this record individually")
                        continue
                    try:
                        dynamo.delete_item(
                            TableName.STORY_HISTORY,
                            Key={"CharacterID": character_id, "StoryInstanceID": story_instance_id},
                        )
                        result["DeletedCount"] += 1
                    except ClientError as err:
                        logger.error(f"Failed to delete history record for StoryInstanceID {story_instance_id} Error: {err}")
                        result["Errors"].append(f"Failed to delete history record for story instance {story_instance_id}: {err}")

    except ClientError as err:
        logger.error(f"Failed to query history for {character_id} Error: {err}")
        result["Errors"].append(f"Failed to query history: {err}")

    return result


def delete_character_record(character_id: str) -> dict:
    """
    Delete the character record from the database.

    Args:
        character_id: Character UUID

    Returns:
        Dict with:
            - Deleted: bool - Whether the character was deleted
            - Error: str - Error message if deletion failed (None if successful)
    """
    result = {"Deleted": False, "Error": None}

    try:
        dynamo.delete_item(TableName.CHARACTERS, Key={"CharacterID": character_id})
        result["Deleted"] = True
        logger.info(f"Deleted character record for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to delete character for {character_id} Error: {err}")
        result["Error"] = f"Failed to delete character: {err}"

    return result


def delete_character(character_id: str, remove_from_player_list: bool = True) -> dict:
    """
    Delete a character and all associated data.

    Note: Ownership verification should be performed before calling this function.

    Args:
        character_id: UUID of the character to delete
        remove_from_player_list: Whether to remove character from player's CharacterList (default: True)

    Returns:
        Dictionary with deletion results including deleted items.
    """
    results = {
        "CharacterDeleted": False,
        "CharacterRemovedFromPlayer": False,
        "ItemsDeleted": 0,
        "ActiveSegmentsDeleted": 0,
        "HistoryDeleted": 0,
        "SegmentHistoryDeleted": 0,
        "Errors": [],
    }

    # Retrieve character data
    character = None
    try:
        character = dynamo.get_item(
            TableName.CHARACTERS,
            {"CharacterID": character_id},
            ProjectionExpression=("PlayerID, CharacterName, Inventory, LeftHandID, RightHandID, Wounds, MaxHealth, CharState"),
        )
    except ClientError as err:
        logger.error(f"Failed to retrieve character for deletion for {character_id} Error: {err}")
        results["Errors"].append(f"Failed to retrieve character: {err}")

    if character:
        # Remove from player list if requested
        if remove_from_player_list:
            player_id = character.get("PlayerID")
            character_name = character.get("CharacterName")

            if player_id and character_name:
                player_result = remove_character_from_player_list(player_id, character_name)
                results["CharacterRemovedFromPlayer"] = player_result.get("Removed", False)
                if player_result.get("Error"):
                    results["Errors"].append(player_result.get("Error"))
                    # Abort deletion to prevent orphaned reference in player's CharacterList
                    logger.error(
                        f"Aborting character deletion for {character_id} - "
                        f"failed to remove from player list, would create orphaned reference"
                    )
                    return results

        # Delete all character items
        items_result = delete_character_items(character)
        results["ItemsDeleted"] = items_result.get("DeletedCount", 0)
        results["Errors"].extend(items_result.get("Errors", []))

        # Delete the character record
        char_result = delete_character_record(character_id)
        results["CharacterDeleted"] = char_result.get("Deleted", False)
        if char_result.get("Error"):
            results["Errors"].append(char_result.get("Error"))

        # Log character deletion with details
        logger.info(f"Character deletion processed for {character_id}")

    # Delete active segments (can proceed even if character not found)
    segments_result = delete_character_active_segments(character_id)
    results["ActiveSegmentsDeleted"] = segments_result.get("DeletedCount", 0)
    results["Errors"].extend(segments_result.get("Errors", []))

    # Delete segment history records
    seg_hist_result = delete_character_segment_history(character_id)
    results["SegmentHistoryDeleted"] = seg_hist_result.get("DeletedCount", 0)
    results["Errors"].extend(seg_hist_result.get("Errors", []))

    # Delete character history records (story history)
    history_result = delete_character_history(character_id)
    results["HistoryDeleted"] = history_result.get("DeletedCount", 0)
    results["Errors"].extend(history_result.get("Errors", []))

    # Log deletion summary
    logger.info(f"Character deletion completed for {character_id}")

    return results


def delete_all_characters(player_id: str) -> dict:
    """
    Delete all characters associated with a player.

    This function is used when deleting a player account to ensure
    all character data is properly cleaned up.

    Args:
        player_id: Player UUID

    Returns:
        Dict with:
            - CharactersDeleted: int - Number of characters deleted
            - ItemsDeleted: int - Total items deleted across all characters
            - ActiveSegmentsDeleted: int - Total segments deleted
            - Errors: list - List of error messages
    """
    results = {
        "CharactersDeleted": 0,
        "ItemsDeleted": 0,
        "ActiveSegmentsDeleted": 0,
        "Errors": [],
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

                    if deletion_result.get("CharacterDeleted"):
                        results["CharactersDeleted"] += 1
                    results["ItemsDeleted"] += deletion_result.get("ItemsDeleted", 0)
                    results["ActiveSegmentsDeleted"] += deletion_result.get("ActiveSegmentsDeleted", 0)

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
