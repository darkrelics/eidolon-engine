"""
Eidolon Engine - Incremental Game

Copyright 2024-2026 Jason E. Robinson

Lambda function to split a stackable item into two separate stacks.
The new stack is placed alongside the original in the same parent container.

Endpoint: POST /item/split
Authentication: Cognito (required)
"""

from botocore.exceptions import ClientError

from eidolon.character_data import character_get
from eidolon.contents import append_to_contents, locate_item
from eidolon.dynamo import TableName, dynamo
from eidolon.errors import ConflictError, NotFoundError, UnauthorizedError
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.player import validate_player
from eidolon.prototypes import get_prototype
from eidolon.requests import parse_event_body
from eidolon.story_rewards import create_reward_item
from eidolon.validation import validate_uuid


def execute_split(
    character_id: str,
    location: dict,
    item_id: str,
    current_quantity: int,
    split_quantity: int,
    prototype_id: str,
) -> dict:
    """Decrement the original stack, mint a new stack, place it alongside."""
    remaining_quantity = current_quantity - split_quantity
    parent_kind = location["parent_kind"]
    parent_id = location["parent_id"]

    # Update the original stack with a quantity precondition to catch races.
    try:
        dynamo.update_item(
            TableName.ITEMS,
            Key={"ItemID": item_id},
            UpdateExpression="SET Quantity = :remaining",
            ConditionExpression="Quantity = :expected",
            ExpressionAttributeValues={
                ":remaining": remaining_quantity,
                ":expected": current_quantity,
            },
        )
    except ClientError as err:
        if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.warning(f"Split failed: item {item_id} quantity changed (race)")
            raise ConflictError("Stack quantity changed during split. Please refresh your inventory.") from err
        logger.error(f"Failed to decrement original stack {item_id}: {err}")
        raise RuntimeError("Failed to split stack") from err

    new_item = create_reward_item(
        prototype_id=prototype_id,
        quantity=split_quantity,
        owner_id=character_id,
    )
    if not new_item:
        restore_original_quantity(item_id, current_quantity)
        raise RuntimeError("Failed to create new stack item")
    new_item_id = new_item.get("ItemID", "")

    try:
        append_to_contents(parent_kind, parent_id, [new_item_id])
    except RuntimeError as err:
        cleanup_orphaned_item(new_item_id)
        restore_original_quantity(item_id, current_quantity)
        raise RuntimeError(f"Failed to record new stack in parent Contents: {err}") from err

    logger.info(
        f"Split item {item_id} for character {character_id}: {split_quantity} into new stack "
        f"{new_item_id}, {remaining_quantity} remaining"
    )

    return {
        "Success": True,
        "OriginalStack": {"ItemID": item_id, "RemainingQuantity": remaining_quantity},
        "NewStack": {"ItemID": new_item_id, "Quantity": split_quantity},
        "PrototypeID": prototype_id,
    }


def restore_original_quantity(item_id: str, quantity: int) -> None:
    """Roll back the original stack's quantity on a post-decrement failure."""
    try:
        dynamo.update_item(
            TableName.ITEMS,
            Key={"ItemID": item_id},
            UpdateExpression="SET Quantity = :q",
            ExpressionAttributeValues={":q": quantity},
        )
    except ClientError as err:
        logger.error(f"Failed to restore original stack quantity for {item_id}: {err}")


def cleanup_orphaned_item(item_id: str) -> None:
    """Delete an orphaned item created during a failed split."""
    try:
        dynamo.delete_item(TableName.ITEMS, Key={"ItemID": item_id})
    except ClientError as err:
        logger.error(f"Failed to clean up orphaned item {item_id}: {err}")


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """Lambda handler for splitting a stackable item into two stacks.

    Request Body:
        {
            "CharacterID": "uuid",
            "ItemID": "uuid",
            "Quantity": 5  (number of items to split off into new stack)
        }
    """
    if not validate_player(player_id):
        logger.error(f"Player {player_id} not found in database")
        raise UnauthorizedError("Unauthorized")

    body = parse_event_body(event)
    character_id = body.get("CharacterID", "")
    item_id = body.get("ItemID", "")
    split_quantity = body.get("Quantity")

    if not character_id:
        raise ValueError("CharacterID is required")
    if not item_id:
        raise ValueError("ItemID is required")
    if split_quantity is None:
        raise ValueError("Quantity is required")
    if not validate_uuid(character_id):
        raise ValueError("Invalid CharacterID format")
    if not validate_uuid(item_id):
        raise ValueError("Invalid ItemID format")

    try:
        split_quantity = int(split_quantity)
    except (TypeError, ValueError) as err:
        raise ValueError("Invalid Quantity value") from err
    if split_quantity < 1:
        raise ValueError("Quantity must be at least 1")

    character = character_get(character_id, player_id)

    location = locate_item(character, item_id)
    if not location.get("found"):
        raise NotFoundError("Item not found in character inventory")

    item_record = location.get("item_record") or {}
    prototype_id = item_record.get("PrototypeID")
    if not prototype_id:
        raise NotFoundError("Item prototype reference missing")

    prototype = get_prototype(prototype_id)
    if not prototype:
        raise NotFoundError("Item prototype not found")
    if not prototype.get("Stackable", False):
        raise ValueError("Cannot split non-stackable items")

    current_quantity = int(item_record.get("Quantity", 1))
    if split_quantity > current_quantity:
        raise ValueError(f"Cannot split {split_quantity} items from a stack of {current_quantity}")
    if split_quantity == current_quantity:
        raise ValueError("Cannot split entire stack. Use a smaller quantity.")

    result = execute_split(character_id, location, item_id, current_quantity, split_quantity, prototype_id)
    return {"status_code": 200, "body": result}
