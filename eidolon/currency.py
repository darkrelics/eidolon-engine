"""Currency management: coins as stackable items, the wallet derived from them.

Currency is held as stackable coin items at the character's top-level Contents
(the purse). A coin prototype is any prototype carrying ``Metadata.Denomination``;
its worth is the prototype's ``Value`` in Fundamental Units (FU). The smallest
coin (bronze) is 10 FU, so every coin-representable amount is a multiple of 10.

The wallet is canonicalized on every change: after a debit or credit the coins
are replaced by the minimal set that represents the new total (greedy, largest
denomination first), so a character holds at most one stack per denomination and
the wallet total is the single source of truth - there is no separate scalar
balance. Coin ItemIDs therefore change whenever the balance changes.
"""

from functools import cache

from botocore.exceptions import ClientError

from eidolon.dynamo import TABLE_ENV_MAP, TableName, dynamo, to_attribute_value
from eidolon.errors import PaymentRequiredError
from eidolon.items import build_item_from_prototype
from eidolon.logger import logger


@cache
def coin_registry() -> tuple:
    """Return coin denominations as ``((prototype_id, value_fu), ...)``, value desc.

    Discovered once from the PROTOTYPES table - immutable game data, safe to cache
    for the container lifetime - by scanning for prototypes that carry
    ``Metadata.Denomination``. The worth of each coin is its ``Value`` field (FU).
    """
    try:
        records = dynamo.scan_all(
            TableName.PROTOTYPES,
            FilterExpression="attribute_exists(#md.#den)",
            ExpressionAttributeNames={"#md": "Metadata", "#den": "Denomination"},
        )
    except ClientError as err:
        logger.error(f"Failed to load coin prototypes: {err}")
        raise RuntimeError("Failed to load currency prototypes") from err

    coins = []
    for record in records:
        prototype_id = record.get("PrototypeID")
        value = record.get("Value")
        if prototype_id and value:
            coins.append((prototype_id, int(value)))

    coins.sort(key=lambda coin: coin[1], reverse=True)
    return tuple(coins)


def coin_value_map() -> dict:
    """Return a ``{prototype_id: value_fu}`` map for all coin denominations."""
    return {prototype_id: value for prototype_id, value in coin_registry()}


def find_coin_stacks(character: dict) -> list:
    """Return ``[(item_id, prototype_id, quantity, value_fu)]`` for top-level coins.

    Only the character's top-level Contents (the purse) is considered spendable;
    coins stored inside a container are not part of the wallet.
    """
    values = coin_value_map()
    stacks: list = []
    for item_id in character.get("Contents") or []:
        if not item_id:
            continue
        record = dynamo.get_item(TableName.ITEMS, {"ItemID": item_id}, ProjectionExpression="PrototypeID, Quantity")
        if not record:
            continue
        value = values.get(record.get("PrototypeID"))
        if value is None:
            continue
        stacks.append((item_id, record.get("PrototypeID"), int(record.get("Quantity", 0) or 0), value))
    return stacks


def total_from_stacks(stacks: list) -> int:
    """Sum the FU value of a list of coin stacks from :func:`find_coin_stacks`."""
    return sum(quantity * value for _, _, quantity, value in stacks)


def wallet_total(character: dict) -> int:
    """Return the character's spendable currency in FU."""
    return total_from_stacks(find_coin_stacks(character))


def canonical_coin_quantities(total_fu: int) -> list:
    """Return ``[(prototype_id, quantity)]`` for the minimal coins representing total_fu.

    Greedy from the largest denomination down. Raises ``ValueError`` if the amount
    cannot be represented exactly (it is not a multiple of the smallest coin).
    """
    if total_fu < 0:
        raise ValueError("Cannot represent negative currency")

    quantities: list = []
    remaining = total_fu
    for prototype_id, value in coin_registry():
        if remaining <= 0:
            break
        count = remaining // value
        if count > 0:
            quantities.append((prototype_id, int(count)))
            remaining -= count * value

    if remaining != 0:
        raise ValueError(f"Amount {total_fu} FU is not representable in the available coin denominations")
    return quantities


def plan_canonicalization(character_id: str, stacks: list, new_total: int) -> dict:
    """Plan replacing the current coin stacks with the canonical set for new_total.

    Args:
        character_id: Owner of the minted coins.
        stacks: Current coin stacks from :func:`find_coin_stacks`.
        new_total: Target wallet balance in FU.

    Returns:
        ``{"old_stacks": [(item_id, quantity)], "new_payloads": [item, ...],
        "removed_ids": [item_id], "new_ids": [item_id]}``.
    """
    new_payloads: list = []
    for prototype_id, quantity in canonical_coin_quantities(new_total):
        payload = build_item_from_prototype(prototype_id=prototype_id, quantity=quantity, owner_id=character_id)
        if not payload:
            raise RuntimeError(f"Failed to build coin item for prototype {prototype_id}")
        new_payloads.append(payload)

    return {
        "new_total": new_total,
        "old_stacks": [(item_id, quantity) for item_id, _, quantity, _ in stacks],
        "new_payloads": new_payloads,
        "removed_ids": [item_id for item_id, _, _, _ in stacks],
        "new_ids": [payload["ItemID"] for payload in new_payloads],
    }


def plan_coin_spend(character: dict, cost_fu: int) -> dict:
    """Validate funds and plan the wallet canonicalization to pay ``cost_fu``.

    Reads the wallet once and returns the plan from :func:`plan_canonicalization`
    for the post-payment balance.

    Raises:
        PaymentRequiredError: If the wallet holds less than ``cost_fu``.
    """
    character_id = character.get("CharacterID", "")
    stacks = find_coin_stacks(character)
    total = total_from_stacks(stacks)
    if total < cost_fu:
        raise PaymentRequiredError(f"Insufficient funds: need {cost_fu}, have {total}")
    return plan_canonicalization(character_id, stacks, total - cost_fu)


def coin_transaction_ops(plan: dict) -> list:
    """Build the transaction ops that delete the old coin stacks and mint the new.

    Each delete is guarded by the stack's expected quantity, so a wallet that
    changed under the caller cancels the whole transaction.
    """
    ops: list = []
    items_table = TABLE_ENV_MAP[TableName.ITEMS]

    for item_id, quantity in plan["old_stacks"]:
        ops.append(
            {
                "Delete": {
                    "TableName": items_table,
                    "Key": {"ItemID": {"S": item_id}},
                    "ConditionExpression": "Quantity = :expected",
                    "ExpressionAttributeValues": {":expected": to_attribute_value(quantity)},
                }
            }
        )

    for payload in plan["new_payloads"]:
        ops.append(
            {
                "Put": {
                    "TableName": items_table,
                    "Item": {field: to_attribute_value(value) for field, value in payload.items()},
                }
            }
        )

    return ops


def contents_after_coin_change(character: dict, plan: dict, added_ids=()) -> list:
    """Return the character's Contents with old coins removed and new ones added.

    ``added_ids`` are extra non-coin ItemIDs (for example purchased goods) appended
    alongside the freshly minted coin stacks.
    """
    removed = set(plan["removed_ids"])
    remaining = [item_id for item_id in (character.get("Contents") or []) if item_id not in removed]
    return remaining + list(plan["new_ids"]) + list(added_ids)


def build_contents_coin_update(character_id: str, character: dict, plan: dict, added_ids=()) -> dict:
    """Build the character Contents update op for a wallet change.

    The new Contents list is set wholesale (the canonicalized coin stacks have new
    ItemIDs), guarded by a ``contains`` check on each removed coin so a concurrent
    wallet change cancels the transaction.
    """
    new_contents = contents_after_coin_change(character, plan, added_ids)
    values = {":new": to_attribute_value(new_contents)}
    update = {
        "Update": {
            "TableName": TABLE_ENV_MAP[TableName.CHARACTERS],
            "Key": {"CharacterID": {"S": character_id}},
            "UpdateExpression": "SET Contents = :new",
            "ExpressionAttributeValues": values,
        }
    }

    conditions = []
    for index, removed_id in enumerate(plan["removed_ids"]):
        placeholder = f":rc{index}"
        conditions.append(f"contains(Contents, {placeholder})")
        values[placeholder] = to_attribute_value(removed_id)
    if conditions:
        update["Update"]["ConditionExpression"] = " AND ".join(conditions)

    return update


def credit_coins(character_id: str, amount_fu: int) -> dict:
    """Grant ``amount_fu`` of currency to a character as canonical coin stacks.

    Provided for reward and drop paths (no caller grants currency yet). Reads the
    wallet, canonicalizes to the new total, and commits the coin and Contents
    changes in one transaction.

    Returns the new wallet total in FU.
    """
    if amount_fu <= 0:
        raise ValueError("Credit amount must be positive")

    character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id}, ProjectionExpression="CharacterID, Contents")
    if not character:
        raise ValueError("Character not found")

    stacks = find_coin_stacks(character)
    new_total = total_from_stacks(stacks) + amount_fu
    plan = plan_canonicalization(character_id, stacks, new_total)

    transact_items = coin_transaction_ops(plan)
    transact_items.append(build_contents_coin_update(character_id, character, plan))

    try:
        dynamo.transact_write_items(transact_items)
    except ClientError as err:
        logger.error(f"Failed to credit {amount_fu} FU to {character_id}: {err}")
        raise RuntimeError("Failed to credit currency") from err

    logger.info(f"Credited {amount_fu} FU to {character_id}; new balance {new_total}")
    return {"CurrencyTotal": new_total}
