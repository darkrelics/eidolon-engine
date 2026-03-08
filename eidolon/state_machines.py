"""
State machine definitions and transition validation.

Provides enums and functions for enforcing valid state transitions across:
- Character GameMode (None/Incremental/MUD)
- Segment ProcessingStatus (pending/processing/processed)
- Story Lifecycle (Available/Active/Completed/Abandoned)
"""

from datetime import datetime, timezone
from enum import Enum

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger


class GameMode(str, Enum):
    """Character GameMode states."""

    NONE = "None"
    INCREMENTAL = "Incremental"
    MUD = "MUD"


class ProcessingStatus(str, Enum):
    """Segment processing states."""

    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"


class StoryLifecycle(str, Enum):
    """Story lifecycle states."""

    AVAILABLE = "Available"
    ACTIVE = "Active"
    COMPLETED = "Completed"
    ABANDONED = "Abandoned"


# Valid ProcessingStatus transitions
VALID_PROCESSING_TRANSITIONS = {
    ProcessingStatus.PENDING: {ProcessingStatus.PROCESSING, ProcessingStatus.PROCESSED},
    ProcessingStatus.PROCESSING: {ProcessingStatus.PROCESSED, ProcessingStatus.PENDING},
    ProcessingStatus.PROCESSED: set(),
}


# Valid GameMode transitions
VALID_GAMEMODE_TRANSITIONS = {
    GameMode.NONE: {GameMode.INCREMENTAL, GameMode.MUD},
    GameMode.INCREMENTAL: {GameMode.NONE},
    GameMode.MUD: {GameMode.NONE},
}


def validate_gamemode_transition(current_mode: str, new_mode: str) -> bool:
    """
    Check if a GameMode transition is valid.

    Args:
        current_mode: Current GameMode value
        new_mode: Desired GameMode value

    Returns:
        True if transition is allowed, False otherwise
    """
    try:
        current = GameMode(current_mode)
        new = GameMode(new_mode)

        if current == new:
            return True

        allowed = VALID_GAMEMODE_TRANSITIONS.get(current, set())
        return new in allowed

    except ValueError as err:
        logger.error(f"Invalid GameMode value: current={current_mode}, new={new_mode}: {err}")
        return False


def set_character_game_mode(
    character_id: str,
    new_mode: str,
    expected_current=None,
    active_story_id=None,
    active_segment_id=None,
    story_instance_id=None,
) -> bool:
    """
    Atomically set character GameMode with validation.

    Uses DynamoDB conditional write to ensure state consistency.

    Args:
        character_id: Character UUID
        new_mode: Desired GameMode (None/Incremental/MUD)
        expected_current: Expected current GameMode (optional, for extra safety)
        active_story_id: Story ID to set when entering Incremental mode
        active_segment_id: Segment ID to set when entering Incremental mode
        story_instance_id: Story instance ID to add to CompletedStories (optional)

    Returns:
        True if transition successful, False if condition failed

    Raises:
        ValueError: If transition is invalid or parameters incorrect
        RuntimeError: If database error occurs
    """
    if not character_id:
        raise ValueError("Character ID cannot be empty")

    try:
        new_game_mode = GameMode(new_mode)
    except ValueError as err:
        raise ValueError(f"Invalid GameMode: {new_mode}") from err

    # Build update expression
    update_expression = "SET GameMode = :new_mode, UpdatedAt = :timestamp"
    expression_values: dict = {
        ":new_mode": new_game_mode.value,
        ":timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Build condition expression
    condition_parts = []

    if expected_current:
        try:
            expected_mode = GameMode(expected_current)
            condition_parts.append("GameMode = :expected_mode")
            expression_values[":expected_mode"] = expected_mode.value
        except ValueError as err:
            raise ValueError(f"Invalid expected GameMode: {expected_current}") from err

    # Special handling for Incremental mode
    if new_game_mode == GameMode.INCREMENTAL:
        if not active_story_id or not active_segment_id:
            raise ValueError("Active story and segment IDs required when entering Incremental mode")

        # Add story/segment to update
        update_expression += ", ActiveStoryID = :story_id, ActiveSegmentID = :segment_id"
        expression_values[":story_id"] = active_story_id
        expression_values[":segment_id"] = active_segment_id

        # Add to CompletedStories if story_instance_id provided
        # Only track "one-time" and "daily" stories (not "repeatable")
        if story_instance_id:
            try:
                # Fetch story to get StoryType
                story = dynamo.get_item(TableName.STORY, {"StoryID": active_story_id})
                story_type = story.get("StoryType", "repeatable") if story else "repeatable"

                # Only add one-time and daily stories to CompletedStories
                if story_type in ("one-time", "daily"):
                    # Create entry: {story_id: {"StoryType": "daily", "CompletedAt": timestamp}}
                    completed_entry = {
                        active_story_id: {
                            "StoryType": story_type,
                            "CompletedAt": int(datetime.now(timezone.utc).timestamp()),
                        }
                    }

                    # Append to CompletedStories list
                    # Initialize as empty list if not exists
                    update_expression += (
                        ", CompletedStories = list_append(if_not_exists(CompletedStories, :empty_list), :completed_entry)"
                    )
                    expression_values[":empty_list"] = []
                    expression_values[":completed_entry"] = [completed_entry]

                    logger.info(f"Adding story {active_story_id} ({story_type}) to CompletedStories for character {character_id}")
                else:
                    logger.debug(f"Story {active_story_id} is repeatable, not adding to CompletedStories")

            except ClientError as err:
                logger.warning(f"Failed to fetch story {active_story_id} for CompletedStories tracking: {err}")
                # Continue without adding to CompletedStories - non-critical
            except Exception as err:
                logger.warning(f"Unexpected error checking story type for CompletedStories: {err}")
                # Continue without adding to CompletedStories - non-critical

        # Require that current mode allows transition to Incremental
        if not expected_current:
            # If no expected mode specified, require None or recovery from broken Incremental state
            condition_parts.append(
                "(GameMode = :none) OR "
                "(GameMode = :incremental AND "
                "(attribute_not_exists(ActiveStoryID) OR ActiveStoryID = :null_value) AND "
                "(attribute_not_exists(ActiveSegmentID) OR ActiveSegmentID = :null_value))"
            )
            expression_values[":none"] = GameMode.NONE.value
            expression_values[":incremental"] = GameMode.INCREMENTAL.value
            expression_values[":null_value"] = None  # type: ignore

    # Special handling for returning to None
    elif new_game_mode == GameMode.NONE:
        # Clear active story/segment fields when returning to None
        update_expression += " REMOVE ActiveStoryID, ActiveSegmentID"

    # Execute conditional update
    try:
        condition_expression = " AND ".join(condition_parts) if condition_parts else None

        update_kwargs = {
            "UpdateExpression": update_expression,
            "ExpressionAttributeValues": expression_values,
        }

        if condition_expression:
            update_kwargs["ConditionExpression"] = condition_expression

        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            **update_kwargs,
        )

        logger.info(f"GameMode transition successful for {character_id}: → {new_mode}")
        return True

    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "Unknown")

        if error_code == "ConditionalCheckFailedException":
            logger.warning(f"GameMode transition failed for {character_id}: condition not met (race condition)")
            return False

        logger.error(f"Failed to update GameMode for {character_id}: {err}", exc_info=True)
        raise RuntimeError(f"Failed to update GameMode: {err}") from err


def claim_segment_for_processing(active_segment_id: str) -> bool:
    """
    Atomically claim a segment for processing (pending → processing).

    Uses DynamoDB conditional write to ensure only one Lambda claims the segment.

    Args:
        active_segment_id: Active segment UUID

    Returns:
        True if claim successful, False if already claimed

    Raises:
        ValueError: If segment ID is empty
        RuntimeError: If database error occurs
    """
    if not active_segment_id:
        raise ValueError("Active segment ID cannot be empty")

    try:
        dynamo.update_item(
            TableName.ACTIVE_SEGMENTS,
            Key={"ActiveSegmentID": active_segment_id},
            UpdateExpression="SET ProcessingStatus = :processing, ProcessingStartedAt = :timestamp",
            ConditionExpression="ProcessingStatus = :pending",
            ExpressionAttributeValues={
                ":processing": ProcessingStatus.PROCESSING.value,
                ":pending": ProcessingStatus.PENDING.value,
                ":timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        logger.info(f"Claimed segment for processing: {active_segment_id}")
        return True

    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "Unknown")

        if error_code == "ConditionalCheckFailedException":
            logger.info(f"Segment already claimed for processing: {active_segment_id}")
            return False

        logger.error(f"Failed to claim segment for processing {active_segment_id}: {err}", exc_info=True)
        raise RuntimeError(f"Failed to claim segment: {err}") from err


