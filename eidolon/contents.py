"""
Tree walk helpers for the character-as-container inventory model.

Both character records and container item records carry a `Contents` list of
ItemIDs. Items and containers nest recursively. These helpers locate items
within the tree and persist mutations to the owning Contents list.
"""

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger


PARENT_CHARACTER = "character"
PARENT_ITEM = "item"


def get_item_record(item_id: str) -> dict:
    """Fetch a single item record from the ITEMS table, or None if missing."""
    try:
        record: dict = dynamo.get_item(TableName.ITEMS, {"ItemID": item_id}) # type: ignore
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
        if not record or not record.get("Container"):
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
                ProjectionExpression="Container, Contents",
            )
        except ClientError as err:
            logger.error(f"Failed to fetch item {current}: {err}")
            continue
        if not record or not record.get("Container"):
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
            raise ValueError("409:Item no longer at expected location. Refresh and retry.") from err
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
