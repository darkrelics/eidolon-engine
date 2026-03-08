"""Consumable item functions for the Eidolon Engine."""

from datetime import datetime, timezone
from decimal import Decimal

from botocore.exceptions import ClientError

from eidolon.character_state import determine_character_state_from_wounds
from eidolon.constants import CharState
from eidolon.dynamo import TABLE_ENV_MAP, TableName, dynamo
from eidolon.environment import DEFAULT_ESSENCE, DEFAULT_HEALTH
from eidolon.items import get_prototype
from eidolon.logger import logger


def coerce_int(value, default: int = 0) -> int:
    """Convert DynamoDB numeric values to int safely."""
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except TypeError as err:
            logger.debug(f"Type error parsing quantity value: {err}")
            return default
        except ValueError as err:
            logger.debug(f"Value error parsing quantity value: {err}")
            return default
    return default


def normalize_effect_config(effects) -> dict:
    """Normalize consumable effect configuration keys."""
    if not isinstance(effects, dict):
        return {}

    normalized = {}
    for key, value in effects.items():
        if not isinstance(key, str):
            continue
        normalized[key.lower()] = value
    return normalized


def remove_wounds(wounds: list, amount: int, priority=None) -> tuple:
    """Remove up to `amount` wounds following optional priority ordering."""
    if amount <= 0 or not isinstance(wounds, list) or not wounds:
        return wounds or [], []

    # Copy wounds to avoid mutating original objects
    remaining: list = []
    for wound in wounds:
        if isinstance(wound, dict):
            remaining.append(dict(wound))
        else:
            logger.warning("Encountered malformed wound entry while applying healing: %s", wound)

    if not remaining:
        return [], []

    removal_order = []
    if priority:
        seen = set()
        for entry in priority:
            entry_lower = str(entry).lower()
            if entry_lower not in seen:
                seen.add(entry_lower)
                removal_order.append(entry_lower)

    if "any" not in removal_order:
        removal_order.append("any")

    removed: list = []

    def pop_match(target: str) -> bool:
        for index, wound in enumerate(remaining):
            damage_type = str(wound.get("DamageType", "")).lower()
            if target == "any" or damage_type == target:
                removed.append(remaining.pop(index))
                return True
        return False

    for target in removal_order:
        while len(removed) < amount and pop_match(target):
            continue
        if len(removed) >= amount:
            break

    while len(removed) < amount and remaining:
        removed.append(remaining.pop(0))

    return remaining, removed


def dynamo_typed_value(value) -> dict:
    """Convert a Python value to a DynamoDB typed attribute value dict."""
    if isinstance(value, str):
        return {"S": value}
    if isinstance(value, bool):
        return {"BOOL": value}
    if isinstance(value, (int, float, Decimal)):
        return {"N": str(value)}
    if isinstance(value, list):
        return {"L": [dynamo_typed_value(v) for v in value]}
    if isinstance(value, dict):
        return {"M": {k: dynamo_typed_value(v) for k, v in value.items()}}
    if value is None:
        return {"NULL": True}
    return {"S": str(value)}


def build_consume_transaction(
    character_id: str, item_id: str, slot_key: str, inventory: dict,
    update_expression_parts: list, expression_values: dict, expression_names: dict,
    stackable: bool, item_removed: bool, remaining_quantity: int, timestamp: str,
) -> list:
    """Build the list of transactional write items for consume_item."""
    # Convert expression values to DynamoDB typed format for transactions
    typed_values = {k: dynamo_typed_value(v) for k, v in expression_values.items()}
    typed_values[":expected_item_id"] = {"S": item_id}

    typed_names = dict(expression_names)
    typed_names["#slot"] = slot_key

    character_update = {
        "Update": {
            "TableName": TABLE_ENV_MAP[TableName.CHARACTERS],
            "Key": {"CharacterID": {"S": character_id}},
            "UpdateExpression": "SET " + ", ".join(update_expression_parts),
            "ConditionExpression": "Inventory.#slot.ItemID = :expected_item_id",
            "ExpressionAttributeValues": typed_values,
            "ExpressionAttributeNames": typed_names,
        }
    }

    transact_items = [character_update]

    if stackable and not item_removed:
        transact_items.append({
            "Update": {
                "TableName": TABLE_ENV_MAP[TableName.ITEMS],
                "Key": {"ItemID": {"S": item_id}},
                "UpdateExpression": "SET Quantity = :quantity, UpdatedAt = :updated_at",
                "ExpressionAttributeValues": {
                    ":quantity": {"N": str(remaining_quantity)},
                    ":updated_at": {"S": timestamp},
                },
            }
        })
    else:
        transact_items.append({
            "Delete": {
                "TableName": TABLE_ENV_MAP[TableName.ITEMS],
                "Key": {"ItemID": {"S": item_id}},
            }
        })

    return transact_items


def load_character_for_consumption(character_id: str, item_id: str) -> dict:
    """Load character and find the inventory slot containing the target item.

    Args:
        character_id: Character UUID.
        item_id: Item UUID to find in inventory.

    Returns:
        Dict with keys: character, slot_key, slot_entry, inventory.

    Raises:
        ValueError: If character not found, in active story, or item not in inventory.
        RuntimeError: If database lookup fails.
    """
    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
    except ClientError as err:
        logger.error("Failed to load character %s Error: %s", character_id, err, exc_info=True)
        raise RuntimeError("Failed to load character") from err

    if not character:
        raise ValueError("Character not found")
    if character.get("ActiveStoryID"):
        raise ValueError("Cannot consume items during an active story")

    inventory_raw = character.get("Inventory", {})
    if not isinstance(inventory_raw, dict):
        inventory_raw = {}

    inventory: dict = {str(key): value for key, value in inventory_raw.items()}
    slot_key = None
    slot_entry = None
    for key, value in inventory.items():
        if isinstance(value, dict) and value.get("ItemID") == item_id:
            slot_key = key
            slot_entry = value
            break

    if slot_key is None or slot_entry is None:
        raise ValueError("Item is not in character inventory")

    return {"character": character, "slot_key": slot_key, "slot_entry": slot_entry, "inventory": inventory}


def load_item_and_prototype(item_id: str) -> dict:
    """Load and validate the item and its prototype for consumption.

    Args:
        item_id: Item UUID.

    Returns:
        Dict with keys: item, prototype, effects.

    Raises:
        ValueError: If item not found, not consumable, or missing effects.
        RuntimeError: If database lookup fails.
    """
    try:
        item = dynamo.get_item(TableName.ITEMS, {"ItemID": item_id})
    except ClientError as err:
        logger.error("Failed to load item %s Error: %s", item_id, err, exc_info=True)
        raise RuntimeError("Failed to load item") from err

    if not item:
        raise ValueError("Item not found")

    prototype_id = item.get("PrototypeID")
    if not prototype_id:
        raise ValueError("Item prototype reference missing")

    prototype = get_prototype(prototype_id)
    if not prototype:
        raise ValueError("Item prototype not found")

    consumable_flag = bool(prototype.get("Consumable", item.get("Consumable", False)))
    if not consumable_flag:
        raise ValueError("Item is not consumable")

    effects_config = (
        prototype.get("ConsumableEffects") or item.get("ConsumableEffects")
        or prototype.get("Effects") or item.get("Effects")
    )
    effects = normalize_effect_config(effects_config)
    if not effects:
        raise ValueError("Consumable item is missing effects configuration")

    return {"item": item, "prototype": prototype, "effects": effects}


def load_consumable_context(character_id: str, item_id: str) -> dict:
    """Load and validate character, item, prototype, and inventory slot for consumption.

    Args:
        character_id: Character UUID.
        item_id: Item UUID.

    Returns:
        Dict with keys: character, item, prototype, slot_key, slot_entry,
        inventory, effects.

    Raises:
        ValueError: If validation fails.
        RuntimeError: If database operations fail.
    """
    if not character_id or not item_id:
        raise ValueError("CharacterID and ItemID are required")

    char_ctx = load_character_for_consumption(character_id, item_id)
    item_ctx = load_item_and_prototype(item_id)

    return {
        "character": char_ctx.get("character"),
        "item": item_ctx.get("item"),
        "prototype": item_ctx.get("prototype"),
        "slot_key": char_ctx.get("slot_key"),
        "slot_entry": char_ctx.get("slot_entry"),
        "inventory": char_ctx.get("inventory"),
        "effects": item_ctx.get("effects"),
    }


def no_heal_result(wounds: list) -> dict:
    """Return a no-op heal effect result preserving the current wounds."""
    return {"effect_summary": {}, "updated_wounds": list(wounds), "removed_wounds": [], "effect_applied": False}


def apply_heal_effect(effects: dict, wounds: list, max_health: int, prototype_id: str) -> dict:
    """Apply wound healing from consumable effects configuration.

    Args:
        effects: Normalized effects config dict.
        wounds: Current list of wound dicts.
        max_health: Character maximum health.
        prototype_id: Prototype ID for logging.

    Returns:
        Dict with keys: effect_summary, updated_wounds, removed_wounds, effect_applied.
    """
    heal_config = effects.get("healwounds") or effects.get("heal") or effects.get("health")
    if heal_config is None:
        return no_heal_result(wounds)

    heal_amount = 0
    damage_priority = None
    if isinstance(heal_config, dict):
        heal_amount = coerce_int(heal_config.get("Amount"), 0)
        priority_raw = heal_config.get("DamageTypes")
        if isinstance(priority_raw, list):
            damage_priority = [str(entry).lower() for entry in priority_raw]
    else:
        heal_amount = coerce_int(heal_config, 0)

    if heal_amount <= 0:
        logger.warning("Heal effect defined for %s but no positive amount provided", prototype_id)
        return no_heal_result(wounds)

    updated_wounds, removed_wounds = remove_wounds(list(wounds), heal_amount, damage_priority)
    removed_count = len(removed_wounds)
    damage_types = [w.get("DamageType") for w in removed_wounds if isinstance(w, dict)]
    effect_summary = {"healWounds": {"requested": heal_amount, "removed": removed_count, "damageTypes": damage_types}}

    return {
        "effect_summary": effect_summary,
        "updated_wounds": updated_wounds,
        "removed_wounds": removed_wounds,
        "effect_applied": removed_count > 0,
    }


def apply_essence_effect(effects: dict, character: dict) -> dict:
    """Apply essence restoration from consumable effects configuration.

    Args:
        effects: Normalized effects config dict.
        character: Character data dict from DynamoDB.

    Returns:
        Dict with keys: effect_summary, new_essence, essence_changed, effect_applied.
    """
    essence_config = effects.get("restoreessence") or effects.get("essence")
    if essence_config is None:
        return {"effect_summary": {}, "new_essence": None, "essence_changed": False, "effect_applied": False}

    essence_amount = 0
    if isinstance(essence_config, dict):
        essence_amount = coerce_int(essence_config.get("Amount"), 0)
    else:
        essence_amount = coerce_int(essence_config, 0)

    current_essence = coerce_int(character.get("Essence"), DEFAULT_ESSENCE)
    max_essence = coerce_int(character.get("MaxEssence"), DEFAULT_ESSENCE)

    if max_essence <= 0:
        max_essence = DEFAULT_ESSENCE

    if essence_amount > 0 and current_essence < max_essence:
        new_essence = min(max_essence, current_essence + essence_amount)
        essence_delta = new_essence - current_essence
        if essence_delta > 0:
            summary = {
                "restoreEssence": {
                    "requested": essence_amount,
                    "restored": essence_delta,
                    "result": new_essence,
                    "max": max_essence,
                }
            }
            return {"effect_summary": summary, "new_essence": new_essence, "essence_changed": True, "effect_applied": True}

    summary = {
        "restoreEssence": {
            "requested": essence_amount,
            "restored": 0,
            "result": current_essence,
            "max": max_essence,
        }
    }
    return {"effect_summary": summary, "new_essence": None, "essence_changed": False, "effect_applied": False}


def update_inventory_for_consumption(
    inventory: dict, slot_key: str, slot_entry: dict, item: dict, item_id: str,
) -> dict:
    """Handle stackable and non-stackable item consumption in inventory.

    Args:
        inventory: Character inventory dict (will be mutated).
        slot_key: Inventory slot key containing the item.
        slot_entry: Inventory slot entry dict.
        item: Item data dict from DynamoDB.
        item_id: Item UUID.

    Returns:
        Dict with keys: inventory, remaining_quantity, item_removed, inventory_changed.
    """
    stackable = bool(item.get("Stackable"))
    current_quantity = coerce_int(slot_entry.get("Quantity", item.get("Quantity", 1)), 1)
    remaining_quantity = 0
    item_removed = False

    if stackable:
        new_quantity = max(0, current_quantity - 1)
        remaining_quantity = new_quantity
        if new_quantity > 0:
            for key, value in inventory.items():
                if isinstance(value, dict) and value.get("ItemID") == item_id:
                    existing = dict(value)
                    existing["Quantity"] = new_quantity
                    inventory[key] = existing
        else:
            inventory.pop(slot_key, None)
            item_removed = True
    else:
        inventory.pop(slot_key, None)
        item_removed = True

    return {
        "inventory": inventory,
        "remaining_quantity": remaining_quantity,
        "item_removed": item_removed,
        "inventory_changed": True,
    }


def build_character_update_expression(
    inventory_changed: bool, inventory: dict,
    wounds_changed: bool, new_wounds: list,
    essence_changed: bool, new_essence: int,
    state_changed: bool, new_state: str, old_state: str,
) -> dict:
    """Build the DynamoDB update expression for character changes after consumption.

    Args:
        inventory_changed: Whether inventory was modified.
        inventory: Updated inventory dict.
        wounds_changed: Whether wounds were modified.
        new_wounds: Updated wounds list.
        essence_changed: Whether essence was modified.
        new_essence: New essence value.
        state_changed: Whether character state changed.
        new_state: New character state value.
        old_state: Previous character state value.

    Returns:
        Dict with keys: update_expression_parts, expression_values, expression_names.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    update_expression_parts = ["UpdatedAt = :updated_at"]
    expression_values: dict = {":updated_at": timestamp}
    expression_names = {}

    if inventory_changed:
        update_expression_parts.append("Inventory = :inventory")
        expression_values[":inventory"] = inventory
    if wounds_changed:
        update_expression_parts.append("Wounds = :wounds")
        expression_values[":wounds"] = new_wounds
    if essence_changed and new_essence is not None:
        update_expression_parts.append("Essence = :essence")
        expression_values[":essence"] = Decimal(str(new_essence))
    if state_changed:
        update_expression_parts.append("CharState = :char_state")
        expression_values[":char_state"] = new_state

    return {
        "update_expression_parts": update_expression_parts,
        "expression_values": expression_values,
        "expression_names": expression_names,
        "timestamp": timestamp,
    }


def apply_consumable_effects(ctx: dict) -> dict:
    """Apply heal and essence effects from a consumable item context.

    Args:
        ctx: Context dict from load_consumable_context.

    Returns:
        Dict with keys: effect_summary, wounds_changed, new_wounds,
        character_state_before, new_char_state.

    Raises:
        ValueError: If neither effect was applied.
    """
    character = ctx.get("character", {})
    item = ctx.get("item", {})
    wounds = character.get("Wounds") or []
    if not isinstance(wounds, list):
        wounds = []
    max_health = coerce_int(character.get("MaxHealth"), DEFAULT_HEALTH)

    heal_result = apply_heal_effect(ctx.get("effects", {}), wounds, max_health, item.get("PrototypeID"))
    essence_result = apply_essence_effect(ctx.get("effects", {}), character)

    if not heal_result.get("effect_applied") and not essence_result.get("effect_applied"):
        raise ValueError("The item has no effect right now")

    effect_summary = {}
    effect_summary.update(heal_result.get("effect_summary", {}))
    effect_summary.update(essence_result.get("effect_summary", {}))

    wounds_changed = bool(heal_result.get("removed_wounds"))
    new_wounds = heal_result.get("updated_wounds", wounds)
    character_state_before = character.get("CharState", CharState.STANDING.value)
    new_char_state = character_state_before
    if wounds_changed:
        new_char_state = determine_character_state_from_wounds(max_health, new_wounds)

    return {
        "effect_summary": effect_summary,
        "essence_result": essence_result,
        "wounds_changed": wounds_changed,
        "new_wounds": new_wounds,
        "character_state_before": character_state_before,
        "new_char_state": new_char_state,
    }


def consume_item(character_id: str, item_id: str) -> dict:
    """Consume an item from a character's inventory and apply its effects.

    Args:
        character_id: Character UUID.
        item_id: Item UUID.

    Returns:
        Dict describing the applied effects and inventory changes.

    Raises:
        ValueError: If validation fails (missing item, not consumable, effect wasted).
        RuntimeError: If database operations fail.
    """
    ctx = load_consumable_context(character_id, item_id)
    item = ctx.get("item", {})
    fx = apply_consumable_effects(ctx)

    inv_result = update_inventory_for_consumption(
        ctx.get("inventory", {}), ctx.get("slot_key", ""), ctx.get("slot_entry", {}), item, item_id,
    )

    state_changed = fx.get("new_char_state") != fx.get("character_state_before")
    essence_result = fx.get("essence_result", {})
    expr = build_character_update_expression(
        inv_result.get("inventory_changed", False), inv_result.get("inventory", {}),
        fx.get("wounds_changed", False), fx.get("new_wounds", []),
        essence_result.get("essence_changed", False), essence_result.get("new_essence", 0),
        state_changed, fx.get("new_char_state", ""), fx.get("character_state_before", ""),
    )

    transact_items = build_consume_transaction(
        character_id, item_id, ctx.get("slot_key", ""), inv_result.get("inventory", {}),
        expr.get("update_expression_parts", []), expr.get("expression_values", {}),
        expr.get("expression_names", {}), bool(item.get("Stackable")),
        inv_result.get("item_removed", False), inv_result.get("remaining_quantity", 0),
        expr.get("timestamp", ""),
    )

    execute_consume_transaction(
        transact_items, fx.get("character_state_before", ""), fx.get("new_char_state", ""),
        ctx.get("character", {}), expr.get("timestamp", ""), character_id, item_id,
    )

    return build_consume_result(
        ctx.get("prototype", {}), item, fx.get("effect_summary", {}),
        inv_result.get("remaining_quantity", 0), inv_result.get("item_removed", False),
        fx.get("new_char_state", ""), character_id, item.get("PrototypeID", ""), item_id,
    )


def execute_consume_transaction(
    transact_items: list, character_state_before: str, new_char_state: str,
    character: dict, timestamp: str, character_id: str, item_id: str,
) -> None:
    """Execute the DynamoDB transaction for item consumption.

    Appends a player table update if the character is being revived from death,
    then executes the transactional write.

    Args:
        transact_items: List of transactional write items.
        character_state_before: Character state before consumption.
        new_char_state: Character state after consumption.
        character: Character data dict.
        timestamp: ISO format timestamp string.
        character_id: Character UUID.
        item_id: Item UUID.

    Raises:
        ValueError: If item was already consumed (race condition).
        RuntimeError: If the transaction fails.
    """
    if character_state_before == CharState.DEAD.value and new_char_state != CharState.DEAD.value:
        player_id = character.get("PlayerID")
        character_name = character.get("CharacterName")
        if player_id and character_name:
            transact_items.append({
                "Update": {
                    "TableName": TABLE_ENV_MAP[TableName.PLAYERS],
                    "Key": {"PlayerID": {"S": player_id}},
                    "UpdateExpression": "SET CharacterList.#name.Dead = :dead, UpdatedAt = :updated_at",
                    "ExpressionAttributeNames": {"#name": character_name},
                    "ExpressionAttributeValues": {":dead": {"BOOL": False}, ":updated_at": {"S": timestamp}},
                }
            })

    try:
        dynamo.transact_write_items(transact_items)
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code == "TransactionCanceledException":
            reasons = err.response.get("CancellationReasons", [])
            first_reason = reasons[0].get("Code", "") if reasons else ""
            if first_reason == "ConditionalCheckFailed":
                logger.warning("Item %s already consumed (race condition) for character %s", item_id, character_id)
                raise ValueError("Item has already been consumed") from err
        logger.error("Failed to consume item %s for character %s Error: %s", item_id, character_id, err, exc_info=True)
        raise RuntimeError("Failed to update character after consumption") from err


def build_consume_result(
    prototype: dict, item: dict, effect_summary: dict,
    remaining_quantity: int, item_removed: bool,
    new_char_state: str, character_id: str, prototype_id: str, item_id: str,
) -> dict:
    """Build the result dict returned from consume_item.

    Args:
        prototype: Prototype data dict.
        item: Item data dict.
        effect_summary: Dict of applied effect summaries.
        remaining_quantity: Remaining stack quantity.
        item_removed: Whether the item was removed from inventory.
        new_char_state: Character state after consumption.
        character_id: Character UUID.
        prototype_id: Prototype ID.
        item_id: Item UUID.

    Returns:
        Dict describing the consumption result.
    """
    item_name = prototype.get("PrototypeName") or prototype.get("Name") or item.get("Name") or "item"

    use_message = "You consume the item."
    verbs = prototype.get("Verbs", {})
    if isinstance(verbs, dict):
        use_value = verbs.get("Use")
        if isinstance(use_value, str):
            use_message = use_value
        elif isinstance(use_value, dict):
            use_message = use_value.get("Message", use_message)

    logger.info(
        "Character %s consumed %s (item %s). Effects: %s",
        character_id, prototype_id, item_id, effect_summary,
    )

    return {
        "success": True,
        "message": use_message or f"You consume {item_name}.",
        "itemName": item_name,
        "effects": effect_summary,
        "remainingQuantity": remaining_quantity,
        "itemRemoved": item_removed,
        "characterState": new_char_state,
    }
