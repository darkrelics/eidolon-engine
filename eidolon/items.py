"""Item management functions for the Eidolon Engine."""

import random
import uuid

from botocore.exceptions import ClientError

from eidolon.contents import PARENT_CHARACTER, append_to_contents
from eidolon.dynamo import TableName, dynamo
from eidolon.equipment import assign_starting_slot
from eidolon.errors import NotFoundError
from eidolon.logger import logger
from eidolon.prototypes import get_prototype, item_is_stackable


def load_top_level_stacks(top_level_ids: list, prototype_id: str) -> list:
    """Return ``(item_id, current_quantity)`` for top-level stackable items
    sharing ``prototype_id``.

    Shared by the purchase and story-reward paths so that buying and earning the
    same stackable item merge identically. Stackability is resolved from the
    prototype (the source of truth), not from any field copied onto the record.
    """
    matching: list = []
    for item_id in top_level_ids:
        if not item_id:
            continue
        try:
            record = dynamo.get_item(TableName.ITEMS, {"ItemID": item_id})
        except ClientError as err:
            logger.error(f"Failed to inspect item {item_id} for stack merge: {err}")
            continue
        if not record or record.get("PrototypeID") != prototype_id:
            continue
        if not item_is_stackable(record):
            continue
        matching.append((item_id, int(record.get("Quantity", 1) or 0)))
    return matching


def stack_merge_quantity(current_quantity: int, add_quantity: int, max_stack: int) -> int:
    """
    Calculate how much of add_quantity fits onto an existing stack.

    Args:
        current_quantity: Current stack quantity
        add_quantity: Quantity the caller wants to add
        max_stack: Maximum stack size from the prototype; zero or less means
            the stack is unbounded and everything fits

    Returns:
        The quantity to merge into this stack (0 if the stack is full)
    """
    # DynamoDB numbers arrive as float (decimal_to_float), so coerce to keep
    # quantities integral; trailing-zero floats must never reach Quantity fields.
    current_quantity = int(current_quantity)
    add_quantity = int(add_quantity)
    max_stack = int(max_stack)
    if max_stack <= 0:
        return add_quantity
    return min(add_quantity, max(0, max_stack - current_quantity))


def distribute_into_stacks(total_quantity: int, max_stack: int) -> list:
    """
    Split a quantity into MaxStack-compliant portions.

    Args:
        total_quantity: Total quantity to distribute
        max_stack: Maximum stack size; zero or less means unbounded, so the
            whole quantity goes into a single stack

    Returns:
        List of quantities, each <= max_stack (or one entry when unbounded)
    """
    # DynamoDB numbers arrive as float (decimal_to_float), so coerce to keep
    # quantities integral; trailing-zero floats must never reach Quantity fields.
    total_quantity = int(total_quantity)
    max_stack = int(max_stack)
    if total_quantity <= 0:
        return []
    if max_stack <= 0:
        return [total_quantity]

    stacks = []
    remaining = total_quantity
    while remaining > 0:
        stack_qty = min(remaining, max_stack)
        stacks.append(stack_qty)
        remaining -= stack_qty
    return stacks


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
        raise NotFoundError(f"Item {item_id} not found")

    prototype_id = item.get("PrototypeID")
    if not prototype_id:
        logger.error(f"Item {item_id} missing PrototypeID field")
        raise NotFoundError("Item data incomplete")

    # Resolve type properties from the prototype, the source of truth.
    prototype = get_prototype(prototype_id)
    is_stackable = prototype.get("Stackable", False) if prototype else False
    is_container = prototype.get("Container", False) if prototype else False
    is_worn = bool(item.get("IsWorn", False))

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
        raise NotFoundError(f"Prototype {prototype_id} not found")

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
    """Construct a minimal item instance that references its prototype.

    Items reference their prototype rather than copying it: type properties
    (name, mass, value, effects, trait mods) are resolved from the prototype at
    read time, so the persisted record carries only instance state. A stackable
    item stores a Quantity; a container stores its Contents; a wearable item
    stores its worn state. Nothing else is denormalized onto the record.

    Args:
        prototype: Prototype definition from DynamoDB
        item_id: UUID assigned to the instance
        is_worn: Whether a wearable item starts worn
        contents: Optional initial Contents list for containers
        quantity_override: Explicit quantity to persist for stackable items
        owner_id: Optional character UUID to persist as OwnerID
    """

    payload = {
        "ItemID": item_id,
        "PrototypeID": prototype.get("PrototypeID", ""),
    }

    if owner_id:
        payload["OwnerID"] = owner_id

    if prototype.get("Stackable", False):
        if quantity_override is not None:
            payload["Quantity"] = quantity_override
        else:
            payload["Quantity"] = prototype.get("Quantity", 1)
        return payload

    if prototype.get("Container", False):
        payload["Contents"] = contents if contents is not None else []

    if prototype.get("Wearable", False):
        payload["IsWorn"] = is_worn

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


def create_items_from_prototypes(starting_items: list, character_id: str) -> dict:
    """Create item instances from starting item definitions.

    The character is the base container: its Contents holds equipped items,
    containers, and any loose items that aren't placed inside another container.
    Loose items are nested inside the first container encountered (if any);
    otherwise they join the character's Contents directly. Items flagged worn are
    assigned an equipment slot, so a starting item is worn only when a slot backs
    it (the equipped invariant: a slot references the item and its IsWorn is set).

    Args:
        starting_items: List of dicts with PrototypeID, IsWorn, Container fields.
        character_id: Character ID for logging and OwnerID on each item.

    Returns:
        Dict with ``Contents`` (top-level ItemIDs) plus the ``LeftHandID``,
        ``RightHandID``, and ``WornSlots`` equipment assignments for worn items.
    """
    empty_result = {"Contents": [], "LeftHandID": None, "RightHandID": None, "WornSlots": {}}
    if not starting_items:
        return empty_result

    try:
        character_contents = []
        # Loose items flow into this bucket. Starts as a standalone list and
        # gets bound to the first container's Contents when one appears.
        loose_bucket = []
        first_container_seen = False
        items_to_create = []
        equipment = {"LeftHandID": None, "RightHandID": None, "WornSlots": {}}

        for item_def in starting_items:
            prototype = get_prototype(item_def.get("PrototypeID"))
            if not prototype:
                logger.warning(f"Prototype not found for {item_def.get('PrototypeID')}")
                continue

            item_id = str(uuid.uuid4())
            # A worn item stays worn only if a free, valid slot is available.
            assigned_slot = assign_starting_slot(prototype, equipment, item_id) if item_def.get("IsWorn") else ""
            item_data = build_item_payload(prototype, item_id, is_worn=bool(assigned_slot), owner_id=character_id)
            items_to_create.append(item_data)

            if item_def.get("Container"):
                if not first_container_seen:
                    # Adopt the bucket: items collected so far (and any that
                    # arrive later as loose) live inside this container.
                    item_data["Contents"] = list(loose_bucket)
                    loose_bucket = item_data["Contents"]
                    first_container_seen = True
                character_contents.append(item_id)
            elif assigned_slot:
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

        equipment["Contents"] = character_contents
        return equipment

    except Exception as err:
        logger.error(f"Error creating items from prototypes for {character_id} Error: {err}")
        return empty_result
