"""Item management functions for the Eidolon Engine."""

import uuid
from botocore.exceptions import ClientError

from eidolon.logger import get_logger
from eidolon.dynamo import TableName, dynamo

logger = get_logger(__name__)


def create_items_from_prototypes(prototype_ids: list[str], character_id: str) -> dict[str, str]:
    """
    Create item instances from prototype IDs.

    Args:
        prototype_ids: List of prototype IDs to instantiate
        character_id: Character ID for logging

    Returns:
        Dict mapping slot numbers to item UUIDs
    """
    if not prototype_ids:
        return {}

    try:
        inventory = {}
        slot_num = 0

        for prototype_id in prototype_ids:
            # Get prototype data
            prototype = dynamo.get_item(TableName.PROTOTYPES, {"PrototypeID": prototype_id})

            if not prototype:
                logger.warning(
                    "Prototype not found",
                    extra={"prototype_id": prototype_id, "character_id": character_id},
                )
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
                "IsWorn": False,
                "CanPickUp": prototype.get("CanPickUp", True),
                "Metadata": prototype.get("Metadata", {}),
            }

            # Put item in Items table
            dynamo.put_item(TableName.ITEMS, item_data)

            # Add to inventory
            inventory[str(slot_num)] = item_id
            slot_num += 1

            logger.info(
                "Created item from prototype",
                extra={
                    "item_id": item_id,
                    "prototype_id": prototype_id,
                    "item_name": item_data["Name"],
                    "character_id": character_id,
                    "slot": str(slot_num - 1),
                },
            )

        return inventory

    except Exception as err:
        logger.error(
            "Error creating items from prototypes",
            extra={
                "error": str(err),
                "character_id": character_id,
                "prototype_count": len(prototype_ids),
            },
        )
        return {}


def get_inventory_details(inventory: dict) -> dict:
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

    for slot, item_id in inventory.items():
        if not item_id:
            enriched_inventory[slot] = None
            continue

        try:
            # Get item details
            item = dynamo.get_item(TableName.ITEMS, {"ItemID": item_id})

            if item:
                enriched_inventory[slot] = {
                    "itemId": item_id,
                    "name": item.get("Name", "Unknown Item"),
                    "description": item.get("Description", ""),
                    "quantity": item.get("Quantity", 1),
                    "stackable": item.get("Stackable", False),
                    "equipped": item.get("Equipped", False),
                    "mass": item.get("Mass", 0),
                    "value": item.get("Value", 0),
                }
            else:
                logger.warning("Item not found in inventory", extra={"item_id": item_id, "slot": slot})
                enriched_inventory[slot] = {
                    "itemId": item_id,
                    "name": "Missing Item",
                    "description": "This item could not be loaded",
                    "quantity": 0,
                }

        except ClientError as err:
            logger.error("Failed to get item details", extra={"item_id": item_id, "slot": slot, "error": str(err)})
            enriched_inventory[slot] = {
                "itemId": item_id,
                "name": "Error Loading Item",
                "description": "Failed to load item details",
                "quantity": 0,
            }

    return enriched_inventory
