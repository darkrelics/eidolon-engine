"""
Active segment and story operations.

Provides functions for managing active segments and stories.
"""

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger
from eidolon.state_machines import GameMode, set_character_game_mode


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

    if len(items) > 1:
        logger.warning(f"Multiple active decision segments found for {character_id}: {[s.get('ActiveSegmentID') for s in items]}")

    # No need to check PlayerID again - already filtered in query
    active_segment = items[0]
    logger.info(
        f"Retrieved active decision segment for {character_id}: "
        f"ActiveSegmentID={active_segment.get('ActiveSegmentID')}, "
        f"Decision={active_segment.get('Decision')}, "
        f"Status={active_segment.get('Status')}"
    )
    return active_segment


def story_update_character(
    character_id: str,
    story_id: str,
    active_segment_id: str,
    story_instance_id: str | None = None,
) -> dict:
    """
    Atomically update character to set GameMode, ActiveStoryID, and ActiveSegmentID.

    Delegates to state machine for GameMode transition validation.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        active_segment_id: Active segment UUID
        story_instance_id: Story instance UUID to add to CompletedStories (optional)

    Returns:
        Empty dict for backward compatibility

    Raises:
        ValueError: If character state changed (race condition)
        RuntimeError: If database update fails
    """
    logger.debug(f"Updating character state with GameMode=Incremental, ActiveStoryID={story_id}")

    # Use state machine to set GameMode to Incremental
    success = set_character_game_mode(
        character_id=character_id,
        new_mode=GameMode.INCREMENTAL.value,
        active_story_id=story_id,
        active_segment_id=active_segment_id,
        story_instance_id=story_instance_id,
    )

    if not success:
        logger.warning(f"Character {character_id} state changed during story start (race condition)")
        raise ValueError("Character state conflict")

    return {}
