"""
Story completion and abandonment operations.

Provides functions for completing stories and cleaning up state.
"""

from datetime import datetime, timezone

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

    Idempotent: safe to call multiple times. Rewards are only applied once.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        story_instance_id: Story instance UUID
        outcome: Final outcome
    """
    # Idempotency check: if story already completed, skip reward application
    already_completed = False
    if story_instance_id:
        try:
            existing_history = dynamo.get_item(
                TableName.STORY_HISTORY, {"CharacterID": character_id, "StoryInstanceID": story_instance_id}
            )
            if existing_history and existing_history.get("FinishedAt"):
                logger.info(
                    f"Story {story_instance_id} already completed for {character_id}, "
                    f"skipping reward application (idempotency check)"
                )
                already_completed = True
        except ClientError as err:
            logger.warning(f"Failed idempotency check for story {story_instance_id}: {err}")
            # Continue with completion - better to risk double rewards than fail

    complete_story_for_character(character_id)

    if story_instance_id:
        try:
            history = dynamo.get_item(TableName.STORY_HISTORY, {"CharacterID": character_id, "StoryInstanceID": story_instance_id})
            if history:
                started_at = history.get("StartedAt", "")
                if started_at:
                    # Handle both string and datetime formats
                    if isinstance(started_at, str):
                        start_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                    else:
                        start_time = started_at
                    end_time = datetime.now(timezone.utc)
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
    logger.info(f"Story {story_id} completed for {character_id} (type={story_type})")

    if story_instance_id:
        history = dynamo.get_item(TableName.STORY_HISTORY, {"CharacterID": character_id, "StoryInstanceID": story_instance_id})
        segments_completed = len(history.get("SegmentHistory", [])) if history else 0
    else:
        segments_completed = 0

    # Only apply rewards if not already completed (idempotency)
    if not already_completed:
        rewards = calculate_story_rewards(story_metadata, outcome, segments_completed)
        if rewards.get("items") or rewards.get("currency", 0) > 0:
            apply_story_rewards(character_id, rewards)
    else:
        logger.debug(f"Skipping rewards for {character_id} - story already completed")
