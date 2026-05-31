"""
Player-Character relationship management utilities.

Handles operations that involve both player and character tables,
breaking circular dependencies between player.py and character_data.py.
"""

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger
from eidolon.prototypes import item_is_container


def delete_single_item(table_name, key: dict, context_label: str = "") -> bool:
    """Attempt to delete a single DynamoDB item, returning True on success.

    Args:
        table_name: TableName enum value
        key: Primary key dict for the item
        context_label: Description for log messages

    Returns:
        True if deleted successfully, False otherwise
    """
    try:
        dynamo.delete_item(table_name, Key=key)
        return True
    except ClientError as err:
        logger.error(f"Failed to delete {context_label} {key} Error: {err}")
        return False


def batch_delete_with_fallback(table_name, delete_keys: list, context_label: str = "") -> dict:
    """Delete items using batch write, falling back to individual deletes on failure.

    Args:
        table_name: TableName enum value
        delete_keys: List of primary key dicts to delete
        context_label: Description for log messages

    Returns:
        Dict with DeletedCount (int) and Errors (list)
    """
    result = {"DeletedCount": 0, "Errors": []}

    if not delete_keys:
        return result

    try:
        failed_items = dynamo.batch_write_with_retries(table_name, delete_keys, operation="delete")
        result["DeletedCount"] = len(delete_keys) - len(failed_items)
        for failed_key in failed_items:
            logger.error(f"Failed to delete {context_label} {failed_key} after retries")
            result["Errors"].append(f"Failed to delete {context_label} {failed_key}")
        return result
    except Exception as err:
        logger.error(f"Batch delete of {context_label} failed: {err}")

    # Fallback to individual deletes
    for key in delete_keys:
        if delete_single_item(table_name, key, context_label):
            result["DeletedCount"] += 1
        else:
            result["Errors"].append(f"Failed to delete {context_label} {key}")

    return result


def process_character_deletion(character_name: str, character_id: str) -> dict:
    """Delete a single character and return the result.

    Args:
        character_name: Character name for logging
        character_id: Character UUID

    Returns:
        Dict with CharacterDeleted, ItemsDeleted, ActiveSegmentsDeleted, Errors
    """
    try:
        deletion_result = delete_character(character_id, remove_from_player_list=False)
        logger.info(f"Processed character deletion for {character_name}")
        return deletion_result
    except Exception as err:
        logger.error(f"Failed to delete character for {character_name} Error: {err}", exc_info=True)
        return {
            "CharacterDeleted": False,
            "ItemsDeleted": 0,
            "ActiveSegmentsDeleted": 0,
            "Errors": [f"Failed to delete character {character_name} ({character_id}): {err}"],
        }


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
    """Delete every item reachable from a character, walking nested containers.

    Returns:
        {"DeletedCount": int, "Errors": list}
    """
    result = {"DeletedCount": 0, "Errors": []}

    top_level_items = list(character.get("Contents") or [])
    for hand_field in ("LeftHandID", "RightHandID"):
        hand_id = character.get(hand_field)
        if hand_id and hand_id not in top_level_items:
            top_level_items.append(hand_id)

    all_item_ids = set()
    items_to_process = list(top_level_items)

    while items_to_process:
        item_id = items_to_process.pop()
        if not item_id or item_id in all_item_ids:
            continue
        all_item_ids.add(item_id)

        try:
            item = dynamo.get_item(
                TableName.ITEMS,
                {"ItemID": item_id},
                ProjectionExpression="PrototypeID, Contents",
            )
            if item and item_is_container(item):
                for content_id in item.get("Contents", []) or []:
                    if content_id and content_id not in all_item_ids:
                        items_to_process.append(content_id)
        except ClientError as err:
            logger.error(f"Failed to check container contents for {item_id} Error: {err}")
            result["Errors"].append(f"Failed to check item {item_id}: {err}")

    if all_item_ids:
        delete_keys = [{"ItemID": item_id} for item_id in all_item_ids]
        delete_result = batch_delete_with_fallback(TableName.ITEMS, delete_keys, "item")
        result["DeletedCount"] = delete_result.get("DeletedCount", 0)
        result["Errors"].extend(delete_result.get("Errors", []))

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
    except ClientError as err:
        logger.error(f"Failed to query active segments for {character_id} Error: {err}")
        result["Errors"].append(f"Failed to query active segments: {err}")
        return result

    if active_segments:
        delete_keys = [{"ActiveSegmentID": seg.get("ActiveSegmentID")} for seg in active_segments if seg.get("ActiveSegmentID")]
        delete_result = batch_delete_with_fallback(TableName.ACTIVE_SEGMENTS, delete_keys, "active segment")
        result["DeletedCount"] = delete_result.get("DeletedCount", 0)
        result["Errors"].extend(delete_result.get("Errors", []))

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
    except ClientError as err:
        logger.error(f"Failed to query segment history for {character_id} Error: {err}")
        result["Errors"].append(f"Failed to query segment history: {err}")
        return result

    if history_records:
        delete_keys = [
            {"CharacterID": character_id, "ActiveSegmentID": rec.get("ActiveSegmentID")}
            for rec in history_records
            if rec.get("ActiveSegmentID")
        ]
        delete_result = batch_delete_with_fallback(TableName.SEGMENT_HISTORY, delete_keys, "segment history record")
        result["DeletedCount"] = delete_result.get("DeletedCount", 0)
        result["Errors"].extend(delete_result.get("Errors", []))

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
    except ClientError as err:
        logger.error(f"Failed to query history for {character_id} Error: {err}")
        result["Errors"].append(f"Failed to query history: {err}")
        return result

    if history_records:
        delete_keys = []
        for record in history_records:
            story_instance_id = record.get("StoryInstanceID")
            if story_instance_id:
                delete_keys.append({"CharacterID": character_id, "StoryInstanceID": story_instance_id})
            else:
                logger.warning(f"History record missing StoryInstanceID for character {character_id}")

        delete_result = batch_delete_with_fallback(TableName.STORY_HISTORY, delete_keys, "story history record")
        result["DeletedCount"] = delete_result.get("DeletedCount", 0)
        result["Errors"].extend(delete_result.get("Errors", []))

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
