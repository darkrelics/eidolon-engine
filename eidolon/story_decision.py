"""
Decision segment handling.

Provides functions for managing decision segments and player choices.
"""

import time

from botocore.exceptions import ClientError

from eidolon.character_segment import update_character_active_segment
from eidolon.dynamo import TableName, dynamo
from eidolon.environment import SEGMENT_QUEUE_URL
from eidolon.logger import logger
from eidolon.player import verify_character_ownership
from eidolon.segment_core import get_segment_definition
from eidolon.segment_history import record_segment_history
from eidolon.segment_polling import delete_active_segment
from eidolon.segment_state import create_next_active_segment
from eidolon.sqs import send_message
from eidolon.story_active import get_active_decision_segment
from eidolon.story_completion import complete_story
from eidolon.story_retrieval import get_story_segment
from eidolon.time_utils import future_iso, now_iso


def validate_decision_option(active_segment: dict, decision_id: str) -> None:
    """
    Validate that the decision is valid for this segment.

    Args:
        active_segment: Active segment data
        decision_id: Decision ID submitted by player

    Raises:
        ValueError: If decision is not valid for this segment
    """
    decision_options = active_segment.get("DecisionOptions", {})
    if decision_id not in decision_options:
        raise ValueError("Invalid decision option")

    if active_segment.get("Decision"):
        logger.warning(f"Decision already submitted for {active_segment.get('ActiveSegmentID')}")
        raise ValueError("Decision already submitted")


def update_segment_decision(active_segment_id: str, decision_id: str) -> dict:
    """
    Update the active segment with the player's decision.

    Uses conditional update to ensure:
    1. Decision hasn't already been submitted (prevents race conditions)
    2. Segment is still in 'active' status (prevents late updates)

    Both conditions result in a ValueError that maps to HTTP 409 Conflict.

    Args:
        active_segment_id: Active segment UUID
        decision_id: Decision ID chosen by player

    Returns:
        Updated active segment data

    Raises:
        ValueError: If decision was already submitted or segment not active (409)
        RuntimeError: If database update fails
    """
    try:
        dynamo.update_item(
            TableName.ACTIVE_SEGMENTS,
            Key={"ActiveSegmentID": active_segment_id},
            UpdateExpression="SET #decision = :decision, #status = :completed",
            ExpressionAttributeNames={"#decision": "Decision", "#status": "Status"},
            ExpressionAttributeValues={":decision": decision_id, ":completed": "completed", ":active": "active", ":null": None},
            ConditionExpression="(attribute_not_exists(#decision) OR #decision = :null) AND #status = :active",
        )

        updated_segment = dynamo.get_item(TableName.ACTIVE_SEGMENTS, {"ActiveSegmentID": active_segment_id})
        if not updated_segment:
            raise RuntimeError("Failed to retrieve updated segment")

        return updated_segment
    except ClientError as err:
        # Check if this was a conditional check failure
        if err.response["Error"]["Code"] == "ConditionalCheckFailedException":
            # Try to determine which condition failed by checking current state
            current_segment = dynamo.get_item(TableName.ACTIVE_SEGMENTS, {"ActiveSegmentID": active_segment_id})
            if current_segment:
                decision_value = current_segment.get("Decision")
                status_value = current_segment.get("Status")
                logger.warning(
                    f"Conditional check failed for {active_segment_id}: "
                    f"Decision={decision_value}, Status={status_value}, "
                    f"SegmentID={current_segment.get('SegmentID')}"
                )
                if decision_value:
                    logger.warning(f"Decision already submitted for {active_segment_id} (race condition detected)")
                    raise ValueError("Decision already submitted") from err
                elif status_value != "active":
                    logger.warning(f"Segment {active_segment_id} is no longer active (status: {status_value})")
                    raise ValueError("Decision already submitted") from err  # Same error for 409 mapping
                else:
                    logger.warning("Conditional check failed but Decision=None and Status=active - unexpected state")
                    raise ValueError("Decision already submitted") from err
            else:
                logger.warning(f"Conditional check failed for {active_segment_id} but segment not found")
                raise ValueError("Decision already submitted") from err

        logger.error(f"Failed to update active segment for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to update active segment: {err}") from err


def get_next_segment_id_from_decision(decision_options: dict, decision_id: str) -> str | None:
    """
    Extract next segment ID from decision options.

    Supports both formats:
    - Legacy: {"choiceId": "segment-uuid"}
    - Rich: {"choiceId": {"NextSegmentID": "segment-uuid", "Text": "..."}}

    Args:
        decision_options: Decision options dict
        decision_id: Chosen decision ID

    Returns:
        Next segment ID or None
    """
    decision_value = decision_options.get(decision_id)
    if not decision_value:
        return None

    # Check if it's rich format (dict with NextSegmentID)
    if isinstance(decision_value, dict):
        return decision_value.get("NextSegmentID")

    # Legacy format (direct segment ID string)
    if isinstance(decision_value, str):
        return decision_value

    return None


def get_next_segment_time(active_segment: dict, decision_id: str) -> int:
    """
    Calculate the next segment completion time based on the decision.

    Args:
        active_segment: Active segment data
        decision_id: Decision ID chosen by player

    Returns:
        Next segment completion time (0 if no next segment)
    """
    decision_options = active_segment.get("DecisionOptions", {})
    next_segment_id = get_next_segment_id_from_decision(decision_options, decision_id)

    if not next_segment_id:
        return 0

    try:
        story_id = active_segment.get("StoryID")
        if not story_id:
            return 0
        next_segment = get_story_segment(story_id, next_segment_id)

        duration = int(next_segment.get("SegmentDuration", 300))
        return int(time.time()) + duration

    except (ValueError, RuntimeError) as err:
        logger.error(f"Failed to get next segment for {next_segment_id} Error: {err}")
        return 0


def submit_decision_for_character(character_id: str, decision_id: str, player_id: str) -> dict:
    """
    Submit a decision for a character's active decision segment.

    Args:
        character_id: Character UUID
        decision_id: Decision ID chosen by player
        player_id: Authenticated player ID

    Returns:
        Dict with accepted status and optional next segment time

    Raises:
        ValueError: If validation fails
        RuntimeError: If database operations fail
    """
    if not verify_character_ownership(character_id, player_id):
        raise ValueError("Character not owned by player")

    active_segment = get_active_decision_segment(character_id, player_id)
    active_segment_id = active_segment.get("ActiveSegmentID")
    story_id = active_segment.get("StoryID")
    segment_id = active_segment.get("SegmentID")

    if not active_segment_id:
        raise ValueError("Active segment ID not found")

    logger.info(
        f"Submitting decision for character={character_id}: "
        f"StoryID={story_id}, SegmentID={segment_id}, ActiveSegmentID={active_segment_id}, Decision={decision_id}"
    )

    validate_decision_option(active_segment, decision_id)

    update_segment_decision(active_segment_id, decision_id)

    if not story_id:
        raise ValueError("Story ID not found in active segment")

    active_segment["Outcome"] = "normal"
    active_segment["Decision"] = decision_id
    active_segment["DecisionMadeAt"] = now_iso()

    story_instance_id = active_segment.get("StoryInstanceID")
    segment_id = active_segment.get("SegmentID")
    if not segment_id:
        raise ValueError("Segment ID not found in active segment")

    segment_def = get_segment_definition(str(story_id), str(segment_id))

    # Generate ClientEvents for the decision to enrich history
    from eidolon.segment_processing import process_decision_segment

    process_decision_segment(active_segment, segment_def)

    record_segment_history(character_id, story_id, active_segment_id, active_segment)

    # Get next segment ID from the decision options (supports both legacy and rich formats)
    decision_options = segment_def.get("DecisionOptions", {})
    next_segment_id = get_next_segment_id_from_decision(decision_options, decision_id)

    response_data: dict = {
        "Accepted": True,
        # Include the completed decision segment so frontend can display narrative immediately
        "CompletedSegment": {
            "ActiveSegmentID": active_segment_id,
            "SegmentID": segment_id,
            "SegmentType": "decision",
            "Status": "completed",
            "Decision": decision_id,
            "Outcome": "normal",
            "ProcessingStatus": "processed",
            "ClientEvents": active_segment.get("ClientEvents", []),
            "DecisionOptions": segment_def.get("DecisionOptions", {}),
            "SegmentTitle": active_segment.get("SegmentTitle"),
            "SegmentActivity": active_segment.get("SegmentActivity"),
        },
    }

    if next_segment_id:
        try:
            next_segment_def = get_segment_definition(story_id, next_segment_id)  # type: ignore

            next_active_segment_id = create_next_active_segment(
                character_id,
                player_id,
                story_id,
                next_segment_def,
                story_instance_id,
            )

            update_character_active_segment(character_id, next_active_segment_id)

            next_segment_duration = next_segment_def.get("SegmentDuration", 60)
            response_data["NextSegmentTime"] = future_iso(next_segment_duration)

            # Return the next segment data so Flutter doesn't need to reload
            response_data["NextSegment"] = {
                "ActiveSegmentID": next_active_segment_id,
                "StoryID": story_id,
                "SegmentID": next_segment_id,
                "SegmentType": next_segment_def.get("SegmentType"),
                "Status": "active",
                "StartTime": now_iso(),
                "EndTime": future_iso(next_segment_duration),
                "ProcessingStatus": "pending",
                "SegmentActivity": next_segment_def.get("SegmentActivity"),
                "SegmentTitle": next_segment_def.get("SegmentTitle"),
                "Duration": next_segment_duration,
            }

            # Add decision-specific fields if next is a decision
            if next_segment_def.get("SegmentType") == "decision":
                response_data["NextSegment"]["DecisionText"] = next_segment_def.get("DecisionText")
                response_data["NextSegment"]["DecisionOptions"] = next_segment_def.get("DecisionOptions", {})
                response_data["NextSegment"]["DefaultDecision"] = next_segment_def.get("DefaultDecision")

            # Attempt to delete the old segment, but treat failure as non-fatal
            # since the story has already successfully advanced
            try:
                delete_active_segment(active_segment_id)
                logger.info(f"Advanced to next segment after decision and deleted prior segment for {character_id}")
            except Exception as err:
                # Log warning but don't fail the request - the advancement was successful
                # and the old segment will be cleaned up by the poller eventually
                logger.warning(f"Failed to delete old active segment {active_segment_id} after successful advancement: {err}")
                logger.info(f"Advanced to next segment after decision for {character_id} (old segment cleanup failed)")

            if next_segment_def.get("SegmentType") == "mechanical":
                try:
                    if SEGMENT_QUEUE_URL:
                        # Send just the ActiveSegmentID string (what ops_segment_process expects)
                        send_message(SEGMENT_QUEUE_URL, next_active_segment_id)
                        logger.info(f"Queued next mechanical segment for processing for {next_active_segment_id}")
                except Exception as err:
                    logger.warning(f"Failed to queue mechanical segment for {next_active_segment_id} Error: {err}")
        except Exception as err:
            logger.error(f"Failed to create next segment after decision for {next_segment_id} Error: {err}", exc_info=True)
            raise RuntimeError(f"Failed to create next segment: {err}") from err
    else:
        complete_story(character_id, story_id, story_instance_id, "normal")
        logger.info(f"Story completed after final decision for character={character_id}, StoryID={story_id}")
        return response_data

    # Log final success with new segment context
    next_active_segment_id = response_data.get("NextSegment", {}).get("ActiveSegmentID")
    next_segment_id = response_data.get("NextSegment", {}).get("SegmentID")
    logger.info(
        f"Decision submitted and story advanced for character={character_id}: "
        f"Decision={decision_id}, NextActiveSegmentID={next_active_segment_id}, NextSegmentID={next_segment_id}"
    )

    return response_data
