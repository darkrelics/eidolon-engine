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
from eidolon.story_rewards import update_reward_stack_quantity
from eidolon.validation import validate_uuid


def find_item_in_inventory(inventory: dict, item_id: str, inventory_slot: str) -> tuple:
    """Find an item in the inventory by ID, optionally using a hint slot.

    Args:
        inventory: Character inventory dict (slot -> slot_data)
        item_id: Item UUID to find
        inventory_slot: Optional slot hint for fast lookup

    Returns:
        Tuple of (found_slot, item_quantity) or (None, 0) if not found
    """
    # Quick lookup using provided slot hint
    if inventory_slot and inventory_slot in inventory:
        slot_data = inventory.get(inventory_slot, {})
        if slot_data.get("ItemID") == item_id:
            return inventory_slot, slot_data.get("Quantity", 1)

    # Fallback to full scan
    for slot, slot_data in inventory.items():
        if slot_data.get("ItemID") == item_id:
            return slot, slot_data.get("Quantity", 1)

    return None, 0


def discard_item(character_id: str, player_id: str, item_id: str, inventory_slot: str, quantity_to_discard: int) -> dict:
    """Handle the business logic for discarding an item from inventory.

    Args:
        character_id: Character UUID
        player_id: Authenticated player ID
        item_id: Item UUID to discard
        inventory_slot: Optional slot hint for fast lookup
        quantity_to_discard: Number to discard, or None for entire stack

    Returns:
        Dict containing discard results for the response body

    Raises:
        ValueError: If character not found/not owned, item not in inventory
        RuntimeError: If database operations fail
    """
    # Get character and verify ownership
    try:
        character = character_get(character_id, player_id)
    except ValueError as err:
        normalized = str(err).lower()
        logger.warning(f"Character access denied: {err}")
        if "not found" in normalized:
            raise ValueError(f"404:{err}") from err
        if "not owned" in normalized:
            raise ValueError(f"403:{err}") from err
        raise

    # Find item in inventory
    inventory = character.get("Inventory", {})
    found_slot, item_quantity = find_item_in_inventory(inventory, item_id, inventory_slot)

    if not found_slot:
        raise ValueError("404:Item not found in character inventory")

    # Get item brief for response
    try:
        item_brief = get_item_brief(item_id)
        prototype_id = item_brief.get("PrototypeID")
    except ValueError as err:
        logger.warning(f"Item brief not found for {item_id}, continuing with discard: {err}")
        prototype_id = "unknown"

    # Determine how much to discard
    if quantity_to_discard is None:
        quantity_to_discard = item_quantity
    else:
        quantity_to_discard = min(quantity_to_discard, item_quantity)

    # Update inventory
    current_inventory = inventory.copy()
    remaining_quantity = item_quantity - quantity_to_discard

    if quantity_to_discard >= item_quantity:
        current_inventory.pop(found_slot, None)
        item_fully_discarded = True
    else:
        current_inventory.get(found_slot, {})["Quantity"] = remaining_quantity
        item_fully_discarded = False

    # Write inventory with conditional check to prevent race conditions
    save_inventory_update(character_id, item_id, found_slot, current_inventory)

    # Sync ITEMS table
    if item_fully_discarded:
        delete_item_record(item_id)
    else:
        update_reward_stack_quantity(item_id, remaining_quantity)

    logger.info(f"Item {item_id} discarded by character {character_id}: {quantity_to_discard} of {item_quantity}")

    response_body = {
        "Success": True,
        "ItemDiscarded": {"ItemID": item_id, "PrototypeID": prototype_id},
        "QuantityDiscarded": quantity_to_discard,
        "ItemFullyDiscarded": item_fully_discarded,
    }

    if not item_fully_discarded:
        response_body["RemainingQuantity"] = remaining_quantity

    return response_body


def save_inventory_update(character_id: str, item_id: str, found_slot: str, current_inventory: dict) -> None:
    """Save inventory to DynamoDB with a conditional check on the discarded slot.

    Args:
        character_id: Character UUID
        item_id: Expected item ID in the slot (for race condition check)
        found_slot: Inventory slot being modified
        current_inventory: Updated inventory dict

    Raises:
        ValueError: With 409 prefix if inventory changed during operation
        RuntimeError: If database update fails
    """
    try:
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET Inventory = :inventory",
            ConditionExpression="Inventory.#slot.ItemID = :expected_item_id",
            ExpressionAttributeNames={"#slot": found_slot},
            ExpressionAttributeValues={":inventory": current_inventory, ":expected_item_id": item_id},
        )
    except ClientError as err:
        if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.warning(f"Discard failed: item {item_id} already removed (race condition detected)")
            raise ValueError("409:Item has already been discarded. Please refresh your inventory.") from err
        logger.error(f"Failed to update inventory for {character_id}: {err}")
        raise RuntimeError("Failed to discard item") from err


def delete_item_record(item_id: str) -> None:
    """Delete an item record from the ITEMS table.

    Non-fatal on failure since the inventory update already succeeded.

    Args:
        item_id: Item UUID to delete
    """
    try:
        dynamo.delete_item(TableName.ITEMS, Key={"ItemID": item_id})
    except ClientError as err:
        logger.error(f"Failed to delete item record {item_id} from ITEMS table: {err}")


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """Lambda handler for discarding items from inventory.

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
    if not validate_player(player_id):
        logger.error(f"Player {player_id} not found in database")
        raise ValueError("401:Unauthorized")

    body = parse_event_body(event)
    character_id = body.get("CharacterID", "")
    item_id = body.get("ItemID", "")
    inventory_slot = body.get("InventorySlot", "")
    quantity_to_discard = body.get("Quantity")

    if not character_id:
        raise ValueError("CharacterID is required")
    if not item_id:
        raise ValueError("ItemID is required")
    if not validate_uuid(character_id):
        raise ValueError("Invalid CharacterID format")
    if not validate_uuid(item_id):
        raise ValueError("Invalid ItemID format")

    # Validate quantity if provided
    validated_quantity: int = None  # type: ignore[assignment]
    if quantity_to_discard is not None:
        try:
            validated_quantity = int(quantity_to_discard)
        except (TypeError, ValueError) as err:
            raise ValueError("Invalid Quantity value") from err
        if validated_quantity < 1:
            raise ValueError("Quantity must be at least 1")

    result = discard_item(character_id, player_id, item_id, inventory_slot, validated_quantity)

    return {"status_code": 200, "body": result}
