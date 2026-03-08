"""
Eidolon Engine - Incremental Game

Copyright 2024-2026 Jason E. Robinson

Lambda function to advance stories after segment completion.
Triggered by SQS to apply character updates and progress stories.
"""

from eidolon.character_data import apply_death_or_unconscious_outcome, get_character
from eidolon.character_segment import update_character_active_segment
from eidolon.dynamo import TableName, dynamo
from eidolon.environment import SEGMENT_QUEUE_URL
from eidolon.logger import log_lambda_statistics, logger
from eidolon.polling import update_polling_state
from eidolon.segment_core import get_active_segment, get_segment_definition, is_simple_segment
from eidolon.segment_history import record_segment_history
from eidolon.segment_polling import check_active_segments_exist, delete_active_segment
from eidolon.segment_processing import determine_next_segment, process_decision_segment
from eidolon.segment_state import create_next_active_segment, mark_segment_as_completed, update_segment_processing_status
from eidolon.sqs import send_message
from eidolon.story_completion import complete_story, complete_story_for_character
from eidolon.story_history import add_segment_to_history, update_story_history_xp
from eidolon.validation import validate_uuid


def queue_next_mechanical_segment(next_active_segment_id: str) -> None:
    """Queue a mechanical segment for processing via SQS. Non-fatal on failure.

    Args:
        next_active_segment_id: Segment to queue
    """
    try:
        if SEGMENT_QUEUE_URL:
            send_message(SEGMENT_QUEUE_URL, next_active_segment_id)
            logger.info(f"Queued next mechanical segment for processing for {next_active_segment_id}")
    except Exception as err:
        logger.warning(f"Failed to queue mechanical segment for {next_active_segment_id} Error: {err}")


def claim_segment_for_advancement(active_segment_id: str) -> tuple:
    """Claim a segment for advancement with idempotency checks.

    Performs three checks before claiming:
    1. Segment exists (may already be deleted/advanced)
    2. Segment status is not already completed or abandoned
    3. Atomic claim via mark_segment_as_completed

    Args:
        active_segment_id: Active segment UUID

    Returns:
        Tuple of (active_segment, None) if claimed, or (None, skip_result) if skipped
    """
    try:
        active_segment = get_active_segment(active_segment_id)
    except ValueError as err:
        logger.info(f"Segment {active_segment_id} not found (may be already processed): {err}")
        return None, {"success": True, "skipped": True, "reason": "Segment not found"}

    status = active_segment.get("Status")
    if status == "completed":
        logger.info(f"Segment {active_segment_id} already completed, skipping")
        return None, {"success": True, "skipped": True, "reason": "Already completed"}
    if status == "abandoned":
        logger.info(f"Segment {active_segment_id} abandoned, skipping")
        return None, {"success": True, "skipped": True, "reason": "Segment abandoned"}

    try:
        mark_segment_as_completed(active_segment_id)
        active_segment["Status"] = "completed"
        logger.info(f"Claimed segment {active_segment_id} for advancement")
    except Exception as err:
        logger.warning(f"Failed to claim segment {active_segment_id}: {err}")
        return None, {"success": True, "skipped": True, "reason": "Already claimed by another worker"}

    return active_segment, None


def resolve_segment_outcome(active_segment: dict, active_segment_id: str, segment_def: dict) -> str:
    """Resolve final outcome for the segment.

    For simple segments (decision), determines the outcome via processing.
    For mechanical segments, the outcome was already set during processing.
    Applies death/unconscious state changes if outcome is death.

    Args:
        active_segment: Active segment record (mutated with outcome data for simple segments)
        active_segment_id: Segment UUID
        segment_def: Segment definition

    Returns:
        Final outcome string
    """
    segment_type = active_segment.get("SegmentType")
    outcome = active_segment.get("Outcome", "normal")
    character_id = active_segment.get("CharacterID")

    if is_simple_segment(segment_type):  # type: ignore
        logger.info(f"Processing decision segment for {active_segment_id}")
        if segment_type == "decision":
            outcome = process_decision_segment(active_segment, segment_def)
        else:
            raise ValueError(f"Unknown simple segment type: {segment_type}")

        client_events = active_segment.get("ClientEvents", [])
        update_segment_processing_status(active_segment_id, outcome, {}, client_events)
        active_segment["Outcome"] = outcome
        active_segment["CharacterUpdates"] = {}
        active_segment["ClientEvents"] = client_events
        active_segment["ProcessingStatus"] = "processed"

    if outcome == "death" and character_id:
        try:
            character = get_character(character_id)
            apply_death_or_unconscious_outcome(character_id, outcome, character.get("Wounds", []))
            logger.info(f"Applied death outcome state change for {character_id}")
        except Exception as err:
            logger.error(f"Failed to apply death/unconscious state for {character_id} Error: {err}", exc_info=True)

    return outcome


def record_advancement_history(
    active_segment: dict, active_segment_id: str, outcome: str, branch_metadata: dict
) -> None:
    """Record segment history, story history, and XP updates.

    Stores branch metadata on the active segment before recording history
    so the history snapshot includes branching information.

    Args:
        active_segment: Active segment record (mutated with branch metadata if present)
        active_segment_id: Segment UUID
        outcome: Segment outcome
        branch_metadata: Branch metadata from determine_next_segment
    """
    character_id = active_segment.get("CharacterID")
    story_id = active_segment.get("StoryID")
    segment_id = active_segment.get("SegmentID")
    story_instance_id = active_segment.get("StoryInstanceID")
    character_updates = active_segment.get("CharacterUpdates", {})

    if branch_metadata:
        try:
            dynamo.update_item(
                TableName.ACTIVE_SEGMENTS,
                Key={"ActiveSegmentID": active_segment_id},
                UpdateExpression="SET BranchMetadata = :metadata",
                ExpressionAttributeValues={":metadata": branch_metadata},
            )
            active_segment["BranchMetadata"] = branch_metadata
            logger.debug(f"Stored branch metadata for {active_segment_id}: {branch_metadata}")
        except Exception as err:
            logger.warning(f"Failed to store branch metadata for {active_segment_id}: {err}")

    record_segment_history(character_id, story_id, active_segment_id, active_segment)  # type: ignore

    if story_instance_id:
        add_segment_to_history(character_id, story_instance_id, segment_id, outcome)  # type: ignore

    skill_xp = character_updates.get("SkillXP", {})
    attribute_xp = character_updates.get("AttributeXP", {})
    if (skill_xp or attribute_xp) and story_instance_id:
        update_story_history_xp(character_id, story_instance_id, skill_xp, attribute_xp)  # type: ignore


def create_next_or_complete(active_segment: dict, outcome: str, next_segment_id: str) -> None:
    """Create the next segment or complete the story.

    When story is complete (no next segment), clears character state immediately
    so clients see the update before story finalization.

    Args:
        active_segment: Current active segment record
        outcome: Segment outcome
        next_segment_id: Next segment ID, or None if story is complete

    Raises:
        RuntimeError: If next segment creation fails
    """
    character_id = active_segment.get("CharacterID")
    story_id = active_segment.get("StoryID")
    story_instance_id = active_segment.get("StoryInstanceID")

    if not next_segment_id:
        complete_story_for_character(character_id)  # type: ignore
        logger.info(f"Story complete - cleared character state for {character_id}")

    if next_segment_id:
        try:
            next_segment_def = get_segment_definition(story_id, next_segment_id)  # type: ignore
            next_active_segment_id = create_next_active_segment(
                character_id,  # type: ignore
                active_segment.get("PlayerID"),  # type: ignore
                story_id,  # type: ignore
                next_segment_def,
                story_instance_id,
                active_segment.get("EndTime"),
            )
            update_character_active_segment(character_id, next_active_segment_id)  # type: ignore
            logger.info(f"Created next segment for {character_id}")

            if next_segment_def.get("SegmentType") == "mechanical":
                queue_next_mechanical_segment(next_active_segment_id)
        except Exception as err:
            logger.error(f"Failed to create next segment for {next_segment_id} Error: {err}", exc_info=True)
            raise RuntimeError(f"Failed to create next segment: {err}") from err
    else:
        complete_story(character_id, story_id, story_instance_id, outcome)  # type: ignore


def advance_story_business_logic(active_segment_id: str) -> dict:
    """Business logic for advancing a story after segment completion.

    IDEMPOTENT: Safe to call multiple times with the same segment ID.
    Returns success if segment already advanced or doesn't exist.

    Args:
        active_segment_id: Active segment UUID

    Returns:
        Dict with processing results

    Raises:
        RuntimeError: If processing fails
    """
    active_segment, skip_result = claim_segment_for_advancement(active_segment_id)
    if skip_result:
        return skip_result

    character_id = active_segment.get("CharacterID")
    story_id = active_segment.get("StoryID")
    segment_id = active_segment.get("SegmentID")

    logger.info(f"Advancing story for {character_id}")

    # Get segment definition once for all downstream use
    segment_def = get_segment_definition(story_id, segment_id)  # type: ignore

    # Resolve outcome (decision processing + death handling)
    outcome = resolve_segment_outcome(active_segment, active_segment_id, segment_def)

    logger.debug(f"CharacterUpdates from segment: {active_segment.get('CharacterUpdates', {})}")

    # Determine next segment with weighted branching
    character = get_character(character_id)  # type: ignore
    next_segment_id, branch_metadata = determine_next_segment(segment_def, active_segment, outcome, character)

    # Record all history (branch metadata stored before history snapshot)
    record_advancement_history(active_segment, active_segment_id, outcome, branch_metadata)

    # Create next segment or complete story
    create_next_or_complete(active_segment, outcome, next_segment_id)

    # Delete processed segment
    delete_active_segment(active_segment_id)

    # Check polling state if story is complete
    if not next_segment_id:
        try:
            if not check_active_segments_exist():
                update_polling_state("stop")
                logger.info("No active segments remaining, signaled poller to stop")
        except Exception as err:
            logger.warning(f"Failed to check/update polling state after story completion Error: {err}")

    return {
        "success": True,
        "outcome": outcome,
        "next_segment": next_segment_id,
        "story_complete": next_segment_id is None,
    }


def lambda_handler(event: dict, context: object) -> dict:
    """Lambda handler to advance stories after segment completion.

    Processes SQS messages containing completed segments, applies character
    updates, and either creates the next segment or completes the story.

    Args:
        event: SQS event with segment completion messages
        context: Lambda context

    Returns:
        SQS batch response with failed message IDs
    """
    # Log invocation
    log_lambda_statistics(event, context)

    # Process SQS messages
    batch_item_failures = []
    success_count = 0
    failure_count = 0
    invalid_count = 0

    for record in event.get("Records", []):
        message_id = record.get("messageId", "unknown")

        try:
            active_segment_id = record.get("body", "").strip()

            if not active_segment_id:
                logger.warning(f"Empty message body for messageId={message_id}")
                invalid_count += 1
                continue

            if not validate_uuid(active_segment_id):
                logger.warning(f"Invalid UUID format for messageId={message_id}: {active_segment_id}")
                invalid_count += 1
                continue

            logger.info(f"Processing segment advancement for {active_segment_id}")

            result = advance_story_business_logic(active_segment_id)

            if result.get("success"):
                success_count += 1
                logger.info(f"Segment advancement complete for {active_segment_id}")
            else:
                raise RuntimeError("Segment advancement failed")

        except Exception as err:
            logger.error(f"Failed to process message for {message_id} Error: {err}", exc_info=True)
            failure_count += 1
            batch_item_failures.append({"itemIdentifier": message_id})

    # Log summary
    if invalid_count > 0:
        logger.warning(f"Batch processing summary: Success={success_count}, Failed={failure_count}, Invalid={invalid_count}")
    else:
        logger.info(f"Batch processing summary: Success={success_count}, Failed={failure_count}")

    return {"batchItemFailures": batch_item_failures}
