"""
This module adds an item based on a prototype to a room.
"""

import uuid
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"  # Replace with your AWS region


def display_rooms(dynamodb) -> list:
    """
    Fetches and displays all rooms from the 'rooms' DynamoDB table.

    Args:
        dynamodb: The DynamoDB resource object.

    Returns:
        A list of room dictionaries.
    """
    try:
        table = dynamodb.Table("rooms")
        response = table.scan()
        rooms = response.get("Items", [])
        if not rooms:
            print("No rooms found.")
            return []

        print("Available Rooms:")
        for room in rooms:
            room_id = int(room["RoomID"])
            title = room.get("Title", "No Title")
            print(f"{room_id}: {title}")
        return rooms
    except ClientError as e:
        print(f"Error fetching rooms: {e.response['Error']['Message']}")
        return []


def prompt_for_room() -> int:
    """
    Prompts the user to enter a room ID.

    Returns:
        The room ID entered by the user, or None to quit.
    """
    while True:
        room_input: str = input("Enter room ID (X to quit): ").strip().upper()
        if room_input == "X":
            return None  # type: ignore
        try:
            return int(room_input)
        except ValueError:
            print("Please enter a valid number or 'X' to quit.")


def display_prototypes(dynamodb) -> list:
    """
    Fetches and displays all item prototypes from the 'prototypes' DynamoDB table.
    """
    try:
        table = dynamodb.Table("prototypes")
        response = table.scan()
        prototypes = response.get("Items", [])
        if not prototypes:
            print("No prototypes found.")
            return []

        print("Available Prototypes:")
        for prototype in prototypes:
            prototype_id = prototype.get("PrototypeID", "No ID")
            name = prototype.get("Name", "No Name")
            print(f"{prototype_id}: {name}")
        return prototypes
    except ClientError as e:
        print(f"Error fetching prototypes: {e.response['Error']['Message']}")
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
        "Name": prototype.get("Name", "Unnamed Item"),
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


def add_item_to_table(dynamodb, new_item: dict) -> bool:
    """
    Adds the new item to the 'items' table.

    Args:
        dynamodb: The DynamoDB resource object.
        new_item: The item dictionary to add.

    Returns:
        True if the item was successfully added to the table, False otherwise.
    """
    items_table = dynamodb.Table("items")
    try:
        items_table.put_item(Item=new_item)
        print(f"Successfully added item '{new_item['Name']}' to items table.")
        return True
    except ClientError as e:
        print(f"Error saving new item to items table: {e.response['Error']['Message']}")
        return False


def add_item_to_room(dynamodb, room: dict, new_item: dict) -> bool:
    """
    Adds the new item to the 'items' table and updates the room to include the item.

    Args:
        dynamodb: The DynamoDB resource object.
        room: The room dictionary where the item will be added.
        new_item: The item dictionary to add.

    Returns:
        True if the item was successfully added to the room, False otherwise.
    """
    rooms_table = dynamodb.Table("rooms")
    room_id = int(room.get("RoomID", 0))

    try:
        # Get the current state of the room
        response = rooms_table.get_item(Key={"RoomID": room_id})
    except ClientError as e:
        print(f"Error getting room: {e.response['Error']['Message']}")
        return False

    current_room = response.get("Item", {})

    if not current_room:
        print(f"Room {room_id} not found.")
        return False

    current_item_ids = current_room.get("ItemID", [])

    # Ensure current_item_ids is a list
    if not isinstance(current_item_ids, list):
        current_item_ids = [current_item_ids] if current_item_ids else []

    # Add the new item's ID to the room's ItemID list
    item_id = new_item.get("ItemID")
    if not item_id:
        print("New item does not have an ID.")
        return False

    current_item_ids.append(item_id)

    try:
        # Update the room with the new ItemID list
        response = rooms_table.update_item(
            Key={"RoomID": room_id},
            UpdateExpression="SET ItemID = :item_ids",
            ExpressionAttributeValues={":item_ids": current_item_ids},
            ReturnValues="UPDATED_NEW",
        )
        print(f"Successfully updated room {room_id}. New ItemID: {response['Attributes'].get('ItemID', [])}")
    except ClientError as e:
        print(f"Error updating room: {e.response['Error']['Message']}")
        # Attempt to roll back by deleting the item we just added
        try:
            items_table = dynamodb.Table("items")
            items_table.delete_item(Key={"ItemID": new_item["ItemID"]})
            print(f"Rolled back: Deleted item '{new_item['Name']}' from items table.")
        except ClientError as del_e:
            print(f"Error rolling back item addition: {del_e.response['Error']['Message']}")
        return False

    print(f"Successfully added item '{new_item['Name']}' (ItemID: {new_item['ItemID']}) to room {room_id}")
    return True


def main() -> None:
    """
    Allows the user to select a room and a prototype, and then adds an item to the room.
    """

    dynamodb = boto3.resource("dynamodb", region_name=REGION)

    while True:
        rooms: list = display_rooms(dynamodb)
        if not rooms:
            print("No rooms available. Exiting.")
            break

        room_id: int = prompt_for_room()
        if room_id is None:
            print("Exiting.")
            break

        room = next((r for r in rooms if int(r["RoomID"]) == room_id), None)
        if not room:
            print("Room not found.")
            continue

        prototypes: list = display_prototypes(dynamodb)
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

        if add_item_to_table(dynamodb, new_item):
            print(f"Successfully added '{new_item['Name']}' to items table.")
        else:
            print("Failed to add item to table.")
            continue

        if add_item_to_room(dynamodb, room, new_item):
            print(f"Successfully added '{new_item['Name']}' to room {room_id}.")
        else:
            print("Failed to add item to room.")


if __name__ == "__main__":
    main()
