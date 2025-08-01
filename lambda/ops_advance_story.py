"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to advance stories after segment completion.
Triggered by SQS to apply character updates and progress stories.
"""

import json

from eidolon.character import apply_death_or_unconscious_outcome, get_character
from eidolon.logger import get_logger
from eidolon.segment import (
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
from eidolon.story import apply_combat_rewards, apply_story_outcome_effects, ensure_story_history_exists, update_story_history_xp
from eidolon.utilities import log_lambda_invocation

# Configure logging
logger = get_logger(__name__)




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

    logger.info(
        "Advancing story",
        extra={
            "active_segment_id": active_segment_id,
            "character_id": character_id,
            "story_id": story_id,
            "segment_type": segment_type,
            "outcome": outcome,
        },
    )

    # Ensure story history exists
    story_title = active_segment.get("StoryTitle", "Unknown Story")
    ensure_story_history_exists(character_id, story_id, story_title) # type: ignore

    # Process simple segments if not already processed
    processing_status = active_segment.get("ProcessingStatus")
    if is_simple_segment(segment_type) and processing_status != "processed": # type: ignore
        logger.info(
            "Processing simple segment",
            extra={
                "active_segment_id": active_segment_id,
                "segment_type": segment_type,
            },
        )

        # Get segment definition
        segment_def = get_segment_definition(story_id, segment_id) # type: ignore

        # Get character data for processing
        character = get_character(character_id) # type: ignore

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
            
            logger.info(
                "Applied character state change for death outcome",
                extra={
                    "character_id": character_id,
                    "new_state": new_character_state,
                    "wound_count": len(wounds)
                }
            )
        except Exception as err:
            logger.error(
                "Failed to apply death/unconscious state",
                extra={
                    "character_id": character_id,
                    "error": str(err)
                },
                exc_info=True
            )
    
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
                    logger.error(
                        "Failed to apply combat rewards",
                        extra={
                            "character_id": character_id,
                            "opponent_id": combat_rewards.get("opponentId"),
                            "error": str(err),
                        },
                        exc_info=True,
                    )
        
        # Apply story outcome effects if present
        story_effects = character_updates.get("StoryEffects", {})
        if story_effects:
            try:
                apply_story_outcome_effects(character_id, story_effects)
            except Exception as err:
                logger.error(
                    "Failed to apply story outcome effects",
                    extra={
                        "character_id": character_id,
                        "effects": story_effects,
                        "error": str(err),
                    },
                    exc_info=True,
                )

    # Record segment history
    record_segment_history(character_id, story_id, active_segment_id, active_segment) # type: ignore
    
    # Update story history with accumulated XP
    skill_xp = character_updates.get("SkillXP", {})
    attribute_xp = character_updates.get("AttributeXP", {})
    if skill_xp or attribute_xp:
        update_story_history_xp(character_id, story_id, skill_xp, attribute_xp) # type: ignore

    # Get segment definition to determine next action
    segment_def = get_segment_definition(story_id, segment_id) # type: ignore
    
    # Check if we need to insert a rest segment for unconscious character
    if new_character_state == "unconscious":
        try:
            # Insert a rest segment after current segment
            rest_segment_id = insert_rest_segment(
                story_id, # type: ignore
                segment_id, # type: ignore
                rest_duration=900,  # 15 minutes to heal
                time_remaining=0  # Current segment is done
            )
            
            # Override next segment to be the rest segment
            next_segment_id = rest_segment_id
            
            logger.info(
                "Inserted rest segment for unconscious character",
                extra={
                    "character_id": character_id,
                    "rest_segment_id": rest_segment_id,
                    "story_id": story_id
                }
            )
        except Exception as err:
            logger.error(
                "Failed to insert rest segment for unconscious character",
                extra={
                    "character_id": character_id,
                    "error": str(err)
                },
                exc_info=True
            )
            # Fall back to normal next segment determination
            next_segment_id = determine_next_segment(segment_def, active_segment, outcome)
    else:
        # Determine next segment normally
        next_segment_id = determine_next_segment(segment_def, active_segment, outcome)

    if next_segment_id:
        # Create next segment
        try:
            next_segment_def = get_segment_definition(story_id, next_segment_id) # type: ignore

            next_active_segment_id = create_next_active_segment(
                character_id, # type: ignore
                active_segment.get("PlayerID"), # type: ignore
                story_id, # type: ignore
                next_segment_def,
                active_segment.get("StoryTitle"), # type: ignore
            )

            # Update character with new active segment
            update_character_active_segment(character_id, next_active_segment_id) # type: ignore

            logger.info(
                "Created next segment",
                extra={
                    "character_id": character_id,
                    "next_segment_id": next_segment_id,
                    "next_active_segment_id": next_active_segment_id,
                    "segment_type": next_segment_def.get("SegmentType"),
                },
            )
            
            # Queue mechanical segments for immediate processing
            if next_segment_def.get("SegmentType") == "mechanical":
                try:
                    from eidolon.environment import SEGMENT_QUEUE_URL
                    from eidolon.sqs import send_message
                    
                    if SEGMENT_QUEUE_URL:
                        message_body = {
                            "ActiveSegmentID": next_active_segment_id,
                            "CharacterID": character_id,
                            "StoryID": story_id,
                            "SegmentID": next_segment_id,
                            "SegmentType": "mechanical",
                        }
                        send_message(SEGMENT_QUEUE_URL, message_body)
                        logger.info(
                            "Queued next mechanical segment for processing",
                            extra={"active_segment_id": next_active_segment_id}
                        )
                except Exception as err:
                    # Non-critical - segment will be picked up by poller
                    logger.warning(
                        "Failed to queue mechanical segment",
                        extra={
                            "active_segment_id": next_active_segment_id,
                            "error": str(err)
                        }
                    )
        except Exception as err:
            logger.error(
                "Failed to create next segment",
                extra={
                    "next_segment_id": next_segment_id,
                    "error": str(err),
                },
                exc_info=True,
            )
            raise RuntimeError(f"Failed to create next segment: {str(err)}")
    else:
        # Story complete
        complete_story(character_id, story_id, outcome) # type: ignore

    # Delete processed segment
    delete_active_segment(active_segment_id)

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
    log_lambda_invocation(context, event)

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

            logger.info(
                "Processing segment advancement",
                extra={
                    "message_id": message_id,
                    "active_segment_id": active_segment_id,
                },
            )

            # Process the segment
            result = advance_story_business_logic(active_segment_id)

            if result.get("success"):
                success_count += 1
                logger.info(
                    "Segment advancement complete",
                    extra={
                        "message_id": message_id,
                        "active_segment_id": active_segment_id,
                        "skipped": result.get("skipped", False),
                        "story_complete": result.get("story_complete", False),
                    },
                )
            else:
                raise RuntimeError("Segment advancement failed")

        except ValueError as err:
            logger.error(
                "Invalid message format",
                extra={
                    "message_id": message_id,
                    "error": str(err),
                },
            )
            failure_count += 1
            # Don't retry invalid messages

        except Exception as err:
            logger.error(
                "Failed to process message",
                extra={
                    "message_id": message_id,
                    "error": str(err),
                },
                exc_info=True,
            )
            failure_count += 1
            # Add to batch failures for retry
            batch_item_failures.append({"itemIdentifier": message_id})

    logger.info(
        "Batch processing complete",
        extra={
            "success_count": success_count,
            "failure_count": failure_count,
            "retry_count": len(batch_item_failures),
        },
    )

    return {"batchItemFailures": batch_item_failures}
