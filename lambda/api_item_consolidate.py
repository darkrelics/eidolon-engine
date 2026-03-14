"""
Eidolon Engine - Incremental Game

Copyright 2024-2026 Jason E. Robinson

Lambda function to consolidate stackable item stacks in character inventory.
Merges multiple separate stacks of the same item into a single stack.

Endpoint: POST /item/consolidate
Authentication: Cognito (required)
"""

from botocore.exceptions import ClientError

from eidolon.character_data import character_get
from eidolon.dynamo import TableName, dynamo
from eidolon.items import distribute_into_stacks, get_item_brief, get_item_prototype_full
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.player import validate_player
from eidolon.player_character import batch_delete_with_fallback
from eidolon.requests import parse_event_body
from eidolon.story_rewards import update_reward_stack_quantity
from eidolon.validation import validate_uuid


def scan_inventory(inventory: dict, prototype_id: str) -> tuple:
    """Scan inventory to build prototype map and detect orphaned items.

    Args:
        inventory: Character inventory dict (slot -> slot_data)
        prototype_id: Optional prototype ID filter (empty string for all)

    Returns:
        Tuple of (prototype_map, orphaned_items, prototype_cache) where:
            - prototype_map: dict of prototype_id -> list of (slot, item_id, quantity)
            - orphaned_items: list of dicts with Slot, ItemID, Error
            - prototype_cache: dict of prototype_id -> prototype data
    """
    prototype_map = {}
    orphaned_items = []
    prototype_cache = {}

    for slot, slot_data in inventory.items():
        item_id = slot_data.get("ItemID")
        if not item_id:
            continue

        # Get item brief to find prototype
        try:
            item_brief = get_item_brief(item_id)
            item_prototype_id = item_brief.get("PrototypeID")
        except ValueError as err:
            logger.error(f"Orphaned item detected in slot {slot}: {item_id} - {err}")
            orphaned_items.append({"Slot": slot, "ItemID": item_id, "Error": str(err)})
            continue

        if not item_prototype_id:
            continue

        if prototype_id and item_prototype_id != prototype_id:
            continue

        # Look up prototype (cache to avoid redundant DB calls)
        if item_prototype_id not in prototype_cache:
            try:
                prototype_cache[item_prototype_id] = get_item_prototype_full(item_prototype_id)
            except ValueError as err:
                logger.warning(f"Could not get prototype for {item_prototype_id}, skipping: {err}")
                continue

        prototype = prototype_cache.get(item_prototype_id, {})
        if not prototype.get("Stackable", False):
            continue

        if item_prototype_id not in prototype_map:
            prototype_map[item_prototype_id] = []

        quantity = slot_data.get("Quantity", 1)
        prototype_map[item_prototype_id].append((slot, item_id, quantity))

    return prototype_map, orphaned_items, prototype_cache


def consolidate_stacks(prototype_map: dict, prototype_cache: dict, updated_inventory: dict) -> list:
    """Consolidate multiple stacks of the same prototype into fewer stacks.

    Updates updated_inventory in place. Also updates ITEMS table quantities
    for kept items and deletes ITEMS table records for removed items.

    Args:
        prototype_map: dict of prototype_id -> list of (slot, item_id, quantity)
        prototype_cache: dict of prototype_id -> prototype data
        updated_inventory: Inventory dict to modify in place

    Returns:
        List of consolidation result dicts
    """
    consolidated_stacks = []
    items_to_delete = []

    for proto_id, item_list in prototype_map.items():
        if len(item_list) < 2:
            continue

        # Get MaxStack from cached prototype data
        prototype = prototype_cache.get(proto_id, {})
        max_stack = prototype.get("MaxStack", 99)
        if max_stack <= 0:
            max_stack = 99

        # Filter to only numeric slots (equipment slots like "weapon" are not consolidated)
        numeric_items = [(s, i, q) for s, i, q in item_list if s.isdigit()]
        if len(numeric_items) < 2:
            continue

        # Sort numeric slots by slot number
        numeric_items.sort(key=lambda x: int(x[0]))
        item_list = numeric_items

        total_quantity = sum(qty for _, _, qty in item_list)
        stack_quantities = distribute_into_stacks(total_quantity, max_stack)
        stacks_needed = len(stack_quantities)

        slots_to_keep = item_list[:stacks_needed]
        slots_to_remove = item_list[stacks_needed:]

        # Update kept slots with new quantities
        kept_slots = []
        kept_item_ids = []
        for i, (slot, item_id, _) in enumerate(slots_to_keep):
            new_qty = stack_quantities[i]
            updated_inventory.get(slot, {})["Quantity"] = new_qty
            kept_slots.append(slot)
            kept_item_ids.append(item_id)
            update_reward_stack_quantity(item_id, new_qty)

        # Remove excess slots from inventory and collect items for ITEMS table deletion
        removed_slots = []
        for slot, item_id, qty in slots_to_remove:
            updated_inventory.pop(slot, None)
            removed_slots.append(slot)
            items_to_delete.append({"ItemID": item_id})

        if removed_slots:
            consolidated_stacks.append(
                {
                    "PrototypeID": proto_id,
                    "KeptSlots": kept_slots,
                    "KeptItemIDs": kept_item_ids,
                    "TotalQuantity": total_quantity,
                    "StacksAfterConsolidation": stacks_needed,
                    "StacksConsolidated": len(item_list),
                    "RemovedSlots": removed_slots,
                }
            )

            logger.info(
                f"Consolidated {len(item_list)} stacks of {proto_id} "
                f"into {stacks_needed} stack(s) with {total_quantity} total items"
            )

    # Delete removed item records from the ITEMS table
    if items_to_delete:
        delete_result = batch_delete_with_fallback(TableName.ITEMS, items_to_delete, "consolidated item")
        errors = delete_result.get("Errors", [])
        if errors:
            logger.warning(f"Some consolidated item records failed to delete: {errors}")

    return consolidated_stacks


def save_inventory(character_id: str, updated_inventory: dict, consolidated_stacks: list, orphaned_items: list) -> None:
    """Save the updated inventory to DynamoDB with a conditional check.

    Args:
        character_id: Character UUID
        updated_inventory: The modified inventory dict
        consolidated_stacks: List of consolidation results (for check_slot selection)
        orphaned_items: List of orphaned item dicts (for check_slot fallback)

    Raises:
        ValueError: With 409 prefix if inventory changed during operation
        RuntimeError: If database update fails
    """
    check_slot = None

    if consolidated_stacks:
        first_removed = consolidated_stacks[0].get("RemovedSlots", [])
        if first_removed:
            check_slot = first_removed[0]

    if not check_slot and orphaned_items:
        check_slot = orphaned_items[0].get("Slot")

    try:
        if check_slot:
            dynamo.update_item(
                TableName.CHARACTERS,
                Key={"CharacterID": character_id},
                UpdateExpression="SET Inventory = :inventory",
                ConditionExpression="attribute_exists(Inventory.#check_slot)",
                ExpressionAttributeNames={"#check_slot": check_slot},
                ExpressionAttributeValues={":inventory": updated_inventory},
            )
        else:
            dynamo.update_item(
                TableName.CHARACTERS,
                Key={"CharacterID": character_id},
                UpdateExpression="SET Inventory = :inventory",
                ExpressionAttributeValues={":inventory": updated_inventory},
            )
    except ClientError as err:
        if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.warning("Consolidation failed: inventory changed during operation (race condition detected)")
            raise ValueError("409:Inventory changed during consolidation. Please try again.") from err
        logger.error(f"Failed to update inventory for {character_id}: {err}")
        raise RuntimeError("Failed to consolidate stacks") from err


def handle_consolidation(character_id: str, player_id: str, prototype_id: str) -> dict:
    """Handle the business logic for item stack consolidation.

    Args:
        character_id: Character UUID
        player_id: Authenticated player ID
        prototype_id: Optional prototype ID filter (empty string for all)

    Returns:
        Dict containing consolidation results for the response body

    Raises:
        ValueError: If character not found or access denied
        RuntimeError: If database operations fail
    """
    # Get character and verify ownership
    try:
        character = character_get(character_id, player_id)
    except ValueError as err:
        logger.warning(f"Character access denied: {err}")
        raise ValueError(f"403:{err}") from err

    inventory = character.get("Inventory", {})

    if not inventory:
        return {
            "Success": True,
            "Message": "Inventory is empty, nothing to consolidate",
            "ConsolidatedStacks": [],
        }

    # Scan inventory for stackable items and orphaned entries
    prototype_map, orphaned_items, prototype_cache = scan_inventory(inventory, prototype_id)

    # Clean up orphaned items from inventory
    updated_inventory = inventory.copy()
    for orphan in orphaned_items:
        orphan_slot = orphan.get("Slot")
        if orphan_slot and orphan_slot in updated_inventory:
            updated_inventory.pop(orphan_slot, None)
            logger.info(f"Removed orphaned item from slot {orphan_slot}")

    # Consolidate stacks
    consolidated_stacks = consolidate_stacks(prototype_map, prototype_cache, updated_inventory)

    # Save inventory if anything changed
    if consolidated_stacks or orphaned_items:
        save_inventory(character_id, updated_inventory, consolidated_stacks, orphaned_items)
        message = f"Successfully consolidated {len(consolidated_stacks)} item type(s)"
    else:
        message = "No stackable items found to consolidate"

    # Build response
    response_body = {
        "Success": True,
        "Message": message,
        "ConsolidatedStacks": consolidated_stacks,
        "TotalStacksRemoved": sum(len(cs.get("RemovedSlots", [])) for cs in consolidated_stacks),
    }

    if orphaned_items:
        response_body["OrphanedItemsCleaned"] = orphaned_items
        response_body["Message"] = f"{message}. Cleaned {len(orphaned_items)} orphaned inventory slot(s)."

    return response_body


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """Lambda handler for consolidating item stacks.

    Request Body:
        {
            "CharacterID": "uuid",
            "PrototypeID": "uuid" (optional - consolidate specific item type),
            "ConsolidateAll": true (optional - consolidate all stackable items)
        }

    If neither PrototypeID nor ConsolidateAll is provided, defaults to ConsolidateAll=true.

    Args:
        event: API Gateway Lambda proxy event
        context: Lambda context
        player_id: Authenticated player ID

    Returns:
        Dict with status_code and body containing consolidation results
    """
    # Validate player exists
    if not validate_player(player_id):
        logger.error(f"Player {player_id} not found in database")
        raise ValueError("401:Unauthorized")

    # Parse request body
    body = parse_event_body(event)
    character_id = body.get("CharacterID", "")
    prototype_id = body.get("PrototypeID", "")
    consolidate_all = body.get("ConsolidateAll", False)

    if not character_id:
        raise ValueError("CharacterID is required")

    if not validate_uuid(character_id):
        raise ValueError("Invalid CharacterID format")

    if prototype_id and not validate_uuid(prototype_id):
        raise ValueError("Invalid PrototypeID format")

    # Default to consolidate all if no specific prototype given
    if not prototype_id and not consolidate_all:
        consolidate_all = True

    # Call business logic
    result = handle_consolidation(character_id, player_id, prototype_id)

    logger.info(f"Stack consolidation for character {character_id}: {len(result.get('ConsolidatedStacks', []))} types")

    return {"status_code": 200, "body": result}
