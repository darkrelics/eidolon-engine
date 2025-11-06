"""
Store and shop functionality for Eidolon Engine.

Handles store inventory management, item purchasing, and currency transactions.
"""

import json
import os
from decimal import Decimal
from typing import Optional

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.items import get_item_prototype_full
from eidolon.logger import logger
from eidolon.story_rewards import create_reward_item, find_next_available_slot


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

    # Check stock availability
    stock = store_item.get("Stock", 0)
    if stock != -1 and stock < quantity:  # -1 = unlimited
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
        # For stackable items, try to find existing stack or create one stack
        from eidolon.items import find_matching_stack

        existing_stack = find_matching_stack(inventory, prototype_id)

        if existing_stack:
            # Add to existing stack
            stack_slot, stack_data = existing_stack
            new_quantity = stack_data.get("Quantity", 1) + quantity
            inventory[stack_slot]["Quantity"] = new_quantity
            item_ids.append(stack_data["ItemID"])
            logger.info(f"Added {quantity} to existing stack in slot {stack_slot}")
        else:
            # Create new stack
            new_item = create_reward_item(prototype_id=prototype_id, quantity=quantity, owner_id=character_id)
            item_id = new_item["ItemID"]
            next_slot = find_next_available_slot(inventory)
            inventory[next_slot] = {"ItemID": item_id, "Quantity": quantity}
            item_ids.append(item_id)
            logger.info(f"Created new stack in slot {next_slot}: {quantity} items")
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

    # Atomic update: deduct currency and update inventory
    try:
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET Inventory = :inventory, #resources.#value = :value",
            ExpressionAttributeNames={
                "#resources": "Resources",
                "#value": "Value",
            },
            ExpressionAttributeValues={
                ":inventory": inventory,
                ":value": Decimal(str(new_currency)),
            },
        )
        logger.info(f"Purchase complete: {quantity}x {prototype_id} for {total_cost} currency")
    except ClientError as err:
        logger.error(f"Failed to complete purchase for {character_id}: {err}")
        raise RuntimeError("Purchase transaction failed") from err

    return {
        "item_ids": item_ids,
        "currency_remaining": new_currency,
        "total_cost": total_cost,
        "quantity": quantity,
    }
