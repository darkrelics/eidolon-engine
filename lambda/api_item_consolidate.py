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
from eidolon.contents import PARENT_CHARACTER, PARENT_ITEM, get_item_record, typed_contents_target
from eidolon.dynamo import dynamo, to_attribute_value
from eidolon.errors import ConflictError, NotFoundError, UnauthorizedError
from eidolon.items import distribute_into_stacks, get_item_prototype_full
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.player import validate_player
from eidolon.prototypes import item_is_container
from eidolon.requests import parse_event_body
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
    keep_updates is a list of (item_id, new_quantity, prior_quantity) and
    remove_entries is a list of entries whose items should be deleted. The prior
    quantity is carried so the persisting transaction can guard each kept-stack
    write against a concurrent change.
    """
    if len(entries) < 2:
        return [], [], 0, len(entries)

    total_quantity = sum(int(e["item_record"].get("Quantity", 1)) for e in entries)
    stack_quantities = distribute_into_stacks(total_quantity, max_stack)
    stacks_needed = len(stack_quantities)

    keep_entries = entries[:stacks_needed]
    remove_entries = entries[stacks_needed:]
    keep_updates = []
    for i in range(stacks_needed):
        keep_entry = keep_entries[i]
        prior_quantity = int(keep_entry["item_record"].get("Quantity", 1))
        keep_updates.append((keep_entry["item_id"], stack_quantities[i], prior_quantity))
    return keep_updates, remove_entries, total_quantity, stacks_needed


def group_removals_by_parent(remove_entries: list) -> dict:
    """Group removed entries by owning parent so each parent is written once.

    Returns {(parent_kind, parent_id): {"parent_contents": list, "to_remove": set}}.
    """
    by_parent = {}
    for entry in remove_entries:
        key = (entry["parent_kind"], entry["parent_id"])
        bucket = by_parent.setdefault(
            key,
            {"parent_contents": entry["parent_contents"], "to_remove": set()},
        )
        bucket["to_remove"].add(entry["item_id"])
    return by_parent


def build_keep_update_ops(keep_updates: list) -> list:
    """Build guarded Quantity-set transaction ops for the kept stacks.

    Each set is conditioned on the stack's prior Quantity, so a concurrent change
    to that stack cancels the transaction instead of being overwritten. No-op
    quantity changes are skipped to keep the transaction small.
    """
    ops = []
    for item_id, new_quantity, prior_quantity in keep_updates:
        if new_quantity == prior_quantity:
            continue
        table_name, typed_key = typed_contents_target(PARENT_ITEM, item_id)
        ops.append({
            "Update": {
                "TableName": table_name,
                "Key": typed_key,
                "UpdateExpression": "SET Quantity = :new",
                "ConditionExpression": "Quantity = :old",
                "ExpressionAttributeValues": {
                    ":new": to_attribute_value(new_quantity),
                    ":old": to_attribute_value(prior_quantity),
                },
            }
        })
    return ops


def build_prune_ops(by_parent: dict) -> list:
    """Build guarded Contents-prune transaction ops, one per parent.

    Each rewrite drops the removed IDs and is conditioned on the parent's prior
    Contents value, so a concurrent append to or removal from the same parent
    cancels the transaction rather than being silently clobbered. A bare
    ``contains`` guard is insufficient here: it would still let a concurrently
    appended ItemID be dropped by the stale full-list write.
    """
    ops = []
    for (kind, parent_id), bucket in by_parent.items():
        old_contents = bucket["parent_contents"]
        new_contents = [cid for cid in old_contents if cid not in bucket["to_remove"]]
        table_name, typed_key = typed_contents_target(kind, parent_id)
        ops.append({
            "Update": {
                "TableName": table_name,
                "Key": typed_key,
                "UpdateExpression": "SET Contents = :new",
                "ConditionExpression": "Contents = :old",
                "ExpressionAttributeValues": {
                    ":new": to_attribute_value(new_contents),
                    ":old": to_attribute_value(old_contents),
                },
            }
        })
    return ops


def build_delete_ops(remove_entries: list) -> list:
    """Build Delete transaction ops for every redundant stack's ITEMS record."""
    ops = []
    for entry in remove_entries:
        table_name, typed_key = typed_contents_target(PARENT_ITEM, entry["item_id"])
        ops.append({"Delete": {"TableName": table_name, "Key": typed_key}})
    return ops


def apply_consolidation(keep_updates: list, remove_entries: list) -> None:
    """Apply stack top-ups and redundant-stack removals in one atomic transaction.

    Kept-stack Quantity sets, parent Contents prunes, and redundant-stack deletes
    commit together. Each set and prune is guarded by the prior value it read, so
    any concurrent inventory change cancels the whole transaction (surfaced as a
    409 conflict) rather than double-counting totals or dropping concurrent edits.
    """
    if not remove_entries:
        return

    ops = build_keep_update_ops(keep_updates)
    ops.extend(build_prune_ops(group_removals_by_parent(remove_entries)))
    ops.extend(build_delete_ops(remove_entries))

    try:
        dynamo.transact_write_items(ops)
    except ClientError as err:
        if err.response.get("Error", {}).get("Code") == "TransactionCanceledException":
            logger.warning("Consolidation cancelled (inventory changed during write)")
            raise ConflictError("Inventory changed during consolidation. Refresh and retry.") from err
        logger.error(f"Failed to consolidate item stacks: {err}")
        raise RuntimeError("Failed to consolidate item stacks") from err


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
    all_keep_updates = []
    all_removals = []
    for proto_id, group in prototype_map.items():
        max_stack = prototype_cache[proto_id].get("MaxStack", 99) or 99
        keep_updates, remove_entries, total_qty, stacks_after = consolidate_group(group, max_stack)
        if not remove_entries:
            continue

        all_keep_updates.extend(keep_updates)
        consolidated_stacks.append({
            "PrototypeID": proto_id,
            "TotalQuantity": total_qty,
            "StacksAfterConsolidation": stacks_after,
            "StacksConsolidated": len(group),
            "RemovedItemIDs": [e["item_id"] for e in remove_entries],
        })
        all_removals.extend(remove_entries)

    apply_consolidation(all_keep_updates, all_removals)

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
