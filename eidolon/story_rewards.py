"""
Story reward calculation and application.

Provides functions for calculating and applying story rewards.
"""

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.items import (
    build_item_from_prototype,
    create_item_from_prototype,
    distribute_into_stacks,
    find_matching_stack,
    find_next_available_slot,
    get_prototype,
    get_stack_space,
)
from eidolon.logger import logger


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
    inventory: dict,
    prototype_id: str,
    quantity: int,
    character_id: str,
    planned_new_items: list,
    planned_stack_updates: list,
) -> None:
    """Plan the inventory mutation for a single reward entry.

    Mutates ``inventory`` in place. Appends new item payloads to
    ``planned_new_items`` and (item_id, new_quantity) pairs to
    ``planned_stack_updates``. No DynamoDB writes happen here.
    """
    prototype = get_prototype(prototype_id)
    is_stackable = prototype.get("Stackable", False) if prototype else False

    if not is_stackable:
        for _ in range(quantity):
            payload = build_item_from_prototype(prototype_id, owner_id=character_id)
            if not payload:
                continue
            item_id = payload["ItemID"]
            next_slot = find_next_available_slot(inventory)
            inventory[next_slot] = {"ItemID": item_id}
            planned_new_items.append(payload)
            logger.info(f"Planned reward item in slot {next_slot}: {item_id}")
        return

    max_stack = prototype.get("MaxStack", 99) if prototype else 99
    if max_stack <= 0:
        max_stack = 99

    remaining = quantity
    while remaining > 0:
        existing_stack = find_matching_stack(inventory, prototype_id, quantity_to_add=1)
        if not existing_stack:
            break

        stack_slot, stack_data = existing_stack
        item_id = stack_data.get("ItemID")
        current_quantity = stack_data.get("Quantity", 0) or 0
        space_available = get_stack_space(current_quantity, max_stack)

        if space_available <= 0:
            break

        add_qty = min(remaining, space_available)
        new_quantity = current_quantity + add_qty
        remaining -= add_qty

        if isinstance(inventory.get(stack_slot), dict):
            inventory[stack_slot]["Quantity"] = new_quantity
        else:
            inventory[stack_slot] = {"ItemID": item_id, "Quantity": new_quantity}

        if item_id:
            planned_stack_updates.append((item_id, new_quantity))
        logger.info(f"Planned merge into slot {stack_slot}: +{add_qty}")

    if remaining <= 0:
        return

    for stack_qty in distribute_into_stacks(remaining, max_stack):
        payload = build_item_from_prototype(prototype_id, quantity=stack_qty, owner_id=character_id)
        if not payload:
            continue
        item_id = payload["ItemID"]
        next_slot = find_next_available_slot(inventory)
        inventory[next_slot] = {"ItemID": item_id, "Quantity": stack_qty}
        planned_new_items.append(payload)
        logger.info(f"Planned new reward stack in slot {next_slot}: {item_id} x{stack_qty}")


def _persist_new_reward_items(character_id: str, inventory: dict, planned_new_items: list) -> None:
    """Persist newly-planned items, reconciling inventory on partial failure."""
    if not planned_new_items:
        return

    failed_payloads = dynamo.batch_write_with_retries(TableName.ITEMS, planned_new_items, operation="put")
    if not failed_payloads:
        return

    failed_ids = {payload.get("ItemID") for payload in failed_payloads}
    logger.error(
        f"Failed to persist {len(failed_ids)} reward items for {character_id}; reverting their inventory slots"
    )
    reconciled = {
        slot: entry
        for slot, entry in inventory.items()
        if not (isinstance(entry, dict) and entry.get("ItemID") in failed_ids)
    }
    try:
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET Inventory = :inventory",
            ExpressionAttributeValues={":inventory": reconciled},
        )
    except ClientError as err:
        logger.error(
            f"Failed to reconcile inventory for {character_id} after partial reward write Error: {err}",
            exc_info=True,
        )


def apply_story_rewards(character_id: str, rewards: dict) -> None:
    """
    Apply calculated rewards to a character.

    Planning and persistence are separated so the character record is the
    source of truth: the inventory update is written first, then the new
    ITEMS rows (and any stack-quantity bumps) are persisted. If the
    character update fails nothing touches the ITEMS table, so quest
    rewards cannot leak orphaned item rows.

    Args:
        character_id: Character UUID
        rewards: Dict containing items and currency

    Raises:
        RuntimeError: If database operations fail
    """
    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
        if not character:
            raise RuntimeError(f"Character {character_id} not found")

        inventory = character.get("Inventory", {})
        if not isinstance(inventory, dict):
            inventory = {}

        original_inventory = set(inventory.keys())

        planned_new_items: list = []
        planned_stack_updates: list = []

        for item_reward in rewards.get("items", []):
            if not isinstance(item_reward, dict):
                continue
            prototype_id = item_reward.get("PrototypeID")
            if not prototype_id:
                continue
            quantity = item_reward.get("Quantity", 1)
            _plan_item_reward(
                inventory,
                prototype_id,
                quantity,
                character_id,
                planned_new_items,
                planned_stack_updates,
            )

        if not planned_new_items and not planned_stack_updates:
            logger.info(f"No reward items planned for {character_id}")
            return

        # Write character first with an idempotency guard on the first new slot.
        first_new_slot = next((slot for slot in inventory if slot not in original_inventory), None)
        update_kwargs = {
            "Key": {"CharacterID": character_id},
            "UpdateExpression": "SET Inventory = :inventory",
            "ExpressionAttributeValues": {":inventory": inventory},
        }
        if first_new_slot is not None:
            update_kwargs["ExpressionAttributeNames"] = {"#check_slot": first_new_slot}
            update_kwargs["ConditionExpression"] = "attribute_not_exists(Inventory.#check_slot)"

        dynamo.update_item(TableName.CHARACTERS, **update_kwargs)

        # Character is committed. Persist items now.
        _persist_new_reward_items(character_id, inventory, planned_new_items)
        for item_id, new_quantity in planned_stack_updates:
            update_reward_stack_quantity(item_id, new_quantity, character_id)

        logger.info(
            f"Applied story rewards for {character_id}: "
            f"{len(planned_new_items)} created, {len(planned_stack_updates)} merged"
        )

    except ClientError as err:
        if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.warning("Rewards failed: inventory changed during application (race condition detected)")
            raise RuntimeError("Rewards already applied or character state changed") from err

        logger.error(f"Failed to apply rewards for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to apply rewards: {err}") from err
    except RuntimeError:
        raise
    except Exception as err:
        logger.error(f"Unexpected error applying rewards for {character_id}: {err}", exc_info=True)
        raise RuntimeError(f"Failed to apply rewards: {err}") from err
