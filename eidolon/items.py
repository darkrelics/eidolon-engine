"""Item management functions for the Eidolon Engine."""

import uuid

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger


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

            # Get prototype data
            prototype = dynamo.get_item(TableName.PROTOTYPES, {"PrototypeID": prototype_id})

            if not prototype:
                logger.warning(f"Prototype not found for {prototype_id}")
                continue

            # Create new item from prototype
            item_id = str(uuid.uuid4())
            item_data = {
                "ItemID": item_id,
                "PrototypeID": prototype_id,
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
                "Contents": [],
                "IsWorn": is_worn,
                # Keep compatibility with any consumers that expect 'Equipped'
                "Equipped": is_worn,
                "CanPickUp": prototype.get("CanPickUp", True),
                "Metadata": prototype.get("Metadata", {}),
            }

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
                    "itemId": item_id,
                    "name": item.get("Name", "Unknown Item"),
                    "description": item.get("Description", ""),
                    "quantity": item.get("Quantity", 1),
                    "stackable": item.get("Stackable", False),
                    # Prefer 'Equipped', fall back to 'IsWorn' used at creation
                    "equipped": item.get("Equipped", item.get("IsWorn", False)),
                    "mass": item.get("Mass", 0),
                    "value": item.get("Value", 0),
                }

                # Assign to all slots that have this item
                for slot in slots:
                    enriched_inventory[slot] = item_details
            else:
                # Item not found - create missing item placeholder
                logger.warning(f"Item not found in inventory for {item_id}")
                missing_item = {
                    "itemId": item_id,
                    "name": "Missing Item",
                    "description": "This item could not be loaded",
                    "quantity": 0,
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
                        "itemId": item_id,
                        "name": item.get("Name", "Unknown Item"),
                        "description": item.get("Description", ""),
                        "quantity": item.get("Quantity", 1),
                        "stackable": item.get("Stackable", False),
                        "equipped": item.get("Equipped", item.get("IsWorn", False)),
                        "mass": item.get("Mass", 0),
                        "value": item.get("Value", 0),
                    }

                    for slot in slots:
                        enriched_inventory[slot] = item_details
                else:
                    for slot in slots:
                        enriched_inventory[slot] = {
                            "itemId": item_id,
                            "name": "Missing Item",
                            "description": "This item could not be loaded",
                            "quantity": 0,
                        }

            except ClientError as individual_err:
                logger.error(f"Failed to get item {item_id} Error: {individual_err}")
                for slot in slots:
                    enriched_inventory[slot] = {
                        "itemId": item_id,
                        "name": "Error Loading Item",
                        "description": "Failed to load item details",
                        "quantity": 0,
                    }

    return enriched_inventory
