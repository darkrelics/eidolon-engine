"""
Eidolon Engine - Incremental Game

Copyright 2024-2026 Jason E. Robinson

Lambda function to purchase items from the store.
Handles atomic currency deduction and inventory updates.

Endpoint: POST /store/purchase
Authentication: Cognito (required)
"""

from eidolon.character_data import character_get
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
        raise ValueError("401:Unauthorized")

    # Parse request body
    body = parse_event_body(event)
    character_id = body.get("CharacterID", "")
    prototype_id = body.get("PrototypeID", "")
    quantity = body.get("Quantity", 1)

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

    # Verify character ownership
    try:
        character_get(character_id, player_id)
    except ValueError as err:
        logger.warning(f"Character access denied: {err}")
        raise ValueError(f"403:{err}") from err

    # Attempt purchase
    try:
        result = purchase_item(character_id, prototype_id, quantity)
        logger.info(
            f"Purchase successful: {quantity}x {prototype_id} " f"for character {character_id} (cost: {result['total_cost']})"
        )

        # Return purchase results
        return {
            "status_code": 200,
            "body": {
                "Success": True,
                "ItemIDs": result["item_ids"],
                "Quantity": result["quantity"],
                "TotalCost": result["total_cost"],
                "CurrencyRemaining": result["currency_remaining"],
                "Message": f"Successfully purchased {result['quantity']} item(s)",
            },
        }
    except ValueError as err:
        # Business logic errors (insufficient funds, out of stock, etc.)
        error_msg = str(err)

        # Map specific errors to appropriate HTTP status codes
        if "insufficient funds" in error_msg.lower():
            raise ValueError(f"402:{error_msg}") from err  # 402 Payment Required
        elif "not available" in error_msg.lower() or "not found" in error_msg.lower():
            raise ValueError(f"404:{error_msg}") from err
        elif "insufficient stock" in error_msg.lower():
            raise ValueError(f"409:{error_msg}") from err  # 409 Conflict
        else:
            raise ValueError(f"400:{error_msg}") from err
