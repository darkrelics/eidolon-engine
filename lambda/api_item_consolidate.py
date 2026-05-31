"""
Eidolon Engine - Incremental Game

Copyright 2024-2026 Jason E. Robinson

Lambda function to consolidate stackable item stacks in a character's Contents tree.
Merges multiple stacks sharing a prototype into fewer stacks, respecting MaxStack.

Endpoint: POST /item/consolidate
Authentication: Cognito (required)
"""

from botocore.exceptions import ClientError

from eidolon.character_data import character_get
from eidolon.contents import PARENT_CHARACTER, PARENT_ITEM, get_item_record
from eidolon.dynamo import TableName, dynamo
from eidolon.errors import NotFoundError, UnauthorizedError
from eidolon.items import distribute_into_stacks, get_item_prototype_full
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.player import validate_player
from eidolon.player_character import batch_delete_with_fallback
from eidolon.prototypes import item_is_container
from eidolon.requests import parse_event_body
from eidolon.story_rewards import update_reward_stack_quantity
from eidolon.validation import validate_uuid


def walk_tree(character: dict) -> list:
    """Walk the character's Contents tree and return every reachable stack entry.

    Returns a list of dicts: {parent_kind, parent_id, parent_contents, item_id, item_record}.
    parent_contents is a mutable reference to the owning parent's Contents list.
    """
    entries = []
    character_id = character.get("CharacterID", "")
    top_contents = character.get("Contents") or []
    queue = [(PARENT_CHARACTER, character_id, top_contents, cid) for cid in top_contents if cid]
    visited = set()

    while queue:
        parent_kind, parent_id, parent_contents, item_id = queue.pop(0)
        if item_id in visited:
            continue
        visited.add(item_id)

        record = get_item_record(item_id)
        if not record:
            continue

        entries.append({
            "parent_kind": parent_kind,
            "parent_id": parent_id,
            "parent_contents": parent_contents,
            "item_id": item_id,
            "item_record": record,
        })

        if item_is_container(record):
            child_contents = record.get("Contents") or []
            for child_id in child_contents:
                if child_id and child_id not in visited:
                    queue.append((PARENT_ITEM, item_id, child_contents, child_id))

    return entries


def group_by_prototype(entries: list, prototype_id_filter: str) -> tuple:
    """Group stackable, non-worn entries by PrototypeID.

    Returns (prototype_map, prototype_cache).
    prototype_map: {prototype_id: [entry, ...]}
    prototype_cache: {prototype_id: prototype_data}
    """
    prototype_map = {}
    prototype_cache = {}

    for entry in entries:
        record = entry["item_record"]
        if record.get("IsWorn"):
            continue
        proto_id = record.get("PrototypeID")
        if not proto_id:
            continue
        if prototype_id_filter and proto_id != prototype_id_filter:
            continue

        if proto_id not in prototype_cache:
            try:
                prototype_cache[proto_id] = get_item_prototype_full(proto_id)
            except NotFoundError as err:
                logger.warning(f"Could not get prototype {proto_id}, skipping: {err}")
                continue
        if not prototype_cache[proto_id].get("Stackable", False):
            continue

        prototype_map.setdefault(proto_id, []).append(entry)

    return prototype_map, prototype_cache


def consolidate_group(entries: list, max_stack: int) -> tuple:
    """Plan consolidation for one prototype group.

    Returns (keep_updates, remove_entries, total_quantity, stacks_after) where
    keep_updates is a list of (item_id, new_quantity) and remove_entries is a
    list of entries whose items should be deleted.
    """
    if len(entries) < 2:
        return [], [], 0, len(entries)

    total_quantity = sum(int(e["item_record"].get("Quantity", 1)) for e in entries)
    stack_quantities = distribute_into_stacks(total_quantity, max_stack)
    stacks_needed = len(stack_quantities)

    keep_entries = entries[:stacks_needed]
    remove_entries = entries[stacks_needed:]
    keep_updates = [(keep_entries[i]["item_id"], stack_quantities[i]) for i in range(stacks_needed)]
    return keep_updates, remove_entries, total_quantity, stacks_needed


def apply_removals(remove_entries: list) -> None:
    """Remove items from their parents' Contents lists, then delete ITEMS records."""
    if not remove_entries:
        return

    # Group removals by parent so each parent is written once.
    by_parent = {}  # (kind, id) -> {"parent_contents": list, "to_remove": {item_ids}}
    for entry in remove_entries:
        key = (entry["parent_kind"], entry["parent_id"])
        bucket = by_parent.setdefault(
            key,
            {"parent_contents": entry["parent_contents"], "to_remove": set()},
        )
        bucket["to_remove"].add(entry["item_id"])

    for (kind, parent_id), bucket in by_parent.items():
        new_contents = [cid for cid in bucket["parent_contents"] if cid not in bucket["to_remove"]]
        table = TableName.CHARACTERS if kind == PARENT_CHARACTER else TableName.ITEMS
        key = {"CharacterID": parent_id} if kind == PARENT_CHARACTER else {"ItemID": parent_id}
        try:
            dynamo.update_item(
                table,
                Key=key,
                UpdateExpression="SET Contents = :new",
                ExpressionAttributeValues={":new": new_contents},
            )
        except ClientError as err:
            logger.error(f"Failed to prune Contents for {kind} {parent_id}: {err}")
            raise RuntimeError("Failed to update Contents during consolidation") from err

    delete_keys = [{"ItemID": e["item_id"]} for e in remove_entries]
    result = batch_delete_with_fallback(TableName.ITEMS, delete_keys, "consolidated item")
    errors = result.get("Errors", [])
    if errors:
        logger.warning(f"Some consolidated item records failed to delete: {errors}")


def handle_consolidation(character_id: str, player_id: str, prototype_id_filter: str) -> dict:
    """Consolidate stackable items across the character's Contents tree."""
    character = character_get(character_id, player_id)

    entries = walk_tree(character)
    if not entries:
        return {
            "Success": True,
            "Message": "Inventory is empty, nothing to consolidate",
            "ConsolidatedStacks": [],
            "TotalStacksRemoved": 0,
        }

    prototype_map, prototype_cache = group_by_prototype(entries, prototype_id_filter)

    consolidated_stacks = []
    all_removals = []
    for proto_id, group in prototype_map.items():
        max_stack = prototype_cache[proto_id].get("MaxStack", 99) or 99
        keep_updates, remove_entries, total_qty, stacks_after = consolidate_group(group, max_stack)
        if not remove_entries:
            continue

        for item_id, new_qty in keep_updates:
            update_reward_stack_quantity(item_id, new_qty)

        consolidated_stacks.append({
            "PrototypeID": proto_id,
            "TotalQuantity": total_qty,
            "StacksAfterConsolidation": stacks_after,
            "StacksConsolidated": len(group),
            "RemovedItemIDs": [e["item_id"] for e in remove_entries],
        })
        all_removals.extend(remove_entries)

    apply_removals(all_removals)

    message = (
        f"Successfully consolidated {len(consolidated_stacks)} item type(s)"
        if consolidated_stacks
        else "No stackable items found to consolidate"
    )
    return {
        "Success": True,
        "Message": message,
        "ConsolidatedStacks": consolidated_stacks,
        "TotalStacksRemoved": len(all_removals),
    }


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """Lambda handler for consolidating item stacks.

    Request Body:
        {
            "CharacterID": "uuid",
            "PrototypeID": "uuid"    (optional - limit to one prototype),
            "ConsolidateAll": true   (optional - default when no PrototypeID)
        }
    """
    if not validate_player(player_id):
        logger.error(f"Player {player_id} not found in database")
        raise UnauthorizedError("Unauthorized")

    body = parse_event_body(event)
    character_id = body.get("CharacterID", "")
    prototype_id = body.get("PrototypeID", "")

    if not character_id:
        raise ValueError("CharacterID is required")
    if not validate_uuid(character_id):
        raise ValueError("Invalid CharacterID format")
    if prototype_id and not validate_uuid(prototype_id):
        raise ValueError("Invalid PrototypeID format")

    result = handle_consolidation(character_id, player_id, prototype_id)
    logger.info(
        f"Stack consolidation for character {character_id}: "
        f"{len(result.get('ConsolidatedStacks', []))} types"
    )
    return {"status_code": 200, "body": result}
