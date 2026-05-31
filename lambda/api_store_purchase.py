"""
Eidolon Engine - Incremental Game

Copyright 2024-2026 Jason E. Robinson

Lambda function to purchase items from the store.
Handles atomic currency deduction and inventory updates.

Endpoint: POST /store/purchase
Authentication: Cognito (required)
"""

from eidolon.character_data import character_get
from eidolon.errors import UnauthorizedError
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.player import validate_player
from eidolon.requests import parse_event_body
from eidolon.store import purchase_item
from eidolon.validation import validate_uuid


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """
    Lambda handler for purchasing store items.

    Request Body:
        {
            "CharacterID": "uuid",
            "PrototypeID": "uuid",
            "Quantity": 1 (optional, defaults to 1)
        }

    Args:
        event: API Gateway Lambda proxy event
        context: Lambda context
        player_id: Authenticated player ID

    Returns:
        Dict with status_code and body containing purchase results
    """
    # Validate player exists
    if not validate_player(player_id):
        logger.error(f"Player {player_id} not found in database")
        raise UnauthorizedError("Unauthorized")

    # Parse request body
    body = parse_event_body(event)
    character_id = body.get("CharacterID", "")
    prototype_id = body.get("PrototypeID", "")
    quantity = body.get("Quantity", 1)
    store_id = body.get("StoreID") or "general-store"

    # Validate required parameters
    if not character_id:
        raise ValueError("CharacterID is required")

    if not prototype_id:
        raise ValueError("PrototypeID is required")

    # Validate UUIDs
    if not validate_uuid(character_id):
        raise ValueError("Invalid CharacterID format")

    if not validate_uuid(prototype_id):
        raise ValueError("Invalid PrototypeID format")

    # Validate quantity
    if not isinstance(quantity, int) or quantity < 1:
        raise ValueError("Quantity must be a positive integer")

    if quantity > 99:
        raise ValueError("Quantity cannot exceed 99 per transaction")

    # Verify character ownership (character_get raises typed errors -> 404 / 403)
    character_get(character_id, player_id)

    # Attempt purchase (purchase_item raises typed errors mapped by the decorator:
    # PaymentRequired 402, NotFound 404, Conflict 409, Validation 400).
    result = purchase_item(character_id, prototype_id, quantity, store_id=store_id)
    total_cost = result.get("total_cost", 0)
    item_ids = result.get("item_ids", [])
    quantity_purchased = result.get("quantity", 0)
    currency_remaining = result.get("currency_remaining", 0)

    logger.info(f"Purchase successful: {quantity}x {prototype_id} for character {character_id} (cost: {total_cost})")

    # Return purchase results
    return {
        "status_code": 200,
        "body": {
            "Success": True,
            "ItemIDs": item_ids,
            "Quantity": quantity_purchased,
            "TotalCost": total_cost,
            "CurrencyRemaining": currency_remaining,
            "Message": f"Successfully purchased {quantity_purchased} item(s)",
        },
    }
