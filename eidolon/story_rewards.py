"""
Story reward calculation and application.

Provides functions for calculating and applying story rewards.
"""

from botocore.exceptions import ClientError

from eidolon.contents import PARENT_CHARACTER, append_to_contents
from eidolon.dynamo import TableName, dynamo
from eidolon.items import (
    build_item_from_prototype,
    create_item_from_prototype,
    distribute_into_stacks,
    get_stack_space,
    load_top_level_stacks,
)
from eidolon.logger import logger
from eidolon.prototypes import get_prototype


def create_reward_item(prototype_id: str, quantity=None, owner_id=None) -> dict:
    """
    Create and persist an item for rewards using the shared item creation helper.

    Args:
        prototype_id: The prototype ID for the item
        quantity: Quantity for stackable items (None for default prototype quantity)
        owner_id: The owner's character ID

    Returns:
        Persisted item payload dict or empty dict on failure
    """
    try:
        return create_item_from_prototype(
            prototype_id,
            quantity=quantity,
            owner_id=owner_id,
        )
    except Exception as err:
        logger.error(f"Failed to create reward item for prototype {prototype_id} Error: {err}", exc_info=True)
        return {}


def calculate_story_rewards(story_metadata: dict, outcome: str, segments_completed: int) -> dict:
    """
    Calculate rewards based on story outcome and segments completed.

    Args:
        story_metadata: Story data from STORY table
        outcome: Final outcome (death, failure, minimal, normal, exceptional)
        segments_completed: Number of segments completed

    Returns:
        Dict with calculated rewards (items list with PrototypeID and Quantity)
    """
    rewards = {
        "items": [],
    }

    if outcome == "death":
        return rewards

    reward_tiers_raw = story_metadata.get("RewardTiers", {})
    reward_tiers: dict = {}
    if isinstance(reward_tiers_raw, dict):
        reward_tiers = {str(k).lower(): v for k, v in reward_tiers_raw.items()}
    else:
        reward_tiers = {}

    # Get rewards based on outcome tier
    # Normalize outcome to lowercase since reward_tiers keys are lowercase
    outcome_key = outcome.lower() if outcome else "normal"
    tier_rewards = reward_tiers.get(outcome_key, {})
    if isinstance(tier_rewards, dict):
        rewards["items"] = tier_rewards.get("items", [])
    else:
        rewards["items"] = []

    return rewards


def update_reward_stack_quantity(item_id: str, new_quantity: int, character_id: str = "") -> None:
    """Update an existing item stack's quantity in the Items table.

    Non-fatal on failure since the inventory update will still set the correct quantity.

    Args:
        item_id: Item UUID to update
        new_quantity: New stack quantity
        character_id: Character UUID for OwnerID field
    """
    try:
        item_update_expr = "SET Quantity = :quantity"
        item_values: dict = {":quantity": new_quantity}
        if character_id:
            item_update_expr += ", OwnerID = if_not_exists(OwnerID, :owner)"
            item_values[":owner"] = character_id
        dynamo.update_item(
            TableName.ITEMS,
            Key={"ItemID": item_id},
            UpdateExpression=item_update_expr,
            ExpressionAttributeValues=item_values,
        )
    except ClientError as err:
        logger.error(f"Failed to update quantity for reward stack {item_id} Error: {err}", exc_info=True)


def _plan_item_reward(
    character_id: str,
    top_level_ids: list,
    prototype_id: str,
    quantity: int,
    planned_new_items: list,
    planned_stack_updates: list,
) -> list:
    """Plan ITEMS-table writes for a single reward entry.

    Returns the list of new ItemIDs that must be appended to the character's
    top-level Contents. Also appends payloads to ``planned_new_items`` and
    ``(item_id, new_quantity)`` tuples to ``planned_stack_updates`` for stack
    top-ups.
    """
    prototype = get_prototype(prototype_id)
    is_stackable = prototype.get("Stackable", False) if prototype else False
    new_item_ids: list = []

    if not is_stackable:
        for _ in range(quantity):
            payload = build_item_from_prototype(prototype_id, owner_id=character_id)
            if not payload:
                continue
            planned_new_items.append(payload)
            new_item_ids.append(payload["ItemID"])
            logger.info(f"Planned reward item: {payload['ItemID']}")
        return new_item_ids

    max_stack = prototype.get("MaxStack", 99) if prototype else 99
    if max_stack <= 0:
        max_stack = 99

    remaining = quantity
    for item_id, current in load_top_level_stacks(top_level_ids, prototype_id):
        if remaining <= 0:
            break
        space = get_stack_space(current, max_stack)
        if space <= 0:
            continue
        add_qty = min(remaining, space)
        new_quantity = current + add_qty
        remaining -= add_qty
        planned_stack_updates.append((item_id, new_quantity))
        logger.info(f"Planned merge into stack {item_id}: +{add_qty}")

    for stack_qty in distribute_into_stacks(remaining, max_stack) if remaining > 0 else []:
        payload = build_item_from_prototype(prototype_id, quantity=stack_qty, owner_id=character_id)
        if not payload:
            continue
        planned_new_items.append(payload)
        new_item_ids.append(payload["ItemID"])
        logger.info(f"Planned new reward stack: {payload['ItemID']} x{stack_qty}")

    return new_item_ids


def _persist_new_reward_items(planned_new_items: list) -> set:
    """Persist newly-planned items; returns the set of ItemIDs that failed."""
    if not planned_new_items:
        return set()
    failed_payloads = dynamo.batch_write_with_retries(TableName.ITEMS, planned_new_items, operation="put")
    return {payload.get("ItemID") for payload in failed_payloads}


def apply_story_rewards(character_id: str, rewards: dict) -> None:
    """Append reward items to a character's top-level Contents.

    Existing top-level stackables share a prototype get topped up first;
    anything left over becomes new items appended to the character's Contents.
    Stack-quantity bumps happen on the ITEMS records (Contents is a pure ID list
    and doesn't duplicate quantity).
    """
    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
        if not character:
            raise RuntimeError(f"Character {character_id} not found")

        top_level = list(character.get("Contents") or [])

        planned_new_items: list = []
        planned_stack_updates: list = []
        items_to_append: list = []

        for item_reward in rewards.get("items", []):
            if not isinstance(item_reward, dict):
                continue
            prototype_id = item_reward.get("PrototypeID")
            if not prototype_id:
                continue
            quantity = item_reward.get("Quantity", 1)
            new_ids = _plan_item_reward(
                character_id,
                top_level,
                prototype_id,
                quantity,
                planned_new_items,
                planned_stack_updates,
            )
            items_to_append.extend(new_ids)

        if not planned_new_items and not planned_stack_updates:
            logger.info(f"No reward items planned for {character_id}")
            return

        failed_ids = _persist_new_reward_items(planned_new_items)
        if failed_ids:
            logger.error(f"Failed to persist {len(failed_ids)} reward items for {character_id}")
            items_to_append = [item_id for item_id in items_to_append if item_id not in failed_ids]

        for item_id, new_quantity in planned_stack_updates:
            update_reward_stack_quantity(item_id, new_quantity, character_id)

        if items_to_append:
            append_to_contents(PARENT_CHARACTER, character_id, items_to_append)

        logger.info(
            f"Applied story rewards for {character_id}: "
            f"{len(items_to_append)} new top-level items, {len(planned_stack_updates)} merged"
        )

    except ClientError as err:
        logger.error(f"Failed to apply rewards for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to apply rewards: {err}") from err
    except RuntimeError:
        raise
    except Exception as err:
        logger.error(f"Unexpected error applying rewards for {character_id}: {err}", exc_info=True)
        raise RuntimeError(f"Failed to apply rewards: {err}") from err
