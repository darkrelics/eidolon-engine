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

    # UUIDv7 has timestamp, so lexicographic comparison gives older item
    if item1["ItemID"] < item2["ItemID"]:
        # item1 is older, keep its ID
        return {
            "ItemID": item1["ItemID"],
            "PrototypeID": item1["PrototypeID"],
            "Quantity": total_quantity,
            "OwnerID": item1.get("OwnerID"),
        }
    else:
        # item2 is older, keep its ID
        return {
            "ItemID": item2["ItemID"],
            "PrototypeID": item2["PrototypeID"],
            "Quantity": total_quantity,
            "OwnerID": item2.get("OwnerID"),
        }


def find_matching_stack(inventory: dict, prototype_id: str) -> tuple:
    """
    Find an existing stack in inventory that matches the prototype.

    Args:
        inventory: Dict mapping slot to item ID
        prototype_id: PrototypeID to find

    Returns:
        Tuple of (slot, item_dict) or empty tuple if no matching stack found
    """
    if not inventory or not prototype_id:
        return ()

    # Get prototype to check if stackable
    prototype = get_prototype(prototype_id)
    if not prototype or not prototype.get("Stackable", False):
        return ()

    # Check each item in inventory
    for slot, item_id in inventory.items():
        if not item_id:
            continue

        # Get the item from database
        try:
            item = dynamo.get_item(TableName.ITEMS, {"ItemID": item_id})
            if item and item.get("PrototypeID") == prototype_id:
                return (slot, item)
        except ClientError:
            continue

    return ()


def create_coins_from_value(value: int) -> list[dict]:
    """
    Convert a value amount into coin item creation requests.
    These are just regular item creation requests for coin prototypes.

    Args:
        value: Total value to convert to coins

    Returns:
        List of dicts with PrototypeID and Quantity for each coin type
    """
    if value <= 0:
        return []

    items_to_create = []

    # Calculate optimal coin distribution
    gold_coins = value // 2400
    remainder = value % 2400
    silver_coins = remainder // 120
    bronze_coins = (remainder % 120) // 10

    # Create coin item requests
    if gold_coins > 0:
        items_to_create.append({"PrototypeID": "6e9f1d4a-3c8b-4a7f-d2e5-8b3f6c9a1e7d", "Quantity": gold_coins})
    if silver_coins > 0:
        items_to_create.append({"PrototypeID": "8f5b3c9e-2d7a-4f8e-b6c1-9a4e7d2b5f3c", "Quantity": silver_coins})
    if bronze_coins > 0:
        items_to_create.append({"PrototypeID": "3d8a6f2e-1c4b-4e9f-a5d2-7b3e9f0c1d8a", "Quantity": bronze_coins})

    return items_to_create


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

    Returns only ItemID and PrototypeID for lightweight item loading.

    Args:
        item_id: Item UUID to fetch

    Returns:
        Dict containing ItemID and PrototypeID

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

    return {"ItemID": item_id, "PrototypeID": prototype_id}


def get_item_prototype_full(prototype_id: str) -> dict:
    """
    Retrieve complete item prototype definition for client-side caching.

    Returns the full prototype data including all properties, stats, and metadata.
    Prototypes are immutable game data and safe to cache indefinitely on client.

    Args:
        prototype_id: Prototype UUID to fetch

    Returns:
        Complete prototype data dict

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

    return prototype


def build_item_payload(
    prototype: dict,
    item_id: str,
    *,
    is_worn: bool = False,
    contents=None,
) -> dict:
    """Construct item payload from a prototype definition."""

    return {
        "ItemID": item_id,
        "PrototypeID": prototype.get("PrototypeID", ""),
        "Name": prototype.get("Name", "Unknown Item"),
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
    }


def create_item_from_prototype(
    prototype_id: str,
    *,
    is_worn: bool = False,
    initial_contents=None,
) -> dict:
    """Create a single item instance from a prototype and persist it."""

    if not prototype_id:
        logger.warning("Cannot create item: missing prototype ID")
        return {}

    prototype = get_prototype(prototype_id)
    if not prototype:
        logger.warning(f"Prototype not found for {prototype_id}")
        return {}

    item_id = str(uuid.uuid4())
    item_payload = build_item_payload(
        prototype,
        item_id,
        is_worn=is_worn,
        contents=initial_contents,
    )

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


def process_items_with_probability(items_data: list) -> list[str]:
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


def add_items_to_inventory(character_id: str, prototype_ids: list[str]) -> list[str]:
    """Create items from prototypes and append them to a character's inventory."""

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

    normalized_inventory = {str(key): value for key, value in inventory.items()}
    granted_items: list[str] = []

    for prototype_id in prototype_ids:
        if not isinstance(prototype_id, str) or not prototype_id:
            logger.warning("Skipping invalid prototype ID in story rewards for %s: %s", character_id, prototype_id)
            continue

        item_payload = create_item_from_prototype(prototype_id)
        if not item_payload:
            continue

        slot_key = find_next_available_slot(normalized_inventory)
        normalized_inventory[slot_key] = item_payload["ItemID"]
        granted_items.append(item_payload["ItemID"])

    if not granted_items:
        return []

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

    logger.info("Added %d item(s) to inventory for %s", len(granted_items), character_id)
    return granted_items


def create_items_from_prototypes(starting_items: list, character_id: str) -> dict:
    """
    Create item instances from starting item definitions.

    Args:
        starting_items: List of dicts with PrototypeID, IsWorn, Slot, Container fields
        character_id: Character ID for logging

    Returns:
        Dict mapping slot numbers to item UUIDs (only worn items and containers)
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
            )

            # Track first container
            if is_container and container_id is None:
                container_id = item_id
                # Update contents with items collected so far (items before container)
                item_data["Contents"] = items_for_container.copy()
                items_before_container = items_for_container.copy()
                # Clear the list for items after container
                items_for_container = []

            # If not worn and not a container, add to items list
            # These will go into the container if one exists or will be created
            if not is_worn and not is_container:
                items_for_container.append(item_id)

            # Add to batch write list
            items_to_create.append(item_data)

            # Add to inventory only if worn or is the container
            if is_worn or (is_container and item_id == container_id):
                inventory[str(slot_num)] = item_id
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


def get_inventory(inventory: dict) -> dict:
    """
    Enrich inventory with item details for display.

    Args:
        inventory: Dict mapping slot to item ID

    Returns:
        Dict mapping slot to item details including name and description
    """
    if not inventory:
        return {}

    enriched_inventory = {}

    # Separate null slots from actual item IDs
    item_slots = {}  # Maps item_id to list of slots
    for slot, item_id in inventory.items():
        if not item_id:
            enriched_inventory[slot] = None
        else:
            if item_id not in item_slots:
                item_slots[item_id] = []
            item_slots[item_id].append(slot)

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
        for item_id, slots in item_slots.items():
            item = items_map.get(item_id)

            if item:
                # Create enriched item data
                item_details = {
                    "ItemID": item_id,
                    "Name": item.get("Name", "Unknown Item"),
                    "Description": item.get("Description", ""),
                    "Quantity": item.get("Quantity", 1),
                    "Stackable": item.get("Stackable", False),
                    # Prefer 'Equipped', fall back to 'IsWorn' used at creation
                    "Equipped": item.get("Equipped", item.get("IsWorn", False)),
                    "Mass": item.get("Mass", 0),
                    "Value": item.get("Value", 0),
                }

                # Assign to all slots that have this item
                for slot in slots:
                    enriched_inventory[slot] = item_details
            else:
                # Item not found - create missing item placeholder
                logger.warning(f"Item not found in inventory for {item_id}")
                missing_item = {
                    "ItemID": item_id,
                    "Name": "Missing Item",
                    "Description": "This item could not be loaded",
                    "Quantity": 0,
                }

                for slot in slots:
                    enriched_inventory[slot] = missing_item

    except ClientError as err:
        logger.error(f"Failed to batch get item details Error: {err}")
        # Fall back to individual lookups on batch failure
        for item_id, slots in item_slots.items():
            try:
                item = dynamo.get_item(TableName.ITEMS, {"ItemID": item_id})

                if item:
                    item_details = {
                        "ItemID": item_id,
                        "Name": item.get("Name", "Unknown Item"),
                        "Description": item.get("Description", ""),
                        "Quantity": item.get("Quantity", 1),
                        "Stackable": item.get("Stackable", False),
                        "Equipped": item.get("Equipped", item.get("IsWorn", False)),
                        "Mass": item.get("Mass", 0),
                        "Value": item.get("Value", 0),
                    }

                    for slot in slots:
                        enriched_inventory[slot] = item_details
                else:
                    for slot in slots:
                        enriched_inventory[slot] = {
                            "ItemID": item_id,
                            "Name": "Missing Item",
                            "Description": "This item could not be loaded",
                            "Quantity": 0,
                        }

            except ClientError as individual_err:
                logger.error(f"Failed to get item {item_id} Error: {individual_err}")
                for slot in slots:
                    enriched_inventory[slot] = {
                        "ItemID": item_id,
                        "Name": "Error Loading Item",
                        "Description": "Failed to load item details",
                        "Quantity": 0,
                    }

    return enriched_inventory
