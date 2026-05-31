"""
Eidolon Engine - Incremental Game

Copyright 2024-2026 Jason E. Robinson

Lambda function to equip a wearable item into a character equipment slot.

Endpoint: POST /item/equip
Authentication: Cognito (required)
"""

from eidolon.character_data import character_get
from eidolon.equipment import equip_item
from eidolon.errors import UnauthorizedError
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.player import validate_player
from eidolon.requests import parse_event_body
from eidolon.validation import validate_uuid


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """Lambda handler for equipping an item into a slot.

    Request Body:
        {
            "CharacterID": "uuid",
            "ItemID": "uuid",
            "Slot": "weapon"   (a slot listed in the prototype's WornOn)
        }
    """
    if not validate_player(player_id):
        logger.error(f"Player {player_id} not found in database")
        raise UnauthorizedError("Unauthorized")

    body = parse_event_body(event)
    character_id = body.get("CharacterID", "")
    item_id = body.get("ItemID", "")
    slot = body.get("Slot", "")

    if not character_id:
        raise ValueError("CharacterID is required")
    if not item_id:
        raise ValueError("ItemID is required")
    if not slot or not isinstance(slot, str):
        raise ValueError("Slot is required")
    if not validate_uuid(character_id):
        raise ValueError("Invalid CharacterID format")
    if not validate_uuid(item_id):
        raise ValueError("Invalid ItemID format")

    # character_get verifies ownership and raises typed errors (404 / 403).
    character = character_get(character_id, player_id)

    result = equip_item(character, item_id, slot)
    return {"status_code": 200, "body": result}
