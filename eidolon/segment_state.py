"""
State management for active segments.

Provides functions for managing segment status and progression.
"""

from botocore.exceptions import ClientError
from uuid_extension import uuid7

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger
from eidolon.segment_core import extract_character_updates_from_results, validate_segment_outcome_results
from eidolon.time_utils import future_unix, now_unix


def update_active_segment_outcome(active_segment_id: str, outcome: str, results: dict, segment_def=None) -> None:
    """
    Update active segment with outcome but keep status as active until timer expires.

    Args:
        active_segment_id: Active segment UUID
        outcome: Outcome type
        results: Challenge or combat results
        segment_def: segment definition containing Results narratives
    """
    if not outcome:
        logger.warning(f"No outcome computed for {active_segment_id}; defaulting to 'normal'")
        outcome = "normal"

    update_expression = "SET #outcome = :outcome, ProcessingStatus = :proc_status"
    expression_names = {"#outcome": "Outcome"}
    expression_values: dict = {":outcome": outcome, ":proc_status": "processed"}

    challenge_results = results.get("ChallengeResults")
    if challenge_results:
        update_expression += ", ChallengeResults = :results"
        expression_values[":results"] = challenge_results  # type: ignore

    combat_state = results.get("CombatState")
    if combat_state:
        update_expression += ", CombatState = :state"
        expression_values[":state"] = combat_state  # type: ignore

    if segment_def:
        character_updates = extract_character_updates_from_results(results, segment_def, outcome)
        if character_updates:
            update_expression += ", CharacterUpdates = :updates"
            expression_values[":updates"] = character_updates  # type: ignore

    client_events = []

    if segment_def:
        try:
            outcome_data = validate_segment_outcome_results(segment_def, outcome)
            narrative = outcome_data.get("Narrative", "")

            if narrative:
                client_events.append(
                    {
                        "EventType": "narrative",
                        "Title": "Outcome",
                        "Description": narrative,
                    }
                )
        except Exception as err:
            logger.error(f"Failed to get outcome narrative for {active_segment_id} Error: {err}", exc_info=True)

    if challenge_results:
        for challenge in challenge_results:
            skill = challenge.get("Skill", "")
            attribute = challenge.get("Attribute", "")
            passed = challenge.get("Passed", False)

            if passed:
                title = f"{skill or attribute} Success"
                description = f"You succeeded at the {skill or attribute} challenge."
            else:
                title = f"{skill or attribute} Failure"
                description = f"You failed the {skill or attribute} challenge."

            client_events.append(
                {
                    "EventType": "skill_check",
                    "Title": title,
                    "Description": description,
                    "Data": challenge,
                }
            )

    if combat_state:
        combat_log = combat_state.get("CombatLog", [])
        for round_data in combat_log[:5]:
            client_events.append(
                {
                    "EventType": "combat",
                    "Title": f"Round {round_data.get('Round', 0)}",
                    "Description": "Combat round",
                    "Data": round_data,
                }
            )

        victor = combat_state.get("Victor")
        if victor:
            if victor == "player":
                title = "Victory!"
                description = "You have defeated your opponent."
            else:
                title = "Defeat"
                description = "You have been defeated in combat."

            client_events.append(
                {
                    "EventType": "combat_result",
                    "Title": title,
                    "Description": description,
                }
            )

    if client_events:
        update_expression += ", ClientEvents = :events"
        expression_values[":events"] = client_events  # type: ignore

    try:
        dynamo.update_item(
            TableName.ACTIVE_SEGMENTS,
            Key={"ActiveSegmentID": active_segment_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values,
        )
        logger.info(f"Updated active segment outcome for {active_segment_id}")
    except ClientError as err:
        logger.error(f"Failed to update active segment outcome for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to update active segment outcome: {err}") from err


def create_next_active_segment(character_id: str, player_id: str, story_id: str, segment: dict, story_instance_id=None) -> str:
    """
    Create an active segment record for the next segment.

    Args:
        character_id: Character UUID
        player_id: Player UUID
        story_id: Story UUID
        segment: Segment data from Segments table
        story_instance_id: Story instance UUID for history tracking

    Returns:
        Active segment ID
    """
    segment_id = segment.get("SegmentID")
    segment_type = segment.get("SegmentType", "mechanical")
    duration = int(segment.get("SegmentDuration", 300))

    start_time = now_unix()
    end_time = future_unix(duration)

    active_segment_id = str(uuid7())

    segment_title = segment.get("SegmentTitle")
    segment_activity = segment.get("SegmentActivity")

    if not segment_title and segment_activity:
        segment_title = segment_activity
    if not segment_activity and segment_title:
        segment_activity = segment_title

    if not segment_title:
        segment_title = "Processing..."
    if not segment_activity:
        segment_activity = "Processing..."

    active_segment = {
        "ActiveSegmentID": active_segment_id,
        "CharacterID": character_id,
        "PlayerID": player_id,
        "StoryID": story_id,
        "StoryInstanceID": story_instance_id if story_instance_id else "",
        "SegmentID": segment_id,
        "SegmentType": segment_type,
        "ProcessingStatus": "pending",  # Add ProcessingStatus field
        "StartTime": start_time,
        "EndTime": end_time,
        "Status": "active",
    }

    active_segment["SegmentTitle"] = segment_title
    active_segment["SegmentActivity"] = segment_activity

    if segment_type == "decision":
        active_segment["Decision"] = None
        active_segment["DecisionOptions"] = segment.get("DecisionOptions", {})
    elif segment_type == "mechanical":
        active_segment["ChallengeResults"] = []
        active_segment["Outcome"] = None

        combat_config = segment.get("Combat", {})
        if combat_config:
            active_segment["CombatState"] = {
                "PlayerWounds": [],
                "OpponentWounds": [],
                "Round": 0,
            }

    try:
        dynamo.put_item(TableName.ACTIVE_SEGMENTS, active_segment)
        logger.info(f"Created active segment for {segment_id}")
        return active_segment_id
    except ClientError as err:
        logger.error(f"Failed to create active segment for {segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to create active segment: {err}") from err


def update_segment_processing_status(active_segment_id: str, outcome: str, character_updates: dict, client_events=None) -> None:
    """
    Update active segment with processing results.

    Args:
        active_segment_id: Active segment UUID
        outcome: Processing outcome
        character_updates: Character updates to apply
        client_events: list of client events (for decision segments)

    Raises:
        RuntimeError: If database operation fails
    """
    if not outcome:
        logger.warning(f"No outcome computed for {active_segment_id}; defaulting to 'normal'")
        outcome = "normal"

    try:
        update_expr = (
            "SET ProcessingStatus = :status, #outcome = :outcome, CharacterUpdates = :updates, ProcessedAt = :processed_at"
        )
        expr_values = {
            ":status": "processed",
            ":outcome": outcome,
            ":updates": character_updates,
            ":processed_at": now_unix(),
        }

        if client_events is not None:
            update_expr += ", ClientEvents = :events"
            expr_values[":events"] = client_events

        dynamo.update_item(
            TableName.ACTIVE_SEGMENTS,
            Key={"ActiveSegmentID": active_segment_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames={"#outcome": "Outcome"},
            ExpressionAttributeValues=expr_values,
        )
        logger.info(f"Updated segment processing status for {active_segment_id}")
    except ClientError as err:
        logger.error(f"Failed to update segment processing status for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to update segment results: {err}") from err


def reset_segment_processing_status(active_segment_id: str) -> None:
    """
    Reset a segment's processing status back to pending.

    Used to retry stuck segments that have been processing too long.

    Args:
        active_segment_id: Active segment UUID

    Raises:
        RuntimeError: If database operation fails
    """
    try:
        dynamo.update_item(
            TableName.ACTIVE_SEGMENTS,
            Key={"ActiveSegmentID": active_segment_id},
            UpdateExpression="SET ProcessingStatus = :status",
            ExpressionAttributeValues={":status": "pending"},
        )
        logger.info(f"Reset segment processing status to pending for {active_segment_id}")
    except ClientError as err:
        logger.error(f"Failed to reset segment processing status for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to reset segment processing status: {err}") from err


def mark_segment_as_completed(active_segment_id: str) -> None:
    """
    Mark a segment as completed.

    Used when advancing a story to mark the current segment as completed
    before recording history and creating the next segment.

    Args:
        active_segment_id: Active segment UUID

    Raises:
        RuntimeError: If database operation fails
    """
    try:
        dynamo.update_item(
            TableName.ACTIVE_SEGMENTS,
            Key={"ActiveSegmentID": active_segment_id},
            UpdateExpression="SET #status = :completed",
            ConditionExpression="#status = :active",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={
                ":completed": "completed",
                ":active": "active",
            },
        )
        logger.info(f"Marked segment as completed for {active_segment_id}")
    except ClientError as err:
        if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.info(f"Segment {active_segment_id} already completed or abandoned, skipping completion")
            return  # Non-fatal - segment already in terminal state
        logger.error(f"Failed to mark segment as completed for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to mark segment as completed: {err}") from err


def mark_segment_as_completed_exceptional(active_segment_id: str) -> None:
    """
    Mark an exhausted segment as completed with exceptional outcome.

    Used when a segment has passed its end time without being processed,
    giving the player the best possible outcome to protect them from system failures.

    Args:
        active_segment_id: Active segment UUID

    Raises:
        RuntimeError: If database operation fails
    """
    try:
        dynamo.update_item(
            TableName.ACTIVE_SEGMENTS,
            Key={"ActiveSegmentID": active_segment_id},
            UpdateExpression="SET ProcessingStatus = :proc_status, #status = :completed, #outcome = :outcome",
            ConditionExpression="#status = :active AND ProcessingStatus <> :proc_status",
            ExpressionAttributeNames={"#outcome": "Outcome", "#status": "Status"},
            ExpressionAttributeValues={
                ":proc_status": "processed",
                ":active": "active",
                ":completed": "completed",
                ":outcome": "exceptional",
            },
        )
        logger.info(f"Marked exhausted segment as completed with exceptional outcome for {active_segment_id}")
    except ClientError as err:
        if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.info(f"Segment {active_segment_id} already processed or completed, skipping exceptional completion")
            return  # Non-fatal - segment already in terminal state
        logger.error(f"Failed to mark segment as completed exceptional for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to mark segment as completed exceptional: {err}") from err
