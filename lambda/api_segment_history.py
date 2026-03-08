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


def get_segment_history_business_logic(character_id: str, player_id: str) -> dict:
    """
    Business logic for retrieving segment history.

    Args:
        character_id: Character UUID
        player_id: Authenticated player ID

    Returns:
        Response data dict with segment history

    Raises:
        ValueError: If character not found or not owned
        RuntimeError: If database operations fail
    """
    # Verify character ownership using player record
    if not verify_character_ownership(character_id, player_id):
        raise ValueError("403:Access denied")

    # Get current active segment to find StoryInstanceID
    # This is more efficient than fetching entire character
    try:
        active_segments = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="CharacterID-index",
            KeyConditionExpression="CharacterID = :cid",
            FilterExpression="#status = :status",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={
                ":cid": character_id,
                ":status": "active",
            },
            Limit=1,
        )
    except ClientError as err:
        logger.error(f"Failed to query active segment for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to query active segment: {err}") from err

    story_id = None
    story_instance_id = None
    story_title = "Unknown Story"
    active_segment = active_segments[0] if active_segments else None

    active_segment_id = None

    if active_segment:
        active_segment_id = active_segment.get("ActiveSegmentID")
        story_id = active_segment.get("StoryID")
        story_instance_id = active_segment.get("StoryInstanceID")

        if story_id:
            try:
                story = dynamo.get_item(TableName.STORY, {"StoryID": story_id})
                if story:
                    story_title = story.get("Title", "Unknown Story")
            except ClientError as err:
                logger.warning(f"Could not fetch story title for {story_id}: {err}")
    else:
        logger.info(f"No active segment found for character={character_id}, loading latest story history")

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
                logger.info(f"No story history entries found for character={character_id}, returning empty history")
                return {"CharacterID": character_id, "StoryID": None, "Segments": []}

            latest_story = story_histories[0]
            story_id = latest_story.get("StoryID")
            story_instance_id = latest_story.get("StoryInstanceID")
            story_title = latest_story.get("StoryTitle", story_title)
        except ClientError as err:
            logger.error(f"Failed to query story history for {character_id} Error: {err}", exc_info=True)
            raise RuntimeError(f"Failed to query story history: {err}") from err

    if not story_id and not story_instance_id:
        logger.info(f"No story context available for character={character_id}, returning empty history")
        return {"CharacterID": character_id, "StoryID": None, "Segments": []}

    # Query completed segments from SegmentHistory table, favouring StoryInstanceID when available
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

        segments = dynamo.query(TableName.SEGMENT_HISTORY, **query_kwargs)
    except ClientError as err:
        logger.error(
            f"Failed to query segment history for {character_id} Error: {err}",
            exc_info=True,
        )
        raise RuntimeError(f"Failed to query segment history: {err}") from err

    # Format segments for response with all the data Flutter expects
    formatted_segments: list = []
    for segment in segments or []:
        if active_segment_id and segment.get("ActiveSegmentID") == active_segment_id:
            continue

        # Convert Unix timestamps to ISO 8601 for API response
        start_time_unix = segment.get("StartTime", 0)
        end_time_unix = segment.get("EndTime", 0)
        completed_at_unix = segment.get("CompletedAt", 0)

        formatted_segment_dict = {
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

        # Add enriched data that Flutter needs
        if segment.get("Outcome"):
            formatted_segment_dict["Outcome"] = segment.get("Outcome")

        if segment.get("ClientEvents"):
            formatted_segment_dict["ClientEvents"] = segment.get("ClientEvents")

        if segment.get("CharacterUpdates"):
            formatted_segment_dict["CharacterUpdates"] = segment.get("CharacterUpdates")

            # Extract XP awards from CharacterUpdates for Flutter
            char_updates = segment.get("CharacterUpdates", {})
            if "SkillsAwarded" in char_updates:
                formatted_segment_dict["SkillXPAwarded"] = char_updates.get("SkillsAwarded")
            if "AttributesAwarded" in char_updates:
                formatted_segment_dict["AttributeXPAwarded"] = char_updates.get("AttributesAwarded")

        if segment.get("Decision"):
            formatted_segment_dict["Decision"] = segment.get("Decision")

        if segment.get("ChallengeResults"):
            formatted_segment_dict["ChallengeResults"] = segment.get("ChallengeResults")

        if segment.get("CombatState"):
            formatted_segment_dict["CombatState"] = segment.get("CombatState")

        # Add StoryInstanceID if available
        if segment.get("StoryInstanceID"):
            formatted_segment_dict["StoryInstanceID"] = segment.get("StoryInstanceID")

        formatted_segments.append(formatted_segment_dict)

    # Sort by completion time, descending (most recent first)
    # Use current time as default for missing timestamps to avoid mixed type comparison
    formatted_segments.sort(key=lambda x: x.get("CompletedAt") or now_iso(), reverse=True)

    response = {"CharacterID": character_id, "StoryID": story_id, "Segments": formatted_segments}

    # Log successful history retrieval with key details for observability
    segment_count = len(formatted_segments)
    source = "active_segment" if active_segment else "story_history"
    logger.info(
        f"Segment history for character={character_id}: "
        f"StoryID={story_id}, StoryInstanceID={story_instance_id}, "
        f"SegmentCount={segment_count}, Source={source}"
    )

    return response


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """
    Get segment history for a character.

    Lambda function to retrieve completed segment history for a character's
    active story. Used by clients to display past outcomes and decisions.

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

    response_data = get_segment_history_business_logic(character_id, player_id)
    return {"status_code": 200, "body": response_data}
