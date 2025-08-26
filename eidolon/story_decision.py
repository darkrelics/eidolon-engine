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
from eidolon.segment_processing import determine_next_segment
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

    Args:
        active_segment_id: Active segment UUID
        decision_id: Decision ID chosen by player

    Returns:
        Updated active segment data

    Raises:
        RuntimeError: If database update fails
    """
    try:
        dynamo.update_item(
            TableName.ACTIVE_SEGMENTS,
            Key={"ActiveSegmentID": active_segment_id},
            UpdateExpression="SET #decision = :decision, #status = :status",
            ExpressionAttributeNames={"#decision": "Decision", "#status": "Status"},
            ExpressionAttributeValues={":decision": decision_id, ":status": "completed"},
        )

        updated_segment = dynamo.get_item(TableName.ACTIVE_SEGMENTS, {"ActiveSegmentID": active_segment_id})
        if not updated_segment:
            raise RuntimeError("Failed to retrieve updated segment")

        return updated_segment
    except ClientError as err:
        logger.error(f"Failed to update active segment for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to update active segment: {err}") from err


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
    next_segment_id = decision_options.get(decision_id)

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

    logger.info(f"Submitting decision for {character_id}")

    active_segment = get_active_decision_segment(character_id, player_id)
    active_segment_id = active_segment.get("ActiveSegmentID")
    if not active_segment_id:
        raise ValueError("Active segment ID not found")

    validate_decision_option(active_segment, decision_id)

    update_segment_decision(active_segment_id, decision_id)

    story_id = active_segment.get("StoryID")
    if not story_id:
        raise ValueError("Story ID not found in active segment")

    active_segment["Outcome"] = "normal"
    active_segment["Decision"] = decision_id
    active_segment["DecisionMadeAt"] = now_iso()

    record_segment_history(character_id, story_id, active_segment_id, active_segment)

    story_instance_id = active_segment.get("StoryInstanceID")
    segment_id = active_segment.get("SegmentID")
    if not segment_id:
        raise ValueError("Segment ID not found in active segment")

    segment_def = get_segment_definition(str(story_id), str(segment_id))

    next_segment_id = determine_next_segment(segment_def, active_segment, "normal")

    response_data: dict = {
        "Accepted": True,
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

            delete_active_segment(active_segment_id)

            logger.info(f"Advanced to next segment after decision and deleted prior segment for {character_id}")

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
                    logger.warning(f"Failed to queue mechanical segment for {next_active_segment_id} Error: {err}")
        except Exception as err:
            logger.error(f"Failed to create next segment after decision for {next_segment_id} Error: {err}", exc_info=True)
            raise RuntimeError(f"Failed to create next segment: {err}") from err
    else:
        complete_story(character_id, story_id, story_instance_id, "normal")
        logger.info(f"Story completed after decision for {character_id}")

    logger.info(f"Decision submitted and story advanced for {active_segment_id}")

    return response_data
