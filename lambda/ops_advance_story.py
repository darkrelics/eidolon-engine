"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to advance stories after segment completion.
Triggered by SQS to apply character updates and progress stories.
"""

import json
from datetime import datetime, timezone
from decimal import Decimal

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import get_logger
from eidolon.segment import (
    claim_segment_for_processing, 
    create_next_active_segment,
    is_simple_segment,
    process_decision_segment,
    process_rest_segment,
)
from eidolon.utilities import log_lambda_invocation

# Configure logging
logger = get_logger(__name__)


def apply_character_updates(character_id: str, updates: dict) -> None:
    """
    Apply accumulated updates to character.
    
    Handles skill XP, attribute XP, wounds, and room changes.
    
    Args:
        character_id: Character UUID
        updates: Dict containing CharacterUpdates from segment processing
        
    Raises:
        RuntimeError: If database update fails
    """
    if not updates:
        logger.info("No character updates to apply", extra={"character_id": character_id})
        return
        
    update_expressions = []
    expression_names = {}
    expression_values = {}
    
    # Apply skill XP updates
    skill_xp = updates.get("SkillXP", {})
    for skill, xp_value in skill_xp.items():
        if xp_value > 0:
            safe_skill = skill.replace("-", "_")
            update_expressions.append(f"Skills.#skill_{safe_skill} = if_not_exists(Skills.#skill_{safe_skill}, :zero) + :xp_{safe_skill}")
            expression_names[f"#skill_{safe_skill}"] = skill
            expression_values[f":xp_{safe_skill}"] = Decimal(str(xp_value))
    
    # Apply attribute XP updates
    attribute_xp = updates.get("AttributeXP", {})
    for attribute, xp_value in attribute_xp.items():
        if xp_value > 0:
            safe_attr = attribute.replace("-", "_")
            update_expressions.append(f"Attributes.#attr_{safe_attr} = if_not_exists(Attributes.#attr_{safe_attr}, :zero) + :xp_{safe_attr}")
            expression_names[f"#attr_{safe_attr}"] = attribute
            expression_values[f":xp_{safe_attr}"] = Decimal(str(xp_value))
    
    # Apply wounds
    wounds = updates.get("Wounds", [])
    if wounds:
        update_expressions.append("Wounds = list_append(if_not_exists(Wounds, :empty_list), :new_wounds)")
        expression_values[":new_wounds"] = wounds
        expression_values[":empty_list"] = []
    
    # Apply room change
    room_id = updates.get("Room")
    if room_id is not None:
        update_expressions.append("RoomID = :room")
        expression_values[":room"] = room_id
    
    # Set common values
    if expression_values and ":zero" not in expression_values:
        expression_values[":zero"] = Decimal("0")
    
    # Execute update if there are changes
    if update_expressions:
        try:
            update_expression = "SET " + ", ".join(update_expressions)
            update_expression += ", UpdatedAt = :updated_at"
            expression_values[":updated_at"] = datetime.now(timezone.utc).isoformat()
            
            dynamo.update_item(
                TableName.CHARACTERS,
                Key={"CharacterID": character_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names if expression_names else None,
                ExpressionAttributeValues=expression_values,
            )
            
            logger.info(
                "Character updates applied",
                extra={
                    "character_id": character_id,
                    "skills_updated": len(skill_xp),
                    "attributes_updated": len(attribute_xp),
                    "wounds_added": len(wounds),
                    "room_changed": room_id is not None,
                },
            )
        except ClientError as err:
            logger.error(
                "Failed to apply character updates",
                extra={
                    "character_id": character_id,
                    "error": str(err),
                    "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
                },
                exc_info=True,
            )
            raise RuntimeError(f"Failed to apply character updates: {str(err)}")


def record_segment_history(character_id: str, story_id: str, active_segment_id: str, segment_data: dict) -> None:
    """
    Record segment completion in history table.
    
    Args:
        character_id: Character UUID
        story_id: Story UUID
        segment_data: Segment completion data
        
    Raises:
        RuntimeError: If database operation fails
    """
    history_entry = {
        "SegmentID": segment_data.get("SegmentID"),
        "SegmentType": segment_data.get("SegmentType"),
        "Outcome": segment_data.get("Outcome"),
        "CompletedAt": datetime.now(timezone.utc).isoformat(),
        "ClientEvents": segment_data.get("ClientEvents", []),
    }
    
    # Add type-specific data
    if segment_data.get("ChallengeResults"):
        history_entry["ChallengeResults"] = segment_data["ChallengeResults"]
    if segment_data.get("CombatState"):
        history_entry["CombatState"] = segment_data["CombatState"]
    if segment_data.get("Decision"):
        history_entry["Decision"] = segment_data["Decision"]
        
    try:
        # Check if segment history record exists
        history = dynamo.get_item(
            TableName.SEGMENT_HISTORY,
            {"CharacterID": character_id, "ActiveSegmentID": active_segment_id},
        )
        
        if not history:
            # Create new segment history record
            dynamo.put_item(
                TableName.SEGMENT_HISTORY,
                {
                    "CharacterID": character_id,
                    "ActiveSegmentID": active_segment_id,
                    "StoryID": story_id,
                    "SegmentID": segment_data.get("SegmentID"),
                    "SegmentType": segment_data.get("SegmentType"),
                    "Outcome": segment_data.get("Outcome"),
                    "CompletedAt": datetime.now(timezone.utc).isoformat(),
                    "ClientEvents": segment_data.get("ClientEvents", []),
                    "ChallengeResults": segment_data.get("ChallengeResults"),
                    "CombatState": segment_data.get("CombatState"),
                    "Decision": segment_data.get("Decision"),
                },
            )
            
        logger.info(
            "Segment history recorded",
            extra={
                "character_id": character_id,
                "story_id": story_id,
                "segment_id": segment_data.get("SegmentID"),
            },
        )
    except ClientError as err:
        logger.error(
            "Failed to record segment history",
            extra={
                "character_id": character_id,
                "story_id": story_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to record segment history: {str(err)}")


def ensure_story_history_exists(character_id: str, story_id: str, story_title: str) -> None:
    """
    Ensure story history record exists.
    
    Creates a new story history record if one doesn't exist.
    
    Args:
        character_id: Character UUID
        story_id: Story UUID
        story_title: Story title for display
        
    Raises:
        RuntimeError: If database operations fail
    """
    try:
        # Check if story history exists
        history = dynamo.get_item(
            TableName.STORY_HISTORY,
            {"CharacterID": character_id, "StoryID": story_id},
        )
        
        if not history:
            # Create new story history
            dynamo.put_item(
                TableName.STORY_HISTORY,
                {
                    "CharacterID": character_id,
                    "StoryID": story_id,
                    "StoryTitle": story_title,
                    "StartedAt": datetime.now(timezone.utc).isoformat(),
                    "SegmentCount": 0,
                },
            )
            logger.info(
                "Created story history record",
                extra={
                    "character_id": character_id,
                    "story_id": story_id,
                },
            )
    except ClientError as err:
        logger.error(
            "Failed to ensure story history exists",
            extra={
                "character_id": character_id,
                "story_id": story_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to ensure story history exists: {str(err)}")


def complete_story(character_id: str, story_id: str, outcome: str) -> None:
    """
    Complete the story and reset character state.
    
    Args:
        character_id: Character UUID
        story_id: Story UUID
        outcome: Final story outcome
        
    Raises:
        RuntimeError: If database operations fail
    """
    # Update character state
    try:
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET GameMode = :none, ActiveStoryID = :null, ActiveSegmentID = :null, CompletedStories = list_append(if_not_exists(CompletedStories, :empty), :story)",
            ExpressionAttributeValues={
                ":none": "None",
                ":null": None,
                ":empty": [],
                ":story": [story_id],
            },
        )
    except ClientError as err:
        logger.error(
            "Failed to update character for story completion",
            extra={
                "character_id": character_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to update character: {str(err)}")
    
    # Update story history
    try:
        dynamo.update_item(
            TableName.STORY_HISTORY,
            Key={"CharacterID": character_id, "StoryID": story_id},
            UpdateExpression="SET CompletedAt = :completed, FinalOutcome = :outcome",
            ExpressionAttributeValues={
                ":completed": datetime.now(timezone.utc).isoformat(),
                ":outcome": outcome,
            },
        )
    except ClientError as err:
        logger.error(
            "Failed to update story history",
            extra={
                "character_id": character_id,
                "story_id": story_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to update story history: {str(err)}")
        
    logger.info(
        "Story completed",
        extra={
            "character_id": character_id,
            "story_id": story_id,
            "outcome": outcome,
        },
    )


def determine_next_segment(segment_def: dict, active_segment: dict, outcome: str) -> object:
    """
    Determine the next segment ID based on segment type and outcome.
    
    Args:
        segment_def: Segment definition from Segments table
        active_segment: Active segment record
        outcome: Segment outcome
        
    Returns:
        Next segment ID or None if story ends
    """
    segment_type = segment_def.get("SegmentType")
    
    if segment_type == "decision":
        # Use decision to determine next segment
        decision = active_segment.get("Decision")
        if decision:
            decision_options = segment_def.get("DecisionOptions", {})
            return decision_options.get(decision)
    elif segment_type in ["mechanical", "rest"]:
        # Check if outcome is terminal
        if outcome in ["death", "failure"]:
            # Some outcomes end the story
            results = segment_def.get("Results", {})
            outcome_result = results.get(outcome, {})
            if outcome_result.get("terminal", False):
                return None
        # Otherwise continue to next segment
        return segment_def.get("NextSegmentID")
    
    return segment_def.get("NextSegmentID")


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
    try:
        active_segment = dynamo.get_item(
            TableName.ACTIVE_SEGMENTS,
            {"ActiveSegmentID": active_segment_id},
        )
        if not active_segment:
            raise ValueError(f"Active segment not found: {active_segment_id}")
    except ClientError as err:
        logger.error(
            "Failed to get active segment",
            extra={
                "active_segment_id": active_segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to get active segment: {str(err)}")
    
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
    ensure_story_history_exists(character_id, story_id, story_title)
    
    # Process simple segments if not already processed
    processing_status = active_segment.get("ProcessingStatus")
    if is_simple_segment(segment_type) and processing_status != "processed":
        logger.info(
            "Processing simple segment",
            extra={
                "active_segment_id": active_segment_id,
                "segment_type": segment_type,
            },
        )
        
        # Get segment definition
        try:
            segment_def = dynamo.get_item(
                TableName.SEGMENTS,
                {"StoryID": story_id, "SegmentID": segment_id},
            )
            if not segment_def:
                raise ValueError(f"Segment definition not found: {segment_id}")
        except ClientError as err:
            logger.error(
                "Failed to get segment definition for simple processing",
                extra={
                    "segment_id": segment_id,
                    "error": str(err),
                    "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
                },
                exc_info=True,
            )
            raise RuntimeError(f"Failed to get segment definition: {str(err)}")
        
        # Get character data for processing
        try:
            character = dynamo.get_item(
                TableName.CHARACTERS,
                {"CharacterID": character_id},
            )
            if not character:
                raise ValueError(f"Character not found: {character_id}")
        except ClientError as err:
            logger.error(
                "Failed to get character for simple processing",
                extra={
                    "character_id": character_id,
                    "error": str(err),
                    "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
                },
                exc_info=True,
            )
            raise RuntimeError(f"Failed to get character: {str(err)}")
        
        # Process based on type
        if segment_type == "rest":
            outcome, healing_data = process_rest_segment(segment_def, character)
            character_updates = {"healingApplied": healing_data}
        elif segment_type == "decision":
            outcome = process_decision_segment(active_segment, segment_def)
            character_updates = {}
        else:
            raise ValueError(f"Unknown simple segment type: {segment_type}")
        
        # Update active segment with results
        try:
            dynamo.update_item(
                TableName.ACTIVE_SEGMENTS,
                Key={"ActiveSegmentID": active_segment_id},
                UpdateExpression="SET ProcessingStatus = :status, #outcome = :outcome, CharacterUpdates = :updates",
                ExpressionAttributeNames={"#outcome": "Outcome"},
                ExpressionAttributeValues={
                    ":status": "processed",
                    ":outcome": outcome,
                    ":updates": character_updates,
                },
            )
            active_segment["Outcome"] = outcome
            active_segment["CharacterUpdates"] = character_updates
            active_segment["ProcessingStatus"] = "processed"
        except ClientError as err:
            logger.error(
                "Failed to update simple segment results",
                extra={
                    "active_segment_id": active_segment_id,
                    "error": str(err),
                    "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
                },
                exc_info=True,
            )
            raise RuntimeError(f"Failed to update segment results: {str(err)}")
    
    # Apply character updates
    character_updates = active_segment.get("CharacterUpdates", {})
    if character_updates:
        apply_character_updates(character_id, character_updates)
    
    # Record segment history
    record_segment_history(character_id, story_id, active_segment_id, active_segment)
    
    # Get segment definition to determine next action
    try:
        segment_def = dynamo.get_item(
            TableName.SEGMENTS,
            {"StoryID": story_id, "SegmentID": segment_id},
        )
        if not segment_def:
            raise ValueError(f"Segment definition not found: {segment_id}")
    except ClientError as err:
        logger.error(
            "Failed to get segment definition",
            extra={
                "segment_id": segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to get segment definition: {str(err)}")
    
    # Determine next segment
    next_segment_id = determine_next_segment(segment_def, active_segment, outcome)
    
    if next_segment_id:
        # Create next segment
        try:
            next_segment_def = dynamo.get_item(
                TableName.SEGMENTS,
                {"StoryID": story_id, "SegmentID": next_segment_id},
            )
            if not next_segment_def:
                raise ValueError(f"Next segment not found: {next_segment_id}")
                
            next_active_segment_id = create_next_active_segment(
                character_id,
                active_segment.get("PlayerID"),
                story_id,
                next_segment_def,
                active_segment.get("StoryTitle"),
            )
            
            # Update character with new active segment
            dynamo.update_item(
                TableName.CHARACTERS,
                Key={"CharacterID": character_id},
                UpdateExpression="SET ActiveSegmentID = :segment",
                ExpressionAttributeValues={":segment": next_active_segment_id},
            )
            
            logger.info(
                "Created next segment",
                extra={
                    "character_id": character_id,
                    "next_segment_id": next_segment_id,
                    "next_active_segment_id": next_active_segment_id,
                },
            )
        except ClientError as err:
            logger.error(
                "Failed to create next segment",
                extra={
                    "next_segment_id": next_segment_id,
                    "error": str(err),
                    "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
                },
                exc_info=True,
            )
            raise RuntimeError(f"Failed to create next segment: {str(err)}")
    else:
        # Story complete
        complete_story(character_id, story_id, outcome)
    
    # Delete processed segment
    try:
        dynamo.delete_item(
            TableName.ACTIVE_SEGMENTS,
            {"ActiveSegmentID": active_segment_id},
        )
    except ClientError as err:
        logger.warning(
            "Failed to delete processed segment",
            extra={
                "active_segment_id": active_segment_id,
                "error": str(err),
            },
        )
        # Non-critical, continue
    
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