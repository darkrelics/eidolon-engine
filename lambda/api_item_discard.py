"""
Eidolon Engine - Incremental Game

Copyright 2024-2026 Jason E. Robinson

Lambda function to discard (delete) items from a character's Contents tree.
Removes items permanently without applying any effects.

Endpoint: POST /item/discard
Authentication: Cognito (required)
"""

from botocore.exceptions import ClientError

from eidolon.character_data import character_get
from eidolon.contents import locate_item, write_contents
from eidolon.dynamo import TableName, dynamo
from eidolon.items import get_item_brief
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.player import validate_player
from eidolon.requests import parse_event_body
from eidolon.story_rewards import update_reward_stack_quantity
from eidolon.validation import validate_uuid


def discard_item(character_id: str, player_id: str, item_id: str, quantity_to_discard) -> dict:
    """Discard an item from the character's Contents tree.

    Locates ``item_id`` anywhere in the character's nested contents, removes
    the requested quantity, and persists the update on the owning parent
    (character or container item).
    """
    try:
        character = character_get(character_id, player_id)
    except ValueError as err:
        normalized = str(err).lower()
        logger.warning(f"Character access denied: {err}")
        if "not found" in normalized:
            raise ValueError(f"404:{err}") from err
        if "not owned" in normalized:
            raise ValueError(f"403:{err}") from err
        raise

    location = locate_item(character, item_id)
    if not location.get("found"):
        raise ValueError("404:Item not found in character inventory")

    item_record = location.get("item_record") or {}
    try:
        item_brief = get_item_brief(item_id)
        prototype_id = item_brief.get("PrototypeID")
    except ValueError as err:
        logger.warning(f"Item brief not found for {item_id}, continuing with discard: {err}")
        prototype_id = "unknown"

    is_stackable = bool(item_record.get("Stackable"))
    current_quantity = int(item_record.get("Quantity", 1)) if is_stackable else 1

    if quantity_to_discard is None:
        quantity_to_discard = current_quantity
    else:
        quantity_to_discard = min(quantity_to_discard, current_quantity)

    remaining_quantity = current_quantity - quantity_to_discard
    item_fully_discarded = remaining_quantity <= 0 or not is_stackable

    if item_fully_discarded:
        new_contents = [cid for cid in location["parent_contents"] if cid != item_id]
        write_contents(location["parent_kind"], location["parent_id"], new_contents, item_id)
        delete_item_record(item_id)
    else:
        update_reward_stack_quantity(item_id, remaining_quantity)

    logger.info(f"Item {item_id} discarded by character {character_id}: {quantity_to_discard} of {current_quantity}")

    response_body = {
        "Success": True,
        "ItemDiscarded": {"ItemID": item_id, "PrototypeID": prototype_id},
        "QuantityDiscarded": quantity_to_discard,
        "ItemFullyDiscarded": item_fully_discarded,
    }
    if not item_fully_discarded:
        response_body["RemainingQuantity"] = remaining_quantity
    return response_body


def delete_item_record(item_id: str) -> None:
    """Delete an item record from the ITEMS table.

    Non-fatal on failure since the parent Contents update already succeeded.
    """
    try:
        dynamo.delete_item(TableName.ITEMS, Key={"ItemID": item_id})
    except ClientError as err:
        logger.error(f"Failed to delete item record {item_id} from ITEMS table: {err}")


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """Lambda handler for discarding items.

    Request Body:
        {
            "CharacterID": "uuid",
            "ItemID": "uuid",
            "Quantity": 1  (optional; stackables only; default discards entire stack)
        }
    """
    if not validate_player(player_id):
        logger.error(f"Player {player_id} not found in database")
        raise ValueError("401:Unauthorized")

    body = parse_event_body(event)
    character_id = body.get("CharacterID", "")
    item_id = body.get("ItemID", "")
    quantity_to_discard = body.get("Quantity")

    if not character_id:
        raise ValueError("CharacterID is required")
    if not item_id:
        raise ValueError("ItemID is required")
    if not validate_uuid(character_id):
        raise ValueError("Invalid CharacterID format")
    if not validate_uuid(item_id):
        raise ValueError("Invalid ItemID format")

    validated_quantity: int = None  # type: ignore[assignment]
    if quantity_to_discard is not None:
        try:
            validated_quantity = int(quantity_to_discard)
        except (TypeError, ValueError) as err:
            raise ValueError("Invalid Quantity value") from err
        if validated_quantity < 1:
            raise ValueError("Quantity must be at least 1")

    result = discard_item(character_id, player_id, item_id, validated_quantity)
    return {"status_code": 200, "body": result}
