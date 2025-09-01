"""
Story completion and abandonment operations.

Provides functions for completing stories and cleaning up state.
"""

from datetime import datetime

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger
from eidolon.story_rewards import apply_story_rewards, calculate_story_rewards
from eidolon.time_utils import now_iso


def complete_story_for_character(character_id: str) -> None:
    """
    Clean up character state when story is completed.

    Args:
        character_id: Character UUID

    Raises:
        RuntimeError: If database operations fail
    """
    try:
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET GameMode = :none REMOVE ActiveStoryID, ActiveSegmentID",
            ExpressionAttributeValues={":none": "None"},
        )

        logger.info(f"Character state cleared for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to clear character state for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to clear character state: {err}") from err


def complete_story(character_id: str, story_id: str, story_instance_id, outcome: str) -> None:
    """
    Complete the story, apply rewards, and update character state.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        story_instance_id: Story instance UUID
        outcome: Final outcome
    """
    complete_story_for_character(character_id)

    if story_instance_id:
        try:
            history = dynamo.get_item(TableName.STORY_HISTORY, {"CharacterID": character_id, "StoryInstanceID": story_instance_id})
            if history:
                started_at = history.get("StartedAt", "")
                if started_at:
                    start_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                    end_time = datetime.utcnow()
                    duration = int((end_time - start_time).total_seconds())
                else:
                    duration = 0

                dynamo.update_item(
                    TableName.STORY_HISTORY,
                    Key={"CharacterID": character_id, "StoryInstanceID": story_instance_id},
                    UpdateExpression="SET FinishedAt = :finished, FinalOutcome = :outcome, TotalDuration = :duration",
                    ExpressionAttributeValues={
                        ":finished": now_iso(),
                        ":outcome": outcome,
                        ":duration": duration,
                    },
                )
        except Exception as err:
            logger.warning(f"Failed to update story history completion: {err}")

    try:
        story_metadata = dynamo.get_item(TableName.STORY, {"StoryID": story_id})
        if not story_metadata:
            raise ValueError("Story not found")
    except ClientError as err:
        logger.error(f"Failed to get story for {story_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get story: {err}") from err

    story_type = story_metadata.get("StoryType", "repeatable")
    if story_type == "repeatable":
        # For repeatable stories, we don't track in CompletedStories
        # since they can be repeated. Just log the completion.
        logger.info(f"Repeatable story {story_id} completed for {character_id}")

    if story_instance_id:
        history = dynamo.get_item(TableName.STORY_HISTORY, {"CharacterID": character_id, "StoryInstanceID": story_instance_id})
        segments_completed = len(history.get("SegmentHistory", [])) if history else 0
    else:
        segments_completed = 0

    rewards = calculate_story_rewards(story_metadata, outcome, segments_completed)
    if rewards.get("xp", 0) > 0 or rewards.get("items") or rewards.get("currency", 0) > 0:
        apply_story_rewards(character_id, rewards)
