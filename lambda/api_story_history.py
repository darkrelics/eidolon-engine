"""
Eidolon Engine - Incremental Game

Copyright 2024-2026 Jason E. Robinson

Lambda function to retrieve story history entries for a character.
Accepts up to 10 story instance IDs (UUIDv7) provided by the client and
returns the corresponding story history records if the character owns them.

Endpoint: GET /story/history
Authentication: Cognito (required)
"""

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.errors import AccessDeniedError
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.player import verify_character_ownership
from eidolon.requests import get_query_parameter
from eidolon.validation import validate_uuid

MAX_HISTORY_IDS = 10


def extract_story_instance_ids(event: dict) -> list:
    """Extract up to MAX_HISTORY_IDS story instance IDs from the query string."""
    query_value = get_query_parameter(event, "StoryInstanceIDs")
    if not query_value:
        return []

    seen = set()
    ordered = []
    for part in query_value.split(","):
        candidate = part.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        ordered.append(candidate)
        if len(ordered) >= MAX_HISTORY_IDS:
            break
    return ordered


def get_story_history_entries(character_id: str, story_instance_ids: list) -> dict:
    """Business logic for fetching story history entries for a character."""

    if not character_id:
        raise ValueError("CharacterID is required")

    if not story_instance_ids:
        return {"CharacterID": character_id, "Stories": [], "Missing": []}

    keys = [{"CharacterID": character_id, "StoryInstanceID": story_instance_id} for story_instance_id in story_instance_ids]

    try:
        items = dynamo.batch_get_items(TableName.STORY_HISTORY, keys)
    except ClientError as err:
        logger.error(
            f"Failed to batch get story history for {character_id} Error: {err}",
            exc_info=True,
        )
        raise RuntimeError(f"Failed to retrieve story history: {err}") from err

    stories_by_instance = {item.get("StoryInstanceID"): item for item in items if item.get("StoryInstanceID")}  # type: ignore

    ordered_results = []
    missing = []
    for instance_id in story_instance_ids:
        story = stories_by_instance.get(instance_id)
        if story:
            ordered_results.append(story)
        else:
            missing.append(instance_id)

    return {
        "CharacterID": character_id,
        "Stories": ordered_results,
        "Missing": missing,
    }


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """Lambda handler for GET /story/history."""

    character_id = get_query_parameter(event, "CharacterID")
    if not character_id:
        raise ValueError("Missing CharacterID")

    if not validate_uuid(character_id):
        raise ValueError("Invalid CharacterID")

    story_instance_ids = extract_story_instance_ids(event)

    if not story_instance_ids:
        logger.info(f"No StoryInstanceIDs provided in request for {character_id}")
        return {
            "status_code": 200,
            "body": {"CharacterID": character_id, "Stories": [], "Missing": []},
        }

    if not verify_character_ownership(character_id, player_id):
        raise AccessDeniedError("Access denied")

    # Validate UUID format for each requested story instance
    invalid_ids = [sid for sid in story_instance_ids if not validate_uuid(sid)]
    if invalid_ids:
        raise ValueError(f"Invalid StoryInstanceID values: {', '.join(invalid_ids)}")

    result = get_story_history_entries(character_id, story_instance_ids)
    return {"status_code": 200, "body": result}
