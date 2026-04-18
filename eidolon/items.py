"""Item management functions for the Eidolon Engine."""

import random
import uuid
from datetime import datetime, timezone
from functools import cache

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger


def merge_stacks(item1: dict, item2: dict) -> dict:
    """
    Merge two stackable items.
    The older stack (by UUIDv7 timestamp) keeps its ItemID.

    Args:
        item1: First item dict
        item2: Second item dict

    Returns:
        Merged item dict or empty dict if items can't stack
    """
    # Must be same prototype
    if item1.get("PrototypeID") != item2.get("PrototypeID"):
        return {}

    # Get prototype to check if stackable
    prototype = get_prototype(item1.get("PrototypeID"))
    if not prototype or not prototype.get("Stackable", False):
        return {}

    # Check both items have only allowed fields for stackable items
    allowed_fields = {"ItemID", "PrototypeID", "Quantity", "OwnerID", "LocationID"}
    item1_fields = set(item1.keys())
    item2_fields = set(item2.keys())

    # Remove None/empty fields from check
    item1_fields = {k for k in item1_fields if item1.get(k) is not None}
    item2_fields = {k for k in item2_fields if item2.get(k) is not None}

    if not item1_fields.issubset(allowed_fields) or not item2_fields.issubset(allowed_fields):
        return {}

    total_quantity = item1.get("Quantity", 1) + item2.get("Quantity", 1)

    # Check if merged quantity would exceed MaxStack
    max_stack = prototype.get("MaxStack", 99)
    if max_stack <= 0:
        max_stack = 99
    if total_quantity > max_stack:
        return {}

    item1_id = item1.get("ItemID", "")
    item2_id = item2.get("ItemID", "")
    if not item1_id or not item2_id:
        return {}

    # UUIDv7 has timestamp, so lexicographic comparison gives older item
    if item1_id < item2_id:
        # item1 is older, keep its ID
        return {
            "ItemID": item1_id,
            "PrototypeID": item1.get("PrototypeID", ""),
            "Quantity": total_quantity,
            "OwnerID": item1.get("OwnerID"),
        }
    else:
        # item2 is older, keep its ID
        return {
            "ItemID": item2_id,
            "PrototypeID": item2.get("PrototypeID", ""),
            "Quantity": total_quantity,
            "OwnerID": item2.get("OwnerID"),
        }


def find_matching_stack(inventory: dict, prototype_id: str, quantity_to_add: int = 1, owner_id: str = "") -> tuple:
    """
    Find an existing stack in inventory that matches the prototype and has room.

    Args:
        inventory: Dict mapping slot to item data: {slot: {"ItemID": "...", "Quantity": int}}
        prototype_id: PrototypeID to find
        quantity_to_add: Quantity that needs to fit in the stack (default 1)
        owner_id: Character ID to verify ownership (recommended to prevent cross-character merge)

    Returns:
        Tuple of (slot, item_data_dict) or empty tuple if no matching stack found
    """
    if not inventory or not prototype_id:
        return ()

    # Get prototype to check if stackable and get MaxStack
    prototype = get_prototype(prototype_id)
    if not prototype or not prototype.get("Stackable", False):
        return ()

    max_stack = prototype.get("MaxStack", 99)
    if max_stack <= 0:
        max_stack = 99

    # Check each item in inventory
    for slot, item_data in inventory.items():
        if not item_data or not isinstance(item_data, dict):
            continue

        item_id = item_data.get("ItemID")
        if not item_id:
            continue

        # Get the item from database to check PrototypeID
        try:
            item = dynamo.get_item(TableName.ITEMS, {"ItemID": item_id})
            if item and item.get("PrototypeID") == prototype_id:
                # Verify ownership if owner_id provided (prevents cross-character merge)
                if owner_id and item.get("OwnerID") and item.get("OwnerID") != owner_id:
                    logger.warning(f"Item {item_id} ownership mismatch: expected {owner_id}, found {item.get('OwnerID')}")
                    continue

                # Check if stack has room for the quantity
                current_quantity = item_data.get("Quantity", 1)
                if can_add_to_stack(current_quantity, quantity_to_add, max_stack):
                    return (slot, item_data)
        except ClientError as err:
            logger.debug(f"Failed to get item {item_id} for stacking: {err}")
            continue

    return ()


def can_add_to_stack(current_quantity: int, add_quantity: int, max_stack: int) -> bool:
    """
    Check if quantity can be added to a stack without exceeding MaxStack.

    Args:
        current_quantity: Current stack quantity
        add_quantity: Quantity to add
        max_stack: Maximum stack size from prototype

    Returns:
        True if the addition would not exceed MaxStack
    """
    if max_stack <= 0:
        max_stack = 99
    return current_quantity + add_quantity <= max_stack


def get_stack_space(current_quantity: int, max_stack: int) -> int:
    """
    Calculate how many items can be added to a stack.

    Args:
        current_quantity: Current stack quantity
        max_stack: Maximum stack size from prototype

    Returns:
        Number of items that can be added (0 if stack is full)
    """
    if max_stack <= 0:
        max_stack = 99
    return max(0, max_stack - current_quantity)


def distribute_into_stacks(total_quantity: int, max_stack: int) -> list:
    """
    Split a quantity into MaxStack-compliant portions.

    Args:
        total_quantity: Total quantity to distribute
        max_stack: Maximum stack size

    Returns:
        List of quantities, each <= max_stack
    """
    if max_stack <= 0:
        max_stack = 99
    if total_quantity <= 0:
        return []

    stacks = []
    remaining = total_quantity
    while remaining > 0:
        stack_qty = min(remaining, max_stack)
        stacks.append(stack_qty)
        remaining -= stack_qty
    return stacks


@cache
def get_prototype(prototype_id: str) -> dict:
    """
    Retrieve a prototype from DynamoDB with caching.

    Args:
        prototype_id: Prototype ID to fetch

    Returns:
        Prototype data dict or empty dict if not found
    """
    result = dynamo.get_item(TableName.PROTOTYPES, {"PrototypeID": prototype_id})
    return result or {}


def get_item_brief(item_id: str) -> dict:
    """
    Retrieve item brief information for IndexedDB caching.

    Returns ItemID, PrototypeID, and Quantity for lightweight item loading.

    Args:
        item_id: Item UUID to fetch

    Returns:
        Dict containing ItemID, PrototypeID, and Quantity

    Raises:
        ValueError: If item not found or missing PrototypeID
        RuntimeError: If database operation fails
    """
    try:
        item = dynamo.get_item(TableName.ITEMS, {"ItemID": item_id})
    except ClientError as err:
        logger.error(f"Failed to fetch item {item_id} from database")
        raise RuntimeError("Failed to retrieve item data") from err

    if not item:
        raise ValueError(f"Item {item_id} not found")

    prototype_id = item.get("PrototypeID")
    if not prototype_id:
        logger.error(f"Item {item_id} missing PrototypeID field")
        raise ValueError("Item data incomplete")

    # Get prototype to determine if item is stackable
    prototype = get_prototype(prototype_id)
    is_stackable = prototype.get("Stackable", False) if prototype else False

    # Build response with Quantity field for API consistency
    # Storage: stackable items have Quantity field, non-stackable don't
    # API response: always include Quantity (actual count or 0 for non-stackable)
    result = {
        "ItemID": item_id,
        "PrototypeID": prototype_id,
    }

    if is_stackable:
        result["Quantity"] = item.get("Quantity", 1)
    else:
        # Non-stackable: return 0 for API consistency (field not stored in DB)
        result["Quantity"] = 0

    return result


def get_item_prototype_full(prototype_id: str) -> dict:
    """
    Retrieve complete item prototype definition for client-side caching.

    Returns the full prototype data including all properties, stats, and metadata.
    Prototypes are immutable game data and safe to cache indefinitely on client.

    Args:
        prototype_id: Prototype UUID to fetch

    Returns:
        Complete prototype data dict with Name field for client compatibility

    Raises:
        ValueError: If prototype not found
        RuntimeError: If database operation fails
    """
    try:
        prototype = dynamo.get_item(TableName.PROTOTYPES, {"PrototypeID": prototype_id})
    except ClientError as err:
        logger.error(f"Failed to fetch prototype {prototype_id} from database")
        raise RuntimeError("Failed to retrieve prototype data") from err

    if not prototype:
        raise ValueError(f"Prototype {prototype_id} not found")

    # Add Name field for client compatibility (prototypes store PrototypeName)
    result = dict(prototype)
    result["Name"] = prototype.get("PrototypeName", prototype.get("Name", "Unknown Item"))

    return result


def build_item_payload(
    prototype: dict,
    item_id: str,
    *,
    is_worn: bool = False,
    contents=None,
    quantity_override=None,
    owner_id=None,
) -> dict:
    """Construct item payload from a prototype definition.

    Args:
        prototype: Prototype definition from DynamoDB
        item_id: UUID assigned to the instance
        is_worn: Whether the item starts worn
        contents: Optional contents list for containers
        quantity_override: Explicit quantity to persist (primarily for stackable rewards)
        owner_id: Optional character UUID to persist as OwnerID
    """

    payload = {
        "ItemID": item_id,
        "PrototypeID": prototype.get("PrototypeID", ""),
        "Name": prototype.get("PrototypeName", prototype.get("Name", "Unknown Item")),
        "Description": prototype.get("Description", ""),
        "Mass": prototype.get("Mass", 0),
        "Value": prototype.get("Value", 0),
        "Stackable": prototype.get("Stackable", False),
        "MaxStack": prototype.get("MaxStack", 1),
        "Quantity": prototype.get("Quantity", 1),
        "Wearable": prototype.get("Wearable", False),
        "WornOn": prototype.get("WornOn", ""),
        "Verbs": prototype.get("Verbs", {}),
        "Overrides": prototype.get("Overrides", {}),
        "TraitMods": prototype.get("TraitMods", {}),
        "Container": prototype.get("Container", False),
        "Contents": contents if contents is not None else [],
        "IsWorn": is_worn,
        # Keep compatibility with any consumers that expect 'Equipped'
        "Equipped": is_worn,
        "CanPickUp": prototype.get("CanPickUp", True),
        "Metadata": prototype.get("Metadata", {}),
        "Consumable": prototype.get("Consumable", False),
        "ConsumableEffects": prototype.get("ConsumableEffects", {}),
    }

    if quantity_override is not None:
        payload["Quantity"] = quantity_override

    if owner_id:
        payload["OwnerID"] = owner_id

    return payload


def build_item_from_prototype(
    prototype_id: str,
    *,
    is_worn: bool = False,
    initial_contents=None,
    quantity=None,
    owner_id=None,
) -> dict:
    """Build an item payload from a prototype without persisting it.

    Returns a payload dict complete with a fresh ItemID, or {} when the
    prototype can't be resolved. Use this when the caller needs to plan
    inventory changes before committing to DynamoDB — persist the result
    with dynamo.put_item or a batch write once the character update succeeds.
    """

    if not prototype_id:
        logger.warning("Cannot build item: missing prototype ID")
        return {}

    prototype = get_prototype(prototype_id)
    if not prototype:
        logger.warning(f"Prototype not found for {prototype_id}")
        return {}

    item_id = str(uuid.uuid4())
    return build_item_payload(
        prototype,
        item_id,
        is_worn=is_worn,
        contents=initial_contents,
        quantity_override=quantity,
        owner_id=owner_id,
    )


def create_item_from_prototype(
    prototype_id: str,
    *,
    is_worn: bool = False,
    initial_contents=None,
    quantity=None,
    owner_id=None,
) -> dict:
    """Create a single item instance from a prototype and persist it."""

    item_payload = build_item_from_prototype(
        prototype_id,
        is_worn=is_worn,
        initial_contents=initial_contents,
        quantity=quantity,
        owner_id=owner_id,
    )
    if not item_payload:
        return {}

    item_id = item_payload["ItemID"]
    try:
        dynamo.put_item(TableName.ITEMS, item_payload)
        logger.info(f"Created item {item_id} from prototype {prototype_id}")
        return item_payload
    except Exception as err:  # pragma: no cover - DynamoDB client handles errors
        logger.error(f"Error creating item {item_id} from prototype {prototype_id} Error: {err}", exc_info=True)
        return {}


def find_next_available_slot(inventory: dict) -> str:
    """Return the next open inventory slot, reusing empty entries when possible."""

    normalized = {str(key): value for key, value in inventory.items()}
    index = 0
    while True:
        key = str(index)
        value = normalized.get(key)
        if value in (None, "", 0) or key not in normalized:
            return key
        index += 1


def process_items_with_probability(items_data: list) -> list:
    """
    Process Items field and determine which items to grant based on probability.

    Supports two formats:
    1. Simple: ["uuid-1", "uuid-2"] - all items granted
    2. Probabilistic: [{"ItemID": "uuid-1", "Chance": 0.3}, ...] - rolled independently

    Args:
        items_data: Items list in either format

    Returns:
        List of prototype IDs to grant
    """
    if not items_data:
        return []

    granted_items = []

    # Check format by examining first element
    first_item = items_data[0]

    if isinstance(first_item, str):
        # Simple format - grant all items
        return items_data

    elif isinstance(first_item, dict):
        # Probabilistic format - process with cumulative probability
        # Sort by Chance ascending (smallest to highest)
        sorted_items = sorted(items_data, key=lambda x: x.get("Chance", 0))

        # Process with cumulative clipping
        cumulative = 0.0
        for item_def in sorted_items:
            item_id = item_def.get("ItemID")
            chance = item_def.get("Chance", 0)

            if not item_id or chance <= 0:
                continue

            # Clip if cumulative exceeds 1.0
            effective_chance = min(chance, 1.0 - cumulative)
            cumulative += effective_chance

            # Roll for this item
            if random.random() < effective_chance:
                granted_items.append(item_id)

            # Stop if we've reached 100% cumulative
            if cumulative >= 1.0:
                break

        return granted_items

    else:
        logger.warning(f"Unexpected Items format: {type(first_item)}")
        return []


def add_items_to_inventory(character_id: str, prototype_ids: list) -> list:
    """Create items from prototypes and append them to a character's inventory.

    Writes the character record first, then persists the ITEMS rows. Any
    ITEMS that fail to persist after the character write are deleted from
    the character's Inventory in a follow-up update so the two tables stay
    consistent.
    """

    if not prototype_ids:
        return []

    try:
        character_record = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
    except ClientError as err:
        logger.error("Failed to load character %s for story rewards Error: %s", character_id, err, exc_info=True)
        return []

    if not character_record:
        logger.error("Character %s not found when applying story rewards", character_id)
        return []

    inventory = character_record.get("Inventory") or {}
    if not isinstance(inventory, dict):
        logger.warning("Character %s has unexpected inventory format; initializing empty inventory", character_id)
        inventory = {}

    # Plan the inventory changes without touching DynamoDB yet.
    normalized_inventory = {str(key): value for key, value in inventory.items()}
    planned_items = []  # list[(slot_key, item_payload)]

    for prototype_id in prototype_ids:
        if not isinstance(prototype_id, str) or not prototype_id:
            logger.warning("Skipping invalid prototype ID in story rewards for %s: %s", character_id, prototype_id)
            continue

        item_payload = build_item_from_prototype(prototype_id, owner_id=character_id)
        if not item_payload:
            continue

        slot_key = find_next_available_slot(normalized_inventory)
        item_id = item_payload["ItemID"]
        slot_entry = {"ItemID": item_id}
        if item_payload.get("Stackable", False):
            slot_entry["Quantity"] = item_payload.get("Quantity", 1)
        normalized_inventory[slot_key] = slot_entry
        planned_items.append((slot_key, item_payload))

    if not planned_items:
        return []

    # Write the character first. If this fails the ITEMS table is untouched.
    try:
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET Inventory = :inventory, UpdatedAt = :updated_at",
            ExpressionAttributeValues={
                ":inventory": normalized_inventory,
                ":updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except ClientError as err:
        logger.error(
            "Failed to update inventory for %s while applying story rewards Error: %s",
            character_id,
            err,
            exc_info=True,
        )
        return []

    # Persist items in batch now that the character points at them.
    items_to_write = [payload for _, payload in planned_items]
    failed_payloads = dynamo.batch_write_with_retries(TableName.ITEMS, items_to_write, operation="put")
    failed_ids = {payload.get("ItemID") for payload in failed_payloads}

    if failed_ids:
        logger.error(
            "Failed to persist %d reward items for %s; reverting their inventory slots",
            len(failed_ids),
            character_id,
        )
        reconciled_inventory = {
            slot: entry
            for slot, entry in normalized_inventory.items()
            if not (isinstance(entry, dict) and entry.get("ItemID") in failed_ids)
        }
        try:
            dynamo.update_item(
                TableName.CHARACTERS,
                Key={"CharacterID": character_id},
                UpdateExpression="SET Inventory = :inventory, UpdatedAt = :updated_at",
                ExpressionAttributeValues={
                    ":inventory": reconciled_inventory,
                    ":updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except ClientError as reconcile_err:
            logger.error(
                "Failed to reconcile inventory for %s after partial item write Error: %s",
                character_id,
                reconcile_err,
                exc_info=True,
            )

    granted_items = [payload["ItemID"] for _, payload in planned_items if payload["ItemID"] not in failed_ids]
    logger.info("Added %d item(s) to inventory for %s", len(granted_items), character_id)
    return granted_items


def create_items_from_prototypes(starting_items: list, character_id: str) -> dict:
    """
    Create item instances from starting item definitions.

    Every starting item gets a numbered slot in the returned inventory so
    the character record stays in sync with the ITEMS table. Worn equipment,
    containers, and loose items all land in the inventory; the first container
    additionally records loose items in its Contents field for deletion cleanup.

    Args:
        starting_items: List of dicts with PrototypeID, IsWorn, Slot, Container fields
        character_id: Character ID for logging

    Returns:
        Dict mapping slot numbers to item data.
        Non-stackable (equipment): {slot: {"ItemID": "..."}}
        Stackable (if any): {slot: {"ItemID": "...", "Quantity": count}}
    """
    if not starting_items:
        return {}

    try:
        inventory = {}
        slot_num = 0
        container_id = None
        items_for_container = []
        items_before_container = []
        items_to_create = []

        # First pass: Build all item payloads
        for item_def in starting_items:
            prototype_id = item_def.get("PrototypeID")
            is_worn = item_def.get("IsWorn", False)
            is_container = item_def.get("Container", False)

            prototype = get_prototype(prototype_id)

            if not prototype:
                logger.warning(f"Prototype not found for {prototype_id}")
                continue

            item_id = str(uuid.uuid4())
            item_data = build_item_payload(
                prototype,
                item_id,
                is_worn=is_worn,
                owner_id=character_id,
            )

            # Track first container
            if is_container and container_id is None:
                container_id = item_id
                # Update contents with items collected so far (items before container)
                item_data["Contents"] = items_for_container.copy()
                items_before_container = items_for_container.copy()
                # Clear the list for items after container
                items_for_container = []

            # Loose items (not worn, not a container) are also tracked on the
            # container's Contents list so character-deletion cleanup can recurse.
            if not is_worn and not is_container:
                items_for_container.append(item_id)

            # Add to batch write list
            items_to_create.append(item_data)

            # Every starting item gets an Inventory slot on the character.
            # Stackable entries carry Quantity; worn/container/non-stackable do not.
            slot_entry = {"ItemID": item_id}
            if prototype.get("Stackable", False):
                slot_entry["Quantity"] = item_data.get("Quantity", prototype.get("Quantity", 1))
            inventory[str(slot_num)] = slot_entry
            slot_num += 1

        # Batch write all items at once
        if items_to_create:
            failed = dynamo.batch_write_with_retries(TableName.ITEMS, items_to_create, operation="put")
            if failed:
                logger.warning(f"Failed to create {len(failed)} items for {character_id}")
            else:
                logger.info(f"Created {len(items_to_create)} items from prototypes for {character_id}")

        # After all items are created, update container with items added after it
        if container_id and items_for_container:
            # Combine items before and after container
            final_contents = items_before_container + items_for_container
            dynamo.update_item(
                TableName.ITEMS,
                Key={"ItemID": container_id},
                UpdateExpression="SET Contents = :contents",
                ExpressionAttributeValues={":contents": final_contents},
            )
            logger.info(f"Updated container {container_id} with total of {len(final_contents)} items")

        return inventory

    except Exception as err:
        logger.error(f"Error creating items from prototypes for {character_id} Error: {err}")
        return {}


def fetch_single_item_details(item_id: str, slot_data: list, enriched_inventory: dict) -> None:
    """Fetch a single item from DynamoDB and populate its inventory slots.

    Args:
        item_id: Item UUID to fetch
        slot_data: List of (slot, quantity) tuples for this item
        enriched_inventory: Dict to populate with item details
    """
    try:
        item = dynamo.get_item(TableName.ITEMS, {"ItemID": item_id})
    except ClientError as err:
        logger.error(f"Failed to get item {item_id} Error: {err}")
        for slot, quantity in slot_data:
            enriched_inventory[slot] = {
                "ItemID": item_id,
                "Name": "Error Loading Item",
                "Description": "Failed to load item details",
                "Quantity": quantity,
            }
        return

    if item:
        base_item_details = {
            "ItemID": item_id,
            "Name": item.get("Name", "Unknown Item"),
            "Description": item.get("Description", ""),
            "Stackable": item.get("Stackable", False),
            "Equipped": item.get("Equipped", item.get("IsWorn", False)),
            "Mass": item.get("Mass", 0),
            "Value": item.get("Value", 0),
            "Rarity": item.get("Rarity", "common"),
            "Type": item.get("Type", ""),
            "Consumable": item.get("Consumable", False),
            "WornOn": item.get("WornOn", ""),
        }
        for slot, quantity in slot_data:
            enriched_inventory[slot] = {**base_item_details, "Quantity": quantity}
    else:
        for slot, quantity in slot_data:
            enriched_inventory[slot] = {
                "ItemID": item_id,
                "Name": "Missing Item",
                "Description": "This item could not be loaded",
                "Quantity": quantity,
            }


def get_inventory(inventory: dict) -> dict:
    """
    Enrich inventory with item details for display.

    Args:
        inventory: Dict mapping slot to item data.
            Stackable: {slot: {"ItemID": "...", "Quantity": count}}
            Non-stackable: {slot: {"ItemID": "..."}} (no Quantity field)

    Returns:
        Dict mapping slot to enriched item details including name, description, and quantity.
        Quantity field always included in response: actual count for stackable, 0 for non-stackable.
    """
    if not inventory:
        return {}

    enriched_inventory = {}

    # Separate null/empty slots from actual item entries
    # Track both item_id and the slot's quantity
    item_slots = {}  # Maps item_id to list of (slot, quantity) tuples
    for slot, item_data in inventory.items():
        if not item_data:
            enriched_inventory[slot] = None
            continue

        # Extract ItemID and Quantity from new format
        if isinstance(item_data, dict):
            item_id = item_data.get("ItemID")
            # If Quantity field exists, use it (stackable)
            # If Quantity field missing, default to 0 (non-stackable)
            quantity = item_data.get("Quantity", 0)
        else:
            # Malformed entry
            logger.warning(f"Invalid inventory entry in slot {slot}: {item_data}")
            enriched_inventory[slot] = None
            continue

        if not item_id:
            enriched_inventory[slot] = None
        else:
            if item_id not in item_slots:
                item_slots[item_id] = []
            item_slots[item_id].append((slot, quantity))

    # If no actual items, return early
    if not item_slots:
        return enriched_inventory

    # Batch fetch all unique items
    unique_item_ids = list(item_slots.keys())
    item_keys = [{"ItemID": item_id} for item_id in unique_item_ids]

    try:
        # Use batch_get_items to fetch all items in one operation
        items_data = dynamo.batch_get_items(TableName.ITEMS, item_keys)

        # Create lookup map for fetched items (handle None or empty response)
        items_map = {}
        if items_data:
            items_map = {item["ItemID"]: item for item in items_data}

        # Process each item and its slots
        for item_id, slot_data in item_slots.items():
            item = items_map.get(item_id)

            if item:
                # Get base item data (shared across all slots with this item)
                base_item_details = {
                    "ItemID": item_id,
                    "Name": item.get("Name", "Unknown Item"),
                    "Description": item.get("Description", ""),
                    "Stackable": item.get("Stackable", False),
                    "Equipped": item.get("Equipped", item.get("IsWorn", False)),
                    "Mass": item.get("Mass", 0),
                    "Value": item.get("Value", 0),
                    "Rarity": item.get("Rarity", "common"),
                    "Type": item.get("Type", ""),
                    "Consumable": item.get("Consumable", False),
                    "WornOn": item.get("WornOn", ""),
                }

                # Assign to all slots with slot-specific quantity
                for slot, quantity in slot_data:
                    enriched_inventory[slot] = {
                        **base_item_details,
                        "Quantity": quantity,  # Use slot-specific quantity
                    }
            else:
                # Item not found - create missing item placeholder
                logger.warning(f"Item not found in inventory for {item_id}")
                for slot, quantity in slot_data:
                    enriched_inventory[slot] = {
                        "ItemID": item_id,
                        "Name": "Missing Item",
                        "Description": "This item could not be loaded",
                        "Quantity": quantity,
                    }

    except ClientError as err:
        logger.error(f"Failed to batch get item details Error: {err}")
        # Fall back to individual lookups on batch failure
        for item_id, slot_data in item_slots.items():
            fetch_single_item_details(item_id, slot_data, enriched_inventory)

    return enriched_inventory
