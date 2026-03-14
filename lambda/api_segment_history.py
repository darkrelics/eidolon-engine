"""
Eidolon Engine - Incremental Game

Copyright 2024-2026 Jason E. Robinson

Lambda function to retrieve segment history for a character.
Returns completed segment results from the character's story history.

Endpoint: GET /segment/history
Authentication: Cognito (required)
"""

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.player import verify_character_ownership
from eidolon.requests import get_query_parameter
from eidolon.time_utils import from_unix, now_iso
from eidolon.validation import validate_uuid

EMPTY_HISTORY = {"StoryID": None, "Segments": []}


def get_story_context_from_active_segment(character_id: str) -> dict:
    """Look up story context from the active segment.

    Args:
        character_id: Character UUID

    Returns:
        Dict with story_id, story_instance_id, story_title, active_segment_id.
        All values are None if no active segment exists.

    Raises:
        RuntimeError: If database query fails
    """
    try:
        active_segments = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="CharacterID-index",
            KeyConditionExpression="CharacterID = :cid",
            FilterExpression="#status = :status",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={":cid": character_id, ":status": "active"},
        )
    except ClientError as err:
        logger.error(f"Failed to query active segment for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to query active segment: {err}") from err

    active_segment = active_segments[0] if active_segments else None
    if not active_segment:
        return {"story_id": None, "story_instance_id": None, "story_title": None, "active_segment_id": None}

    story_id = active_segment.get("StoryID")
    story_title = "Unknown Story"

    if story_id:
        try:
            story = dynamo.get_item(TableName.STORY, {"StoryID": story_id})
            if story:
                story_title = story.get("Title", "Unknown Story")
        except ClientError as err:
            logger.warning(f"Could not fetch story title for {story_id}: {err}")

    return {
        "story_id": story_id,
        "story_instance_id": active_segment.get("StoryInstanceID"),
        "story_title": story_title,
        "active_segment_id": active_segment.get("ActiveSegmentID"),
    }


def get_story_context_from_history(character_id: str) -> dict:
    """Fall back to story history when no active segment exists.

    Args:
        character_id: Character UUID

    Returns:
        Dict with story_id, story_instance_id, story_title, active_segment_id (always None).
        story_id is None if no history exists.

    Raises:
        ValueError: If character not found
        RuntimeError: If database operations fail
    """
    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
        if not character:
            raise ValueError("404:Character not found")
    except ClientError as err:
        logger.error(f"Failed to get character data: {err}")
        raise RuntimeError(f"Failed to load character: {err}") from err

    preferred_story_id = character.get("ActiveStoryID")

    try:
        history_query_values = {":cid": character_id}
        history_kwargs = {
            "KeyConditionExpression": "CharacterID = :cid",
            "ExpressionAttributeValues": history_query_values,
            "ScanIndexForward": False,
        }

        if preferred_story_id:
            history_kwargs["FilterExpression"] = "StoryID = :sid"
            history_query_values[":sid"] = preferred_story_id

        story_histories = dynamo.query(TableName.STORY_HISTORY, **history_kwargs)

        if not story_histories and preferred_story_id:
            # Retry without filter to get the most recent story if filter returned nothing
            history_kwargs.pop("FilterExpression", None)
            story_histories = dynamo.query(TableName.STORY_HISTORY, **history_kwargs)

        if not story_histories:
            return {"story_id": None, "story_instance_id": None, "story_title": None, "active_segment_id": None}

        latest_story = story_histories[0]
        return {
            "story_id": latest_story.get("StoryID"),
            "story_instance_id": latest_story.get("StoryInstanceID"),
            "story_title": latest_story.get("StoryTitle", "Unknown Story"),
            "active_segment_id": None,
        }
    except ClientError as err:
        logger.error(f"Failed to query story history for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to query story history: {err}") from err


def query_segment_history(character_id: str, story_id: str, story_instance_id: str) -> list:
    """Query completed segments from the SegmentHistory table.

    Args:
        character_id: Character UUID
        story_id: Story UUID (optional filter)
        story_instance_id: Story instance UUID (optional filter)

    Returns:
        List of segment dicts from DynamoDB

    Raises:
        RuntimeError: If database query fails
    """
    try:
        expr_values = {":cid": character_id}
        query_kwargs = {
            "KeyConditionExpression": "CharacterID = :cid",
            "ExpressionAttributeValues": expr_values,
        }

        filter_parts = []
        if story_id:
            filter_parts.append("StoryID = :sid")
            expr_values[":sid"] = story_id
        if story_instance_id:
            filter_parts.append("StoryInstanceID = :siid")
            expr_values[":siid"] = story_instance_id
        if filter_parts:
            query_kwargs["FilterExpression"] = " AND ".join(filter_parts)

        results: list = dynamo.query(TableName.SEGMENT_HISTORY, **query_kwargs) or []
        return results
    except ClientError as err:
        logger.error(f"Failed to query segment history for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to query segment history: {err}") from err


def format_segment(segment: dict, story_title: str) -> dict:
    """Format a single segment record for the API response.

    Args:
        segment: Raw segment dict from DynamoDB
        story_title: Story title to include in each segment

    Returns:
        Formatted segment dict with ISO timestamps and enriched data
    """
    start_time_unix = segment.get("StartTime", 0)
    end_time_unix = segment.get("EndTime", 0)
    completed_at_unix = segment.get("CompletedAt", 0)

    formatted = {
        "ActiveSegmentID": segment.get("ActiveSegmentID"),
        "SegmentID": segment.get("SegmentID"),
        "SegmentType": segment.get("SegmentType"),
        "SegmentTitle": segment.get("SegmentTitle"),
        "SegmentActivity": segment.get("SegmentActivity"),
        "StartTime": from_unix(start_time_unix) if start_time_unix else None,
        "EndTime": from_unix(end_time_unix) if end_time_unix else None,
        "StoryTitle": story_title,
        "CompletedAt": from_unix(completed_at_unix) if completed_at_unix else None,
    }

    # Add optional enriched data that Flutter needs
    for key in ("Outcome", "ClientEvents", "Decision", "ChallengeResults", "CombatState", "StoryInstanceID"):
        value = segment.get(key)
        if value:
            formatted[key] = value

    char_updates = segment.get("CharacterUpdates")
    if char_updates:
        formatted["CharacterUpdates"] = char_updates
        skills_awarded = char_updates.get("SkillsAwarded")
        if skills_awarded:
            formatted["SkillXPAwarded"] = skills_awarded
        attrs_awarded = char_updates.get("AttributesAwarded")
        if attrs_awarded:
            formatted["AttributeXPAwarded"] = attrs_awarded

    return formatted


def get_segment_history(character_id: str, player_id: str) -> dict:
    """Business logic for retrieving segment history.

    Args:
        character_id: Character UUID
        player_id: Authenticated player ID

    Returns:
        Response data dict with segment history

    Raises:
        ValueError: If character not found or not owned
        RuntimeError: If database operations fail
    """
    if not verify_character_ownership(character_id, player_id):
        raise ValueError("403:Access denied")

    # Try active segment first, fall back to story history
    context = get_story_context_from_active_segment(character_id)
    source = "active_segment"

    if not context.get("story_id"):
        logger.info(f"No active segment found for character={character_id}, loading latest story history")
        context = get_story_context_from_history(character_id)
        source = "story_history"

    story_id: str = context.get("story_id", "")
    story_instance_id: str = context.get("story_instance_id", "")
    story_title = context.get("story_title", "Unknown Story")
    active_segment_id = context.get("active_segment_id")

    if not story_id and not story_instance_id:
        logger.info(f"No story context available for character={character_id}, returning empty history")
        return {**EMPTY_HISTORY, "CharacterID": character_id}

    # Query and format segment history
    segments = query_segment_history(character_id, story_id, story_instance_id)

    formatted_segments = []
    for segment in segments or []:
        if active_segment_id and segment.get("ActiveSegmentID") == active_segment_id:
            continue
        formatted_segments.append(format_segment(segment, story_title))

    # Sort by completion time descending; capture fallback once for consistency
    sort_fallback = now_iso()
    formatted_segments.sort(key=lambda x: x.get("CompletedAt") or sort_fallback, reverse=True)

    segment_count = len(formatted_segments)
    logger.info(
        f"Segment history for character={character_id}: "
        f"StoryID={story_id}, StoryInstanceID={story_instance_id}, "
        f"SegmentCount={segment_count}, Source={source}"
    )

    return {"CharacterID": character_id, "StoryID": story_id, "Segments": formatted_segments}


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """Get segment history for a character.

    Query Parameters:
        CharacterID: Character ID to get history for

    Returns:
        Dict with status_code and body
    """
    character_id = get_query_parameter(event, "CharacterID")
    if not character_id:
        raise ValueError("Missing CharacterID parameter")

    if not validate_uuid(character_id):
        raise ValueError("Invalid CharacterID format")

    logger.info(f"Retrieving segment history for character={character_id}")

    response_data = get_segment_history(character_id, player_id)
    return {"status_code": 200, "body": response_data}
