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


def _claim_story_completion(character_id: str, story_instance_id: str, outcome: str) -> tuple[bool, dict]:
    """
    Atomically mark a story instance as finished.

    Uses a conditional DynamoDB update so only the first caller "wins" and is
    responsible for applying rewards. Retried or concurrent invocations will
    see ConditionalCheckFailedException and skip reward application.

    Returns:
        (won_race, history) where won_race is True when this call successfully
        set FinishedAt. history is the story history record used for duration.
    """
    try:
        history = (
            dynamo.get_item(
                TableName.STORY_HISTORY,
                {"CharacterID": character_id, "StoryInstanceID": story_instance_id},
            )
            or {}
        )
    except ClientError as err:
        logger.error(f"Failed to read story history {story_instance_id}: {err}", exc_info=True)
        raise RuntimeError("Failed to read story history") from err

    started_at = history.get("StartedAt", "")
    if started_at:
        if isinstance(started_at, str):
            start_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        else:
            start_time = started_at
        duration = int((datetime.now(timezone.utc) - start_time).total_seconds())
    else:
        duration = 0

    try:
        dynamo.update_item(
            TableName.STORY_HISTORY,
            Key={"CharacterID": character_id, "StoryInstanceID": story_instance_id},
            UpdateExpression="SET FinishedAt = :finished, FinalOutcome = :outcome, TotalDuration = :duration",
            ConditionExpression="attribute_not_exists(FinishedAt)",
            ExpressionAttributeValues={
                ":finished": now_iso(),
                ":outcome": outcome,
                ":duration": duration,
            },
        )
        return True, history
    except ClientError as err:
        if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.info(
                f"Story {story_instance_id} already completed for {character_id}; "
                f"skipping reward application (atomic idempotency)"
            )
            return False, history
        logger.error(f"Failed to finalize story history {story_instance_id}: {err}", exc_info=True)
        raise RuntimeError("Failed to finalize story history") from err


def complete_story(character_id: str, story_id: str, story_instance_id, outcome: str) -> None:
    """
    Complete the story, apply rewards, and update character state.

    Idempotent: safe to call multiple times. Rewards are only applied once,
    guarded by a conditional write on StoryHistory.FinishedAt.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        story_instance_id: Story instance UUID
        outcome: Final outcome
    """
    complete_story_for_character(character_id)

    won_race = True
    history: dict = {}
    if story_instance_id:
        won_race, history = _claim_story_completion(character_id, story_instance_id, outcome)

    try:
        story_metadata = dynamo.get_item(TableName.STORY, {"StoryID": story_id})
        if not story_metadata:
            raise ValueError("Story not found")
    except ClientError as err:
        logger.error(f"Failed to get story for {story_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get story: {err}") from err

    story_type = story_metadata.get("StoryType", "repeatable")
    logger.info(f"Story {story_id} completed for {character_id} (type={story_type})")

    if not won_race:
        logger.debug(f"Skipping rewards for {character_id} - story already completed")
        return

    segments_completed = len(history.get("SegmentHistory", [])) if history else 0
    rewards = calculate_story_rewards(story_metadata, outcome, segments_completed)
    if rewards.get("items") or rewards.get("currency", 0) > 0:
        apply_story_rewards(character_id, rewards)
