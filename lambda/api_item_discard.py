"""
Eidolon Engine - Incremental Game

Copyright 2024-2026 Jason E. Robinson

Lambda function to discard (delete) items from character inventory.
Removes items permanently without applying any effects.

Endpoint: POST /item/discard
Authentication: Cognito (required)
"""

from botocore.exceptions import ClientError

from eidolon.character_data import character_get
from eidolon.dynamo import TableName, dynamo
from eidolon.items import get_item_brief
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.player import validate_player
from eidolon.requests import parse_event_body
from eidolon.validation import validate_uuid


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """
    Lambda handler for discarding items from inventory.

    Request Body:
        {
            "CharacterID": "uuid",
            "ItemID": "uuid",
            "InventorySlot": "1" (optional - for faster lookup),
            "Quantity": 1 (optional - for stackable items, defaults to all)
        }

    Args:
        event: API Gateway Lambda proxy event
        context: Lambda context
        player_id: Authenticated player ID

    Returns:
        Dict with status_code and body containing discard results
    """
    # Validate player exists
    if not validate_player(player_id):
        logger.error(f"Player {player_id} not found in database")
        raise ValueError("401:Unauthorized")

    # Parse request body
    body = parse_event_body(event)
    character_id = body.get("CharacterID", "")
    item_id = body.get("ItemID", "")
    inventory_slot = body.get("InventorySlot")
    quantity_to_discard = body.get("Quantity")

    # Validate required parameters
    if not character_id:
        raise ValueError("CharacterID is required")

    if not item_id:
        raise ValueError("ItemID is required")

    # Validate UUIDs
    if not validate_uuid(character_id):
        raise ValueError("Invalid CharacterID format")

    if not validate_uuid(item_id):
        raise ValueError("Invalid ItemID format")

    # Validate quantity if provided
    if quantity_to_discard is not None:
        try:
            quantity_to_discard = int(quantity_to_discard)
            if quantity_to_discard < 1:
                raise ValueError("Quantity must be at least 1")
        except (TypeError, ValueError) as err:
            raise ValueError("Invalid Quantity value") from err

    # Get character and verify ownership
    try:
        character = character_get(character_id, player_id)
    except ValueError as err:
        logger.warning(f"Character access denied: {err}")
        raise ValueError(f"403:{err}") from err

    # Find item in inventory
    inventory = character.get("Inventory", {})
    found_slot = None
    item_quantity = None

    if inventory_slot and inventory_slot in inventory:
        # Quick lookup using provided slot
        slot_data = inventory[inventory_slot]
        if slot_data.get("ItemID") == item_id:
            found_slot = inventory_slot
            item_quantity = slot_data.get("Quantity", 1)

    if not found_slot:
        # Search all slots
        for slot, slot_data in inventory.items():
            if slot_data.get("ItemID") == item_id:
                found_slot = slot
                item_quantity = slot_data.get("Quantity", 1)
                break

    if not found_slot:
        raise ValueError("404:Item not found in character inventory")

    # Get item brief for logging and response
    try:
        item_brief = get_item_brief(item_id)
        prototype_id = item_brief.get("PrototypeID")
    except ValueError as err:
        logger.warning(f"Item brief not found for {item_id}, continuing with discard: {err}")
        prototype_id = "unknown"

    # Determine how much to discard
    if quantity_to_discard is None:
        # Discard entire stack
        quantity_to_discard = item_quantity
    else:
        # Discard specified quantity (up to available)
        quantity_to_discard = min(quantity_to_discard, item_quantity)

    # Update inventory: decrement quantity or remove item entirely
    try:
        current_inventory = inventory.copy()
        item_fully_discarded = False

        if quantity_to_discard >= item_quantity:
            # Remove item entirely
            del current_inventory[found_slot]
            logger.info(f"Removed item {item_id} from inventory slot {found_slot}")
            item_fully_discarded = True
        else:
            # Decrement quantity
            current_inventory[found_slot]["Quantity"] = item_quantity - quantity_to_discard
            logger.info(f"Decremented item {item_id} quantity: {item_quantity} -> " f"{item_quantity - quantity_to_discard}")
            item_fully_discarded = False

        # ✅ FIX BUG #3: Use conditional update to prevent race conditions
        # Ensures item still exists in the expected slot with expected ID
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET Inventory = :inventory",
            ConditionExpression="Inventory.#slot.ItemID = :expected_item_id",
            ExpressionAttributeNames={
                "#slot": found_slot,
            },
            ExpressionAttributeValues={
                ":inventory": current_inventory,
                ":expected_item_id": item_id,
            },
        )

    except ClientError as err:
        # Check if this was a conditional check failure (item already removed = race condition)
        if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.warning(f"Discard failed: item {item_id} already removed (race condition detected)")
            raise ValueError("409:Item has already been discarded. Please refresh your inventory.") from err

        logger.error(f"Failed to update inventory for {character_id}: {err}")
        raise RuntimeError("Failed to discard item") from err

    # Build response
    response_body = {
        "Success": True,
        "ItemDiscarded": {
            "ItemID": item_id,
            "PrototypeID": prototype_id,
        },
        "QuantityDiscarded": quantity_to_discard,
        "ItemFullyDiscarded": item_fully_discarded,
    }

    # Add remaining quantity if item not fully discarded
    if not item_fully_discarded:
        response_body["RemainingQuantity"] = item_quantity - quantity_to_discard

    logger.info(f"Item {item_id} discarded by character {character_id}: " f"{quantity_to_discard} of {item_quantity}")

    return {"status_code": 200, "body": response_body}
