"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

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
from eidolon.requests import parse_event_body
from eidolon.validation import validate_uuid


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """
    Lambda handler for consolidating item stacks.

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
    prototype_id = body.get("PrototypeID")
    consolidate_all = body.get("ConsolidateAll", False)

    # Validate required parameters
    if not character_id:
        raise ValueError("CharacterID is required")

    # Validate UUID
    if not validate_uuid(character_id):
        raise ValueError("Invalid CharacterID format")

    if prototype_id and not validate_uuid(prototype_id):
        raise ValueError("Invalid PrototypeID format")

    # Default to consolidate all if no specific prototype given
    if not prototype_id and not consolidate_all:
        consolidate_all = True

    # Get character and verify ownership
    try:
        character = character_get(character_id, player_id)
    except ValueError as err:
        logger.warning(f"Character access denied: {err}")
        raise ValueError(f"403:{err}") from err

    inventory = character.get("Inventory", {})

    if not inventory:
        return {
            "status_code": 200,
            "body": {
                "Success": True,
                "Message": "Inventory is empty, nothing to consolidate",
                "ConsolidatedStacks": [],
            },
        }

    # Build a mapping of PrototypeID -> list of (slot, item_id, quantity)
    prototype_map = {}
    orphaned_items = []  # Track items that exist in inventory but not in ITEMS table

    for slot, slot_data in inventory.items():
        item_id = slot_data.get("ItemID")
        if not item_id:
            continue

        # Get item brief to find prototype
        try:
            item_brief = get_item_brief(item_id)
            item_prototype_id = item_brief.get("PrototypeID")
        except ValueError as err:
            # Orphaned item - exists in inventory but not in ITEMS table
            logger.error(f"Orphaned item detected in slot {slot}: {item_id} - {err}")
            orphaned_items.append({"Slot": slot, "ItemID": item_id, "Error": str(err)})
            continue

        # If filtering by prototype, skip non-matching items
        if prototype_id and item_prototype_id != prototype_id:
            continue

        # Check if item is stackable
        try:
            prototype = get_item_prototype_full(item_prototype_id)
            is_stackable = prototype.get("Stackable", False)
        except ValueError as err:
            logger.warning(f"Could not get prototype for {item_prototype_id}, skipping: {err}")
            continue

        if not is_stackable:
            continue

        # Add to prototype map
        if item_prototype_id not in prototype_map:
            prototype_map[item_prototype_id] = []

        quantity = slot_data.get("Quantity", 1)
        prototype_map[item_prototype_id].append((slot, item_id, quantity))

    # Clean up orphaned items from inventory
    updated_inventory = inventory.copy()
    for orphan in orphaned_items:
        orphan_slot = orphan["Slot"]
        if orphan_slot in updated_inventory:
            del updated_inventory[orphan_slot]
            logger.info(f"Removed orphaned item from slot {orphan_slot}")

    # Consolidate stacks with MaxStack enforcement
    consolidated_stacks = []

    for proto_id, item_list in prototype_map.items():
        # Only consolidate if there are multiple stacks of the same prototype
        if len(item_list) < 2:
            continue

        # Get MaxStack from prototype
        try:
            prototype = get_item_prototype_full(proto_id)
            max_stack = prototype.get("MaxStack", 99)
            if max_stack <= 0:
                max_stack = 99
        except ValueError:
            max_stack = 99

        # Sort by slot to keep the lowest slot numbers
        # Filter to only numeric slots (equipment slots like "weapon" are not consolidated)
        numeric_items = [(s, i, q) for s, i, q in item_list if s.isdigit()]

        # Only consolidate if we have multiple numeric slots
        if len(numeric_items) < 2:
            # If only non-numeric or single numeric slot, skip consolidation for this prototype
            continue

        # Sort numeric slots by slot number
        numeric_items.sort(key=lambda x: int(x[0]))
        item_list = numeric_items

        # Calculate total quantity
        total_quantity = sum(qty for _, _, qty in item_list)

        # Distribute into MaxStack-compliant stacks
        stack_quantities = distribute_into_stacks(total_quantity, max_stack)
        stacks_needed = len(stack_quantities)

        # Determine which slots to keep and which to remove
        slots_to_keep = item_list[:stacks_needed]
        slots_to_remove = item_list[stacks_needed:]

        # Update kept slots with new quantities
        kept_slots = []
        kept_item_ids = []
        for i, (slot, item_id, _) in enumerate(slots_to_keep):
            new_qty = stack_quantities[i]
            updated_inventory[slot]["Quantity"] = new_qty
            kept_slots.append(slot)
            kept_item_ids.append(item_id)

        # Remove excess slots
        removed_slots = []
        for slot, item_id, qty in slots_to_remove:
            del updated_inventory[slot]
            removed_slots.append(slot)

        # Only report as consolidated if we actually reduced the number of stacks
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

    # Update inventory if consolidation occurred or orphaned items were cleaned
    if consolidated_stacks or orphaned_items:
        try:
            # Determine which slot to use for conditional check
            # Prefer consolidated slots, but fall back to orphaned slots
            check_slot = None

            if consolidated_stacks:
                first_stack = consolidated_stacks[0]
                if first_stack.get("RemovedSlots"):
                    check_slot = first_stack["RemovedSlots"][0]

            if not check_slot and orphaned_items:
                check_slot = orphaned_items[0]["Slot"]

            if check_slot:
                # Ensure the slot we're about to remove still exists in its original state
                dynamo.update_item(
                    TableName.CHARACTERS,
                    Key={"CharacterID": character_id},
                    UpdateExpression="SET Inventory = :inventory",
                    ConditionExpression="attribute_exists(Inventory.#check_slot)",
                    ExpressionAttributeNames={
                        "#check_slot": check_slot,
                    },
                    ExpressionAttributeValues={":inventory": updated_inventory},
                )
            else:
                # No slots removed (edge case), do unchecked update
                dynamo.update_item(
                    TableName.CHARACTERS,
                    Key={"CharacterID": character_id},
                    UpdateExpression="SET Inventory = :inventory",
                    ExpressionAttributeValues={":inventory": updated_inventory},
                )
        except ClientError as err:
            # Check if this was a conditional check failure (inventory changed = race condition)
            if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                logger.warning("Consolidation failed: inventory changed during operation (race condition detected)")
                raise ValueError("409:Inventory changed during consolidation. Please try again.") from err

            logger.error(f"Failed to update inventory for {character_id}: {err}")
            raise RuntimeError("Failed to consolidate stacks") from err

        message = f"Successfully consolidated {len(consolidated_stacks)} item type(s)"
    else:
        message = "No stackable items found to consolidate"

    # Build response
    response_body = {
        "Success": True,
        "Message": message,
        "ConsolidatedStacks": consolidated_stacks,
        "TotalStacksRemoved": sum(len(cs["RemovedSlots"]) for cs in consolidated_stacks),
    }

    # Include orphaned items if any were found and cleaned
    if orphaned_items:
        response_body["OrphanedItemsCleaned"] = orphaned_items
        response_body["Message"] = f"{message}. Cleaned {len(orphaned_items)} orphaned inventory slot(s)."

    logger.info(f"Stack consolidation for character {character_id}: {len(consolidated_stacks)} types")

    return {"status_code": 200, "body": response_body}
