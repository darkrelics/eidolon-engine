"""
Segment creation and management.

Provides functions for creating and managing story segments.
"""

from botocore.exceptions import ClientError
from uuid_extension import uuid7

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger
from eidolon.time_utils import from_unix, future_unix, now_unix


def create_active_segment(character_id: str, player_id: str, story_id: str, segment: dict, story_instance_id = None) -> dict:
    """
    Create an active segment record for tracking progress.
    Also creates a SegmentHistory record and adds it to StoryHistory if story_instance_id is provided.

    Args:
        character_id: Character UUID
        player_id: Player UUID
        story_id: Story UUID
        segment: Segment data from Segments table
        story_instance_id: StoryInstanceID for this story execution (optional for backward compatibility)

    Returns:
        Active segment record

    Raises:
        RuntimeError: If database operation fails
    """
    segment_id = segment.get("SegmentID")
    segment_type = segment.get("SegmentType", "mechanical")
    duration = int(segment.get("SegmentDuration", 300))

    start_time = now_unix()
    end_time = future_unix(duration)

    logger.info(f"Creating segment with StartTime: {from_unix(start_time)}, EndTime: {from_unix(end_time)}, Duration: {duration}s")

    active_segment_id = str(uuid7())

    active_segment = {
        "ActiveSegmentID": active_segment_id,
        "CharacterID": character_id,
        "PlayerID": player_id,
        "StoryID": story_id,
        "StoryInstanceID": story_instance_id if story_instance_id else None,
        "SegmentID": segment_id,
        "SegmentType": segment_type,
        "Status": "active",
        "StartTime": start_time,
        "EndTime": end_time,
        "DefaultStatus": segment.get("ShortStatus", "Processing..."),
    }

    if segment_type == "decision":
        active_segment["Decision"] = None
        active_segment["DecisionOptions"] = segment.get("DecisionOptions", {})
    elif segment_type == "mechanical":
        active_segment["ChallengeResults"] = []
        active_segment["Outcome"] = None

        combat_config = segment.get("Combat", {})
        if combat_config:
            opponent_id = combat_config.get("OpponentID") or combat_config.get("opponentId")

            opponent_health = 5
            if opponent_id:
                try:
                    opponent = dynamo.get_item(TableName.OPPONENTS, {"OpponentID": opponent_id})
                    if opponent:
                        opponent_health = opponent.get("Health", 5)
                except Exception as err:
                    logger.warning(f"Failed to load opponent for combat state init for {opponent_id} Error: {err}")

            active_segment["CombatState"] = {
                "Round": 0,
                "PlayerWounds": [],
                "OpponentWounds": [],
                "OpponentHealth": opponent_health,
                "OpponentID": opponent_id,
            }

    try:
        dynamo.put_item(TableName.ACTIVE_SEGMENTS, active_segment)
    except ClientError as err:
        logger.error(f"Failed to create active segment for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to create active segment: {err}") from err

    if story_instance_id:
        try:
            segment_history = {
                "CharacterID": character_id,
                "ActiveSegmentID": active_segment_id,
                "StoryInstanceID": story_instance_id,
                "StoryID": story_id,
                "SegmentID": segment_id,
                "SegmentType": segment_type,
                "StartTime": start_time,
                "EndTime": end_time,
            }
            dynamo.put_item(TableName.SEGMENT_HISTORY, segment_history)
            
            dynamo.update_item(
                TableName.STORY_HISTORY,
                Key={"CharacterID": character_id, "StoryInstanceID": story_instance_id},
                UpdateExpression="SET SegmentHistory = list_append(SegmentHistory, :segment_id)",
                ExpressionAttributeValues={":segment_id": [active_segment_id]},
            )
            
            logger.info(f"Created SegmentHistory record and updated StoryHistory for segment {active_segment_id}")
        except ClientError as err:
            logger.error(f"Failed to create segment history for {active_segment_id}: {err}")

    return active_segment