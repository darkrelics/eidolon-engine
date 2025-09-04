"""
Segment history tracking and special segment operations.

Provides functions for recording segment history and managing rest segments.
"""

from botocore.exceptions import ClientError
from uuid_extension import uuid7

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger
from eidolon.time_utils import now_unix


def record_segment_history(character_id: str, story_id: str, active_segment_id: str, segment_data: dict) -> None:
    """
    Update segment history record with completion data.
    The record should already exist (created when segment started).

    Args:
        character_id: Character UUID
        story_id: Story UUID
        active_segment_id: Active segment UUID
        segment_data: Complete active segment data including all fields

    Raises:
        RuntimeError: If database operation fails
    """
    character_updates = segment_data.get("CharacterUpdates", {})

    update_expressions = []
    expression_values = {}

    update_expressions.append("CompletedAt = :completed_at")
    expression_values[":completed_at"] = now_unix()

    update_expressions.append("Outcome = :outcome")
    expression_values[":outcome"] = segment_data.get("Outcome", "unknown")

    update_expressions.append("CharacterUpdates = :char_updates")
    expression_values[":char_updates"] = character_updates

    if segment_data.get("ProcessedAt"):
        update_expressions.append("ProcessedAt = :processed_at")
        expression_values[":processed_at"] = segment_data["ProcessedAt"]

    if segment_data.get("ClientEvents"):
        update_expressions.append("ClientEvents = :client_events")
        expression_values[":client_events"] = segment_data["ClientEvents"]

    if segment_data.get("ChallengeResults"):
        update_expressions.append("ChallengeResults = :challenge_results")
        expression_values[":challenge_results"] = segment_data["ChallengeResults"]

    if segment_data.get("CombatState"):
        update_expressions.append("CombatState = :combat_state")
        expression_values[":combat_state"] = segment_data["CombatState"]

    if segment_data.get("Decision"):
        update_expressions.append("Decision = :decision")
        expression_values[":decision"] = segment_data["Decision"]

    if segment_data.get("DecisionMadeAt"):
        update_expressions.append("DecisionMadeAt = :decision_made_at")
        expression_values[":decision_made_at"] = segment_data["DecisionMadeAt"]

    try:
        dynamo.update_item(
            TableName.SEGMENT_HISTORY,
            Key={"CharacterID": character_id, "ActiveSegmentID": active_segment_id},
            UpdateExpression="SET " + ", ".join(update_expressions),
            ExpressionAttributeValues=expression_values,
        )

        logger.info(f"Segment history recorded for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to record segment history for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to record segment history: {err}") from err


def record_abandoned_segment_history(character_id: str, story_id: str, active_segment: dict) -> None:
    """
    Record abandoned segment in history table.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        active_segment: Active segment data

    Raises:
        RuntimeError: If database operation fails
    """
    try:
        history_entry = {
            "CharacterID": character_id,
            "ActiveSegmentID": active_segment.get("ActiveSegmentID"),
            "StoryID": story_id,
            "StoryInstanceID": active_segment.get("StoryInstanceID"),
            "SegmentID": active_segment.get("SegmentID"),
            "SegmentType": active_segment.get("SegmentType"),
            "StartTime": active_segment.get("StartTime"),
            "EndTime": active_segment.get("EndTime"),
            "ProcessedAt": active_segment.get("ProcessedAt"),
            "CompletedAt": now_unix(),
            "Outcome": "abandoned",
            "ClientEvents": active_segment.get("ClientEvents", []),
            "CharacterUpdates": {},
        }

        dynamo.put_item(TableName.SEGMENT_HISTORY, history_entry)

        logger.info(f"Recorded abandoned segment in history for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to record segment history for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to record segment history: {err}") from err


def insert_rest_segment(story_id: str, current_segment_id: str, rest_duration: int = 900, time_remaining: int = 0) -> str:
    """
    Insert a rest segment into the story flow after the current segment.

    This function:
    1. Checks if current segment has at least 30 seconds remaining
    2. If not, attempts to insert after the next segment(s)
    3. Creates a rest segment that points to the appropriate NextSegmentID
    4. Updates the appropriate segment to point to the rest segment

    Args:
        story_id: Story UUID
        current_segment_id: Current segment UUID
        rest_duration: Duration of rest segment in seconds (default 15 minutes)
        time_remaining: Time remaining in current segment (seconds)

    Returns:
        Rest segment ID

    Raises:
        ValueError: If no suitable segment found or segments not found
        RuntimeError: If database operations fail
    """
    min_time_required: int = 30

    try:
        current_segment = dynamo.get_item(TableName.SEGMENTS, {"StoryID": story_id, "SegmentID": current_segment_id})
        if not current_segment:
            raise ValueError(f"Current segment not found: {current_segment_id}")
    except ClientError as err:
        logger.error(f"Failed to get current segment for {current_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get current segment: {err}") from err

    # Get the next segment ID from the current segment's Normal outcome
    results = current_segment.get("Results", {})
    normal_result = results.get("Normal", {})
    next_segment_id = normal_result.get("NextSegmentID") if isinstance(normal_result, dict) else None

    if not next_segment_id:
        logger.warning(f"Cannot insert rest - current segment has no normal outcome NextSegmentID for {story_id}")
        raise ValueError("Cannot insert rest segment - current segment has no normal outcome continuation")

    if time_remaining >= min_time_required:
        insertion_point_id = current_segment_id
        rest_next_segment_id = next_segment_id
        logger.info(f"Inserting rest after current segment with {time_remaining}s remaining for {story_id}")
    else:
        checked_segments = {current_segment_id}
        while next_segment_id and next_segment_id not in checked_segments:
            try:
                next_segment = dynamo.get_item(TableName.SEGMENTS, {"StoryID": story_id, "SegmentID": next_segment_id})
                if not next_segment:
                    raise ValueError(f"Next segment not found: {next_segment_id}")
            except ClientError as err:
                logger.error(f"Failed to get next segment for {next_segment_id} Error: {err}", exc_info=True)
                raise RuntimeError(f"Failed to get next segment: {err}") from err

            segment_duration = next_segment.get("SegmentDuration", 300)
            if segment_duration >= min_time_required:
                insertion_point_id = next_segment_id
                # Get the next segment ID from this segment's Normal outcome
                next_results = next_segment.get("Results", {})
                next_normal = next_results.get("Normal", {})
                rest_next_segment_id = next_normal.get("NextSegmentID") if isinstance(next_normal, dict) else None
                logger.info(f"Inserting rest after segment {next_segment_id} for {story_id}")
                break

            checked_segments.add(next_segment_id)
            # Get the next segment ID from this segment's Normal outcome
            next_results = next_segment.get("Results", {})
            next_normal = next_results.get("Normal", {})
            next_segment_id = next_normal.get("NextSegmentID") if isinstance(next_normal, dict) else None
        else:
            logger.warning(f"Cannot insert rest - no suitable segment found for {story_id}")
            raise ValueError("Cannot insert rest segment - no suitable segment with enough time found")

    rest_segment_id = str(uuid7())

    rest_segment = {
        "StoryID": story_id,
        "SegmentID": rest_segment_id,
        "SegmentType": "rest",
        "SegmentDuration": rest_duration,
        "Title": "Rest and Recovery",
        "Prompt": "You take time to rest and recover from your wounds. Your body slowly heals as you regain your strength.",
        "Results": {
            "Normal": {
                "Narrative": "Your rest was restorative. You feel refreshed and ready to continue.",
                "Effects": {},
                "NextSegmentID": rest_next_segment_id,
            }
        },
        "Created": now_unix(),
        "IsTemporary": True,
    }

    try:
        dynamo.put_item(TableName.SEGMENTS, rest_segment)
        logger.info(f"Created rest segment for {rest_segment_id}")
    except ClientError as err:
        logger.error(f"Failed to create rest segment for {rest_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to create rest segment: {err}") from err

    try:
        dynamo.update_item(
            TableName.SEGMENTS,
            Key={"StoryID": story_id, "SegmentID": insertion_point_id},
            UpdateExpression="SET Results.#normal.NextSegmentID = :rest_id",
            ExpressionAttributeNames={"#normal": "Normal"},
            ExpressionAttributeValues={":rest_id": rest_segment_id},
        )
        logger.info(f"Updated segment normal outcome to point to rest for {insertion_point_id}")
    except ClientError as err:
        logger.error(f"Failed to update segment to point to rest for {insertion_point_id} Error: {err}", exc_info=True)
        try:
            dynamo.delete_item(TableName.SEGMENTS, Key={"StoryID": story_id, "SegmentID": rest_segment_id})
        except ClientError:
            pass
        raise RuntimeError(f"Failed to update segment to point to rest: {err}") from err

    return rest_segment_id
