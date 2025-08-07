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
            - removed: bool - Whether the character was removed
            - error: str - Error message if removal failed
    """
    result = {"removed": False, "error": None}

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
        result["removed"] = True
        logger.info(f"Removed character from player list for {character_name}")
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            logger.error(f"Failed to remove character from player list for {character_name} Error: {err}")
            result["error"] = f"Failed to remove character from player list: {err}"

    return result


def delete_character_items(character: dict) -> dict:
    """
    Delete all items belonging to a character.

    Args:
        character: Character dict containing inventory and equipped items

    Returns:
        Dict with:
            - deleted_count: int - Number of items deleted
            - errors: list - List of error messages
    """
    result = {"deleted_count": 0, "errors": []}

    # Collect all item IDs
    item_ids = []

    # Inventory items
    inventory = character.get("Inventory", {})
    for _, item_id in inventory.items():
        if item_id:
            item_ids.append(item_id)

    # Equipped items
    if character.get("LeftHandID"):
        item_ids.append(character["LeftHandID"])
    if character.get("RightHandID"):
        item_ids.append(character["RightHandID"])

    # Delete each item
    for item_id in item_ids:
        try:
            dynamo.delete_item(TableName.ITEMS, Key={"ItemID": item_id})
            result["deleted_count"] += 1
        except ClientError as err:
            logger.error(f"Failed to delete item for {item_id} Error: {err}")
            result["errors"].append(f"Failed to delete item {item_id}: {err}")

    return result


def delete_character_active_segments(character_id: str) -> dict:
    """
    Delete all active segments for a character.

    Args:
        character_id: Character UUID

    Returns:
        Dict with:
            - deleted_count: int - Number of segments deleted
            - errors: list - List of error messages
    """
    result = {"deleted_count": 0, "errors": []}

    try:
        active_segments = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="CharacterID-index",
            KeyConditionExpression="CharacterID = :cid",
            ExpressionAttributeValues={":cid": character_id},
        )

        for segment in active_segments:  # type: ignore
            try:
                dynamo.delete_item(
                    TableName.ACTIVE_SEGMENTS,
                    Key={"ActiveSegmentID": segment["ActiveSegmentID"]},
                )
                result["deleted_count"] += 1
            except ClientError as err:
                logger.error(f"Failed to delete active segment for {segment['ActiveSegmentID']} Error: {err}")
                result["errors"].append(f"Failed to delete active segment {segment['ActiveSegmentID']}: {err}")

    except ClientError as err:
        logger.error(f"Failed to query active segments for {character_id} Error: {err}")
        result["errors"].append(f"Failed to query active segments: {err}")

    return result


def delete_character_history(character_id: str) -> dict:
    """
    Delete all history records for a character.

    Args:
        character_id: Character UUID

    Returns:
        Dict with:
            - deleted_count: int - Number of history records deleted
            - errors: list - List of error messages
    """
    result = {"deleted_count": 0, "errors": []}

    try:
        history_records = dynamo.query(
            TableName.STORY_HISTORY,
            KeyConditionExpression="CharacterID = :cid",
            ExpressionAttributeValues={":cid": character_id},
        )

        for record in history_records:  # type: ignore
            try:
                dynamo.delete_item(
                    TableName.STORY_HISTORY,
                    Key={"CharacterID": character_id, "StoryID": record["StoryID"]},
                )
                result["deleted_count"] += 1
            except ClientError as err:
                logger.error(f"Failed to delete history record for {record['StoryID']} Error: {err}")
                result["errors"].append(f"Failed to delete history record for story {record['StoryID']}: {err}")

    except ClientError as err:
        logger.error(f"Failed to query history for {character_id} Error: {err}")
        result["errors"].append(f"Failed to query history: {err}")

    return result


def delete_character_record(character_id: str) -> dict:
    """
    Delete the character record from the database.

    Args:
        character_id: Character UUID

    Returns:
        Dict with:
            - deleted: bool - Whether the character was deleted
            - error: str - Error message if deletion failed
    """
    result = {"deleted": False, "error": None}

    try:
        dynamo.delete_item(TableName.CHARACTERS, Key={"CharacterID": character_id})
        result["deleted"] = True
        logger.info(f"Deleted character record for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to delete character for {character_id} Error: {err}")
        result["error"] = f"Failed to delete character: {err}"

    return result


def delete_character(character_id: str, remove_from_player_list: bool = True) -> dict:
    """
    Delete a character and all associated data.

    Note: Ownership verification should be performed before calling this function.

    Args:
        character_id: UUID of the character to delete
        remove_from_player_list: Whether to remove character from player's CharacterList (default: True)

    Returns:
        Dictionary with deletion results including deleted items
    """
    results = {
        "character_deleted": False,
        "character_removed_from_player": False,
        "items_deleted": 0,
        "active_segments_deleted": 0,
        "history_deleted": 0,
        "errors": [],
    }

    # Retrieve character data
    character = None
    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
    except ClientError as err:
        logger.error(f"Failed to retrieve character for deletion for {character_id} Error: {err}")
        results["errors"].append(f"Failed to retrieve character: {err}")

    if character:
        # Remove from player list if requested
        if remove_from_player_list:
            player_id = character.get("PlayerID")
            character_name = character.get("CharacterName")

            if player_id and character_name:
                player_result = remove_character_from_player_list(player_id, character_name)
                results["character_removed_from_player"] = player_result["removed"]
                if player_result["error"]:
                    results["errors"].append(player_result["error"])

        # Delete all character items
        items_result = delete_character_items(character)
        results["items_deleted"] = items_result["deleted_count"]
        results["errors"].extend(items_result["errors"])

        # Delete the character record
        char_result = delete_character_record(character_id)
        results["character_deleted"] = char_result["deleted"]
        if char_result["error"]:
            results["errors"].append(char_result["error"])

        # Log character deletion with details
        logger.info(f"Character deletion processed for {character_id}")

    # Delete active segments (can proceed even if character not found)
    segments_result = delete_character_active_segments(character_id)
    results["active_segments_deleted"] = segments_result["deleted_count"]
    results["errors"].extend(segments_result["errors"])

    # Delete history records
    history_result = delete_character_history(character_id)
    results["history_deleted"] = history_result["deleted_count"]
    results["errors"].extend(history_result["errors"])

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
            - characters_deleted: int - Number of characters deleted
            - items_deleted: int - Total items deleted across all characters
            - active_segments_deleted: int - Total segments deleted
            - history_deleted: int - Total history records deleted
            - errors: list - List of error messages
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
