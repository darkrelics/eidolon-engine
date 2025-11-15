"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to use (consume) items from character inventory.
Applies item effects and removes/decrements item from inventory.

Endpoint: POST /item/use
Authentication: Cognito (required)
"""

from botocore.exceptions import ClientError

from eidolon.character_data import character_get
from eidolon.dynamo import TableName, dynamo
from eidolon.item_effects import apply_item_effects
from eidolon.items import get_item_brief, get_item_prototype_full
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.player import validate_player
from eidolon.requests import parse_event_body
from eidolon.validation import validate_uuid


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """
    Lambda handler for using consumable items.

    Request Body:
        {
            "CharacterID": "uuid",
            "ItemID": "uuid",
            "InventorySlot": "1" (optional - for faster lookup)
        }

    Args:
        event: API Gateway Lambda proxy event
        context: Lambda context
        player_id: Authenticated player ID

    Returns:
        Dict with status_code and body containing effect results
    """
    # Validate player exists
    if not validate_player(player_id):
        logger.error(f"Player {player_id} not found in database")
        raise ValueError("401:Unauthorized")

    # Parse request body
    body = parse_event_body(event)
    character_id = body.get("CharacterID", "")
    item_id = body.get("ItemID", "")
    inventory_slot = body.get("InventorySlot")

    # Validate required parameters
    if not character_id:
        raise ValueError("CharacterID is required")

    if not item_id:
        raise ValueError("ItemID is required")

    # Validate UUIDs
    if not validate_uuid(character_id):
        raise ValueError("Invalid CharacterID format")

    if not validate_uuid(item_id):
        raise ValueError("Invalid ItemID format")

    # Get character and verify ownership
    try:
        character = character_get(character_id, player_id)
    except ValueError as err:
        logger.warning(f"Character access denied: {err}")
        raise ValueError(f"403:{err}") from err

    # Find item in inventory
    inventory = character.get("Inventory", {})
    found_slot = None
    item_quantity = None

    if inventory_slot and inventory_slot in inventory:
        # Quick lookup using provided slot
        slot_data = inventory[inventory_slot]
        if slot_data.get("ItemID") == item_id:
            found_slot = inventory_slot
            item_quantity = slot_data.get("Quantity")

    if not found_slot:
        # Search all slots
        for slot, slot_data in inventory.items():
            if slot_data.get("ItemID") == item_id:
                found_slot = slot
                item_quantity = slot_data.get("Quantity")
                break

    if not found_slot:
        raise ValueError("404:Item not found in character inventory")

    # Get item brief to find prototype
    try:
        item_brief = get_item_brief(item_id)
        prototype_id = item_brief.get("PrototypeID")
    except ValueError as err:
        logger.error(f"Failed to get item brief for {item_id}: {err}")
        raise ValueError("404:Item data not found") from err

    # Get full prototype
    try:
        prototype = get_item_prototype_full(prototype_id)
    except ValueError as err:
        logger.error(f"Failed to get prototype {prototype_id}: {err}")
        raise ValueError("404:Item prototype not found") from err

    # ✅ FIX BUG #5: Validate item is consumable
    metadata = prototype.get("Metadata", {})
    has_healing = metadata.get("HealingAmount")
    has_nutrition = metadata.get("NutritionValue")
    has_buff = metadata.get("BuffDuration")

    if not (has_healing or has_nutrition or has_buff):
        item_name = prototype.get("PrototypeName", "Item")
        logger.warning(f"Attempt to use non-consumable item: {item_name} ({prototype_id})")
        raise ValueError(f"400:{item_name} is not consumable")

    # Check if item is stackable (typically consumable)
    is_stackable = prototype.get("Stackable", False)

    # Apply item effects
    try:
        effect_result = apply_item_effects(character_id, prototype)
    except ValueError as err:
        logger.warning(f"Item use failed: {err}")
        raise ValueError(f"400:{err}") from err
    except RuntimeError as err:
        logger.error(f"Failed to apply item effects: {err}")
        raise RuntimeError("Failed to use item") from err

    # Update inventory: decrement quantity or remove item
    try:
        character_update = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
        if not character_update:
            raise RuntimeError("Character not found after effect application")

        current_inventory = character_update.get("Inventory", {})

        # ✅ FIX BUG #6: Safe to delete because we validated consumability above
        # Only consumable items reach this point (checked at line 122)
        if is_stackable and item_quantity and item_quantity > 1:
            # Decrement quantity for stackable consumables
            current_inventory[found_slot]["Quantity"] = item_quantity - 1
            logger.info(f"Decremented item {item_id} quantity: {item_quantity} -> {item_quantity - 1}")
            item_consumed = False
        else:
            # Remove item entirely (last in stack OR non-stackable consumable)
            del current_inventory[found_slot]
            logger.info(f"Consumed item {item_id} from inventory slot {found_slot}")
            item_consumed = True

        # ✅ FIX BUG #2: Use conditional update to prevent race conditions
        # Ensures item still exists in the same slot (prevents double-use exploits)
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET Inventory = :inventory",
            ConditionExpression="Inventory.#slot.ItemID = :expected_item_id",
            ExpressionAttributeNames={
                "#slot": found_slot,
            },
            ExpressionAttributeValues={
                ":inventory": current_inventory,
                ":expected_item_id": item_id,
            },
        )

    except ClientError as err:
        # Check if this was a conditional check failure (item already consumed = race condition)
        if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.warning(f"Item use failed: item {item_id} already consumed (race condition detected)")
            raise ValueError("409:Item has already been used. Please refresh your inventory.") from err

        logger.error(f"Failed to update inventory for {character_id}: {err}")
        raise RuntimeError("Failed to update inventory") from err

    # Build response
    prototype_name = prototype.get("PrototypeName", "Unknown Item")
    response_body = {
        "Success": True,
        "ItemUsed": {
            "ItemID": item_id,
            "PrototypeID": prototype_id,
            "PrototypeName": prototype_name,
        },
        "Effects": effect_result.get("effects_applied", []),
        "Message": effect_result.get("message", "Item used successfully"),
        "ItemConsumed": item_consumed,
    }

    # Add healing details if present
    if effect_result.get("healing"):
        response_body["Healing"] = effect_result["healing"]

    # Add remaining quantity if item not consumed
    if not item_consumed:
        response_body["RemainingQuantity"] = item_quantity - 1

    logger.info(f"Item {item_id} used by character {character_id}: {effect_result.get('effects_applied')}")

    return {"status_code": 200, "body": response_body}
