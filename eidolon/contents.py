"""
Tree walk helpers for the character-as-container inventory model.

Both character records and container item records carry a `Contents` list of
ItemIDs. Items and containers nest recursively. These helpers locate items
within the tree and persist mutations to the owning Contents list.
"""

from botocore.exceptions import ClientError

from eidolon.dynamo import TABLE_ENV_MAP, TableName, dynamo, to_attribute_value
from eidolon.errors import ConflictError, NotFoundError, ValidationError
from eidolon.logger import logger
from eidolon.prototypes import item_is_container

PARENT_CHARACTER = "character"
PARENT_ITEM = "item"


def get_item_record(item_id: str) -> dict:
    """Fetch a single item record from the ITEMS table, or None if missing."""
    try:
        record: dict = dynamo.get_item(TableName.ITEMS, {"ItemID": item_id})  # type: ignore
    except ClientError as err:
        logger.error(f"Failed to fetch item {item_id}: {err}")
        raise RuntimeError(f"Failed to fetch item {item_id}") from err
    return record


def locate_item(character: dict, item_id: str) -> dict:
    """Locate ``item_id`` inside ``character``'s Contents tree.

    Walks ``character.Contents`` and descends into each container item's
    Contents recursively.

    Returns a dict describing the parent:

        {"found": True,
         "parent_kind": "character" | "item",
         "parent_id": str,
         "parent_contents": list,
         "item_record": dict | None}

    or ``{"found": False}`` when the item is not reachable. The
    ``parent_contents`` field references the list on the parent document;
    callers may copy it, mutate the copy, and persist via :func:`write_contents`.
    """
    if not character or not item_id:
        return {"found": False}

    character_id = character.get("CharacterID", "")
    top_contents = character.get("Contents")
    if not isinstance(top_contents, list):
        return {"found": False}

    if item_id in top_contents:
        return {
            "found": True,
            "parent_kind": PARENT_CHARACTER,
            "parent_id": character_id,
            "parent_contents": top_contents,
            "item_record": get_item_record(item_id),
        }

    visited = set()
    queue = [cid for cid in top_contents if cid]
    while queue:
        container_id = queue.pop(0)
        if container_id in visited:
            continue
        visited.add(container_id)

        record = get_item_record(container_id)
        if not record or not item_is_container(record):
            continue

        contents = record.get("Contents", [])
        if not isinstance(contents, list):
            continue

        if item_id in contents:
            return {
                "found": True,
                "parent_kind": PARENT_ITEM,
                "parent_id": container_id,
                "parent_contents": contents,
                "item_record": get_item_record(item_id),
            }

        for child in contents:
            if child and child not in visited:
                queue.append(child)

    return {"found": False}


def collect_item_ids(character: dict) -> set:
    """Return every ItemID reachable from ``character.Contents``."""
    ids = set()
    if not character:
        return ids

    top_contents = character.get("Contents") or []
    queue = [cid for cid in top_contents if cid]
    while queue:
        current = queue.pop(0)
        if current in ids:
            continue
        ids.add(current)
        try:
            record = dynamo.get_item(
                TableName.ITEMS,
                {"ItemID": current},
                ProjectionExpression="PrototypeID, Contents",
            )
        except ClientError as err:
            logger.error(f"Failed to fetch item {current}: {err}")
            continue
        if not record or not item_is_container(record):
            continue
        for child in record.get("Contents", []) or []:
            if child and child not in ids:
                queue.append(child)
    return ids


def write_contents(parent_kind: str, parent_id: str, new_contents: list, expected_item_id: str) -> None:
    """Persist a replacement Contents list on the parent document.

    Uses a ``contains(Contents, :expected)`` conditional check to catch the
    race where another writer has already removed ``expected_item_id`` from
    the same list.
    """
    if parent_kind == PARENT_CHARACTER:
        table = TableName.CHARACTERS
        key = {"CharacterID": parent_id}
    elif parent_kind == PARENT_ITEM:
        table = TableName.ITEMS
        key = {"ItemID": parent_id}
    else:
        raise ValueError(f"Unknown parent kind: {parent_kind}")

    try:
        dynamo.update_item(
            table,
            Key=key,
            UpdateExpression="SET Contents = :new",
            ConditionExpression="contains(Contents, :expected)",
            ExpressionAttributeValues={":new": new_contents, ":expected": expected_item_id},
        )
    except ClientError as err:
        code = err.response.get("Error", {}).get("Code")
        if code == "ConditionalCheckFailedException":
            raise ConflictError("Item no longer at expected location. Refresh and retry.") from err
        logger.error(f"Failed to write Contents for {parent_kind} {parent_id}: {err}")
        raise RuntimeError(f"Failed to update Contents: {err}") from err


def append_to_contents(parent_kind: str, parent_id: str, new_item_ids: list) -> None:
    """Append one or more ItemIDs to a parent's Contents list (character or item)."""
    if not new_item_ids:
        return
    if parent_kind == PARENT_CHARACTER:
        table = TableName.CHARACTERS
        key = {"CharacterID": parent_id}
    elif parent_kind == PARENT_ITEM:
        table = TableName.ITEMS
        key = {"ItemID": parent_id}
    else:
        raise ValueError(f"Unknown parent kind: {parent_kind}")
    try:
        dynamo.update_item(
            table,
            Key=key,
            UpdateExpression="SET Contents = list_append(if_not_exists(Contents, :empty), :new)",
            ExpressionAttributeValues={":new": list(new_item_ids), ":empty": []},
        )
    except ClientError as err:
        logger.error(f"Failed to append to {parent_kind} {parent_id} Contents: {err}")
        raise RuntimeError(f"Failed to update contents: {err}") from err


def typed_contents_target(parent_kind: str, parent_id: str) -> tuple:
    """Return ``(table_name, typed_key)`` for a transaction op on a parent's Contents.

    The key is a low-level typed attribute value, as required by
    ``transact_write_items``.
    """
    if parent_kind == PARENT_CHARACTER:
        return TABLE_ENV_MAP[TableName.CHARACTERS], {"CharacterID": {"S": parent_id}}
    if parent_kind == PARENT_ITEM:
        return TABLE_ENV_MAP[TableName.ITEMS], {"ItemID": {"S": parent_id}}
    raise ValueError(f"Unknown parent kind: {parent_kind}")


def destination_in_subtree(item_id: str, destination_id: str, item_record: dict) -> bool:
    """Return True when ``destination_id`` is ``item_id`` or lies within its subtree.

    Used to reject moving a container into itself or one of its own descendants.
    Walks the moved item's Contents through nested container items.
    """
    if destination_id == item_id:
        return True
    if not item_record or not item_is_container(item_record):
        return False

    visited = set()
    queue = [cid for cid in (item_record.get("Contents") or []) if cid]
    while queue:
        current = queue.pop()
        if current in visited:
            continue
        visited.add(current)
        if current == destination_id:
            return True

        record = get_item_record(current)
        if not record or not item_is_container(record):
            continue
        for child in record.get("Contents", []) or []:
            if child and child not in visited:
                queue.append(child)

    return False


def build_move_transaction(
    source_kind: str, source_id: str, dest_kind: str, dest_id: str, item_id: str, new_source_contents: list
) -> list:
    """Build the atomic transaction that moves ``item_id`` between two parents.

    Removes the item from the source's Contents (guarded so the item must still
    be there) and appends it to the destination's Contents (guarded so it is not
    already there), so a concurrent change cancels the whole move.
    """
    source_table, source_key = typed_contents_target(source_kind, source_id)
    dest_table, dest_key = typed_contents_target(dest_kind, dest_id)

    return [
        {
            "Update": {
                "TableName": source_table,
                "Key": source_key,
                "UpdateExpression": "SET Contents = :new",
                "ConditionExpression": "contains(Contents, :item)",
                "ExpressionAttributeValues": {
                    ":new": to_attribute_value(new_source_contents),
                    ":item": to_attribute_value(item_id),
                },
            }
        },
        {
            "Update": {
                "TableName": dest_table,
                "Key": dest_key,
                "UpdateExpression": "SET Contents = list_append(if_not_exists(Contents, :empty), :item_list)",
                "ConditionExpression": "attribute_not_exists(Contents) OR NOT contains(Contents, :item)",
                "ExpressionAttributeValues": {
                    ":empty": to_attribute_value([]),
                    ":item_list": to_attribute_value([item_id]),
                    ":item": to_attribute_value(item_id),
                },
            }
        },
    ]


def move_item(character: dict, item_id: str, destination_id: str) -> dict:
    """Move an owned item to a new parent: a container or the character root.

    Validates that the item is in the character's inventory and not currently
    worn, that the destination is the character or an owned container, that the
    move is not a no-op, and that it does not place a container inside itself or a
    descendant. The relocation removes the item from its current parent's Contents
    and appends it to the destination's Contents atomically.

    Raises:
        NotFoundError: If the item or destination is not in the inventory.
        ValidationError: If the item is worn, the destination is not a container,
            the move is a no-op, or it would create a cycle.
        ConflictError: If a concurrent change cancels the move.
        RuntimeError: If the transaction fails for a non-conditional reason.
    """
    character_id = character.get("CharacterID", "")

    source = locate_item(character, item_id)
    if not source.get("found"):
        raise NotFoundError("Item not found in character inventory")
    if (source.get("item_record") or {}).get("IsWorn", False):
        raise ValidationError("Unequip the item before moving it")

    if destination_id == character_id:
        dest_kind, dest_id = PARENT_CHARACTER, character_id
    else:
        dest_location = locate_item(character, destination_id)
        if not dest_location.get("found"):
            raise NotFoundError("Destination container not found in inventory")
        if not item_is_container(dest_location.get("item_record") or {}):
            raise ValidationError("Destination is not a container")
        dest_kind, dest_id = PARENT_ITEM, destination_id

    if source["parent_kind"] == dest_kind and source["parent_id"] == dest_id:
        raise ValidationError("Item is already in the destination")

    if destination_in_subtree(item_id, dest_id, source.get("item_record")):
        raise ValidationError("Cannot move a container into itself or its own contents")

    new_source_contents = [cid for cid in source["parent_contents"] if cid != item_id]
    transact_items = build_move_transaction(
        source["parent_kind"], source["parent_id"], dest_kind, dest_id, item_id, new_source_contents
    )

    try:
        dynamo.transact_write_items(transact_items)
    except ClientError as err:
        if err.response.get("Error", {}).get("Code") == "TransactionCanceledException":
            logger.warning(f"Move cancelled for item {item_id} (inventory changed)")
            raise ConflictError("Inventory changed during move. Refresh and retry.") from err
        logger.error(f"Failed to move item {item_id} for character {character_id}: {err}")
        raise RuntimeError("Failed to move item") from err

    logger.info(f"Moved item {item_id} to {dest_kind} {dest_id} for character {character_id}")
    return {"Success": True, "ItemID": item_id, "DestinationID": dest_id}
