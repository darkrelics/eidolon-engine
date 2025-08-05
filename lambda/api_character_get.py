"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to get a character for the incremental game.
Returns the full character data including active segments if any.
"""

from eidolon.character import character_get_active_segment, character_get, character_get_active_story
from eidolon.cors import cors_handler
from eidolon.dynamo import decimal_to_float
from eidolon.items import get_inventory
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import extract_player_id, validate_player
from eidolon.responses import lambda_error, lambda_response


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
        if "not found" in str(err).lower():
            return {"success": False, "error": "Character not found", "status_code": 404}
        return {"success": False, "error": str(err), "status_code": 400}
    except RuntimeError as err:
        logger.error("Failed to get character", extra={"error": str(err), "character_id": character_id})
        return {"success": False, "error": "Failed to retrieve character data", "status_code": 500}

    # Check for active segment
    active_story: dict = {}
    active_segment: dict = {}
    try:
        active_story = character_get_active_story(character)
        if active_story:
            logger.info("Active story found for character")
        else:
            logger.info("No active story found for character")
            character["ActiveStoryID"] = None
            character["ActiveSegmentID"] = None
    except RuntimeError as err:
        logger.error("Error retrieving active story")

    if active_story:
        
        try:
            active_segment = character_get_active_segment(character)
            if active_segment:
                logger.info("Active segment found for character")
        except RuntimeError as err:
            logger.error("Error retrieving active segments")
            # Continue without active segment data - not critical for response

        if active_segment:
            character["ActiveSegmentID"] = active_segment.get("ActiveSegmentID")
        else:
            character["ActiveStoryID"] = None
            active_story = {}
            character["ActiveSegmentID"] = None
    # Note: Attributes and skills maintain their original casing from the database
    # The Flutter client handles any casing differences flexibly

    # Enrich inventory with item details
    inventory = character.get("Inventory")
    if inventory:
        character["InventoryDetails"] = get_inventory(inventory)

    # Build response data with PascalCase keys
    response_data = {"Character": decimal_to_float(character)}

    # Add story if found
    if active_story:
        response_data["ActiveStory"] = decimal_to_float(active_story)
    if active_segment:
        response_data["ActiveSegment"] = decimal_to_float(active_segment)

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

    # Get character ID from query parameters (flexible: CharacterID or characterId)
    character_id: str = event.get("queryStringParameters", {}).get("CharacterID") or event.get("queryStringParameters", {}).get(
        "characterId"
    )

    if not character_id:
        return lambda_response(400, {"Error": "Missing CharacterID parameter"}, event)

    # Call business logic
    try:
        result: dict = get_character_logic(character_id, player_id)

        if result.get("success"):
            logger.info("Lambda response", extra={"status_code": 200})
            return lambda_response(200, result.get("data", {}), event)
        else:
            # Log the error if it's a server error
            status_code = result.get("status_code", 500)
            return lambda_response(status_code, {"Error": result.get("error", "Unknown error")}, event)
    except Exception as err:
        return lambda_error(event, err)
