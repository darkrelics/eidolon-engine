"""Item management functions for the Eidolon Engine."""

import uuid
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger


def build_item_payload(
    prototype: dict,
    item_id: str,
    *,
    is_worn: bool = False,
    contents: list[str] | None = None,
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
    initial_contents: list[str] | None = None,
) -> dict | None:
    """Create a single item instance from a prototype and persist it."""

    if not prototype_id:
        logger.warning("Cannot create item: missing prototype ID")
        return None

    prototype = dynamo.get_item(TableName.PROTOTYPES, {"PrototypeID": prototype_id})
    if not prototype:
        logger.warning(f"Prototype not found for {prototype_id}")
        return None

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
        return None


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
        items_before_container = []  # Track items that went into container at creation

        # Single pass through all items
        for item_def in starting_items:
            prototype_id = item_def.get("PrototypeID")
            is_worn = item_def.get("IsWorn", False)
            is_container = item_def.get("Container", False)

            prototype = dynamo.get_item(TableName.PROTOTYPES, {"PrototypeID": prototype_id})

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
                items_before_container = items_for_container.copy()  # Remember what we put in
                # Clear the list for items after container
                items_for_container = []

            # If not worn and not a container, add to items list
            # These will go into the container if one exists or will be created
            if not is_worn and not is_container:
                items_for_container.append(item_id)

            # Put item in Items table
            dynamo.put_item(TableName.ITEMS, item_data)

            # Add to inventory only if worn or is the container
            if is_worn or (is_container and item_id == container_id):
                inventory[str(slot_num)] = item_id
                slot_num += 1

            logger.info(f"Created item from prototype for {character_id}")

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
