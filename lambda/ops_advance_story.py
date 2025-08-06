"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to advance stories after segment completion.
Triggered by SQS to apply character updates and progress stories.
"""

import json

from eidolon.character import apply_death_or_unconscious_outcome, get_character
from eidolon.environment import SEGMENT_QUEUE_URL
from eidolon.logger import log_lambda_statistics, logger
from eidolon.polling import update_polling_state
from eidolon.segment import (
    check_active_segments_exist,
    claim_segment_for_processing,
    complete_story,
    create_next_active_segment,
    delete_active_segment,
    determine_next_segment,
    get_active_segment,
    get_segment_definition,
    insert_rest_segment,
    is_simple_segment,
    process_decision_segment,
    process_rest_segment,
    record_segment_history,
    update_character_active_segment,
    update_segment_processing_status,
)
from eidolon.sqs import send_message
from eidolon.story import apply_combat_rewards, apply_story_outcome_effects, ensure_story_history_exists, update_story_history_xp


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
    # Claim segment for processing
    if not claim_segment_for_processing(active_segment_id):
        return {"success": True, "skipped": True, "reason": "Already being processed"}

    # Get active segment
    active_segment = get_active_segment(active_segment_id)

    # Extract key data
    character_id = active_segment.get("CharacterID")
    story_id = active_segment.get("StoryID")
    segment_id = active_segment.get("SegmentID")
    segment_type = active_segment.get("SegmentType")
    outcome = active_segment.get("Outcome", "normal")

    logger.info(f"Advancing story for {character_id}")

    # Ensure story history exists
    story_title = active_segment.get("StoryTitle", "Unknown Story")
    ensure_story_history_exists(character_id, story_id, story_title)  # type: ignore

    # Process simple segments if not already processed
    processing_status = active_segment.get("ProcessingStatus")
    if is_simple_segment(segment_type) and processing_status != "processed":  # type: ignore
        logger.info(f"Processing simple segment for {active_segment_id}")

        # Get segment definition
        segment_def = get_segment_definition(story_id, segment_id)  # type: ignore

        # Get character data for processing
        character = get_character(character_id)  # type: ignore

        # Process based on type
        if segment_type == "rest":
            outcome, _ = process_rest_segment(segment_def, character)
            character_updates = {}
        elif segment_type == "decision":
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
    if character_updates and character_id:
        # Apply combat rewards if present
        combat_rewards = character_updates.get("CombatRewards", {})
        if combat_rewards and combat_rewards.get("defeated"):
            opponent_data = combat_rewards.get("opponentData")
            if opponent_data:
                try:
                    apply_combat_rewards(character_id, opponent_data)
                except Exception as err:
                    logger.error(f"Failed to apply combat rewards for {character_id} Error: {err}", exc_info=True)

        # Apply story outcome effects if present
        story_effects = character_updates.get("StoryEffects", {})
        if story_effects:
            try:
                apply_story_outcome_effects(character_id, story_effects)
            except Exception as err:
                logger.error(f"Failed to apply story outcome effects for {character_id} Error: {err}", exc_info=True)

    # Record segment history
    record_segment_history(character_id, story_id, active_segment_id, active_segment)  # type: ignore

    # Update story history with accumulated XP
    skill_xp = character_updates.get("SkillXP", {})
    attribute_xp = character_updates.get("AttributeXP", {})
    if skill_xp or attribute_xp:
        update_story_history_xp(character_id, story_id, skill_xp, attribute_xp)  # type: ignore

    # Get segment definition to determine next action
    segment_def = get_segment_definition(story_id, segment_id)  # type: ignore

    # Check if we need to insert a rest segment for unconscious character
    if new_character_state == "unconscious":
        try:
            # Insert a rest segment after current segment
            rest_segment_id = insert_rest_segment(
                story_id,  # type: ignore
                segment_id,  # type: ignore
                rest_duration=900,  # 15 minutes to heal
                time_remaining=0,  # Current segment is done
            )

            # Override next segment to be the rest segment
            next_segment_id = rest_segment_id

            logger.info(f"Inserted rest segment for unconscious character for {character_id}")
        except Exception as err:
            logger.error(f"Failed to insert rest segment for unconscious character for {character_id} Error: {err}", exc_info=True)
            # Fall back to normal next segment determination
            next_segment_id = determine_next_segment(segment_def, active_segment, outcome)
    else:
        # Determine next segment normally
        next_segment_id = determine_next_segment(segment_def, active_segment, outcome)

    if next_segment_id:
        # Create next segment
        try:
            next_segment_def = get_segment_definition(story_id, next_segment_id)  # type: ignore

            next_active_segment_id = create_next_active_segment(
                character_id,  # type: ignore
                active_segment.get("PlayerID"),  # type: ignore
                story_id,  # type: ignore
                next_segment_def,
                active_segment.get("StoryTitle"),  # type: ignore
            )

            # Update character with new active segment
            update_character_active_segment(character_id, next_active_segment_id)  # type: ignore

            logger.info(f"Created next segment for {character_id}")

            # Queue mechanical segments for immediate processing
            if next_segment_def.get("SegmentType") == "mechanical":
                try:

                    if SEGMENT_QUEUE_URL:
                        message_body = {
                            "ActiveSegmentID": next_active_segment_id,
                            "CharacterID": character_id,
                            "StoryID": story_id,
                            "SegmentID": next_segment_id,
                            "SegmentType": "mechanical",
                        }
                        send_message(SEGMENT_QUEUE_URL, message_body)
                        logger.info(f"Queued next mechanical segment for processing for {next_active_segment_id}")
                except Exception as err:
                    # Non-critical - segment will be picked up by poller
                    logger.warning(f"Failed to queue mechanical segment for {next_active_segment_id} Error: {err}")
        except Exception as err:
            logger.error(f"Failed to create next segment for {next_segment_id} Error: {err}", exc_info=True)
            raise RuntimeError(f"Failed to create next segment: {err}") from err
    else:
        # Story complete
        complete_story(character_id, story_id, outcome)  # type: ignore

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

    for record in event.get("Records", []):
        message_id = record.get("messageId", "unknown")

        try:
            # Parse message body
            message_body = json.loads(record.get("body", "{}"))
            active_segment_id = message_body.get("ActiveSegmentID")

            if not active_segment_id:
                raise ValueError("Missing ActiveSegmentID in message")

            logger.info(f"Processing segment advancement for {active_segment_id}")

            # Process the segment
            result = advance_story_business_logic(active_segment_id)

            if result.get("success"):
                success_count += 1
                logger.info(f"Segment advancement complete for {active_segment_id}")
            else:
                raise RuntimeError("Segment advancement failed")

        except ValueError as err:
            logger.error(f"Invalid message format for {message_id} Error: {err}")
            failure_count += 1
            # Don't retry invalid messages

        except Exception as err:
            logger.error(f"Failed to process message for {message_id} Error: {err}", exc_info=True)
            failure_count += 1
            # Add to batch failures for retry
            batch_item_failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": batch_item_failures}
