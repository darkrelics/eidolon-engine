"""
Store and shop functionality for Eidolon Engine.

Handles store inventory management, item purchasing, and currency transactions.
"""

import json
from decimal import Decimal
from pathlib import Path

from botocore.exceptions import ClientError

from eidolon.contents import append_to_contents, PARENT_CHARACTER
from eidolon.dynamo import TableName, dynamo
from eidolon.items import (
    build_item_from_prototype,
    distribute_into_stacks,
    get_item_prototype_full,
    get_stack_space,
)
from eidolon.logger import logger


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

    if not Path(store_file).exists():
        raise ValueError(f"Store '{store_id}' not found")

    try:
        with Path(store_file).open(encoding="utf-8") as f:
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
        except ValueError as err:
            logger.warning(f"Prototype {prototype_id} not found for store item, skipping: {err}")
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

    # [FIX] BUG #4: Stock management documented as not implemented
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
    top_level = list(character.get("Contents") or [])

    item_ids: list = []
    planned_new_items: list = []
    planned_stack_updates: list = []  # (item_id, new_qty) for existing stack top-ups
    items_to_append: list = []  # ItemIDs to add to character.Contents

    if is_stackable:
        max_stack = prototype.get("MaxStack", 99)
        if max_stack <= 0:
            max_stack = 99

        remaining_quantity = quantity
        for existing_id, current_qty in _load_top_level_stacks(top_level, prototype_id):
            if remaining_quantity <= 0:
                break
            space = get_stack_space(current_qty, max_stack)
            if space <= 0:
                continue
            add_qty = min(remaining_quantity, space)
            new_qty = current_qty + add_qty
            remaining_quantity -= add_qty
            if existing_id not in item_ids:
                item_ids.append(existing_id)
            planned_stack_updates.append((existing_id, new_qty))
            logger.info(f"Planned stack merge into {existing_id}: +{add_qty}")

        for stack_qty in distribute_into_stacks(remaining_quantity, max_stack) if remaining_quantity > 0 else []:
            payload = build_item_from_prototype(
                prototype_id=prototype_id, quantity=stack_qty, owner_id=character_id
            )
            if not payload:
                continue
            planned_new_items.append(payload)
            item_ids.append(payload["ItemID"])
            items_to_append.append(payload["ItemID"])
            logger.info(f"Planned new stack: {payload['ItemID']} x{stack_qty}")
    else:
        for _ in range(quantity):
            payload = build_item_from_prototype(prototype_id=prototype_id, quantity=None, owner_id=character_id)
            if not payload:
                continue
            planned_new_items.append(payload)
            item_ids.append(payload["ItemID"])
            items_to_append.append(payload["ItemID"])

    new_currency = current_currency - total_cost

    # Deduct currency first with a conditional balance check so a racing
    # purchase can't double-spend.
    try:
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET #resources.#value = :value",
            ConditionExpression="#resources.#value = :expected_currency",
            ExpressionAttributeNames={
                "#resources": "Resources",
                "#value": "Value",
            },
            ExpressionAttributeValues={
                ":value": Decimal(str(new_currency)),
                ":expected_currency": Decimal(str(current_currency)),
            },
        )
        logger.info(f"Purchase currency committed: {quantity}x {prototype_id} for {total_cost}")
    except ClientError as err:
        if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.warning("Purchase failed: currency changed during transaction (race)")
            raise ValueError("409:Currency balance changed during purchase. Please try again.") from err
        logger.error(f"Failed to deduct currency for {character_id}: {err}")
        raise RuntimeError("Purchase transaction failed") from err

    if planned_new_items:
        failed_payloads = dynamo.batch_write_with_retries(TableName.ITEMS, planned_new_items, operation="put")
        if failed_payloads:
            failed_ids = {payload.get("ItemID") for payload in failed_payloads}
            logger.error(f"Failed to persist {len(failed_ids)} purchased items for {character_id}")
            items_to_append = [iid for iid in items_to_append if iid not in failed_ids]
            item_ids = [iid for iid in item_ids if iid not in failed_ids]

    for existing_id, new_qty in planned_stack_updates:
        try:
            dynamo.update_item(
                TableName.ITEMS,
                Key={"ItemID": existing_id},
                UpdateExpression="SET Quantity = :quantity",
                ExpressionAttributeValues={":quantity": new_qty},
            )
        except ClientError as err:
            logger.error(f"Failed to bump stack quantity for {existing_id}: {err}", exc_info=True)

    if items_to_append:
        append_to_contents(PARENT_CHARACTER, character_id, items_to_append)

    return {
        "item_ids": item_ids,
        "currency_remaining": new_currency,
        "total_cost": total_cost,
        "quantity": quantity,
    }


def _load_top_level_stacks(top_level_ids: list, prototype_id: str) -> list:
    """Return ``(item_id, current_quantity)`` for top-level stackable items
    sharing ``prototype_id``."""
    matching: list = []
    for item_id in top_level_ids:
        if not item_id:
            continue
        try:
            record = dynamo.get_item(TableName.ITEMS, {"ItemID": item_id})
        except ClientError as err:
            logger.error(f"Failed to inspect item {item_id} for purchase merge: {err}")
            continue
        if not record or record.get("PrototypeID") != prototype_id:
            continue
        if not record.get("Stackable"):
            continue
        matching.append((item_id, int(record.get("Quantity", 1) or 0)))
    return matching
