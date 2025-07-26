"""Item management functions for the Eidolon Engine."""

import uuid
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
