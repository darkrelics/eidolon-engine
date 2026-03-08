"""
Story reward calculation and application.

Provides functions for calculating and applying story rewards.
"""

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.items import (
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
        item_values = {":quantity": new_quantity}
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


def apply_story_rewards(character_id: str, rewards: dict) -> None:
    """
    Apply calculated rewards to a character.

    Args:
        character_id: Character UUID
        rewards: Dict containing items and currency

    Raises:
        RuntimeError: If database operations fail
    """
    try:
        # Get character data from DynamoDB
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
        if not character:
            raise RuntimeError(f"Character {character_id} not found")

        # Get current inventory
        inventory = character.get("Inventory", {})
        if not isinstance(inventory, dict):
            inventory = {}

        # Capture original inventory slots for conditional check
        original_inventory = set(inventory.keys())

        items_created = []
        update_expressions = []
        expression_names = {}
        expression_values = {}

        # Handle item rewards from story with MaxStack enforcement
        item_rewards = rewards.get("items", [])
        for item_reward in item_rewards:
            if isinstance(item_reward, dict):
                prototype_id = item_reward.get("PrototypeID")
                quantity = item_reward.get("Quantity", 1)

                if prototype_id:
                    # Get MaxStack from prototype
                    prototype = get_prototype(prototype_id)
                    is_stackable = prototype.get("Stackable", False) if prototype else False

                    if not is_stackable:
                        # Non-stackable: create individual items
                        for _ in range(quantity):
                            new_item = create_reward_item(
                                prototype_id=prototype_id,
                                quantity=None,
                                owner_id=character_id,
                            )
                            if not new_item:
                                continue
                            item_id = new_item["ItemID"]
                            next_slot = find_next_available_slot(inventory)
                            inventory[next_slot] = {"ItemID": item_id}
                            items_created.append(item_id)
                            logger.info(f"Created reward item in slot {next_slot}: {item_id}")
                    else:
                        # Stackable: respect MaxStack
                        max_stack = prototype.get("MaxStack", 99) if prototype else 99
                        if max_stack <= 0:
                            max_stack = 99

                        remaining_quantity = quantity

                        # First, try to fill existing stacks
                        while remaining_quantity > 0:
                            existing_stack = find_matching_stack(inventory, prototype_id, quantity_to_add=1)
                            if not existing_stack:
                                break

                            stack_slot, stack_data = existing_stack
                            item_id = stack_data.get("ItemID")
                            current_quantity = stack_data.get("Quantity", 0) or 0
                            space_available = get_stack_space(current_quantity, max_stack)

                            if space_available <= 0:
                                break

                            add_qty = min(remaining_quantity, space_available)
                            new_quantity = current_quantity + add_qty
                            remaining_quantity -= add_qty

                            if isinstance(inventory.get(stack_slot), dict):
                                inventory[stack_slot]["Quantity"] = new_quantity
                            else:
                                inventory[stack_slot] = {"ItemID": item_id, "Quantity": new_quantity}

                            if item_id:
                                update_reward_stack_quantity(item_id, new_quantity, character_id)
                            logger.info(f"Merged reward item with existing stack in slot {stack_slot}: +{add_qty}")

                        # Create new stacks for remaining quantity
                        if remaining_quantity > 0:
                            stack_quantities = distribute_into_stacks(remaining_quantity, max_stack)
                            for stack_qty in stack_quantities:
                                new_item = create_reward_item(
                                    prototype_id=prototype_id,
                                    quantity=stack_qty,
                                    owner_id=character_id,
                                )
                                if not new_item:
                                    continue
                                item_id = new_item["ItemID"]
                                next_slot = find_next_available_slot(inventory)
                                inventory[next_slot] = {"ItemID": item_id, "Quantity": stack_qty}
                                items_created.append(item_id)
                                logger.info(f"Created reward item in slot {next_slot}: {item_id}")

        # Update inventory in update expression
        update_expressions.append("Inventory = :inventory")
        expression_values[":inventory"] = inventory

        # Build and execute the update
        if update_expressions:
            update_expression = "SET " + ", ".join(update_expressions)

            # Use inventory slot check to prevent race conditions
            first_new_slot = None
            for slot in inventory:
                if slot not in original_inventory:
                    first_new_slot = slot
                    break

            if first_new_slot:
                expression_names["#check_slot"] = first_new_slot
                dynamo.update_item(
                    TableName.CHARACTERS,
                    {"CharacterID": character_id},
                    update_expression,
                    expression_names,
                    expression_values,
                    "attribute_not_exists(Inventory.#check_slot)",
                )
            else:
                # Only updating existing stacks, no new slots
                dynamo.update_item(
                    TableName.CHARACTERS,
                    {"CharacterID": character_id},
                    update_expression,
                    expression_names if expression_names else None,
                    expression_values,
                )

        logger.info(f"Applied story rewards for {character_id}: {len(items_created)} items created")

    except ClientError as err:
        # Check if this was a conditional check failure (rewards already applied = race condition)
        if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.warning("Rewards failed: inventory changed during application (race condition detected)")
            raise RuntimeError("Rewards already applied or character state changed") from err

        logger.error(f"Failed to apply rewards for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to apply rewards: {err}") from err
    except Exception as err:
        logger.error(f"Unexpected error applying rewards for {character_id}: {err}", exc_info=True)
        raise RuntimeError(f"Failed to apply rewards: {err}") from err


def apply_combat_rewards(character_id: str, opponent_data: dict) -> None:
    """
    Apply rewards from defeating an opponent in combat.

    Args:
        character_id: Character UUID
        opponent_data: Opponent data including XPReward and Items

    Raises:
        RuntimeError: If database operations fail
    """
    try:
        # Segment processing already applied skill/attribute XP.
        # Additional combat rewards must come from segment/story data; none are applied here.
        items = opponent_data.get("Items", [])
        if items:
            logger.info(
                "Item rewards are defined on the opponent but segment/story data must trigger distribution; skipping Dynamo writes"
            )

        logger.info(f"No additional combat rewards applied for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to apply combat rewards for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to apply combat rewards: {err}") from err
