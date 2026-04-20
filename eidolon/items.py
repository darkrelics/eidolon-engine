"""Item management functions for the Eidolon Engine."""

import random
import uuid
from functools import cache

from botocore.exceptions import ClientError

from eidolon.contents import PARENT_CHARACTER, append_to_contents
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

    is_container = prototype.get("Container", False) if prototype else False
    is_worn = bool(item.get("IsWorn", item.get("Equipped", False)))

    # Build response with Quantity field for API consistency
    # Storage: stackable items have Quantity field, non-stackable don't
    # API response: always include Quantity (actual count or 0 for non-stackable)
    result = {
        "ItemID": item_id,
        "PrototypeID": prototype_id,
        "Container": is_container,
        "Contents": item.get("Contents", []) if is_container else [],
        "IsWorn": is_worn,
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
    """Create items from prototypes and append them to ``character.Contents``."""
    if not prototype_ids:
        return []

    planned_items: list = []
    new_ids: list = []

    for prototype_id in prototype_ids:
        if not isinstance(prototype_id, str) or not prototype_id:
            logger.warning("Skipping invalid prototype ID in story rewards for %s: %s", character_id, prototype_id)
            continue
        payload = build_item_from_prototype(prototype_id, owner_id=character_id)
        if not payload:
            continue
        planned_items.append(payload)
        new_ids.append(payload["ItemID"])

    if not planned_items:
        return []

    failed_payloads = dynamo.batch_write_with_retries(TableName.ITEMS, planned_items, operation="put")
    failed_ids = {payload.get("ItemID") for payload in failed_payloads}
    new_ids = [iid for iid in new_ids if iid not in failed_ids]

    if failed_ids:
        logger.error("Failed to persist %d reward items for %s", len(failed_ids), character_id)

    if new_ids:
        try:
            append_to_contents(PARENT_CHARACTER, character_id, new_ids)
        except RuntimeError as err:
            logger.error("Failed to append new items to character %s Contents: %s", character_id, err)
            return []

    logger.info("Added %d item(s) to inventory for %s", len(new_ids), character_id)
    return new_ids


def create_items_from_prototypes(starting_items: list, character_id: str) -> list:
    """Create item instances from starting item definitions.

    The character is the base container: its Contents holds equipped items,
    containers, and any loose items that aren't placed inside another container.
    Loose items are nested inside the first container encountered (if any);
    otherwise they join the character's Contents directly.

    Args:
        starting_items: List of dicts with PrototypeID, IsWorn, Container fields.
        character_id: Character ID for logging and OwnerID on each item.

    Returns:
        List of ItemIDs carried directly by the character.
    """
    if not starting_items:
        return []

    try:
        character_contents = []
        # Loose items flow into this bucket. Starts as a standalone list and
        # gets bound to the first container's Contents when one appears.
        loose_bucket = []
        first_container_seen = False
        items_to_create = []

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
            items_to_create.append(item_data)

            if is_container:
                if not first_container_seen:
                    # Adopt the bucket: items collected so far (and any that
                    # arrive later as loose) live inside this container.
                    item_data["Contents"] = list(loose_bucket)
                    loose_bucket = item_data["Contents"]
                    first_container_seen = True
                character_contents.append(item_id)
            elif is_worn:
                character_contents.append(item_id)
            else:
                loose_bucket.append(item_id)

        # No container ever appeared: loose items live directly on the character.
        if not first_container_seen:
            character_contents.extend(loose_bucket)

        if items_to_create:
            failed = dynamo.batch_write_with_retries(TableName.ITEMS, items_to_create, operation="put")
            if failed:
                logger.warning(f"Failed to create {len(failed)} items for {character_id}")
            else:
                logger.info(f"Created {len(items_to_create)} items from prototypes for {character_id}")

        return character_contents

    except Exception as err:
        logger.error(f"Error creating items from prototypes for {character_id} Error: {err}")
        return []


