"""
Story management utilities for Lambda functions.

Provides common functions for story operations including starting, abandoning,
and managing story segments.
"""

from datetime import datetime, timezone

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import get_logger

logger = get_logger(__name__)


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
        logger.error(
            "Failed to query active segments",
            extra={
                "character_id": character_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown")
            },
            exc_info=True
        )
        raise RuntimeError(f"Failed to query active segments: {str(err)}")

    if not items:
        raise ValueError(f"No active story found for character {character_id}")

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
        logger.error(
            "Failed to mark segment as abandoned",
            extra={
                "active_segment_id": active_segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown")
            },
            exc_info=True
        )
        raise RuntimeError(f"Failed to mark segment as abandoned: {str(err)}")

    logger.info(
        "Marked segment as abandoned",
        extra={"active_segment_id": active_segment_id}
    )


def record_story_abandonment(character_id: str, story_id: str) -> None:
    """
    Update history to record story abandonment.

    Args:
        character_id: Character UUID
        story_id: Story UUID

    Raises:
        ValueError: If character_id or story_id is empty
        RuntimeError: If database operations fail
    """
    if not character_id:
        raise ValueError("Character ID cannot be empty")
    if not story_id:
        raise ValueError("Story ID cannot be empty")

    try:
        history = dynamo.get_item(
            TableName.HISTORY, 
            {"CharacterID": character_id, "StoryID": story_id}
        )
    except ClientError as err:
        logger.error(
            "Failed to get story history",
            extra={
                "character_id": character_id,
                "story_id": story_id,
                "error": str(err)
            },
            exc_info=True
        )
        raise RuntimeError(f"Failed to get story history: {str(err)}")

    if history:
        abandoned_count = history.get("AbandonedCount", 0) + 1

        try:
            dynamo.update_item(
                TableName.HISTORY,
                Key={"CharacterID": character_id, "StoryID": story_id},
                UpdateExpression="SET FinishedAt = :finished, AbandonedCount = :count, FinalOutcome = :outcome",
                ExpressionAttributeValues={
                    ":finished": datetime.now(timezone.utc).isoformat(),
                    ":count": abandoned_count,
                    ":outcome": "abandoned",
                },
            )
        except ClientError as err:
            logger.error(
                "Failed to update story history",
                extra={
                    "character_id": character_id,
                    "story_id": story_id,
                    "error": str(err)
                },
                exc_info=True
            )
            raise RuntimeError(f"Failed to update story history: {str(err)}")

        logger.info(
            "Updated story history with abandonment",
            extra={
                "character_id": character_id,
                "story_id": story_id,
                "abandoned_count": abandoned_count,
            },
        )


def add_story_to_abandoned_list(character_id: str, story_id: str) -> None:
    """
    Add a story to the character's AbandonedStories list.

    Uses DynamoDB's ADD operation which automatically handles duplicates,
    ensuring each story ID appears only once in the set.

    Args:
        character_id: Character UUID
        story_id: Story UUID to add to abandoned list

    Raises:
        ValueError: If character_id or story_id is empty
        RuntimeError: If database update fails
    """
    if not character_id:
        raise ValueError("Character ID cannot be empty")
    if not story_id:
        raise ValueError("Story ID cannot be empty")

    try:
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="ADD AbandonedStories :story",
            ExpressionAttributeValues={":story": {story_id}},
        )
    except ClientError as err:
        logger.error(
            "Failed to add story to abandoned list",
            extra={
                "character_id": character_id,
                "story_id": story_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown")
            },
            exc_info=True
        )
        raise RuntimeError(f"Failed to add story to abandoned list: {str(err)}")

    logger.info(
        "Added story to abandoned list",
        extra={"character_id": character_id, "story_id": story_id}
    )
