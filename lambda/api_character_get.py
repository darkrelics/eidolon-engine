"""
Eidolon Engine - Incremental Game

Copyright 2024-2026 Jason E. Robinson

Lambda function to get a character for the incremental game.
Returns the full character data including active segments if any.

Endpoint: GET /character/get
Authentication: Cognito (required)
"""

from eidolon.character_data import character_get, cleanup_expired_daily_stories
from eidolon.character_story import get_active_story_and_segment, get_stories_with_character
from eidolon.dynamo import decimal_to_float
from eidolon.items import get_inventory
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.player import validate_player
from eidolon.requests import get_query_parameter
from eidolon.story_retrieval import enrich_segment_with_narrative
from eidolon.validation import validate_uuid


def get_character_logic(character_id: str, player_id: str) -> dict:
    """
    Business logic for getting character data.

    Args:
        character_id: Character UUID from query parameter
        player_id: Authenticated player ID

    Returns:
        Dict containing character data, active story/segment, and available stories

    Raises:
        ValueError: With status code prefix for 400/403/404 errors
        RuntimeError: For system errors
    """
    # Get character and validate ownership
    character: dict = character_get(character_id, player_id)

    # Clean up expired daily stories (24+ hours old)
    try:
        character = cleanup_expired_daily_stories(character)
    except RuntimeError as err:
        logger.error(f"Failed to cleanup expired daily stories: {err}")
        # Continue - not critical, character data is still valid

    # Get active story and segment, handling broken story chains
    active_story, active_segment = get_active_story_and_segment(character)

    # Note: If broken chains were detected, get_active_story_and_segment already
    # cleared the fields in the database. The character dict may have stale values
    # but clients should use the presence of ActiveStory/ActiveSegment in the response
    # rather than these fields in the Character object.

    # Note: Attributes and skills maintain their original casing from the database
    # The Flutter client handles any casing differences flexibly

    # Enrich inventory with item details
    inventory = character.get("Inventory")
    if inventory:
        character["InventoryDetails"] = get_inventory(inventory)

    response_data: dict = {"Character": decimal_to_float(character)}

    # Add story if found (already converted by get_active_story_and_segment)
    if active_story:
        response_data["ActiveStory"] = active_story

    if active_segment:
        # active_segment already converted by get_active_story_and_segment
        if isinstance(active_segment, dict):
            segment_data = enrich_segment_with_narrative(active_segment, active_segment)
        else:
            segment_data = active_segment
        response_data["ActiveSegment"] = segment_data

    # If there isn't an active story the available stories will be provided.
    if not active_story:
        # Get available stories from character
        available_story_ids = character.get("AvailableStories", [])
        logger.info(f"Available stories for character for {character_id}")

        # Get story details with prerequisite and cooldown checking
        # Use the character we already loaded to avoid a duplicate DB read
        stories: list = get_stories_with_character(character, available_story_ids)

        # Sort stories by availability and title
        stories.sort(key=lambda s: (not s["Available"], s["Title"]))

        logger.debug(f"Stories retrieved successfully for {character_id}")

        response_data["AvailableStories"] = stories

    return response_data


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """
    Lambda handler for getting incremental character data.

    Args:
        event: API Gateway Lambda proxy event
        context: Lambda context
        player_id: Authenticated player ID

    Returns:
        Dict with status_code and body
    """
    # Validate player exists
    if not validate_player(player_id):
        logger.error(f"Player: {player_id} not found in database")
        raise ValueError("401:Unauthorized")

    # Get character ID from query parameters
    character_id = get_query_parameter(event, "CharacterID")

    if not character_id:
        raise ValueError("Missing CharacterID parameter")

    if not validate_uuid(character_id):
        raise ValueError("Invalid CharacterID format")

    # Call business logic
    result: dict = get_character_logic(character_id, player_id)
    character_name = result.get("Character", {}).get("CharacterName", "unknown")
    logger.info(f"Retrieved character '{character_name}' ({character_id}) for player {player_id}")

    return {"status_code": 200, "body": result}
