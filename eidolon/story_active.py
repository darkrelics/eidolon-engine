"""
Active segment and story operations.

Provides functions for managing active segments and stories.
"""

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger


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
        raise RuntimeError(f"Failed to query active segments: {err}") from err

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
        ValueError: If active_segment_id is empty or segment not in processing state
        RuntimeError: If database update fails
    """
    if not active_segment_id:
        raise ValueError("Active segment ID cannot be empty")

    try:
        dynamo.update_item(
            TableName.ACTIVE_SEGMENTS,
            Key={"ActiveSegmentID": active_segment_id},
            UpdateExpression="SET #status = :abandoned, ProcessingStatus = :processed, #outcome = :outcome",
            ConditionExpression="attribute_exists(ActiveSegmentID) AND (#status = :active OR #status = :abandoned)",
            ExpressionAttributeNames={"#status": "Status", "#outcome": "Outcome"},
            ExpressionAttributeValues={
                ":abandoned": "abandoned",
                ":processed": "processed",
                ":outcome": "abandoned",
                ":active": "active",
            },
        )
    except ClientError as err:
        if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.info(f"Segment {active_segment_id} already in terminal state, skipping abandonment")
            return
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

    # No need to check PlayerID again - already filtered in query
    return items[0]


def story_update_character(
    character_id: str,
    story_id: str,
    active_segment_id: str,
    story_instance_id: str | None = None,
) -> dict:
    """
    Atomically update character to set GameMode, ActiveStoryID, and ActiveSegmentID.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        active_segment_id: Active segment UUID

    Returns:
        DynamoDB update response

    Raises:
        ValueError: If character state changed (race condition)
        RuntimeError: If database update fails
    """
    update_expression = "SET GameMode = :mode, ActiveStoryID = :story_id, ActiveSegmentID = :segment_id"

    # Build condition expression - allow if GameMode is None OR (Incremental with no active story/segment)
    condition_expression = (
        "(GameMode = :none) OR "
        "(GameMode = :incremental AND "
        "(attribute_not_exists(ActiveStoryID) OR ActiveStoryID = :null) AND "
        "(attribute_not_exists(ActiveSegmentID) OR ActiveSegmentID = :null))"
    )

    try:
        logger.debug(f"Updating character state with GameMode=Incremental, ActiveStoryID={story_id}")
        expression_values = {
            ":mode": "Incremental",
            ":none": "None",
            ":incremental": "Incremental",
            ":null": None,
            ":story_id": story_id,
            ":segment_id": active_segment_id,
        }

        if story_instance_id:
            update_expression += " ADD CompletedStories :story_instance"
            expression_values[":story_instance"] = {story_instance_id}

        response = dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values,
            ConditionExpression=condition_expression,
        )
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "Unknown")
        logger.error(f"DynamoDB error updating character {character_id}: Code={error_code}, Error={err}")

        if error_code == "ConditionalCheckFailedException":
            logger.warning(f"Character {character_id} state changed during story start (race condition)")
            raise ValueError("Character state conflict") from err

        logger.error(f"Failed to update character state for {character_id}: {err}", exc_info=True)
        raise RuntimeError(f"Failed to update character state: {err}") from err

    return response  # type: ignore

