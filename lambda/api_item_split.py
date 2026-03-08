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


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """
    Lambda handler for splitting a stackable item into two stacks.

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
    # Validate player exists
    if not validate_player(player_id):
        logger.error(f"Player {player_id} not found in database")
        raise ValueError("401:Unauthorized")

    # Parse request body
    body = parse_event_body(event)
    character_id = body.get("CharacterID", "")
    slot = body.get("Slot", "")
    split_quantity = body.get("Quantity")

    # Validate required parameters
    if not character_id:
        raise ValueError("CharacterID is required")

    if not slot:
        raise ValueError("Slot is required")

    if split_quantity is None:
        raise ValueError("Quantity is required")

    # Validate UUID
    if not validate_uuid(character_id):
        raise ValueError("Invalid CharacterID format")

    # Validate quantity
    try:
        split_quantity = int(split_quantity)
        if split_quantity < 1:
            raise ValueError("Quantity must be at least 1")
    except TypeError as err:
        raise ValueError("Invalid Quantity value") from err
    except ValueError as err:
        raise ValueError("Invalid Quantity value") from err

    # Get character and verify ownership
    try:
        character = character_get(character_id, player_id)
    except ValueError as err:
        logger.warning(f"Character access denied: {err}")
        raise ValueError(f"403:{err}") from err

    # Find item in inventory
    inventory = character.get("Inventory", {})
    slot = str(slot)

    if slot not in inventory:
        raise ValueError("404:Slot not found in inventory")

    slot_data = inventory.get(slot)
    if not slot_data or not isinstance(slot_data, dict):
        raise ValueError("404:Invalid slot data")

    item_id = slot_data.get("ItemID")
    if not item_id:
        raise ValueError("404:No item in specified slot")

    current_quantity = slot_data.get("Quantity", 1)

    # Validate split quantity against current quantity
    if split_quantity > current_quantity:
        raise ValueError(f"Cannot split {split_quantity} items from a stack of {current_quantity}")

    if split_quantity == current_quantity:
        raise ValueError("Cannot split entire stack. Use a smaller quantity.")

    # Get item brief and prototype to verify it's stackable
    try:
        item_brief = get_item_brief(item_id)
        prototype_id = item_brief.get("PrototypeID")
    except ValueError as err:
        logger.warning(f"Item brief not found for {item_id}: {err}")
        raise ValueError("404:Item not found") from err

    prototype = get_prototype(prototype_id)
    if not prototype:
        raise ValueError("404:Item prototype not found")

    if not prototype.get("Stackable", False):
        raise ValueError("Cannot split non-stackable items")

    # Calculate new quantities
    remaining_quantity = current_quantity - split_quantity

    # Create new item for the split stack
    new_item = create_reward_item(
        prototype_id=prototype_id,
        quantity=split_quantity,
        owner_id=character_id,
    )

    if not new_item:
        raise RuntimeError("Failed to create new stack item")

    new_item_id = new_item.get("ItemID")

    # Find next available slot for the new stack
    new_slot = find_next_available_slot(inventory)

    # Update inventory
    try:
        # Deep copy inventory to avoid mutating the original
        updated_inventory = {k: dict(v) if isinstance(v, dict) else v for k, v in inventory.items()}

        # Update original slot with reduced quantity
        updated_inventory[slot]["Quantity"] = remaining_quantity

        # Add new slot with split quantity
        updated_inventory[new_slot] = {
            "ItemID": new_item_id,
            "Quantity": split_quantity,
        }

        # Use conditional update to prevent race conditions
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET Inventory = :inventory",
            ConditionExpression="Inventory.#slot.ItemID = :expected_item_id AND Inventory.#slot.Quantity = :expected_quantity",
            ExpressionAttributeNames={
                "#slot": slot,
            },
            ExpressionAttributeValues={
                ":inventory": updated_inventory,
                ":expected_item_id": item_id,
                ":expected_quantity": current_quantity,
            },
        )

    except ClientError as err:
        # Check if this was a conditional check failure (stack changed = race condition)
        if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.warning(f"Split failed: item {item_id} quantity changed (race condition detected)")
            # Clean up the created item
            try:
                dynamo.delete_item(TableName.ITEMS, {"ItemID": new_item_id})
            except ClientError as err:
                logger.error(f"Failed to clean up orphaned item {new_item_id}: {err}")
            raise ValueError("409:Stack quantity changed during split. Please refresh your inventory.") from err

        logger.error(f"Failed to update inventory for {character_id}: {err}")
        raise RuntimeError("Failed to split stack") from err

    # Update original item quantity in Items table
    try:
        dynamo.update_item(
            TableName.ITEMS,
            Key={"ItemID": item_id},
            UpdateExpression="SET Quantity = :quantity",
            ExpressionAttributeValues={":quantity": remaining_quantity},
        )
    except ClientError as err:
        logger.error(f"Failed to update original item {item_id} quantity: {err}")
        # Non-fatal - inventory is already updated

    logger.info(
        f"Split item {item_id} for character {character_id}: "
        f"{split_quantity} into new stack {new_item_id}, {remaining_quantity} remaining"
    )

    # Build response
    response_body = {
        "Success": True,
        "OriginalStack": {
            "ItemID": item_id,
            "Slot": slot,
            "RemainingQuantity": remaining_quantity,
        },
        "NewStack": {
            "ItemID": new_item_id,
            "Slot": new_slot,
            "Quantity": split_quantity,
        },
        "PrototypeID": prototype_id,
    }

    return {"status_code": 200, "body": response_body}
