"""Consumable item functions for the Eidolon Engine."""

import random
import re
from datetime import datetime, timezone
from decimal import Decimal

from botocore.exceptions import ClientError

from eidolon.character_state import determine_character_state_from_wounds
from eidolon.constants import CharState
from eidolon.contents import PARENT_CHARACTER, PARENT_ITEM, locate_item
from eidolon.dynamo import TABLE_ENV_MAP, TableName, dynamo, to_attribute_value
from eidolon.environment import DEFAULT_ESSENCE, DEFAULT_HEALTH
from eidolon.errors import ConflictError, NotFoundError, ValidationError
from eidolon.logger import logger
from eidolon.prototypes import get_prototype, item_is_stackable


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


def parse_dice_notation(notation: str) -> int:
    """Roll dice notation and return the result.

    Supports "2d4+2", "1d6", "3d8-1", or a plain integer string like "10".
    Returns at least 1 for any dice roll; returns 0 for empty input.
    """
    text = str(notation).strip()
    if not text:
        return 0
    if text.isdigit():
        return int(text)

    match = re.fullmatch(r"(\d+)d(\d+)(?:([+-])(\d+))?", text, re.IGNORECASE)
    if not match:
        logger.warning(f"Invalid dice notation '{notation}', defaulting to 1")
        return 1

    num_dice = int(match.group(1))
    die_size = int(match.group(2))
    if num_dice < 1 or die_size < 1:
        return 1

    modifier = 0
    if match.group(3):
        modifier = int(match.group(4)) if match.group(3) == "+" else -int(match.group(4))

    total = sum(random.randint(1, die_size) for _ in range(num_dice))
    return max(1, total + modifier)


def resolve_effect_amount(value) -> int:
    """Resolve an effect Amount that may be a fixed number or dice notation.

    String values are rolled as dice notation (for example "2d4+2"); numeric
    values coerce directly to int. Returns 0 when the amount is missing.
    """
    if isinstance(value, str):
        return parse_dice_notation(value)
    return coerce_int(value, 0)


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


def build_consume_transaction(
    character_id: str,
    item_id: str,
    location: dict,
    new_parent_contents: list,
    update_expression_parts: list,
    expression_values: dict,
    stackable: bool,
    item_removed: bool,
    remaining_quantity: int,
    timestamp: str,
    current_quantity: int = 0,
) -> list:
    """Build the transactional write items for consume_item.

    ``location`` is the ``locate_item`` result for the consumed item; its
    ``parent_kind`` dictates whether the Contents mutation rides on the
    character update or on a separate item-record update.
    """
    parent_kind = location.get("parent_kind")
    parent_id = location.get("parent_id")

    # Start with the base character update (state/wounds/essence/UpdatedAt).
    typed_values = {k: to_attribute_value(v) for k, v in expression_values.items()}
    parts = list(update_expression_parts)

    if item_removed and parent_kind == PARENT_CHARACTER:
        # Fold the character Contents mutation into the same character update.
        parts.append("Contents = :new_contents")
        typed_values[":new_contents"] = to_attribute_value(new_parent_contents)
        typed_values[":expected_item_id"] = to_attribute_value(item_id)
        character_update = {
            "Update": {
                "TableName": TABLE_ENV_MAP[TableName.CHARACTERS],
                "Key": {"CharacterID": {"S": character_id}},
                "UpdateExpression": "SET " + ", ".join(parts),
                "ConditionExpression": "contains(Contents, :expected_item_id)",
                "ExpressionAttributeValues": typed_values,
            }
        }
        transact_items = [character_update]
    else:
        # Character update doesn't touch Contents; use a neutral precondition
        # so the transaction still detects a missing character.
        character_update = {
            "Update": {
                "TableName": TABLE_ENV_MAP[TableName.CHARACTERS],
                "Key": {"CharacterID": {"S": character_id}},
                "UpdateExpression": "SET " + ", ".join(parts),
                "ExpressionAttributeValues": typed_values,
                "ConditionExpression": "attribute_exists(CharacterID)",
            }
        }
        transact_items = [character_update]

        if item_removed and parent_kind == PARENT_ITEM:
            # Separate update on the container item record.
            transact_items.append(
                {
                    "Update": {
                        "TableName": TABLE_ENV_MAP[TableName.ITEMS],
                        "Key": {"ItemID": {"S": parent_id}},
                        "UpdateExpression": "SET Contents = :new_contents",
                        "ConditionExpression": "contains(Contents, :expected_item_id)",
                        "ExpressionAttributeValues": {
                            ":new_contents": to_attribute_value(new_parent_contents),
                            ":expected_item_id": to_attribute_value(item_id),
                        },
                    }
                }
            )

    if stackable and not item_removed:
        # Decrement the stack on the ITEMS record with a quantity precondition.
        transact_items.append(
            {
                "Update": {
                    "TableName": TABLE_ENV_MAP[TableName.ITEMS],
                    "Key": {"ItemID": {"S": item_id}},
                    "UpdateExpression": "SET Quantity = :quantity, UpdatedAt = :updated_at",
                    "ConditionExpression": "Quantity = :expected_quantity",
                    "ExpressionAttributeValues": {
                        ":quantity": to_attribute_value(remaining_quantity),
                        ":updated_at": to_attribute_value(timestamp),
                        ":expected_quantity": to_attribute_value(current_quantity),
                    },
                }
            }
        )
    else:
        transact_items.append(
            {
                "Delete": {
                    "TableName": TABLE_ENV_MAP[TableName.ITEMS],
                    "Key": {"ItemID": {"S": item_id}},
                }
            }
        )

    return transact_items


def load_character_for_consumption(character_id: str, item_id: str) -> dict:
    """Load the character and locate the target item in its Contents tree.

    Returns a dict with keys: character, location (from contents.locate_item).

    Raises:
        ValueError: If the character isn't found, is mid-story, or the item
            isn't anywhere in the character's tree.
        RuntimeError: On database failure.
    """
    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
    except ClientError as err:
        logger.error("Failed to load character %s Error: %s", character_id, err, exc_info=True)
        raise RuntimeError("Failed to load character") from err

    if not character:
        raise NotFoundError("Character not found")
    if character.get("ActiveStoryID"):
        raise ConflictError("Cannot consume items during an active story")

    location = locate_item(character, item_id)
    if not location.get("found"):
        raise NotFoundError("Item is not in character inventory")

    return {"character": character, "location": location}


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
        raise NotFoundError("Item not found")

    prototype_id = item.get("PrototypeID")
    if not prototype_id:
        raise ValidationError("Item prototype reference missing")

    prototype = get_prototype(prototype_id)
    if not prototype:
        raise NotFoundError("Item prototype not found")

    consumable_flag = bool(prototype.get("Consumable", False))
    if not consumable_flag:
        raise ValidationError("Item is not consumable")

    effects_config = prototype.get("ConsumableEffects") or prototype.get("Effects")
    effects = normalize_effect_config(effects_config)
    if not effects:
        raise ValidationError("Consumable item is missing effects configuration")

    return {"item": item, "prototype": prototype, "effects": effects}


def load_consumable_context(character_id: str, item_id: str) -> dict:
    """Load and validate character, item, prototype, and location for consumption.

    Returns a dict with keys: character, item, prototype, location, effects.

    Raises:
        ValueError: If validation fails.
        RuntimeError: If database operations fail.
    """
    if not character_id or not item_id:
        raise ValidationError("CharacterID and ItemID are required")

    char_ctx = load_character_for_consumption(character_id, item_id)
    item_ctx = load_item_and_prototype(item_id)

    return {
        "character": char_ctx.get("character"),
        "item": item_ctx.get("item"),
        "prototype": item_ctx.get("prototype"),
        "location": char_ctx.get("location"),
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
        heal_amount = resolve_effect_amount(heal_config.get("Amount"))
        priority_raw = heal_config.get("DamageTypes")
        if isinstance(priority_raw, list):
            damage_priority = [str(entry).lower() for entry in priority_raw]
    else:
        heal_amount = resolve_effect_amount(heal_config)

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
        essence_amount = resolve_effect_amount(essence_config.get("Amount"))
    else:
        essence_amount = resolve_effect_amount(essence_config)

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


def update_contents_for_consumption(location: dict, item: dict, item_id: str) -> dict:
    """Decide how consuming one unit of ``item`` changes its parent's Contents.

    Returns:
        Dict with keys: new_parent_contents, current_quantity,
        remaining_quantity, item_removed.
    """
    stackable = item_is_stackable(item)
    current_quantity = coerce_int(item.get("Quantity", 1), 1)
    parent_contents = location.get("parent_contents") or []

    if stackable:
        remaining_quantity = max(0, current_quantity - 1)
        if remaining_quantity > 0:
            return {
                "new_parent_contents": list(parent_contents),
                "current_quantity": current_quantity,
                "remaining_quantity": remaining_quantity,
                "item_removed": False,
            }

    new_contents = [cid for cid in parent_contents if cid != item_id]
    return {
        "new_parent_contents": new_contents,
        "current_quantity": current_quantity,
        "remaining_quantity": 0,
        "item_removed": True,
    }


def build_character_update_expression(
    wounds_changed: bool,
    new_wounds: list,
    essence_changed: bool,
    new_essence: int,
    state_changed: bool,
    new_state: str,
) -> dict:
    """Build the DynamoDB update expression for character changes after consumption.

    Contents mutations are applied elsewhere (conditionally on the owning
    parent) and are not part of this base expression.

    Returns:
        Dict with keys: update_expression_parts, expression_values, timestamp.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    update_expression_parts = ["UpdatedAt = :updated_at"]
    expression_values: dict = {":updated_at": timestamp}

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
        raise ConflictError("The item has no effect right now")

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
    """Consume an item from a character's Contents tree and apply its effects."""
    ctx = load_consumable_context(character_id, item_id)
    item = ctx.get("item", {})
    location = ctx.get("location", {})
    fx = apply_consumable_effects(ctx)

    inv_result = update_contents_for_consumption(location, item, item_id)

    state_changed = fx.get("new_char_state") != fx.get("character_state_before")
    essence_result = fx.get("essence_result", {})
    expr = build_character_update_expression(
        fx.get("wounds_changed", False),
        fx.get("new_wounds", []),
        essence_result.get("essence_changed", False),
        essence_result.get("new_essence", 0),
        state_changed,
        fx.get("new_char_state", ""),
    )

    transact_items = build_consume_transaction(
        character_id,
        item_id,
        location,
        inv_result.get("new_parent_contents", []),
        expr.get("update_expression_parts", []),
        expr.get("expression_values", {}),
        item_is_stackable(item),
        inv_result.get("item_removed", False),
        inv_result.get("remaining_quantity", 0),
        expr.get("timestamp", ""),
        inv_result.get("current_quantity", 0),
    )

    execute_consume_transaction(
        transact_items,
        fx.get("character_state_before", ""),
        fx.get("new_char_state", ""),
        ctx.get("character", {}),
        expr.get("timestamp", ""),
        character_id,
        item_id,
    )

    return build_consume_result(
        ctx.get("prototype", {}),
        item,
        fx.get("effect_summary", {}),
        inv_result.get("remaining_quantity", 0),
        inv_result.get("item_removed", False),
        fx.get("new_char_state", ""),
        character_id,
        item.get("PrototypeID", ""),
        item_id,
    )


def execute_consume_transaction(
    transact_items: list,
    character_state_before: str,
    new_char_state: str,
    character: dict,
    timestamp: str,
    character_id: str,
    item_id: str,
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
            transact_items.append(
                {
                    "Update": {
                        "TableName": TABLE_ENV_MAP[TableName.PLAYERS],
                        "Key": {"PlayerID": {"S": player_id}},
                        "UpdateExpression": "SET CharacterList.#name.Dead = :dead, UpdatedAt = :updated_at",
                        "ExpressionAttributeNames": {"#name": character_name},
                        "ExpressionAttributeValues": {":dead": to_attribute_value(False), ":updated_at": to_attribute_value(timestamp)},
                    }
                }
            )

    try:
        dynamo.transact_write_items(transact_items)
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code == "TransactionCanceledException":
            reasons = err.response.get("CancellationReasons", [])
            first_reason = reasons[0].get("Code", "") if reasons else ""
            if first_reason == "ConditionalCheckFailed":
                logger.warning("Item %s already consumed (race condition) for character %s", item_id, character_id)
                raise ConflictError("Item has already been consumed") from err
        logger.error("Failed to consume item %s for character %s Error: %s", item_id, character_id, err, exc_info=True)
        raise RuntimeError("Failed to update character after consumption") from err


def build_consume_result(
    prototype: dict,
    item: dict,
    effect_summary: dict,
    remaining_quantity: int,
    item_removed: bool,
    new_char_state: str,
    character_id: str,
    prototype_id: str,
    item_id: str,
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
    item_name = prototype.get("PrototypeName") or prototype.get("Name") or "item"

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
        character_id,
        prototype_id,
        item_id,
        effect_summary,
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
