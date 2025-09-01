"""
Story and segment data retrieval.

Provides functions for retrieving story and segment information.
"""

from datetime import datetime, timezone

from botocore.exceptions import ClientError

from eidolon.character_story import get_story_history
from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger
from eidolon.schema import normalize_segment_definition
from eidolon.segment_core import validate_segment_outcome_results
from eidolon.time_utils import from_unix


def get_story_segment(story_id: str, segment_id: str) -> dict:
    """
    Get a specific segment from the SEGMENTS table.

    Args:
        story_id: Story UUID
        segment_id: Segment UUID

    Returns:
        Segment data dict

    Raises:
        ValueError: If segment not found
        RuntimeError: If database query fails
    """
    if not story_id:
        raise ValueError("Story ID cannot be empty")
    if not segment_id:
        raise ValueError("Segment ID cannot be empty")

    try:
        segment = dynamo.get_item(TableName.SEGMENTS, {"StoryID": story_id, "SegmentID": segment_id})
        if not segment:
            raise ValueError("Segment not found")
        return normalize_segment_definition(segment)
    except ClientError as err:
        logger.error(f"Failed to get segment for {segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get segment: {err}") from err


def get_completed_segment_for_character(character_id: str, player_id: str, segment_id: str) -> dict:
    """
    Get a completed segment for a character with player ID verification.

    Args:
        character_id: Character UUID
        player_id: Player ID for verification
        segment_id: Segment UUID to find

    Returns:
        Active segment data dict

    Raises:
        ValueError: If segment not found or not completed
        RuntimeError: If database query fails
    """
    if not character_id:
        raise ValueError("Character ID cannot be empty")
    if not player_id:
        raise ValueError("Player ID cannot be empty")
    if not segment_id:
        raise ValueError("Segment ID cannot be empty")

    try:
        items = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="CharacterID-index",
            KeyConditionExpression="CharacterID = :cid",
            FilterExpression="PlayerID = :pid AND SegmentID = :sid AND (#status = :completed OR ProcessingStatus = :processed)",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={
                ":cid": character_id,
                ":pid": player_id,
                ":sid": segment_id,
                ":completed": "completed",
                ":processed": "processed",
            },
        )
    except ClientError as err:
        logger.error(f"Failed to query active segments for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to query segments: {err}") from err

    if not items:
        try:
            history_items = dynamo.query(
                TableName.SEGMENT_HISTORY,
                KeyConditionExpression="CharacterID = :cid",
                ExpressionAttributeValues={":cid": character_id},
            )
        except ClientError as err:
            logger.error(
                f"Failed to query segment history for {character_id} Error: {err}",
                exc_info=True,
            )
            raise RuntimeError(f"Failed to query segments: {err}") from err

        if not history_items:
            raise ValueError("Completed segment not found")

        candidates = [it for it in history_items if it.get("SegmentID") == segment_id]
        if not candidates:
            raise ValueError("Completed segment not found")

        def sort_key(it: dict):
            completed = it.get("CompletedAt") or ""
            end_time = it.get("EndTime") or 0
            return (1, completed) if completed else (0, end_time)

        return max(candidates, key=sort_key)

    active_segment = items[0]

    if active_segment.get("Status") != "completed" and active_segment.get("ProcessingStatus") != "processed":
        raise ValueError("Segment not yet completed")

    return active_segment


def get_story_and_first_segment(story_id: str) -> tuple:
    """
    Get story metadata and first segment details.

    Args:
        story_id: Story UUID

    Returns:
        Tuple of (story_data, first_segment)

    Raises:
        ValueError: If story or first segment not found
        RuntimeError: If database operations fail
    """
    try:
        story = dynamo.get_item(TableName.STORY, {"StoryID": story_id})
        if not story:
            raise ValueError("Story not found")
    except ClientError as err:
        logger.error(f"Failed to get story for {story_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get story: {err}") from err

    first_segment_id = story.get("FirstSegmentID")
    if not first_segment_id:
        logger.error(f"Story has no first segment for {story_id}")
        raise ValueError("Story configuration error")

    first_segment = get_story_segment(story_id, first_segment_id)
    return story, first_segment


def get_story_cooldown(character_id: str, story_id: str, story_type: str):
    """
    Calculate cooldown remaining for a story based on its type and last completion.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        story_type: Type of story (one-time, daily, repeatable)

    Returns:
        Seconds remaining on cooldown, 0 if playable, -1 if permanently unavailable
    """
    if story_type == "repeatable":
        return 0

    try:
        history = get_story_history(character_id, story_id)

        if not history:
            return 0

        if not history.get("FinishedAt"):
            return 0

        if story_type == "one-time":
            outcome = history.get("FinalOutcome", "")
            if outcome in ["normal", "exceptional", "minimal"]:
                return -1
            return 0

        if story_type == "daily":
            # Allow retry if story was abandoned
            final_outcome = history.get("FinalOutcome", "")
            if final_outcome == "abandoned":
                return 0

            finished_at = datetime.fromisoformat(history.get("FinishedAt", "").replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)

            if finished_at.date() == now.date():
                midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
                midnight = midnight.replace(day=midnight.day + 1)
                return int((midnight - now).total_seconds())

            return 0

    except Exception as err:
        logger.error(f"Error checking story cooldown Error: {err}")
        return 0


def enrich_segment_with_narrative(segment_data: dict, active_segment: dict) -> dict:
    """
    Enrich segment data with narrative content, timestamps, and next segment information.

    Handles:
    - Unix timestamp to ISO 8601 conversion
    - Narrative content based on segment type and processing status
    - Next segment ID calculation
    - Effects from segment outcomes

    Args:
        segment_data: Decimal-converted segment data dict
        active_segment: Original segment with type and status information

    Returns:
        Enriched segment_data dict with narrative and navigation data
    """
    # Convert Unix timestamps to ISO 8601
    if "StartTime" in segment_data and segment_data["StartTime"] is not None:
        try:
            unix_time = float(segment_data["StartTime"])
            segment_data["StartTime"] = from_unix(int(unix_time))
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to convert StartTime: {e}")

    if "EndTime" in segment_data and segment_data["EndTime"] is not None:
        try:
            unix_time = float(segment_data["EndTime"])
            segment_data["EndTime"] = from_unix(int(unix_time))
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to convert EndTime: {e}")

    # Add narrative data if segment is processed/completed
    processing_status = active_segment.get("ProcessingStatus", "")
    segment_status = active_segment.get("Status", "")
    segment_type = active_segment.get("SegmentType", "").lower()

    if processing_status == "processed" or segment_status == "completed":
        try:
            story_id = active_segment.get("StoryID")
            segment_id = active_segment.get("SegmentID")

            # Get segment definition for narrative
            segment_def = get_story_segment(story_id, segment_id)  # type: ignore
            segment_def = normalize_segment_definition(segment_def)

            if segment_type == "mechanical":
                outcome = active_segment.get("Outcome", "normal")
                validated_result = validate_segment_outcome_results(segment_def, outcome)
                segment_data["Narrative"] = validated_result.get("Narrative", "")
                segment_data["Effects"] = validated_result.get("Effects", {})

                # Get next segment based on outcome
                results = segment_def.get("Results", {}) or {}
                next_segment_id = None
                if isinstance(results, dict):
                    outcome_map = {
                        "death": "Death",
                        "failure": "Failure",
                        "minimal": "Minimal",
                        "normal": "Normal",
                        "exceptional": "Exceptional",
                    }
                    outcome_key = outcome_map.get(str(outcome).lower())
                    if outcome_key and isinstance(results.get(outcome_key), dict):
                        outcome_block = results.get(outcome_key, {})
                        if isinstance(outcome_block, dict) and "NextSegmentID" in outcome_block:
                            next_segment_id = outcome_block.get("NextSegmentID")

                if next_segment_id is None and "NextSegmentID" in segment_def:
                    next_segment_id = segment_def.get("NextSegmentID")

                segment_data["NextSegmentID"] = next_segment_id

            elif segment_type == "rest":
                segment_data["Narrative"] = "You have rested and recovered."
                segment_data["Effects"] = {}
                segment_data["NextSegmentID"] = segment_def.get("NextSegmentID")

            elif segment_type == "decision":
                decision = active_segment.get("Decision")
                decision_options = segment_def.get("DecisionOptions", {})
                segment_data["NextSegmentID"] = decision_options.get(decision) if decision else None
                segment_data["Narrative"] = ""
                segment_data["Effects"] = {}

        except Exception as err:
            logger.warning(f"Failed to get narrative data: {err}")
            # Continue without narrative - not critical

    return segment_data
