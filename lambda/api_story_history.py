"""
Eidolon Engine - Incremental Game

Lambda function to retrieve story history entries for a character.
Accepts up to 10 story instance IDs (UUIDv7) provided by the client and
returns the corresponding story history records if the character owns them.
"""

from typing import Iterable, List

from botocore.exceptions import ClientError

from eidolon.cognito import extract_player_id
from eidolon.cors import cors_handler
from eidolon.dynamo import TableName, dynamo
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import verify_character_ownership
from eidolon.requests import get_query_parameter, parse_event_body
from eidolon.responses import lambda_error, lambda_response
from eidolon.validation import validate_uuid

MAX_HISTORY_IDS = 10


def _extract_story_instance_ids(event: dict) -> List[str]:
    """Extract up to MAX_HISTORY_IDS story instance IDs from the request."""

    def _clean(ids: Iterable[str]) -> List[str]:
        seen = set()
        ordered: List[str] = []
        for raw in ids:
            candidate = (raw or "").strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            ordered.append(candidate)
            if len(ordered) >= MAX_HISTORY_IDS:
                break
        return ordered

    # Try query string first (comma-separated list)
    query_value = get_query_parameter(event, "StoryInstanceIDs")
    if query_value:
        return _clean(part.strip() for part in query_value.split(","))

    # Fall back to request body JSON
    try:
        body = parse_event_body(event)
    except ValueError:
        body = None

    if isinstance(body, dict):
        raw_ids = body.get("StoryInstanceIDs") or body.get("storyInstanceIds")
        if isinstance(raw_ids, list):
            return _clean(str(item) for item in raw_ids)
        if isinstance(raw_ids, str):
            return _clean(part.strip() for part in raw_ids.split(","))

    return []


def get_story_history_entries(character_id: str, story_instance_ids: List[str]) -> dict:
    """Business logic for fetching story history entries for a character."""

    if not character_id:
        raise ValueError("CharacterID is required")

    if not story_instance_ids:
        return {"CharacterID": character_id, "Stories": [], "Missing": []}

    keys = [
        {"CharacterID": character_id, "StoryInstanceID": story_instance_id}
        for story_instance_id in story_instance_ids
    ]

    try:
        items = dynamo.batch_get_items(TableName.STORY_HISTORY, keys)
    except ClientError as err:
        logger.error(
            f"Failed to batch get story history for {character_id} Error: {err}",
            exc_info=True,
        )
        raise RuntimeError(f"Failed to retrieve story history: {err}") from err

    stories_by_instance = {
        item.get("StoryInstanceID"): item for item in items if item.get("StoryInstanceID")
    }

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


def lambda_handler(event: dict, context: object) -> dict:
    """Lambda handler for GET /story/history."""
    log_lambda_statistics(event, context)

    preflight_response = cors_handler.handle_preflight(event)
    if preflight_response:
        return preflight_response

    try:
        player_id = extract_player_id(event)
    except ValueError as err:
        logger.warning(f"Authentication failed: {err}", exc_info=False)
        return lambda_response(401, {"Error": "Unauthorized"}, event)
    except Exception as err:
        return lambda_error(event, err)

    character_id = get_query_parameter(event, "CharacterID")
    if not character_id:
        # Allow body-based CharacterID for flexibility
        try:
            body = parse_event_body(event)
        except ValueError:
            body = None
        if isinstance(body, dict):
            character_id = body.get("CharacterID") or body.get("characterId")

    if not character_id:
        return lambda_response(400, {"Error": "Missing CharacterID"}, event)

    if not validate_uuid(character_id):
        return lambda_response(400, {"Error": "Invalid CharacterID"}, event)

    story_instance_ids = _extract_story_instance_ids(event)

    if not story_instance_ids:
        logger.info(f"No StoryInstanceIDs provided in request for {character_id}")
        return lambda_response(
            200,
            {"CharacterID": character_id, "Stories": [], "Missing": []},
            event,
        )

    if not verify_character_ownership(character_id, player_id):
        return lambda_response(403, {"Error": "Access denied"}, event)

    # Validate UUID format for each requested story instance
    invalid_ids = [sid for sid in story_instance_ids if not validate_uuid(sid)]
    if invalid_ids:
        return lambda_response(
            400,
            {"Error": "Invalid StoryInstanceID values", "Invalid": invalid_ids},
            event,
        )

    try:
        result = get_story_history_entries(character_id, story_instance_ids)
        return lambda_response(200, result, event)
    except ValueError as err:
        return lambda_response(400, {"Error": str(err)}, event)
    except RuntimeError as err:
        logger.error(f"Failed to retrieve story history for {character_id} Error: {err}", exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)

