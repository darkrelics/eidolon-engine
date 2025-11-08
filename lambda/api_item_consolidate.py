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
from eidolon.items import get_item_brief, get_item_prototype_full
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

    for slot, slot_data in inventory.items():
        item_id = slot_data.get("ItemID")
        if not item_id:
            continue

        # Get item brief to find prototype
        try:
            item_brief = get_item_brief(item_id)
            item_prototype_id = item_brief.get("PrototypeID")
        except ValueError as err:
            logger.warning(f"Could not get brief for item {item_id}, skipping: {err}")
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

    # Consolidate stacks
    consolidated_stacks = []
    updated_inventory = inventory.copy()

    for proto_id, item_list in prototype_map.items():
        # Only consolidate if there are multiple stacks of the same prototype
        if len(item_list) < 2:
            continue

        # Sort by slot to keep the lowest slot number
        item_list.sort(key=lambda x: int(x[0]))

        # Keep the first slot, sum up all quantities
        keep_slot, keep_item_id, _ = item_list[0]
        total_quantity = sum(qty for _, _, qty in item_list)

        # Update the kept slot with total quantity
        updated_inventory[keep_slot]["Quantity"] = total_quantity

        # Remove all other slots
        removed_slots = []
        for slot, item_id, qty in item_list[1:]:
            del updated_inventory[slot]
            removed_slots.append(slot)

        consolidated_stacks.append(
            {
                "PrototypeID": proto_id,
                "KeptSlot": keep_slot,
                "KeptItemID": keep_item_id,
                "TotalQuantity": total_quantity,
                "StacksConsolidated": len(item_list),
                "RemovedSlots": removed_slots,
            }
        )

        logger.info(f"Consolidated {len(item_list)} stacks of {proto_id} " f"into slot {keep_slot} with {total_quantity} items")

    # Update inventory if consolidation occurred
    if consolidated_stacks:
        try:
            dynamo.update_item(
                TableName.CHARACTERS,
                Key={"CharacterID": character_id},
                UpdateExpression="SET Inventory = :inventory",
                ExpressionAttributeValues={":inventory": updated_inventory},
            )
        except ClientError as err:
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

    logger.info(f"Stack consolidation for character {character_id}: {len(consolidated_stacks)} types")

    return {"status_code": 200, "body": response_body}
