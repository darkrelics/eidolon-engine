"""
Segment history tracking.

Provides functions for recording segment history and checking completion status.
"""

from botocore.exceptions import ClientError

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
    expression_names: dict = {}

    story_id_value = segment_data.get("StoryID") or story_id
    story_instance_id = segment_data.get("StoryInstanceID")
    segment_id_value = segment_data.get("SegmentID")
    segment_type = segment_data.get("SegmentType")
    start_time = segment_data.get("StartTime")
    end_time = segment_data.get("EndTime")
    player_id = segment_data.get("PlayerID")
    status = segment_data.get("Status")
    processing_status = segment_data.get("ProcessingStatus")

    if story_id_value:
        update_expressions.append("StoryID = :story_id")
        expression_values[":story_id"] = story_id_value

    if story_instance_id:
        update_expressions.append("StoryInstanceID = :story_instance_id")
        expression_values[":story_instance_id"] = story_instance_id

    if segment_id_value:
        update_expressions.append("SegmentID = :segment_id")
        expression_values[":segment_id"] = segment_id_value

    if segment_type:
        update_expressions.append("SegmentType = :segment_type")
        expression_values[":segment_type"] = segment_type

    segment_title = segment_data.get("SegmentTitle")
    if segment_title is not None:
        update_expressions.append("SegmentTitle = :segment_title")
        expression_values[":segment_title"] = segment_title

    segment_activity = segment_data.get("SegmentActivity")
    if segment_activity is not None:
        update_expressions.append("SegmentActivity = :segment_activity")
        expression_values[":segment_activity"] = segment_activity

    if start_time is not None:
        update_expressions.append("StartTime = :start_time")
        expression_values[":start_time"] = start_time

    if end_time is not None:
        update_expressions.append("EndTime = :end_time")
        expression_values[":end_time"] = end_time

    if player_id:
        update_expressions.append("PlayerID = :player_id")
        expression_values[":player_id"] = player_id

    if status:
        update_expressions.append("#status = :status")
        expression_values[":status"] = status
        expression_names["#status"] = "Status"

    if processing_status:
        update_expressions.append("ProcessingStatus = :processing_status")
        expression_values[":processing_status"] = processing_status

    update_expressions.append("CompletedAt = :completed_at")
    expression_values[":completed_at"] = now_unix()

    update_expressions.append("Outcome = :outcome")
    expression_values[":outcome"] = segment_data.get("Outcome", "unknown")

    update_expressions.append("CharacterUpdates = :char_updates")
    expression_values[":char_updates"] = character_updates

    processed_at = segment_data.get("ProcessedAt")
    if processed_at:
        update_expressions.append("ProcessedAt = :processed_at")
        expression_values[":processed_at"] = processed_at

    client_events = segment_data.get("ClientEvents")
    if client_events:
        update_expressions.append("ClientEvents = :client_events")
        expression_values[":client_events"] = client_events

    challenge_results = segment_data.get("ChallengeResults")
    if challenge_results:
        update_expressions.append("ChallengeResults = :challenge_results")
        expression_values[":challenge_results"] = challenge_results

    combat_state = segment_data.get("CombatState")
    if combat_state:
        update_expressions.append("CombatState = :combat_state")
        expression_values[":combat_state"] = combat_state

    decision = segment_data.get("Decision")
    if decision:
        update_expressions.append("Decision = :decision")
        expression_values[":decision"] = decision

    decision_made_at = segment_data.get("DecisionMadeAt")
    if decision_made_at:
        update_expressions.append("DecisionMadeAt = :decision_made_at")
        expression_values[":decision_made_at"] = decision_made_at

    branch_metadata = segment_data.get("BranchMetadata")
    if branch_metadata:
        update_expressions.append("BranchMetadata = :branch_metadata")
        expression_values[":branch_metadata"] = branch_metadata

    try:
        update_kwargs = {
            "Key": {"CharacterID": character_id, "ActiveSegmentID": active_segment_id},
            "UpdateExpression": "SET " + ", ".join(update_expressions),
            "ExpressionAttributeValues": expression_values,
        }

        if expression_names:
            update_kwargs["ExpressionAttributeNames"] = expression_names

        dynamo.update_item(TableName.SEGMENT_HISTORY, **update_kwargs)

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
            "SegmentTitle": active_segment.get("SegmentTitle"),
            "SegmentActivity": active_segment.get("SegmentActivity"),
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
