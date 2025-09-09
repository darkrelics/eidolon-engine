"""
Character segment management utilities.

Provides functions for managing character interactions with story segments.
"""

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger


def character_get_active_segment(character: dict) -> dict:
    """
    Get active segment for a character.

    Args:
        character: Character Record dict

    Returns:
        Active segment dict. Empty dict if no active segment found.

    Raises:
        RuntimeError: If database error occurs
    """
    character_id: str = character.get("CharacterID")  # type: ignore
    active_segment_id: str = character.get("ActiveSegmentID")  # type: ignore

    # First try: If character has ActiveSegmentID, use GetItem
    if active_segment_id:
        try:
            active_segment: dict = dynamo.get_item(TableName.ACTIVE_SEGMENTS, key={"ActiveSegmentID": active_segment_id})  # type: ignore

            if active_segment:
                # Verify the segment is still active and belongs to this character
                if active_segment.get("Status") == "active" and active_segment.get("CharacterID") == character_id:
                    logger.debug("Active segment found via GetItem")
                    return active_segment
                else:
                    logger.warning("Segment found but not valid")
        except ClientError as err:
            logger.error(f"Error retrieving active segment by ID for {character_id} Error: {err}")
            # Fall through to query approach

    # Second try: Query by CharacterID index
    query_params: dict = {
        "IndexName": "CharacterID-index",
        "KeyConditionExpression": "CharacterID = :cid",
        "FilterExpression": "#status = :status",
        "ExpressionAttributeNames": {"#status": "Status"},
        "ExpressionAttributeValues": {
            ":cid": character_id,
            ":status": "active",
        },
        "Limit": 1,
    }

    try:
        items: list = dynamo.query(TableName.ACTIVE_SEGMENTS, **query_params)  # type: ignore

        if not items:
            logger.info(f"No active segment found via query for {character_id}")
            return {}

        # Should only be one active segment per character
        active_segment = items[0]

        segment_id = active_segment.get("ActiveSegmentID", "unknown")
        logger.info(f"Active segment {segment_id} found for character {character_id}")

        return active_segment

    except ClientError as err:
        logger.error(f"Error querying active segments for {character_id} Error: {err}")
        raise RuntimeError(f"Failed to retrieve active segment: {err}") from err


def update_character_active_segment(character_id: str, active_segment_id: str) -> None:
    """
    Update character's ActiveSegmentID field.

    Args:
        character_id: Character UUID
        active_segment_id: Active segment UUID to set

    Raises:
        ValueError: If character_id or active_segment_id is empty
        RuntimeError: If database update fails
    """
    if not character_id:
        raise ValueError("Character ID cannot be empty")
    if not active_segment_id:
        raise ValueError("Active segment ID cannot be empty")

    try:
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET ActiveSegmentID = :segment_id",
            ExpressionAttributeValues={":segment_id": active_segment_id},
        )
        logger.info(f"Updated character active segment for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to update character active segment for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to update character active segment: {err}") from err
