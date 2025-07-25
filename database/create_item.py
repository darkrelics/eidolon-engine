"""
Eidolon Engine

Copyright 2024-2025 Jason Robinson

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

This module adds an item based on a prototype to a room.
"""

import os
import sys
import uuid
from decimal import Decimal

# Add parent directory to path to import eidolon modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eidolon.dynamo import TableName, dynamo  # noqa: C0413


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
        "TraitMods": {k: Decimal(str(v)) for k, v in prototype.get("TraitMods", {}).items()},
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


def add_item_to_room(room: dict, new_item: dict) -> bool:
    """
    Adds the new item to the 'items' table and updates the room to include the item.

    Args:
        room: The room dictionary where the item will be added.
        new_item: The item dictionary to add.

    Returns:
        True if the item was successfully added to the room, False otherwise.
    """
    room_id = int(room.get("RoomID", 0))

    try:
        current_room = dynamo.get_item(TableName.ROOMS, {"RoomID": room_id})
    except Exception as err:
        print(f"Error fetching room: {err}")
        return False

    if not current_room:
        print(f"Room {room_id} not found.")
        return False

    current_item_ids = current_room.get("ItemID", [])

    if not isinstance(current_item_ids, list):
        current_item_ids = [current_item_ids] if current_item_ids else []

    # Add the new item's ID to the room's ItemID list
    item_id = new_item.get("ItemID")
    if not item_id:
        print("New item does not have an ID.")
        return False

    current_item_ids.append(item_id)

    try:
        dynamo.update_item(
            TableName.ROOMS,
            Key={"RoomID": room_id},
            UpdateExpression="SET ItemID = :item_ids",
            ExpressionAttributeValues={":item_ids": current_item_ids}
        )
        print(f"Successfully added item '{new_item['item_name']}' (ItemID: {new_item['ItemID']}) to room {room_id}")
        return True
    except Exception as err:
        print(f"Error updating room: {err}")
        # Attempt to roll back by deleting the item we just added
        try:
            dynamo.delete_item(TableName.ITEMS, Key={"ItemID": new_item["ItemID"]})
            print(f"Rolled back: Deleted item '{new_item['item_name']}' from items table.")
        except Exception as rollback_err:
            print(f"Error rolling back item addition: {rollback_err}")
        return False


def main() -> None:
    """
    Allows the user to select a room and a prototype, and then adds an item to the room.
    """

    while True:
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

        selected_prototype = next((p for p in prototypes if p.get("PrototypeID") == prototype_id), None)
        if not selected_prototype:
            print("Prototype not found.")
            continue

        print(f"Selected prototype: {selected_prototype}")

        new_item: dict = create_new_item_from_prototype(selected_prototype)
        print(f"New item created: {new_item}")

        if add_item_to_table(new_item):
            print(f"Successfully added '{new_item['item_name']}' to items table.")
        else:
            print("Failed to add item to table.")
            continue

        if add_item_to_room(room, new_item):
            print(f"Successfully added '{new_item['item_name']}' to room {room_id}.")
        else:
            print("Failed to add item to room.")


if __name__ == "__main__":
    main()
