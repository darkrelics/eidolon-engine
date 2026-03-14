"""
Story history tracking operations.

Provides functions for creating and updating story history records.
"""

from decimal import Decimal

from botocore.exceptions import ClientError
from uuid_extension import uuid7

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger
from eidolon.time_utils import now_iso


def create_story_history_entry(character_id: str, story_id: str, story: dict, story_instance_id: str = "") -> str:
    """
    Create initial history entry for story tracking with new schema.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        story: Story data from database containing Title and StoryType
        story_instance_id: Pre-generated StoryInstanceID (optional, generates new if empty)

    Returns:
        StoryInstanceID (UUIDv7) for this story execution

    Raises:
        RuntimeError: If database operation fails
    """
    story_title = story.get("Title", "Unknown Story")
    story_type = story.get("StoryType", "repeatable")

    try:
        if not story_instance_id:
            story_instance_id = str(uuid7())

        history_entry = {
            "CharacterID": character_id,
            "StoryInstanceID": story_instance_id,
            "StoryID": story_id,
            "StoryTitle": story_title,
            "StartedAt": now_iso(),
            "StoryType": story_type,
            "SegmentHistory": [],
            "SkillXPAwarded": {},
            "AttributeXPAwarded": {},
        }

        dynamo.put_item(TableName.STORY_HISTORY, history_entry)

        logger.info(f"Created story history entry with StoryInstanceID: {story_instance_id}")
        return story_instance_id

    except ClientError as err:
        logger.error(f"Failed to create history entry for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to create history entry: {err}") from err


def record_story_abandonment(character_id: str, story_instance_id: str) -> None:
    """
    Update history to record story abandonment.

    Args:
        character_id: Character UUID
        story_instance_id: Story instance UUID (UUIDv7)

    Raises:
        ValueError: If character_id or story_instance_id is empty
        RuntimeError: If database operations fail
    """
    if not character_id:
        raise ValueError("Character ID cannot be empty")
    if not story_instance_id:
        raise ValueError("Story instance ID cannot be empty")

    try:
        dynamo.update_item(
            TableName.STORY_HISTORY,
            Key={"CharacterID": character_id, "StoryInstanceID": story_instance_id},
            UpdateExpression="SET FinishedAt = :finished, FinalOutcome = :outcome",
            ExpressionAttributeValues={
                ":finished": now_iso(),
                ":outcome": "abandoned",
            },
        )
    except ClientError as err:
        logger.error(f"Failed to update story history for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to update story history: {err}") from err

    logger.info(f"Updated story history with abandonment for {character_id}")


def add_story_to_abandoned_list(character_id: str, story_id: str) -> None:
    """
    Add a story to the character's AbandonedStories list.

    Uses DynamoDB's ADD operation which automatically handles duplicates,
    ensuring each story ID appears only once in the set.

    Args:
        character_id: Character UUID
        story_id: Story UUID to add to abandoned list

    Raises:
        ValueError: If character_id or story_id is empty
        RuntimeError: If database update fails
    """
    if not character_id:
        raise ValueError("Character ID cannot be empty")
    if not story_id:
        raise ValueError("Story ID cannot be empty")

    try:
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="ADD AbandonedStories :story",
            ExpressionAttributeValues={":story": {story_id}},
        )
    except ClientError as err:
        logger.error(f"Failed to add story to abandoned list for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to add story to abandoned list: {err}") from err

    logger.info(f"Added story to abandoned list for {character_id}")


def add_segment_to_history(character_id: str, story_instance_id: str, segment_id: str, outcome: str) -> None:
    """
    Add a completed segment to the story history.

    Args:
        character_id: Character UUID
        story_instance_id: Story instance UUID
        segment_id: Segment UUID
        outcome: Segment outcome

    Raises:
        RuntimeError: If database operations fail
    """
    try:
        segment_entry = {
            "SegmentID": segment_id,
            "CompletedAt": now_iso(),
            "Outcome": outcome,
        }

        dynamo.update_item(
            TableName.STORY_HISTORY,
            Key={"CharacterID": character_id, "StoryInstanceID": story_instance_id},
            UpdateExpression="SET SegmentHistory = list_append(SegmentHistory, :segment)",
            ExpressionAttributeValues={
                ":segment": [segment_entry],
            },
        )

        logger.info(f"Added segment to history for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to add segment to history for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to add segment to history: {err}") from err


def update_story_history_xp(character_id: str, story_instance_id: str, skill_xp: dict, attribute_xp: dict) -> None:
    """
    Update the story history with accumulated XP from this segment.

    Args:
        character_id: Character UUID
        story_instance_id: Story instance UUID
        skill_xp: Skill XP awarded in this segment
        attribute_xp: Attribute XP awarded in this segment

    Raises:
        RuntimeError: If database operation fails
    """
    if not skill_xp and not attribute_xp:
        return

    try:
        update_expressions = []
        expression_names = {}
        expression_values = {":zero": Decimal("0")}

        for skill, xp_value in skill_xp.items():
            if xp_value > 0:
                safe_skill = skill.replace("-", "_").replace(" ", "_")
                update_expressions.append(
                    f"SkillXPAwarded.#skill_{safe_skill} = if_not_exists(SkillXPAwarded.#skill_{safe_skill}, :zero) + :xp_{safe_skill}"
                )
                expression_names[f"#skill_{safe_skill}"] = skill
                expression_values[f":xp_{safe_skill}"] = Decimal(str(xp_value))

        for attribute, xp_value in attribute_xp.items():
            if xp_value > 0:
                safe_attr = attribute.replace("-", "_").replace(" ", "_")
                update_expressions.append(
                    f"AttributeXPAwarded.#attr_{safe_attr} = if_not_exists(AttributeXPAwarded.#attr_{safe_attr}, :zero) + :xp_attr_{safe_attr}"
                )
                expression_names[f"#attr_{safe_attr}"] = attribute
                expression_values[f":xp_attr_{safe_attr}"] = Decimal(str(xp_value))

        if not update_expressions:
            return

        update_expression = "SET " + ", ".join(update_expressions)

        update_kwargs = {
            "Key": {"CharacterID": character_id, "StoryInstanceID": story_instance_id},
            "UpdateExpression": update_expression,
            "ExpressionAttributeValues": expression_values,
        }
        if expression_names:
            update_kwargs["ExpressionAttributeNames"] = expression_names

        dynamo.update_item(TableName.STORY_HISTORY, **update_kwargs)

        logger.info(f"Updated story history with XP for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to update story history XP for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to update story history XP: {err}") from err
