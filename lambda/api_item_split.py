"""
Eidolon Engine - Incremental Game

Copyright 2024-2026 Jason E. Robinson

Lambda function to split a stackable item into two separate stacks.
Creates a new stack with the specified quantity.

Endpoint: POST /item/split
Authentication: Cognito (required)
"""

from botocore.exceptions import ClientError

from eidolon.character_data import character_get
from eidolon.dynamo import TableName, dynamo
from eidolon.items import find_next_available_slot, get_item_brief, get_prototype
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.player import validate_player
from eidolon.requests import parse_event_body
from eidolon.story_rewards import create_reward_item
from eidolon.validation import validate_uuid


def validate_split_request(character: dict, slot: str, item_id_out: list) -> tuple:
    """Validate the inventory slot and retrieve item data for splitting.

    Args:
        character: Character dict from character_get
        slot: Inventory slot string
        item_id_out: Empty list; item_id is appended for caller access

    Returns:
        Tuple of (slot_data, item_id, current_quantity)

    Raises:
        ValueError: If slot/item not found or item is not stackable
    """
    inventory = character.get("Inventory", {})
    slot = str(slot)

    if slot not in inventory:
        raise ValueError("404:Slot not found in inventory")

    slot_data = inventory.get(slot, {})
    if not slot_data or not isinstance(slot_data, dict):
        raise ValueError("404:Invalid slot data")

    item_id = slot_data.get("ItemID")
    if not item_id:
        raise ValueError("404:No item in specified slot")

    current_quantity = slot_data.get("Quantity", 1)

    # Verify item is stackable
    try:
        item_brief = get_item_brief(item_id)
        prototype_id = item_brief.get("PrototypeID", "")
    except ValueError as err:
        logger.warning(f"Item brief not found for {item_id}: {err}")
        raise ValueError("404:Item not found") from err

    if not prototype_id:
        raise ValueError("404:Item prototype reference missing")

    prototype = get_prototype(prototype_id)
    if not prototype:
        raise ValueError("404:Item prototype not found")

    if not prototype.get("Stackable", False):
        raise ValueError("Cannot split non-stackable items")

    return item_id, prototype_id, current_quantity


def execute_split(
    character_id: str, inventory: dict, slot: str, item_id: str, current_quantity: int, split_quantity: int, prototype_id: str
) -> dict:
    """Execute the item split: create new item, update inventory, sync ITEMS table.

    Args:
        character_id: Character UUID
        inventory: Character inventory dict
        slot: Source inventory slot
        item_id: Source item UUID
        current_quantity: Current stack quantity
        split_quantity: Number to split off
        prototype_id: Item prototype UUID

    Returns:
        Dict containing split results for the response body

    Raises:
        ValueError: With 409 prefix on race condition
        RuntimeError: If item creation or inventory update fails
    """
    remaining_quantity = current_quantity - split_quantity

    # Create new item for the split stack
    new_item = create_reward_item(
        prototype_id=prototype_id,
        quantity=split_quantity,
        owner_id=character_id,
    )

    if not new_item:
        raise RuntimeError("Failed to create new stack item")

    new_item_id: str = new_item.get("ItemID", "")
    new_slot = find_next_available_slot(inventory)

    # Build updated inventory (deep copy to avoid mutating original)
    updated_inventory = {k: dict(v) if isinstance(v, dict) else v for k, v in inventory.items()}
    updated_inventory.get(slot, {})["Quantity"] = remaining_quantity
    updated_inventory[new_slot] = {"ItemID": new_item_id, "Quantity": split_quantity}

    # Write with conditional check to prevent race conditions
    try:
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET Inventory = :inventory",
            ConditionExpression="Inventory.#slot.ItemID = :expected_item_id AND Inventory.#slot.Quantity = :expected_quantity",
            ExpressionAttributeNames={"#slot": slot},
            ExpressionAttributeValues={
                ":inventory": updated_inventory,
                ":expected_item_id": item_id,
                ":expected_quantity": current_quantity,
            },
        )
    except ClientError as err:
        if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.warning(f"Split failed: item {item_id} quantity changed (race condition detected)")
            cleanup_orphaned_item(new_item_id)
            raise ValueError("409:Stack quantity changed during split. Please refresh your inventory.") from err
        logger.error(f"Failed to update inventory for {character_id}: {err}")
        raise RuntimeError("Failed to split stack") from err

    # Update original item quantity in ITEMS table (non-fatal)
    try:
        dynamo.update_item(
            TableName.ITEMS,
            Key={"ItemID": item_id},
            UpdateExpression="SET Quantity = :quantity",
            ExpressionAttributeValues={":quantity": remaining_quantity},
        )
    except ClientError as err:
        logger.error(f"Failed to update original item {item_id} quantity: {err}")

    logger.info(
        f"Split item {item_id} for character {character_id}: "
        f"{split_quantity} into new stack {new_item_id}, {remaining_quantity} remaining"
    )

    return {
        "Success": True,
        "OriginalStack": {"ItemID": item_id, "Slot": slot, "RemainingQuantity": remaining_quantity},
        "NewStack": {"ItemID": new_item_id, "Slot": new_slot, "Quantity": split_quantity},
        "PrototypeID": prototype_id,
    }


def cleanup_orphaned_item(item_id: str) -> None:
    """Delete an orphaned item created during a failed split.

    Non-fatal on failure since the item is already orphaned.

    Args:
        item_id: Item UUID to delete
    """
    try:
        dynamo.delete_item(TableName.ITEMS, Key={"ItemID": item_id})
    except ClientError as err:
        logger.error(f"Failed to clean up orphaned item {item_id}: {err}")


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """Lambda handler for splitting a stackable item into two stacks.

    Request Body:
        {
            "CharacterID": "uuid",
            "Slot": "1",
            "Quantity": 5 (number of items to split off into new stack)
        }

    Args:
        event: API Gateway Lambda proxy event
        context: Lambda context
        player_id: Authenticated player ID

    Returns:
        Dict with status_code and body containing split results
    """
    if not validate_player(player_id):
        logger.error(f"Player {player_id} not found in database")
        raise ValueError("401:Unauthorized")

    body = parse_event_body(event)
    character_id = body.get("CharacterID", "")
    slot = body.get("Slot", "")
    split_quantity = body.get("Quantity")

    if not character_id:
        raise ValueError("CharacterID is required")
    if not slot:
        raise ValueError("Slot is required")
    if split_quantity is None:
        raise ValueError("Quantity is required")

    if not validate_uuid(character_id):
        raise ValueError("Invalid CharacterID format")

    # Validate quantity
    try:
        split_quantity = int(split_quantity)
    except (TypeError, ValueError) as err:
        raise ValueError("Invalid Quantity value") from err
    if split_quantity < 1:
        raise ValueError("Quantity must be at least 1")

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

    # Validate slot and item
    item_id, prototype_id, current_quantity = validate_split_request(character, slot, [])

    if split_quantity > current_quantity:
        raise ValueError(f"Cannot split {split_quantity} items from a stack of {current_quantity}")
    if split_quantity == current_quantity:
        raise ValueError("Cannot split entire stack. Use a smaller quantity.")

    # Execute the split
    inventory = character.get("Inventory", {})
    result = execute_split(character_id, inventory, str(slot), item_id, current_quantity, split_quantity, prototype_id)

    return {"status_code": 200, "body": result}
