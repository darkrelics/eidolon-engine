"""Equipment management for the Eidolon Engine.

An item is equipped when a character slot references it and the item's ``IsWorn``
flag is set. Hand-held items use the character's ``LeftHandID`` / ``RightHandID``
fields; everything else uses a ``WornSlots`` map ({slot: ItemID}) keyed by body
slot. The slot a given item may occupy is defined by its prototype's ``WornOn``
list, and equipping is allowed only for prototypes flagged ``Wearable``.

Equip and unequip are single transactions over two records (the character slot
and the item's ``IsWorn`` flag), each guarded by a conditional expression so a
race cannot leave a slot and an item disagreeing about what is worn.

Combat and any derived-stat calculation read the equipped set through
``compute_effective_combat_traits``, which sums each equipped item's prototype
``TraitMods`` into the character's attributes and skills. ``Overrides`` has no
defined semantics yet and is intentionally not consumed here.
"""

from botocore.exceptions import ClientError

from eidolon.contents import locate_item
from eidolon.dynamo import TABLE_ENV_MAP, TableName, dynamo, to_attribute_value
from eidolon.errors import ConflictError, NotFoundError, ValidationError
from eidolon.logger import logger
from eidolon.prototypes import get_prototype

HAND_SLOTS = {"left_hand", "right_hand"}
HAND_SLOT_FIELDS = {"left_hand": "LeftHandID", "right_hand": "RightHandID"}


def assign_starting_slot(prototype: dict, equipment: dict, item_id: str) -> str:
    """Assign the first free, valid slot to a worn starting item.

    Records the assignment in the ``equipment`` accumulator (the ``LeftHandID`` /
    ``RightHandID`` fields or the ``WornSlots`` map) and returns the slot name.
    Returns an empty string when the prototype is not wearable or every candidate
    slot from its ``WornOn`` list is already taken, so the caller can leave the
    item unworn rather than break the one-item-per-slot invariant.
    """
    if not prototype.get("Wearable", False):
        return ""

    worn_slots = equipment.setdefault("WornSlots", {})
    for slot in prototype.get("WornOn", []) or []:
        if slot in HAND_SLOTS:
            field = HAND_SLOT_FIELDS[slot]
            if not equipment.get(field):
                equipment[field] = item_id
                return slot
        elif slot not in worn_slots:
            worn_slots[slot] = item_id
            return slot

    return ""


def find_equipped_slot(character: dict, item_id: str) -> str:
    """Return the slot name currently holding ``item_id``, or an empty string.

    Checks the two hand fields first, then the ``WornSlots`` body-slot map.
    """
    if not character or not item_id:
        return ""

    for slot, field in HAND_SLOT_FIELDS.items():
        if character.get(field) == item_id:
            return slot

    for slot, equipped_id in (character.get("WornSlots") or {}).items():
        if equipped_id == item_id:
            return slot

    return ""


def gather_equipped_item_ids(character: dict) -> list:
    """Return the ItemIDs referenced by the character's equipment slots.

    Combines the two hand slots and the ``WornSlots`` body-slot map, preserving
    order and skipping duplicates.
    """
    item_ids: list = []
    seen: set = set()

    for field in ("LeftHandID", "RightHandID"):
        item_id = character.get(field)
        if item_id and item_id not in seen:
            seen.add(item_id)
            item_ids.append(item_id)

    for item_id in (character.get("WornSlots") or {}).values():
        if item_id and item_id not in seen:
            seen.add(item_id)
            item_ids.append(item_id)

    return item_ids


def gather_equipped_trait_mods(character: dict) -> dict:
    """Sum the ``TraitMods`` of every equipped item, resolved from its prototype.

    Returns a ``{trait: total}`` map. Type properties are read from the prototype
    (the source of truth), so an item carries only its ItemID in the slot.
    """
    totals: dict = {}
    for item_id in gather_equipped_item_ids(character):
        try:
            record = dynamo.get_item(TableName.ITEMS, {"ItemID": item_id}, ProjectionExpression="PrototypeID")
        except ClientError as err:
            logger.error(f"Failed to load equipped item {item_id} for trait mods: {err}")
            continue
        if not record:
            continue

        prototype = get_prototype(record.get("PrototypeID", ""))
        for trait, mod in (prototype.get("TraitMods", {}) or {}).items():
            totals[trait] = totals.get(trait, 0) + mod

    return totals


def compute_effective_combat_traits(character: dict) -> tuple:
    """Return ``(attributes, skills)`` with equipped trait mods folded in.

    Each equipped item's ``TraitMods`` are added to the matching trait: a mod
    whose name is an existing attribute boosts that attribute, otherwise it is
    applied to skills (where combat reads Melee, Parry, Dodge, and the rest).
    The character's stored attributes and skills are not mutated.
    """
    attributes = dict(character.get("Attributes", {}) or {})
    skills = dict(character.get("Skills", {}) or {})

    for trait, mod in gather_equipped_trait_mods(character).items():
        if trait in attributes:
            attributes[trait] = attributes.get(trait, 0) + mod
        else:
            skills[trait] = skills.get(trait, 0) + mod

    return attributes, skills


def build_equip_transaction(character_id: str, item_id: str, slot: str) -> list:
    """Build the atomic transaction that occupies a slot and marks an item worn.

    The character update is guarded so the slot must currently be empty, and the
    item update so it must not already be worn; either failing cancels the whole
    transaction.
    """
    item_values = {":true": to_attribute_value(True), ":false": to_attribute_value(False)}
    if slot in HAND_SLOTS:
        field = HAND_SLOT_FIELDS[slot]
        character_update = {
            "Update": {
                "TableName": TABLE_ENV_MAP[TableName.CHARACTERS],
                "Key": {"CharacterID": {"S": character_id}},
                "UpdateExpression": f"SET {field} = :item",
                "ConditionExpression": f"attribute_not_exists({field})",
                "ExpressionAttributeValues": {":item": to_attribute_value(item_id)},
            }
        }
    else:
        character_update = {
            "Update": {
                "TableName": TABLE_ENV_MAP[TableName.CHARACTERS],
                "Key": {"CharacterID": {"S": character_id}},
                "UpdateExpression": "SET WornSlots.#slot = :item",
                "ConditionExpression": "attribute_not_exists(WornSlots.#slot)",
                "ExpressionAttributeNames": {"#slot": slot},
                "ExpressionAttributeValues": {":item": to_attribute_value(item_id)},
            }
        }

    item_update = {
        "Update": {
            "TableName": TABLE_ENV_MAP[TableName.ITEMS],
            "Key": {"ItemID": {"S": item_id}},
            "UpdateExpression": "SET IsWorn = :true",
            "ConditionExpression": "attribute_not_exists(IsWorn) OR IsWorn = :false",
            "ExpressionAttributeValues": item_values,
        }
    }

    return [character_update, item_update]


def build_unequip_transaction(character_id: str, item_id: str, slot: str) -> list:
    """Build the atomic transaction that frees a slot and clears an item's worn flag.

    The character update is guarded so the slot must still hold ``item_id``.
    """
    if slot in HAND_SLOTS:
        field = HAND_SLOT_FIELDS[slot]
        character_update = {
            "Update": {
                "TableName": TABLE_ENV_MAP[TableName.CHARACTERS],
                "Key": {"CharacterID": {"S": character_id}},
                "UpdateExpression": f"REMOVE {field}",
                "ConditionExpression": f"{field} = :item",
                "ExpressionAttributeValues": {":item": to_attribute_value(item_id)},
            }
        }
    else:
        character_update = {
            "Update": {
                "TableName": TABLE_ENV_MAP[TableName.CHARACTERS],
                "Key": {"CharacterID": {"S": character_id}},
                "UpdateExpression": "REMOVE WornSlots.#slot",
                "ConditionExpression": "WornSlots.#slot = :item",
                "ExpressionAttributeNames": {"#slot": slot},
                "ExpressionAttributeValues": {":item": to_attribute_value(item_id)},
            }
        }

    item_update = {
        "Update": {
            "TableName": TABLE_ENV_MAP[TableName.ITEMS],
            "Key": {"ItemID": {"S": item_id}},
            "UpdateExpression": "SET IsWorn = :false",
            "ExpressionAttributeValues": {":false": to_attribute_value(False)},
        }
    }

    return [character_update, item_update]


def equip_item(character: dict, item_id: str, slot: str) -> dict:
    """Equip an owned, wearable item into a valid, empty slot.

    Validates that the item is in the character's inventory, that its prototype
    is wearable and permits ``slot``, and that the item is not already worn, then
    commits the slot occupancy and the item's worn flag atomically.

    Raises:
        NotFoundError: If the item or its prototype is missing.
        ValidationError: If the item is not wearable or cannot use ``slot``.
        ConflictError: If the item is already worn or the slot is occupied.
        RuntimeError: If the transaction fails for a non-conditional reason.
    """
    character_id = character.get("CharacterID", "")

    location = locate_item(character, item_id)
    if not location.get("found"):
        raise NotFoundError("Item not found in character inventory")

    item_record = location.get("item_record") or {}
    prototype_id = item_record.get("PrototypeID")
    if not prototype_id:
        raise NotFoundError("Item prototype reference missing")

    prototype = get_prototype(prototype_id)
    if not prototype:
        raise NotFoundError("Item prototype not found")
    if not prototype.get("Wearable", False):
        raise ValidationError("Item is not wearable")

    allowed_slots = prototype.get("WornOn", []) or []
    if slot not in allowed_slots:
        raise ValidationError(f"Item cannot be equipped to slot '{slot}'")

    if item_record.get("IsWorn", False):
        raise ConflictError("Item is already equipped")

    try:
        dynamo.transact_write_items(build_equip_transaction(character_id, item_id, slot))
    except ClientError as err:
        if err.response.get("Error", {}).get("Code") == "TransactionCanceledException":
            logger.warning(f"Equip cancelled for item {item_id} slot {slot} (race or occupied)")
            raise ConflictError("Slot is occupied or item state changed. Refresh and retry.") from err
        logger.error(f"Failed to equip item {item_id} for character {character_id}: {err}")
        raise RuntimeError("Failed to equip item") from err

    logger.info(f"Equipped item {item_id} to slot {slot} for character {character_id}")
    return {"Success": True, "ItemID": item_id, "Slot": slot, "PrototypeID": prototype_id}


def unequip_item(character: dict, item_id: str) -> dict:
    """Unequip an item from whichever slot currently holds it.

    Raises:
        ConflictError: If the item is not currently equipped or a race frees it
            first.
        RuntimeError: If the transaction fails for a non-conditional reason.
    """
    character_id = character.get("CharacterID", "")

    slot = find_equipped_slot(character, item_id)
    if not slot:
        raise ConflictError("Item is not currently equipped")

    try:
        dynamo.transact_write_items(build_unequip_transaction(character_id, item_id, slot))
    except ClientError as err:
        if err.response.get("Error", {}).get("Code") == "TransactionCanceledException":
            logger.warning(f"Unequip cancelled for item {item_id} slot {slot} (race)")
            raise ConflictError("Item state changed. Refresh and retry.") from err
        logger.error(f"Failed to unequip item {item_id} for character {character_id}: {err}")
        raise RuntimeError("Failed to unequip item") from err

    logger.info(f"Unequipped item {item_id} from slot {slot} for character {character_id}")
    return {"Success": True, "ItemID": item_id, "Slot": slot}
