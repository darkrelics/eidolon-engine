"""
Store and shop functionality for Eidolon Engine.

Handles store inventory management, item purchasing, and currency transactions.
"""

import json
import os
from decimal import Decimal

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.items import (
    distribute_into_stacks,
    find_matching_stack,
    find_next_available_slot,
    get_item_prototype_full,
    get_stack_space,
)
from eidolon.logger import logger
from eidolon.story_rewards import create_reward_item


def load_store_inventory(store_id: str) -> dict:
    """
    Load store inventory from data file.

    Args:
        store_id: Store identifier (e.g., "general-store")

    Returns:
        Dict containing store configuration and inventory

    Raises:
        ValueError: If store file not found or invalid
        RuntimeError: If file read fails
    """
    store_file = f"data/store_{store_id.replace('-', '_')}.json"

    if not os.path.exists(store_file):
        raise ValueError(f"Store '{store_id}' not found")

    try:
        with open(store_file, encoding="utf-8") as f:
            store_data = json.load(f)

        logger.info(f"Loaded store inventory for '{store_id}': {len(store_data.get('Inventory', []))} items")
        return store_data
    except json.JSONDecodeError as err:
        logger.error(f"Invalid JSON in store file {store_file}: {err}")
        raise ValueError(f"Invalid store configuration for '{store_id}'") from err
    except OSError as err:
        logger.error(f"Failed to read store file {store_file}: {err}")
        raise RuntimeError(f"Failed to load store '{store_id}'") from err


def get_store_items(store_id: str, character_level: int = 0) -> dict:
    """
    Get available store items for a character.

    Filters items based on character level and enriches with prototype details.

    Args:
        store_id: Store identifier
        character_level: Character's current level (for MinLevel filtering)

    Returns:
        Dict with store info and available items with full prototype data

    Raises:
        ValueError: If store not found
        RuntimeError: If database operations fail
    """
    store_data = load_store_inventory(store_id)

    available_items = []

    for store_item in store_data.get("Inventory", []):
        # Check level requirement
        min_level = store_item.get("MinLevel", 0)
        if character_level < min_level:
            continue

        # Check stock availability
        stock = store_item.get("Stock", 0)
        if stock == 0:  # Out of stock
            continue

        # Get full prototype details
        prototype_id = store_item.get("PrototypeID")
        try:
            prototype = get_item_prototype_full(prototype_id)
        except ValueError:
            logger.warning(f"Prototype {prototype_id} not found for store item, skipping")
            continue

        # Combine store data with prototype details
        available_item = {
            "PrototypeID": prototype_id,
            "PrototypeName": store_item.get("PrototypeName"),
            "Price": store_item.get("Price"),
            "Stock": stock,
            "Category": store_item.get("Category"),
            "Featured": store_item.get("Featured", False),
            "Prototype": prototype,
        }

        available_items.append(available_item)

    return {
        "StoreID": store_data.get("StoreID"),
        "StoreName": store_data.get("StoreName"),
        "Description": store_data.get("Description"),
        "Items": available_items,
    }


def purchase_item(character_id: str, prototype_id: str, quantity: int = 1) -> dict:
    """
    Purchase an item from the store with atomic currency deduction.

    Args:
        character_id: Character UUID
        prototype_id: Item prototype UUID to purchase
        quantity: Number of items to purchase (default 1)

    Returns:
        Dict with purchase results:
            - item_ids: List of created item UUIDs
            - currency_remaining: Character's remaining currency
            - total_cost: Total cost of purchase

    Raises:
        ValueError: If insufficient funds, invalid quantity, item not available
        RuntimeError: If database operations fail
    """
    if quantity < 1:
        raise ValueError("Quantity must be at least 1")

    # Get character data
    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
        if not character:
            raise ValueError("Character not found")
    except ClientError as err:
        logger.error(f"Failed to fetch character {character_id}: {err}")
        raise RuntimeError("Failed to fetch character data") from err

    # Get current currency
    current_currency = character.get("Resources", {}).get("Value", 0)
    if isinstance(current_currency, Decimal):
        current_currency = int(current_currency)

    # Find item in all stores (for now, just check general-store)
    # TODO: Support multiple stores or pass store_id as parameter
    store_data = load_store_inventory("general-store")

    store_item = None
    for item in store_data.get("Inventory", []):
        if item.get("PrototypeID") == prototype_id:
            store_item = item
            break

    if not store_item:
        raise ValueError("Item not available in store")

    # Calculate total cost
    item_price = store_item.get("Price", 0)
    total_cost = item_price * quantity

    # Check sufficient funds
    if current_currency < total_cost:
        raise ValueError(f"Insufficient funds: need {total_cost}, have {current_currency}")

    # ✅ FIX BUG #4: Stock management documented as not implemented
    # Check stock availability (currently all items set to -1 = unlimited)
    # TODO: Implement proper stock management with DynamoDB table or atomic file updates
    stock = store_item.get("Stock", 0)
    if stock != -1 and stock < quantity:  # -1 = unlimited
        # NOTE: Stock is checked but never decremented (static JSON file)
        # All items currently set to Stock=-1 to avoid confusion
        raise ValueError(f"Insufficient stock: only {stock} available")

    # Get prototype to determine if stackable
    try:
        prototype = get_item_prototype_full(prototype_id)
    except ValueError as err:
        raise ValueError("Item prototype not found") from err

    is_stackable = prototype.get("Stackable", False)

    # Get current inventory
    inventory = character.get("Inventory", {})
    if not isinstance(inventory, dict):
        inventory = {}

    # Create items
    item_ids = []

    if is_stackable:
        # For stackable items, respect MaxStack when adding to inventory
        max_stack = prototype.get("MaxStack", 99)
        if max_stack <= 0:
            max_stack = 99

        remaining_quantity = quantity

        # First, try to add to existing stacks
        while remaining_quantity > 0:
            existing_stack = find_matching_stack(inventory, prototype_id, quantity_to_add=1)
            if not existing_stack:
                break

            stack_slot, stack_data = existing_stack
            current_qty = stack_data.get("Quantity", 1)
            space_available = get_stack_space(current_qty, max_stack)

            if space_available <= 0:
                break

            add_qty = min(remaining_quantity, space_available)
            inventory[stack_slot]["Quantity"] = current_qty + add_qty
            remaining_quantity -= add_qty

            if stack_data["ItemID"] not in item_ids:
                item_ids.append(stack_data["ItemID"])
            logger.info(f"Added {add_qty} to existing stack in slot {stack_slot}")

        # Create new stacks for remaining quantity
        if remaining_quantity > 0:
            stack_quantities = distribute_into_stacks(remaining_quantity, max_stack)
            for stack_qty in stack_quantities:
                new_item = create_reward_item(prototype_id=prototype_id, quantity=stack_qty, owner_id=character_id)
                item_id = new_item["ItemID"]
                next_slot = find_next_available_slot(inventory)
                inventory[next_slot] = {"ItemID": item_id, "Quantity": stack_qty}
                item_ids.append(item_id)
                logger.info(f"Created new stack in slot {next_slot}: {stack_qty} items")
    else:
        # For non-stackable items, create separate item for each
        for _ in range(quantity):
            new_item = create_reward_item(prototype_id=prototype_id, quantity=None, owner_id=character_id)
            item_id = new_item["ItemID"]
            next_slot = find_next_available_slot(inventory)
            inventory[next_slot] = {"ItemID": item_id}
            item_ids.append(item_id)
            logger.info(f"Created non-stackable item in slot {next_slot}")

    # Calculate new currency value
    new_currency = current_currency - total_cost

    # ✅ FIX BUG #1: Use conditional update to prevent race conditions
    # Ensures currency hasn't changed since we read it (prevents double-purchase exploits)
    try:
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET Inventory = :inventory, #resources.#value = :value",
            ConditionExpression="#resources.#value = :expected_currency",
            ExpressionAttributeNames={
                "#resources": "Resources",
                "#value": "Value",
            },
            ExpressionAttributeValues={
                ":inventory": inventory,
                ":value": Decimal(str(new_currency)),
                ":expected_currency": Decimal(str(current_currency)),
            },
        )
        logger.info(f"Purchase complete: {quantity}x {prototype_id} for {total_cost} currency")
    except ClientError as err:
        # Check if this was a conditional check failure (currency changed = race condition)
        if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.warning("Purchase failed: currency changed during transaction (race condition detected)")
            raise ValueError("409:Currency balance changed during purchase. Please try again.") from err

        logger.error(f"Failed to complete purchase for {character_id}: {err}")
        raise RuntimeError("Purchase transaction failed") from err

    return {
        "item_ids": item_ids,
        "currency_remaining": new_currency,
        "total_cost": total_cost,
        "quantity": quantity,
    }
