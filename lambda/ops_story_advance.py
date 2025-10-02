"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to advance stories after segment completion.
Triggered by SQS to apply character updates and progress stories.
"""

from eidolon.character_data import get_character
from eidolon.character_segment import update_character_active_segment
from eidolon.environment import SEGMENT_QUEUE_URL
from eidolon.logger import log_lambda_statistics, logger
from eidolon.mechanics import apply_death_or_unconscious_outcome
from eidolon.polling import update_polling_state
from eidolon.segment_core import get_active_segment, get_segment_definition, is_simple_segment
from eidolon.segment_history import record_segment_history, segment_already_in_history
from eidolon.segment_polling import check_active_segments_exist, delete_active_segment
from eidolon.segment_processing import determine_next_segment, process_decision_segment
from eidolon.segment_state import create_next_active_segment, mark_segment_as_completed, update_segment_processing_status
from eidolon.sqs import send_message
from eidolon.story_completion import complete_story
from eidolon.story_history import add_segment_to_history, update_story_history_xp
from eidolon.story_rewards import apply_combat_rewards
from eidolon.validation import validate_uuid


def advance_story_business_logic(active_segment_id: str) -> dict:
    """
    Business logic for advancing a story after segment completion.

    Args:
        active_segment_id: Active segment UUID

    Returns:
        Dict with processing results

    Raises:
        ValueError: If segment not found or invalid state
        RuntimeError: If processing fails
    """
    # Get active segment first to check its status
    active_segment = get_active_segment(active_segment_id)

    # Segments marked as completed still need to be advanced to create the next segment
    # Only skip if the segment is abandoned or missing critical data
    status = active_segment.get("Status")
    if status == "abandoned":
        logger.info(f"Segment abandoned, skipping advancement for {active_segment_id}")
        return {"success": True, "skipped": True, "reason": "Segment abandoned"}

    # Extract key data
    character_id = active_segment.get("CharacterID")
    story_id = active_segment.get("StoryID")
    segment_id = active_segment.get("SegmentID")
    segment_type = active_segment.get("SegmentType")
    outcome = active_segment.get("Outcome", "normal")

    logger.info(f"Advancing story for {character_id}")

    # Idempotency check - skip if segment already in history
    if segment_already_in_history(character_id, active_segment_id):  # type: ignore
        logger.info(f"Segment {active_segment_id} already in history, skipping effect application")
        return {"success": True, "skipped": True, "reason": "Already processed"}

    # Story history should already exist (created when story started)

    # Handle decision segments that need their outcome determined
    if is_simple_segment(segment_type):  # type: ignore
        logger.info(f"Processing decision segment for {active_segment_id}")

        # Get segment definition
        segment_def = get_segment_definition(story_id, segment_id)  # type: ignore

        # Get character data for processing
        character = get_character(character_id)  # type: ignore

        # Process decision segment
        if segment_type == "decision":
            outcome = process_decision_segment(active_segment, segment_def)
            character_updates = {}
        else:
            raise ValueError(f"Unknown simple segment type: {segment_type}")

        # Update active segment with results
        update_segment_processing_status(active_segment_id, outcome, character_updates)
        active_segment["Outcome"] = outcome
        active_segment["CharacterUpdates"] = character_updates
        active_segment["ProcessingStatus"] = "processed"

    # Check for death outcome and apply character state changes
    new_character_state = None
    if outcome == "death" and character_id:
        try:
            # Get current character to check wounds
            character = get_character(character_id)
            wounds = character.get("Wounds", [])

            # Apply death or unconscious state based on wounds
            new_character_state = apply_death_or_unconscious_outcome(character_id, outcome, wounds)

            logger.info(f"Applied character state change for death outcome for {character_id}")
        except Exception as err:
            logger.error(f"Failed to apply death/unconscious state for {character_id} Error: {err}", exc_info=True)

    # Apply deferred rewards (combat rewards and story outcome effects)
    character_updates = active_segment.get("CharacterUpdates", {})
    logger.info(f"CharacterUpdates from segment: {character_updates}")
    if character_updates and character_id:
        # Apply combat rewards if present
        combat_rewards = character_updates.get("CombatRewards", {})
        if combat_rewards and combat_rewards.get("Defeated"):
            opponent_data = combat_rewards.get("OpponentData")
            if opponent_data:
                try:
                    apply_combat_rewards(character_id, opponent_data)
                except Exception as err:
                    logger.error(f"Failed to apply combat rewards for {character_id} Error: {err}", exc_info=True)

        # Story outcome effects are now applied immediately in ops_segment_process
        # This is kept for backwards compatibility with existing segments that may have effects stored
        story_effects = character_updates.get("StoryEffects", {})
        if story_effects:
            logger.info("Found legacy StoryEffects in CharacterUpdates (already applied by processor)")
            # Effects should have already been applied by ops_segment_process

    # Mark segment as completed in DynamoDB before recording history
    try:
        mark_segment_as_completed(active_segment_id)
        active_segment["Status"] = "completed"
    except Exception as err:
        logger.error(f"Failed to mark segment as completed for {active_segment_id} Error: {err}", exc_info=True)

    # Record segment history
    record_segment_history(character_id, story_id, active_segment_id, active_segment)  # type: ignore

    # Add segment to story history's SegmentHistory array
    story_instance_id = active_segment.get("StoryInstanceID")
    if story_instance_id:
        add_segment_to_history(character_id, story_instance_id, segment_id, outcome)  # type: ignore

    # Update story history with accumulated XP
    skill_xp = character_updates.get("SkillXP", {})
    attribute_xp = character_updates.get("AttributeXP", {})
    if (skill_xp or attribute_xp) and story_instance_id:
        update_story_history_xp(character_id, story_instance_id, skill_xp, attribute_xp)  # type: ignore

    # Get segment definition to determine next action
    segment_def = get_segment_definition(story_id, segment_id)  # type: ignore
    logger.debug(f"Retrieved segment_def for {segment_id}")
    logger.info(f"  SegmentType: {segment_def.get('SegmentType')}")
    logger.info(f"  Results keys: {list(segment_def.get('Results', {}).keys())}")
    logger.info(f"  Has top-level NextSegmentID: {segment_def.get('NextSegmentID') is not None}")

    # Get character for branching prerequisites
    character = get_character(character_id)  # type: ignore

    # Determine next segment with weighted branching
    next_segment_id, branch_metadata = determine_next_segment(segment_def, active_segment, outcome, character)

    # Store branch metadata in current segment history before advancing
    if branch_metadata:
        try:
            from eidolon.dynamo import TableName, dynamo

            dynamo.update_item(
                TableName.ACTIVE_SEGMENTS,
                Key={"ActiveSegmentID": active_segment_id},
                UpdateExpression="SET BranchMetadata = :metadata",
                ExpressionAttributeValues={":metadata": branch_metadata},
            )
            logger.debug(f"Stored branch metadata for {active_segment_id}: {branch_metadata}")
        except Exception as err:
            # Non-critical - just log warning
            logger.warning(f"Failed to store branch metadata for {active_segment_id}: {err}")

    if next_segment_id:
        # Create next segment
        try:
            next_segment_def = get_segment_definition(story_id, next_segment_id)  # type: ignore

            next_active_segment_id = create_next_active_segment(
                character_id,  # type: ignore
                active_segment.get("PlayerID"),  # type: ignore
                story_id,  # type: ignore
                next_segment_def,
                story_instance_id,  # Pass instance ID for history tracking
            )

            # Update character with new active segment
            update_character_active_segment(character_id, next_active_segment_id)  # type: ignore

            logger.info(f"Created next segment for {character_id}")

            # Queue mechanical segments for immediate processing
            if next_segment_def.get("SegmentType") == "mechanical":
                try:

                    if SEGMENT_QUEUE_URL:
                        # Send just the ActiveSegmentID string (what ops_segment_process expects)
                        send_message(SEGMENT_QUEUE_URL, next_active_segment_id)
                        logger.info(f"Queued next mechanical segment for processing for {next_active_segment_id}")
                except Exception as err:
                    # Non-critical - segment will be picked up by poller
                    logger.warning(f"Failed to queue mechanical segment for {next_active_segment_id} Error: {err}")
        except Exception as err:
            logger.error(f"Failed to create next segment for {next_segment_id} Error: {err}", exc_info=True)
            raise RuntimeError(f"Failed to create next segment: {err}") from err
    else:
        # Story complete
        complete_story(character_id, story_id, story_instance_id, outcome)  # type: ignore

    # Delete processed segment
    delete_active_segment(active_segment_id)

    # Check if any active segments remain after deletion
    # If none remain, signal the poller to check if it should stop
    if next_segment_id is None:  # This story is complete
        try:
            if not check_active_segments_exist():
                # No more active segments, signal poller to stop
                update_polling_state("stop")
                logger.info("No active segments remaining, signaled poller to stop")
        except Exception as err:
            # Non-critical - poller will detect empty table on next run
            logger.warning(f"Failed to check/update polling state after story completion Error: {err}")

    return {
        "success": True,
        "outcome": outcome,
        "next_segment": next_segment_id,
        "story_complete": next_segment_id is None,
    }


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to advance stories after segment completion.

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
            # Message body should be just the ActiveSegmentID string
            active_segment_id = record.get("body", "").strip()

            if not active_segment_id:
                logger.error(f"Empty message body for messageId={message_id}")
                invalid_count += 1
                continue

            if not validate_uuid(active_segment_id):
                logger.error(f"Invalid UUID format for messageId={message_id}: {active_segment_id}")
                invalid_count += 1
                continue

            logger.info(f"Processing segment advancement for {active_segment_id}")

            # Process the segment
            result = advance_story_business_logic(active_segment_id)

            if result.get("success"):
                success_count += 1
                logger.info(f"Segment advancement complete for {active_segment_id}")
            else:
                raise RuntimeError("Segment advancement failed")

        except Exception as err:
            logger.error(f"Failed to process message for {message_id} Error: {err}", exc_info=True)
            failure_count += 1
            # Add to batch failures for retry
            batch_item_failures.append({"itemIdentifier": message_id})

    # Log summary
    if invalid_count > 0:
        logger.warning(f"Batch processing summary: Success={success_count}, Failed={failure_count}, Invalid={invalid_count}")
    else:
        logger.info(f"Batch processing summary: Success={success_count}, Failed={failure_count}")

    return {"batchItemFailures": batch_item_failures}
