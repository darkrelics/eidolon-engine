"""
Store and shop functionality for Eidolon Engine.

Handles store inventory management, item purchasing, and currency transactions.
"""

import json
from pathlib import Path

from botocore.exceptions import ClientError

from eidolon.currency import build_contents_coin_update, coin_transaction_ops, plan_coin_spend, wallet_total
from eidolon.dynamo import TABLE_ENV_MAP, TableName, dynamo, to_attribute_value
from eidolon.errors import ConflictError, NotFoundError, ValidationError
from eidolon.items import (
    build_item_from_prototype,
    distribute_into_stacks,
    get_item_prototype_full,
    get_stack_space,
    load_top_level_stacks,
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
        raise NotFoundError(f"Store '{store_id}' not found")

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


def get_store_stock_levels(store_id: str) -> dict:
    """Return ``{prototype_id: live_stock}`` for a store's stock-tracked items.

    Reads the STORES table, which holds the mutable stock state. The store catalog
    (Price, MinLevel, Category) stays in the JSON config; an item with no row here
    is not stock-tracked and the caller uses the catalog's configured Stock.
    """
    try:
        rows = dynamo.query(
            TableName.STORES,
            KeyConditionExpression="StoreID = :sid",
            ExpressionAttributeValues={":sid": store_id},
        )
    except ClientError as err:
        logger.error(f"Failed to read stock for store {store_id}: {err}")
        raise RuntimeError("Failed to read store stock") from err
    return {row.get("PrototypeID"): int(row.get("Stock", 0)) for row in rows or [] if row.get("PrototypeID")}


def get_live_stock(store_id: str, prototype_id: str):
    """Return the live stock for one store item, or None when it is not tracked."""
    try:
        record = dynamo.get_item(TableName.STORES, {"StoreID": store_id, "PrototypeID": prototype_id})
    except ClientError as err:
        logger.error(f"Failed to read stock for {store_id}/{prototype_id}: {err}")
        raise RuntimeError("Failed to read store stock") from err
    if not record:
        return None
    return int(record.get("Stock", 0))


def build_stock_decrement_op(store_id: str, prototype_id: str, quantity: int) -> dict:
    """Build the conditional stock-decrement op for the purchase transaction.

    The condition fails the whole transaction when stock is insufficient or the
    row is missing, so an out-of-stock or raced purchase commits nothing.
    """
    return {
        "Update": {
            "TableName": TABLE_ENV_MAP[TableName.STORES],
            "Key": {"StoreID": {"S": store_id}, "PrototypeID": {"S": prototype_id}},
            "UpdateExpression": "SET Stock = Stock - :qty",
            "ConditionExpression": "Stock >= :qty",
            "ExpressionAttributeValues": {":qty": to_attribute_value(quantity)},
        }
    }


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

    # Overlay live stock (mutable state) onto the catalog (config). An item with
    # no row is not stock-tracked and uses its configured Stock.
    live_stock = get_store_stock_levels(store_id)

    available_items = []

    for store_item in store_data.get("Inventory", []):
        # Check level requirement
        min_level = store_item.get("MinLevel", 0)
        if character_level < min_level:
            continue

        prototype_id = store_item.get("PrototypeID")

        # Check stock availability against live stock when tracked
        stock = live_stock.get(prototype_id, store_item.get("Stock", 0))
        if stock == 0:  # Out of stock
            continue

        # Get full prototype details
        try:
            prototype = get_item_prototype_full(prototype_id)
        except NotFoundError as err:
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


def allocate_purchase(prototype: dict, prototype_id: str, quantity: int, top_level: list, character_id: str) -> tuple:
    """Plan the item records a purchase creates or tops up.

    Stackable purchases merge into existing top-level stacks first (up to
    MaxStack), then mint new stacks; non-stackable purchases mint one record each.

    Returns ``(item_ids, planned_new_items, planned_stack_updates, items_to_append)``
    where ``planned_stack_updates`` is ``(item_id, new_qty, expected_qty)`` tuples.
    """
    item_ids: list = []
    planned_new_items: list = []
    planned_stack_updates: list = []
    items_to_append: list = []

    if not prototype.get("Stackable", False):
        for _ in range(quantity):
            payload = build_item_from_prototype(prototype_id=prototype_id, quantity=None, owner_id=character_id)
            if not payload:
                continue
            planned_new_items.append(payload)
            item_ids.append(payload["ItemID"])
            items_to_append.append(payload["ItemID"])
        return item_ids, planned_new_items, planned_stack_updates, items_to_append

    max_stack = prototype.get("MaxStack", 99)
    if max_stack <= 0:
        max_stack = 99

    remaining_quantity = quantity
    for existing_id, current_qty in load_top_level_stacks(top_level, prototype_id):
        if remaining_quantity <= 0:
            break
        space = get_stack_space(current_qty, max_stack)
        if space <= 0:
            continue
        add_qty = min(remaining_quantity, space)
        remaining_quantity -= add_qty
        if existing_id not in item_ids:
            item_ids.append(existing_id)
        planned_stack_updates.append((existing_id, current_qty + add_qty, current_qty))
        logger.info(f"Planned stack merge into {existing_id}: +{add_qty}")

    for stack_qty in distribute_into_stacks(remaining_quantity, max_stack) if remaining_quantity > 0 else []:
        payload = build_item_from_prototype(prototype_id=prototype_id, quantity=stack_qty, owner_id=character_id)
        if not payload:
            continue
        planned_new_items.append(payload)
        item_ids.append(payload["ItemID"])
        items_to_append.append(payload["ItemID"])
        logger.info(f"Planned new stack: {payload['ItemID']} x{stack_qty}")

    return item_ids, planned_new_items, planned_stack_updates, items_to_append


def purchase_item(character_id: str, prototype_id: str, quantity: int = 1, store_id: str = "general-store") -> dict:
    """Purchase an item from the store, paying with coin items.

    Currency is held as coin items (see ``eidolon/currency.py``). Payment spends
    the character's coins and re-mints the canonical change; the goods records,
    coin changes, and the character Contents update all commit in one transaction,
    so a partial failure can never charge the player without delivering the goods.

    Args:
        character_id: Character UUID
        prototype_id: Item prototype UUID to purchase
        quantity: Number of items to purchase (default 1)
        store_id: Store identifier (default "general-store")

    Returns:
        Dict with item_ids, currency_remaining (FU), total_cost, and quantity.

    Raises:
        ValidationError: Invalid quantity or unallocatable purchase.
        NotFoundError: Character, store item, or prototype missing.
        PaymentRequiredError: Insufficient coins.
        ConflictError: Out of stock or a raced balance / inventory change.
        RuntimeError: If database operations fail.
    """
    if quantity < 1:
        raise ValidationError("Quantity must be at least 1")

    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
        if not character:
            raise NotFoundError("Character not found")
    except ClientError as err:
        logger.error(f"Failed to fetch character {character_id}: {err}")
        raise RuntimeError("Failed to fetch character data") from err

    store_data = load_store_inventory(store_id)
    store_item = None
    for item in store_data.get("Inventory", []):
        if item.get("PrototypeID") == prototype_id:
            store_item = item
            break
    if not store_item:
        raise NotFoundError("Item not available in store")

    total_cost = store_item.get("Price", 0) * quantity

    # Stock: -1 in the catalog means untracked / unlimited. Otherwise the live
    # count in the STORES table is authoritative - pre-check it for a clear error
    # and decrement it atomically inside the purchase transaction.
    catalog_stock = store_item.get("Stock", 0)
    stock_op = None
    if catalog_stock != -1:
        available = get_live_stock(store_id, prototype_id)
        if available is None:
            available = catalog_stock
        if available < quantity:
            raise ConflictError(f"Insufficient stock: only {available} available")
        stock_op = build_stock_decrement_op(store_id, prototype_id, quantity)

    try:
        prototype = get_item_prototype_full(prototype_id)
    except NotFoundError as err:
        raise NotFoundError("Item prototype not found") from err

    item_ids, planned_new_items, planned_stack_updates, items_to_append = allocate_purchase(
        prototype, prototype_id, quantity, list(character.get("Contents") or []), character_id
    )
    if not planned_new_items and not planned_stack_updates:
        raise ValidationError("Unable to allocate purchased items")

    # Plan the coin payment (raises PaymentRequiredError when funds are short).
    coin_plan = plan_coin_spend(character, total_cost) if total_cost > 0 else None

    transact_items = build_purchase_transaction(
        character_id, character, coin_plan, planned_new_items, planned_stack_updates, items_to_append, stock_op=stock_op
    )

    # DynamoDB caps a transaction at 100 actions; refuse oversized purchases
    # rather than fall back to a non-atomic path that could lose currency.
    if len(transact_items) > 100:
        raise ValidationError("Purchase quantity too large to process atomically")

    try:
        dynamo.transact_write_items(transact_items)
    except ClientError as err:
        if err.response.get("Error", {}).get("Code") == "TransactionCanceledException":
            logger.warning(f"Purchase cancelled (balance or stack changed) for {character_id}: {prototype_id}")
            raise ConflictError("Inventory or balance changed during purchase. Please try again.") from err
        logger.error(f"Purchase transaction failed for {character_id}: {err}")
        raise RuntimeError("Purchase transaction failed") from err

    currency_remaining = coin_plan["new_total"] if coin_plan else wallet_total(character)
    logger.info(f"Purchase committed atomically: {quantity}x {prototype_id} for {total_cost}")

    return {
        "item_ids": item_ids,
        "currency_remaining": currency_remaining,
        "total_cost": total_cost,
        "quantity": quantity,
    }


def build_purchase_transaction(
    character_id: str,
    character: dict,
    coin_plan,
    planned_new_items: list,
    planned_stack_updates: list,
    items_to_append: list,
    stock_op=None,
) -> list:
    """Build the atomic transaction for a purchase.

    Combines the new goods records and existing-stack quantity bumps with the coin
    payment (delete the spent coin stacks, mint the canonicalized change), the
    conditional store-stock decrement (when the item is stock-tracked), and a
    single character Contents update. With a coin payment the Contents are set
    wholesale - the canonicalized coins have new ItemIDs - guarded by a
    ``contains`` check on each spent coin so a racing balance change cancels the
    purchase; a free purchase appends goods with the concurrency-safe list_append.
    Each existing-stack bump is guarded by its expected quantity, and the stock
    decrement by ``Stock >= :qty``, so stock, currency, and goods commit together.
    """
    items_table = TABLE_ENV_MAP[TableName.ITEMS]
    transact_items: list = []

    if stock_op is not None:
        transact_items.append(stock_op)

    for payload in planned_new_items:
        transact_items.append(
            {"Put": {"TableName": items_table, "Item": {field: to_attribute_value(value) for field, value in payload.items()}}}
        )

    for existing_id, new_qty, expected_qty in planned_stack_updates:
        transact_items.append(
            {
                "Update": {
                    "TableName": items_table,
                    "Key": {"ItemID": {"S": existing_id}},
                    "UpdateExpression": "SET Quantity = :quantity",
                    "ConditionExpression": "Quantity = :expected",
                    "ExpressionAttributeValues": {
                        ":quantity": to_attribute_value(new_qty),
                        ":expected": to_attribute_value(expected_qty),
                    },
                }
            }
        )

    if coin_plan is not None:
        transact_items.extend(coin_transaction_ops(coin_plan))
        transact_items.append(build_contents_coin_update(character_id, character, coin_plan, added_ids=items_to_append))
    elif items_to_append:
        transact_items.append(
            {
                "Update": {
                    "TableName": TABLE_ENV_MAP[TableName.CHARACTERS],
                    "Key": {"CharacterID": {"S": character_id}},
                    "UpdateExpression": "SET Contents = list_append(if_not_exists(Contents, :empty), :appended)",
                    "ExpressionAttributeValues": {
                        ":appended": to_attribute_value(items_to_append),
                        ":empty": to_attribute_value([]),
                    },
                }
            }
        )

    return transact_items
