"""
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

This module adds an item based on a prototype to a room.
"""

import os
import sys
import uuid
from decimal import Decimal

# Add parent directory to path to import eidolon modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from botocore.exceptions import ClientError

from eidolon.dynamo import dynamo  # noqa: E402
from eidolon.dynamo import TableName


def display_rooms() -> list:
    """
    Fetches and displays all rooms from the 'rooms' DynamoDB table.

    Returns:
        A list of room dictionaries.
    """
    try:
        rooms = dynamo.scan(TableName.ROOMS)
        if not rooms:
            print("No rooms found.")
            return []

        print("Available Rooms:")
        for room in rooms:
            room_id = int(room["RoomID"])
            title = room.get("Title", "No Title")
            print(f"{room_id}: {title}")
        return rooms
    except Exception as err:
        print(f"Error fetching rooms: {err}")
        return []


def prompt_for_room():
    """
    Prompts the user to enter a room ID.

    Returns:
        The room ID entered by the user, or None to quit.
    """
    while True:
        room_input = input("Enter room ID (X to quit): ").strip().upper()
        if room_input == "X":
            return None
        try:
            return int(room_input)
        except ValueError:
            print("Please enter a valid number or 'X' to quit.")


def display_prototypes() -> list:
    """
    Fetches and displays all item prototypes from the 'prototypes' DynamoDB table.
    """
    try:
        prototypes = dynamo.scan(TableName.PROTOTYPES)
        if not prototypes:
            print("No prototypes found.")
            return []

        print("Available Prototypes:")
        for prototype in prototypes:
            prototype_id = prototype.get("PrototypeID", "No ID")
            name = prototype.get("prototype_name", "No Name")
            print(f"{prototype_id}: {name}")
        return prototypes
    except Exception as err:
        print(f"Error fetching prototypes: {err}")
        return []


def prompt_for_prototype() -> str:
    """
    Prompts the user to enter a prototype ID.

    Returns:
        The prototype ID entered by the user, or an empty string to cancel.
    """
    return input("Enter prototype ID (empty to cancel): ").strip()


def create_new_item_from_prototype(prototype: dict) -> dict:
    """
    Creates a new item based on the given prototype.

    Args:
        prototype: The prototype dictionary.

    Returns:
        A new item dictionary with a unique ID and properties copied from the prototype.
    """
    new_item: dict = {
        "ItemID": str(uuid.uuid4()),
        "PrototypeID": prototype.get("PrototypeID", "No ID"),
        "item_name": prototype.get("prototype_name", "Unnamed Item"),
        "Description": prototype.get("Description", ""),
        "Mass": Decimal(str(prototype.get("Mass", 0))),
        "Value": Decimal(str(prototype.get("Value", 0))),
        "Stackable": prototype.get("Stackable", False),
        "MaxStack": Decimal(str(prototype.get("MaxStack", 1))),
        "Quantity": Decimal("1"),
        "Wearable": prototype.get("Wearable", False),
        "WornOn": prototype.get("WornOn", []),
        "Verbs": prototype.get("Verbs", {}),
        "Overrides": prototype.get("Overrides", {}),
        "TraitMods": {
            k: Decimal(str(v)) for k, v in prototype.get("TraitMods", {}).items()
        },
        "Container": prototype.get("Container", False),
        "Contents": prototype.get("Contents", []),
        "IsWorn": False,
        "CanPickUp": prototype.get("CanPickUp", True),
        "Metadata": prototype.get("Metadata", {}),
    }
    return new_item


def add_item_to_table(new_item: dict) -> bool:
    """
    Adds the new item to the 'items' table.

    Args:
        new_item: The item dictionary to add.

    Returns:
        True if the item was successfully added to the table, False otherwise.
    """
    try:
        dynamo.put_item(TableName.ITEMS, new_item)
        print(f"Successfully added item '{new_item['item_name']}' to items table.")
        return True
    except Exception as err:
        print(f"Error saving new item to items table: {err}")
        return False


def add_item_to_room(room: dict, new_item: dict) -> None:
    """
    Adds the new item to the 'items' table and updates the room to include the item.

    Args:
        room: The room dictionary where the item will be added.
        new_item: The item dictionary to add.

    Raises:
        ValueError: If room or item data is invalid
        RuntimeError: If database operations fail
    """
    room_id = int(room.get("RoomID", 0))

    try:
        current_room = dynamo.get_item(TableName.ROOMS, {"RoomID": room_id})
    except ClientError as err:
        raise RuntimeError(f"Error fetching room: {err}")

    if not current_room:
        raise ValueError(f"Room {room_id} not found.")

    current_item_ids = current_room.get("ItemID", [])

    if not isinstance(current_item_ids, list):
        current_item_ids = [current_item_ids] if current_item_ids else []

    # Add the new item's ID to the room's ItemID list
    item_id = new_item.get("ItemID")
    if not item_id:
        raise ValueError("New item does not have an ID.")

    current_item_ids.append(item_id)

    try:
        dynamo.update_item(
            TableName.ROOMS,
            Key={"RoomID": room_id},
            UpdateExpression="SET ItemID = :item_ids",
            ExpressionAttributeValues={":item_ids": current_item_ids},
        )
        print(
            f"Successfully added item '{new_item['item_name']}' (ItemID: {new_item['ItemID']}) to room {room_id}"
        )
    except ClientError as err:
        # Attempt to roll back by deleting the item we just added
        try:
            dynamo.delete_item(TableName.ITEMS, Key={"ItemID": new_item["ItemID"]})
            print(
                f"Rolled back: Deleted item '{new_item['item_name']}' from items table."
            )
        except ClientError as rollback_err:
            print(f"Error rolling back item addition: {rollback_err}")
        raise RuntimeError(f"Error updating room: {err}")


def main() -> None:
    """
    Allows the user to select a room and a prototype, and then adds an item to the room.
    """

    while True:
        try:
            rooms: list = display_rooms()
            if not rooms:
                print("No rooms available. Exiting.")
                break

            room_id = prompt_for_room()
            if room_id is None:
                print("Exiting.")
                break

            room = next((r for r in rooms if int(r["RoomID"]) == room_id), None)
            if not room:
                print("Room not found.")
                continue

            prototypes: list = display_prototypes()
            if not prototypes:
                print("No item prototypes found. Please add some prototypes first.")
                continue

            prototype_id: str = prompt_for_prototype()
            if not prototype_id:
                print("No prototype selected. Returning to room selection.")
                continue

            selected_prototype = next(
                (p for p in prototypes if p.get("PrototypeID") == prototype_id), None
            )
            if not selected_prototype:
                print("Prototype not found.")
                continue

            print(f"Selected prototype: {selected_prototype}")

            new_item: dict = create_new_item_from_prototype(selected_prototype)
            print(f"New item created: {new_item}")

            try:
                add_item_to_table(new_item)
                print(f"Successfully added '{new_item['item_name']}' to items table.")
            except (ValueError, RuntimeError) as err:
                print(f"Failed to add item to table: {err}")
                continue

            try:
                add_item_to_room(room, new_item)
                print(f"Successfully added '{new_item['item_name']}' to room {room_id}.")
            except (ValueError, RuntimeError) as err:
                print(f"Failed to add item to room: {err}")

        except RuntimeError as err:
            print(f"Database error: {err}")
            continue
        except Exception as err:
            print(f"Unexpected error: {err}")
            continue


if __name__ == "__main__":
    main()
