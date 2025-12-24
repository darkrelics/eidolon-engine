"""
Story reward calculation and application.

Provides functions for calculating and applying story rewards.
"""

from decimal import Decimal

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.items import create_coins_from_value, create_item_from_prototype, find_matching_stack
from eidolon.logger import logger


def find_next_available_slot(inventory: dict) -> str:
    """
    Find the next available numeric slot in inventory.

    Args:
        inventory: Inventory dict. Format:
            Non-stackable: {slot: {"ItemID": "..."}}
            Stackable: {slot: {"ItemID": "...", "Quantity": count}}

    Returns:
        Next available slot as string (e.g., "0", "1", "2")
    """
    slot_num = 0
    while str(slot_num) in inventory and inventory[str(slot_num)]:
        slot_num += 1
    return str(slot_num)


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
        Dict with calculated rewards (items, currency)
    """
    rewards = {
        "items": [],
        "currency": 0,
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
        rewards["currency"] = tier_rewards.get("currency", 0)
    else:
        rewards["items"] = []
        rewards["currency"] = 0

    return rewards


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

        items_created = []
        update_expressions = []
        expression_names = {}
        expression_values = {}

        # Handle currency rewards by converting to coin items
        currency_value = rewards.get("currency", 0)
        if currency_value > 0:
            # Create coin items from the currency value
            coin_requests = create_coins_from_value(currency_value)

            # Process each coin type
            for coin_request in coin_requests:
                prototype_id = coin_request.get("PrototypeID")
                quantity = coin_request.get("Quantity")
                if not prototype_id or not quantity:
                    logger.warning(f"Invalid coin request: {coin_request}")
                    continue

                # Check if we have an existing stack of this coin type
                existing_stack = find_matching_stack(inventory, prototype_id)

                if existing_stack:
                    # Merge with existing stack
                    stack_slot, stack_data = existing_stack
                    item_id = stack_data.get("ItemID")
                    current_quantity = stack_data.get("Quantity", 0) or 0
                    new_quantity = current_quantity + quantity

                    # Update the existing stack with new quantity locally
                    if isinstance(inventory.get(stack_slot), dict):
                        inventory[stack_slot]["Quantity"] = new_quantity
                    else:
                        inventory[stack_slot] = {"ItemID": item_id, "Quantity": new_quantity}

                    # Persist quantity (and owner if missing) on the item record
                    if item_id:
                        try:
                            update_expression = "SET Quantity = :quantity"
                            expression_values = {":quantity": new_quantity}
                            if character_id:
                                update_expression += ", OwnerID = if_not_exists(OwnerID, :owner)"
                                expression_values[":owner"] = character_id
                            dynamo.update_item(
                                TableName.ITEMS,
                                Key={"ItemID": item_id},
                                UpdateExpression=update_expression,
                                ExpressionAttributeValues=expression_values,
                            )
                        except ClientError as err:
                            logger.error(
                                "Failed to update quantity for coin stack %s Error: %s",
                                item_id,
                                err,
                                exc_info=True,
                            )
                    logger.info(f"Updated existing coin stack in slot {stack_slot}: +{quantity} (total: {new_quantity})")
                else:
                    # Create new coin stack in next available slot
                    new_item = create_reward_item(prototype_id=prototype_id, quantity=quantity, owner_id=character_id)
                    if not new_item:
                        continue
                    item_id = new_item["ItemID"]
                    next_slot = find_next_available_slot(inventory)
                    slot_entry = {"ItemID": item_id}
                    if new_item.get("Stackable", False):
                        slot_entry["Quantity"] = new_item.get("Quantity", quantity)
                    inventory[next_slot] = slot_entry
                    items_created.append(item_id)
                    logger.info(
                        f"Created new coin stack in slot {next_slot}: {item_id} (Quantity: {slot_entry.get('Quantity', 0)})"
                    )

            # Update character's total currency value
            current_value = character.get("Resources", {}).get("Value", 0)
            new_value = current_value + currency_value

            # Add to update expression
            update_expressions.append("Resources.#value = :value")
            expression_names["#value"] = "Value"
            expression_values[":value"] = Decimal(str(new_value))

            logger.info(f"Updated character currency value: +{currency_value} (total: {new_value})")

        # Handle direct item rewards from story
        item_rewards = rewards.get("items", [])
        for item_reward in item_rewards:
            if isinstance(item_reward, dict):
                prototype_id = item_reward.get("PrototypeID")
                quantity = item_reward.get("Quantity", 1)

                if prototype_id:
                    # For stackable items, check if we can merge
                    existing_stack = find_matching_stack(inventory, prototype_id)

                    if existing_stack:
                        # Merge with existing stack
                        stack_slot, stack_data = existing_stack
                        item_id = stack_data.get("ItemID")
                        current_quantity = stack_data.get("Quantity", 0) or 0
                        new_quantity = current_quantity + quantity

                        if isinstance(inventory.get(stack_slot), dict):
                            inventory[stack_slot]["Quantity"] = new_quantity
                        else:
                            inventory[stack_slot] = {"ItemID": item_id, "Quantity": new_quantity}

                        if item_id:
                            try:
                                update_expression = "SET Quantity = :quantity"
                                expression_values = {":quantity": new_quantity}
                                if character_id:
                                    update_expression += ", OwnerID = if_not_exists(OwnerID, :owner)"
                                    expression_values[":owner"] = character_id
                                dynamo.update_item(
                                    TableName.ITEMS,
                                    Key={"ItemID": item_id},
                                    UpdateExpression=update_expression,
                                    ExpressionAttributeValues=expression_values,
                                )
                            except ClientError as err:
                                logger.error(
                                    "Failed to update quantity for reward stack %s Error: %s",
                                    item_id,
                                    err,
                                    exc_info=True,
                                )
                        logger.info(f"Merged reward item with existing stack in slot {stack_slot}: +{quantity}")
                    else:
                        # Create as new item in next available slot
                        new_item = create_reward_item(
                            prototype_id=prototype_id,
                            quantity=quantity if item_reward.get("Stackable") else None,
                            owner_id=character_id,
                        )
                        if not new_item:
                            continue
                        item_id = new_item["ItemID"]
                        next_slot = find_next_available_slot(inventory)

                        # Stackable: include Quantity field, Non-stackable: omit Quantity
                        if new_item.get("Stackable", False):
                            inventory[next_slot] = {"ItemID": item_id, "Quantity": new_item.get("Quantity", quantity)}
                        else:
                            inventory[next_slot] = {"ItemID": item_id}

                        items_created.append(item_id)
                        logger.info(f"Created reward item in slot {next_slot}: {item_id}")

        # Update inventory in update expression
        update_expressions.append("Inventory = :inventory")
        expression_values[":inventory"] = inventory

        # Build and execute the update
        if update_expressions:
            update_expression = "SET " + ", ".join(update_expressions)

            # ✅ FIX BUG #3: Use conditional update to prevent race conditions
            # If currency was updated, check it hasn't changed (prevents double-reward exploits)
            if currency_value > 0:
                current_value = character.get("Resources", {}).get("Value", 0)
                expression_names["#resources"] = "Resources"
                expression_names["#check_value"] = "Value"

                dynamo.update_item(
                    TableName.CHARACTERS,
                    {"CharacterID": character_id},
                    update_expression,
                    expression_names if expression_names else None,
                    expression_values,
                    "#resources.#check_value = :expected_currency",
                    {":expected_currency": Decimal(str(current_value))},
                )
            else:
                # No currency reward, do unchecked update (only inventory items)
                dynamo.update_item(
                    TableName.CHARACTERS,
                    {"CharacterID": character_id},
                    update_expression,
                    expression_names if expression_names else None,
                    expression_values,
                )

        logger.info(
            f"Applied story rewards for {character_id}: " f"{currency_value} currency value, " f"{len(items_created)} items created"
        )

    except ClientError as err:
        # Check if this was a conditional check failure (rewards already applied = race condition)
        if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.warning("Rewards failed: currency changed during application (race condition/double-reward detected)")
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
