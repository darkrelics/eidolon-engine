"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to get a character for the incremental game.
Returns the full character data including active segments if any.
"""

from eidolon.character_data import character_get
from eidolon.character_story import get_active_story_and_segment, get_stories_with_character
from eidolon.cognito import extract_player_id
from eidolon.cors import cors_handler
from eidolon.dynamo import decimal_to_float
from eidolon.items import get_inventory
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import validate_player
from eidolon.requests import get_query_parameter
from eidolon.responses import lambda_error, lambda_response
from eidolon.story_retrieval import enrich_segment_with_narrative


def get_character_logic(character_id: str, player_id: str) -> dict:
    """
    Business logic for getting character data.

    Args:
        character_id: Character UUID from query parameter
        player_id: Authenticated player ID

    Returns:
        Dict containing:
            - success: bool
            - data: dict (if success)
            - error: str (if failed)
            - status_code: int (if failed)
    """

    # Get character and validate ownership
    try:
        character: dict = character_get(character_id, player_id)
    except ValueError as err:
        error_msg = str(err).lower()
        if "not found" in error_msg:
            return {"success": False, "error": "Character not found", "status_code": 404}
        elif "not owned" in error_msg:
            return {"success": False, "error": "Access denied", "status_code": 403}
        return {"success": False, "error": str(err), "status_code": 400}
    except RuntimeError as err:
        logger.error(f"Failed to get character: {err}")
        return {"success": False, "error": "Failed to retrieve character data", "status_code": 500}

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

    # Build response data with PascalCase keys
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

    return {"success": True, "data": response_data}


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler for getting incremental character data.

    Args:
        event: API Gateway Lambda proxy event
        context: Lambda context

    Returns:
        API Gateway Lambda proxy response
    """
    # Log invocation
    log_lambda_statistics(event, context)

    # Handle preflight
    preflight_response: dict = cors_handler.handle_preflight(event)
    if preflight_response:
        return preflight_response

    # Extract player ID from JWT
    try:
        player_id: str = extract_player_id(event)
    except ValueError as err:
        logger.warning(f"Authentication failed: {err}", exc_info=False)
        return lambda_response(401, {"Error": "Unauthorized"}, event)
    except Exception as err:
        logger.error(f"Failed to extract player ID: {err}", exc_info=True)
        return lambda_error(event, err)

    # Validate player exists
    try:
        if not validate_player(player_id):
            logger.error(f"Player: {player_id} not found in database")
            return lambda_response(401, {"Error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error(f"Failed to validate player: {err}", exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)

    # Get character ID from query parameters
    character_id = get_query_parameter(event, "CharacterID")

    if not character_id:
        return lambda_response(400, {"Error": "Missing CharacterID parameter"}, event)

    # Call business logic
    try:
        result: dict = get_character_logic(character_id, player_id)

        if result.get("success"):
            character_name = result.get("data", {}).get("CharacterName", "unknown")
            logger.info(f"Retrieved character '{character_name}' ({character_id}) for player {player_id}")
            return lambda_response(200, result.get("data", {}), event)
        else:
            # Log the error if it's a server error
            status_code = result.get("status_code", 500)
            return lambda_response(status_code, {"Error": result.get("error", "Unknown error")}, event)
    except Exception as err:
        return lambda_error(event, err)
