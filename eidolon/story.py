"""
Story management utilities for Lambda functions.

Provides common functions for story operations including starting, abandoning,
and managing story segments.
"""

from datetime import datetime, timezone

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import get_logger

logger = get_logger(__name__)


def get_active_story_segment(character_id: str) -> dict:
    """
    Get the active story segment for a character.

    Args:
        character_id: Character UUID

    Returns:
        Dict with:
            - success: bool
            - data: Active segment data (if success)
            - error: Error message (if failed)
    """

    try:
        # Query by CharacterID index
        items = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="CharacterID-index",
            KeyConditionExpression="CharacterID = :cid",
            FilterExpression="#status = :status",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={":cid": character_id, ":status": "active"},
        )

        if not items:
            return {"success": False, "error": "No active story found"}

        # Should only be one active segment per character
        return {"success": True, "data": items[0]}

    except Exception as err:
        logger.error(
            "Error querying active segments",
            extra={"character_id": character_id, "error": str(err)},
        )
        return {"success": False, "error": "Failed to query active segments"}


def mark_segment_as_abandoned(active_segment_id: str) -> dict:
    """
    Mark an active segment as abandoned.

    Args:
        active_segment_id: Active segment UUID

    Returns:
        Dict with:
            - success: bool
            - error: Error message (if failed)
    """

    try:
        dynamo.update_item(
            TableName.ACTIVE_SEGMENTS,
            Key={"ActiveSegmentID": active_segment_id},
            UpdateExpression="SET #status = :status",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={":status": "abandoned"},
        )
        logger.info("Marked segment as abandoned", extra={"active_segment_id": active_segment_id})
        return {"success": True}

    except Exception as err:
        logger.error(
            "Failed to mark segment as abandoned",
            extra={"active_segment_id": active_segment_id, "error": str(err)},
        )
        return {"success": False, "error": "Failed to update segment"}


def record_story_abandonment(character_id: str, story_id: str) -> dict:
    """
    Update history to record story abandonment.

    Args:
        character_id: Character UUID
        story_id: Story UUID

    Returns:
        Dict with:
            - success: bool
            - error: Error message (if failed)
    """

    try:
        # Get existing history entry
        history = dynamo.get_item(TableName.HISTORY, {"CharacterID": character_id, "StoryID": story_id})

        if history:
            # Increment abandoned count and set finished time
            abandoned_count = history.get("AbandonedCount", 0) + 1

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
            logger.info(
                "Updated story history with abandonment",
                extra={
                    "character_id": character_id,
                    "story_id": story_id,
                    "abandoned_count": abandoned_count,
                },
            )
        return {"success": True}

    except Exception as err:
        logger.error(
            "Failed to record story abandonment",
            extra={"character_id": character_id, "story_id": story_id, "error": str(err)},
        )
        return {"success": False, "error": "Failed to update history"}


def add_story_to_abandoned_list(character_id: str, story_id: str) -> dict:
    """
    Add a story to the character's AbandonedStories list.

    Args:
        character_id: Character UUID
        story_id: Story UUID to add to abandoned list

    Returns:
        Dict with:
            - success: bool
            - error: Error message (if failed)
    """
    try:
        # Add story to AbandonedStories list if not already present
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="ADD AbandonedStories :story",
            ExpressionAttributeValues={":story": {story_id}},
        )
        logger.info(
            "Added story to abandoned list",
            extra={"character_id": character_id, "story_id": story_id},
        )
        return {"success": True}

    except Exception as err:
        logger.error(
            "Failed to add story to abandoned list",
            extra={"character_id": character_id, "story_id": story_id, "error": str(err)},
        )
        return {"success": False, "error": "Failed to update character"}
