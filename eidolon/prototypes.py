"""Prototype resolution for the Eidolon Engine.

Items are built from prototypes: a prototype is immutable, shared game data
(the PROTOTYPES table) that owns every type-level property - name, mass, value,
stackability, wearability, container-ness, consumable effects, trait modifiers.
An item record references a prototype by ``PrototypeID`` and stores only its own
instance state (Quantity, Contents, IsWorn, OwnerID).

This module is the single place that resolves an item's type properties from its
prototype, so no caller has to trust a copy of a prototype field that may have
been written onto the item record. It depends only on the DynamoDB interface and
the logger, which keeps it below ``items`` and ``contents`` in the import graph.
"""

from functools import cache

from eidolon.dynamo import TableName, dynamo


@cache
def get_prototype(prototype_id: str) -> dict:
    """Retrieve a prototype from DynamoDB with caching.

    Prototypes are immutable game data, so caching them for the life of a warm
    Lambda container is safe and intended.

    Args:
        prototype_id: Prototype ID to fetch

    Returns:
        Prototype data dict or empty dict if not found
    """
    if not prototype_id:
        return {}
    result = dynamo.get_item(TableName.PROTOTYPES, {"PrototypeID": prototype_id})
    return result or {}


def item_is_container(item: dict) -> bool:
    """Return True when the item's prototype marks it as a container.

    Resolves container-ness from the prototype rather than from any ``Container``
    field copied onto the item record. The item must carry its ``PrototypeID``.
    """
    if not item:
        return False
    prototype = get_prototype(item.get("PrototypeID", ""))
    return bool(prototype.get("Container", False))


def item_is_stackable(item: dict) -> bool:
    """Return True when the item's prototype marks it as stackable.

    Resolves stackability from the prototype rather than from any ``Stackable``
    field copied onto the item record. The item must carry its ``PrototypeID``.
    """
    if not item:
        return False
    prototype = get_prototype(item.get("PrototypeID", ""))
    return bool(prototype.get("Stackable", False))
