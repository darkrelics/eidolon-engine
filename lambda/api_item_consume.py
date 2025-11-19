"""
Eidolon Engine - Incremental Game

Lambda function to consume an inventory item for a character.
Validates ownership, applies consumable effects, and updates inventory.

Endpoint: POST /item/consume
Authentication: Cognito (required)
"""

from eidolon.character_data import character_get
from eidolon.cognito import extract_player_id
from eidolon.cors import cors_handler
from eidolon.items import consume_item
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import validate_player
from eidolon.requests import parse_event_body
from eidolon.responses import lambda_error, lambda_response
from eidolon.validation import validate_uuid


def lambda_handler(event: dict, context: object) -> dict:
    """
    Handle POST /item/consume requests.

    Args:
        event: API Gateway proxy event
        context: Lambda execution context

    Returns:
        API Gateway proxy response dict
    """
    log_lambda_statistics(event, context)

    preflight = cors_handler.handle_preflight(event)
    if preflight:
        return preflight

    try:
        player_id = extract_player_id(event)
    except ValueError as err:
        logger.warning(f"Authentication failed: {err}", exc_info=False)
        return lambda_response(401, {"Error": "Unauthorized"}, event)
    except Exception as err:
        logger.error(f"Failed to extract player ID: {err}", exc_info=True)
        return lambda_error(event, err)

    try:
        if not validate_player(player_id):
            logger.error(f"Player {player_id} not found")
            return lambda_response(401, {"Error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error(f"Failed to validate player {player_id}: {err}", exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)

    try:
        body = parse_event_body(event)
    except ValueError as err:
        logger.error(f"Failed to parse consume request body: {err}", exc_info=True)
        return lambda_response(400, {"Error": "Invalid request body"}, event)
    except Exception as err:
        return lambda_error(event, err)

    character_id = str(body.get("CharacterID", "")).strip()
    item_id = str(body.get("ItemID", "")).strip()

    if not character_id:
        return lambda_response(400, {"Error": "CharacterID is required"}, event)
    if not item_id:
        return lambda_response(400, {"Error": "ItemID is required"}, event)

    if not validate_uuid(character_id):
        return lambda_response(400, {"Error": "Invalid CharacterID format"}, event)
    if not validate_uuid(item_id):
        return lambda_response(400, {"Error": "Invalid ItemID format"}, event)

    try:
        character_get(character_id, player_id)
    except ValueError as err:
        message = str(err)
        normalized = message.lower()
        logger.warning(f"Character validation failed for consume request: {message}")
        if "not found" in normalized:
            return lambda_response(404, {"Error": "Character not found"}, event)
        if "not owned" in normalized:
            return lambda_response(403, {"Error": "Access denied"}, event)
        if "invalid character id format" in normalized:
            return lambda_response(400, {"Error": message}, event)
        return lambda_response(400, {"Error": message}, event)
    except RuntimeError as err:
        logger.error(f"Failed to validate character {character_id}: {err}", exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)

    try:
        result = consume_item(character_id, item_id)
    except ValueError as err:
        message = str(err)
        normalized = message.lower()
        logger.warning(f"Consume item failed for character {character_id} item {item_id}: {message}")
        if "active story" in normalized:
            return lambda_response(409, {"Error": message}, event)
        if "no effect" in normalized:
            return lambda_response(409, {"Error": message}, event)
        if "not found" in normalized or "not in character inventory" in normalized:
            return lambda_response(404, {"Error": message}, event)
        return lambda_response(400, {"Error": message}, event)
    except RuntimeError as err:
        logger.error(f"Internal error consuming item {item_id} for {character_id}: {err}", exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)

    logger.info(f"Item {item_id} consumed for character {character_id}")
    return lambda_response(200, result, event)
