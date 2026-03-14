"""
Eidolon Engine - Incremental Game

Lambda function to consume an inventory item for a character.
Validates ownership, applies consumable effects, and updates inventory.

Endpoint: POST /item/consume
Authentication: Cognito (required)
"""

from eidolon.character_data import character_get
from eidolon.consumables import consume_item
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.player import validate_player
from eidolon.requests import parse_event_body
from eidolon.validation import validate_uuid


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """
    Handle POST /item/consume requests.

    Args:
        event: API Gateway proxy event
        context: Lambda execution context
        player_id: Authenticated player ID

    Returns:
        Dict with status_code and body
    """
    if not validate_player(player_id):
        logger.error(f"Player {player_id} not found")
        raise ValueError("401:Unauthorized")

    body = parse_event_body(event)

    character_id = str(body.get("CharacterID", "")).strip()
    item_id = str(body.get("ItemID", "")).strip()

    if not character_id:
        raise ValueError("CharacterID is required")
    if not item_id:
        raise ValueError("ItemID is required")

    if not validate_uuid(character_id):
        raise ValueError("Invalid CharacterID format")
    if not validate_uuid(item_id):
        raise ValueError("Invalid ItemID format")

    try:
        character_get(character_id, player_id)
    except ValueError as err:
        message = str(err)
        normalized = message.lower()
        logger.warning(f"Character validation failed for consume request: {message}")
        if "not found" in normalized:
            raise ValueError("404:Character not found") from err
        if "not owned" in normalized:
            raise ValueError("403:Access denied") from err
        raise err

    try:
        result = consume_item(character_id, item_id)
    except ValueError as err:
        message = str(err)
        normalized = message.lower()
        logger.warning(f"Consume item failed for character {character_id} item {item_id}: {message}")
        if "active story" in normalized or "no effect" in normalized or "already been consumed" in normalized:
            raise ValueError(f"409:{message}") from err
        if "not found" in normalized or "not in character inventory" in normalized:
            raise ValueError(f"404:{message}") from err
        raise err

    logger.info(f"Item {item_id} consumed for character {character_id}")
    return {"status_code": 200, "body": result}
