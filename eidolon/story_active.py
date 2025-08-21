"""
Active segment and story operations.

Provides functions for managing active segments and stories.
"""

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger
from eidolon.time_utils import now_iso


def get_active_story_segment(character_id: str) -> dict:
    """
    Get the active story segment for a character.

    Args:
        character_id: Character UUID

    Returns:
        Active segment data dict

    Raises:
        ValueError: If no active story found for character
        RuntimeError: If database query fails
    """
    if not character_id:
        raise ValueError("Character ID cannot be empty")

    try:
        items = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="CharacterID-index",
            KeyConditionExpression="CharacterID = :cid",
            FilterExpression="#status = :status",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={":cid": character_id, ":status": "active"},
        )
    except ClientError as err:
        logger.error(f"Failed to query active segments for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError from err

    if not items:
        raise ValueError(f"No active story found for character {character_id}")

    return items[0]


def get_active_story_segment_with_player_check(character_id: str, player_id: str) -> dict:
    """
    Get the active story segment for a character with player ID verification.

    Args:
        character_id: Character UUID
        player_id: Player ID for verification

    Returns:
        Active segment data dict

    Raises:
        ValueError: If no active story found for character
        RuntimeError: If database query fails
    """
    if not character_id:
        raise ValueError("Character ID cannot be empty")
    if not player_id:
        raise ValueError("Player ID cannot be empty")

    try:
        items = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="CharacterID-index",
            KeyConditionExpression="CharacterID = :cid",
            FilterExpression="PlayerID = :pid AND #status = :status",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={
                ":cid": character_id,
                ":pid": player_id,
                ":status": "active",
            },
        )
    except ClientError as err:
        logger.error(f"Failed to query active segments for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to query active segments: {err}") from err

    if not items:
        raise ValueError("No active story found")

    return items[0]


def mark_segment_as_abandoned(active_segment_id: str) -> None:
    """
    Mark an active segment as abandoned.

    Args:
        active_segment_id: Active segment UUID

    Raises:
        ValueError: If active_segment_id is empty
        RuntimeError: If database update fails
    """
    if not active_segment_id:
        raise ValueError("Active segment ID cannot be empty")

    try:
        dynamo.update_item(
            TableName.ACTIVE_SEGMENTS,
            Key={"ActiveSegmentID": active_segment_id},
            UpdateExpression="SET #status = :status",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={":status": "abandoned"},
        )
    except ClientError as err:
        logger.error(f"Failed to mark segment as abandoned for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to mark segment as abandoned: {err}") from err

    logger.info(f"Marked segment as abandoned for {active_segment_id}")


def get_active_decision_segment(character_id: str, player_id: str) -> dict:
    """
    Get active decision segment for a character and verify ownership.

    Args:
        character_id: Character UUID
        player_id: Cognito user ID for ownership verification

    Returns:
        Active segment data

    Raises:
        ValueError: If no active decision segment found or validation fails
        RuntimeError: If database query fails
    """
    try:
        items = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="CharacterID-index",
            KeyConditionExpression="CharacterID = :cid",
            FilterExpression="PlayerID = :pid AND #status = :status AND SegmentType = :type",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={
                ":cid": character_id,
                ":pid": player_id,
                ":status": "active",
                ":type": "decision",
            },
        )
    except ClientError as err:
        logger.error(f"Failed to query active segments for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to query active segments: {err}") from err

    if not items:
        logger.warning(f"No active decision segment found for {character_id}")
        raise ValueError("No active decision segment found")

    active_segment = items[0]

    if active_segment.get("PlayerID") != player_id:
        logger.warning(f"Active segment ownership mismatch for {active_segment.get('ActiveSegmentID')}")
        raise ValueError("Active segment not found")

    return active_segment