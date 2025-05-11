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

Utility to add an item to a room in the DynamoDB database.
"""

import argparse
import json
import logging
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError


def load_json(file_path):
    """
    Loads JSON data from a file.

    Args:
        file_path (str): The path to the JSON file.

    Returns:
        dict: The data loaded from the JSON file.
    """
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def convert_to_dynamodb_format(data):
    """
    Converts numeric values to Decimal for DynamoDB compatibility.

    Args:
        data: The data to convert.

    Returns:
        The data with numeric values converted to Decimal.
    """
    if isinstance(data, dict):
        return {k: convert_to_dynamodb_format(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_to_dynamodb_format(v) for v in data]
    elif isinstance(data, float):
        return Decimal(str(data))
    else:
        return data


def store_exits(dynamodb, exits_data):
    """
    Stores exit data into the 'exits' DynamoDB table.

    Args:
        dynamodb: The DynamoDB resource object.
        exits_data (dict): The exits data to store.
    """
    exits_table = dynamodb.Table("exits")
    try:
        with exits_table.batch_writer() as exits_batch:
            for exit_data in exits_data.get("exits", []):
                exit_item = {
                    "ExitID": exit_data["ExitID"],
                    "Direction": exit_data["Direction"],
                    "Description": exit_data.get("Description", ""),
                    "TargetRoom": exit_data["TargetRoom"],
                    "ArrivalText": exit_data.get("ArrivalText", ""),
                    "Visible": exit_data["Visible"],
                    "ScriptID": exit_data.get("ScriptID", ""),
                }
                exits_batch.put_item(Item=convert_to_dynamodb_format(exit_item))
        print("Exit data stored in DynamoDB successfully")
    except ClientError as e:
        logging.error(f"An error occurred while storing exits: {e.response['Error']['Message']}")
    except Exception as e:
        logging.error(f"An unexpected error occurred while storing exits: {str(e)}")


def store_rooms(dynamodb, rooms_data):
    """
    Stores room data into the 'rooms' DynamoDB table.

    Args:
        dynamodb: The DynamoDB resource object.
        rooms_data (dict): The rooms data to store.
    """
    rooms_table = dynamodb.Table("rooms")
    try:
        with rooms_table.batch_writer() as rooms_batch:
            for room in rooms_data.get("rooms", []):
                room_item = {
                    "RoomID": room["RoomID"],
                    "Area": room["Area"],
                    "Title": room["Title"],
                    "Description": room["Description"],
                    "ExitID": room["ExitID"],
                    "Persistent": room.get("Persistent", False),  # Default to False if not specified
                    "ScriptID": room.get("ScriptID", ""),  # Default to empty string if not specified
                }
                rooms_batch.put_item(Item=convert_to_dynamodb_format(room_item))
        print("Room data stored in DynamoDB successfully")
    except ClientError as e:
        logging.error(f"An error occurred while storing rooms: {e.response['Error']['Message']}")
    except Exception as e:
        logging.error(f"An unexpected error occurred while storing rooms: {str(e)}")


def store_archetypes(dynamodb, archetypes_data):
    """
    Stores archetype data into the 'archetypes' DynamoDB table.

    Args:
        dynamodb: The DynamoDB resource object.
        archetypes_data (dict): The archetypes data to store.
    """
    table = dynamodb.Table("archetypes")
    try:
        with table.batch_writer() as batch:
            for name, archetype in archetypes_data.get("archetypes", {}).items():
                # Convert attributes to lowercase
                attributes = {k.lower(): v for k, v in archetype.get("Attributes", {}).items()}
                # Convert abilities to lowercase
                abilities = {k.lower(): v for k, v in archetype.get("Abilities", {}).items()}

                archetype_item = {
                    "ArchetypeName": name,
                    "Description": archetype.get("Description", ""),
                    "Attributes": attributes,
                    "Abilities": abilities,
                    "StartRoom": archetype.get("StartRoom", 0),
                }
                batch.put_item(Item=convert_to_dynamodb_format(archetype_item))
        print("Archetype data stored in DynamoDB successfully")
    except ClientError as err:
        logging.error(f"An error occurred while storing archetypes: {err.response['Error']['Message']}")
    except Exception as err:
        logging.error(f"An unexpected error occurred while storing archetypes: {str(err)}")


def store_item_prototypes(dynamodb, prototypes_data):
    """
    Stores item prototype data into the 'prototypes' DynamoDB table.

    Args:
        dynamodb: The DynamoDB resource object.
        prototypes_data (dict): The item prototypes data to store.
    """
    table = dynamodb.Table("prototypes")
    try:
        with table.batch_writer() as batch:
            for prototype in prototypes_data.get("itemPrototypes", []):
                prototype["PrototypeID"] = prototype.pop("PrototypeID")
                batch.put_item(Item=convert_to_dynamodb_format(prototype))
        print("Item prototype data stored in DynamoDB successfully")
    except ClientError as err:
        logging.error(f"An error occurred while storing item prototypes: {err.response['Error']['Message']}")
    except Exception as err:
        logging.error(f"An unexpected error occurred while storing item prototypes: {str(err)}")


def load_exits(dynamodb):
    """
    Loads exit data from the 'exits' DynamoDB table.

    Args:
        dynamodb: The DynamoDB resource object.

    Returns:
        dict: A dictionary of exit data.
    """
    exits_table = dynamodb.Table("exits")
    try:
        exits_response = exits_table.scan()
        exits = {item["ExitID"]: item for item in exits_response.get("Items", [])}
        print("Exit data loaded from DynamoDB successfully")
        return exits
    except ClientError as e:
        logging.error(f"An error occurred while loading exits: {e.response['Error']['Message']}")
        return {}
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading exits: {str(e)}")
        return {}


def load_rooms(dynamodb):
    """
    Loads room data from the 'rooms' DynamoDB table.

    Args:
        dynamodb: The DynamoDB resource object.

    Returns:
        dict: A dictionary of room data.
    """
    rooms_table = dynamodb.Table("rooms")
    try:
        rooms_response = rooms_table.scan()
        rooms = {item["RoomID"]: item for item in rooms_response.get("Items", [])}
        print("Room data loaded from DynamoDB successfully")
        return rooms
    except ClientError as e:
        logging.error(f"An error occurred while loading rooms: {e.response['Error']['Message']}")
        return {}
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading rooms: {str(e)}")
        return {}


def load_archetypes(dynamodb):
    """
    Loads archetype data from the 'archetypes' DynamoDB table.

    Args:
        dynamodb: The DynamoDB resource object.

    Returns:
        dict: A dictionary containing the archetypes.
    """
    table = dynamodb.Table("archetypes")
    try:
        response = table.scan()
        archetypes = {"archetypes": {item["ArchetypeName"]: item for item in response.get("Items", [])}}
        print("Archetype data loaded from DynamoDB successfully")
        return archetypes
    except ClientError as e:
        logging.error(f"An error occurred while loading archetypes: {e.response['Error']['Message']}")
        return {}
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading archetypes: {str(e)}")
        return {}


def load_item_prototypes(dynamodb):
    """
    Loads item prototype data from the 'prototypes' DynamoDB table.

    Args:
        dynamodb: The DynamoDB resource object.

    Returns:
        dict: A dictionary containing the item prototypes.
    """
    table = dynamodb.Table("prototypes")
    try:
        response = table.scan()
        prototypes = {"itemPrototypes": response.get("Items", [])}
        print("Item prototype data loaded from DynamoDB successfully")
        return prototypes
    except ClientError as e:
        logging.error(f"An error occurred while loading item prototypes: {e.response['Error']['Message']}")
        return {}
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading item prototypes: {str(e)}")
        return {}


def display_exits(exits):
    """
    Displays exit information.

    Args:
        exits (dict): The exits data to display.
    """
    print("Exits:")
    for exit_id, exit_data in exits.items():
        print(f"Exit ID: {exit_id}")
        print(f"  Direction: {exit_data['Direction']}")
        if exit_data.get('Description'):
            print(f"  Description: {exit_data['Description']}")
        print(f"  Target Room: {exit_data['TargetRoom']}")
        if exit_data.get('ArrivalText'):
            print(f"  Arrival Text: {exit_data['ArrivalText']}")
        print(f"  Visible: {exit_data['Visible']}")
        if exit_data.get('ScriptID'):
            print(f"  Script ID: {exit_data['ScriptID']}")
        print()


def display_rooms(rooms):
    """
    Displays room information.

    Args:
        rooms (dict): The rooms data to display.
    """
    print("Rooms:")
    for room_id, room in rooms.items():
        print(f"Room {room_id}: {room.get('Title', 'No Title')}")
        print(f"  Area: {room.get('Area', 'Unknown')}")
        print(f"  Description: {room.get('Description', 'No description')}")
        print(f"  Exits: {', '.join(room.get('ExitID', []))}")
        print(f"  Persistent: {room.get('Persistent', False)}")
        print(f"  ScriptID: {room.get('ScriptID', '')}")
        print()


def display_archetypes(archetypes):
    """
    Displays archetype information.

    Args:
        archetypes (dict): The archetypes data to display.
    """
    print("Archetypes:")
    for name, archetype in archetypes.get("archetypes", {}).items():
        print(f"Name: {name}")
        print(f"  Description: {archetype.get('Description', 'No description')}")
        print("  Attributes:")
        for attr, value in archetype.get("Attributes", {}).items():
            print(f"    {attr}: {value}")
        print("  Abilities:")
        for ability, value in archetype.get("Abilities", {}).items():
            print(f"    {ability}: {value}")
        print()


def display_item_prototypes(prototypes):
    """
    Displays item prototype information.

    Args:
        prototypes (dict): The item prototypes data to display.
    """
    print("Item Prototypes:")
    for prototype in prototypes.get("itemPrototypes", []):
        print(f"ID: {prototype.get('PrototypeID', 'No ID')}")
        print(f"  Name: {prototype.get('Name', 'No Name')}")
        print(f"  Description: {prototype.get('Description', 'No description')}")
        print(f"  Mass: {prototype.get('Mass', 'Unknown')}")
        print(f"  Value: {prototype.get('Value', 'Unknown')}")
        print(f"  Wearable: {prototype.get('Wearable', False)}")
        if prototype.get("Wearable"):
            print(f"  Worn on: {', '.join(prototype.get('WornOn', []))}")
        print()


def main():
    """
    Main function to load game data from JSON files and store it in DynamoDB.

    - Parses command-line arguments for file paths and AWS region.
    - Loads data from JSON files.
    - Stores data into DynamoDB tables.
    - Loads data back from DynamoDB and displays it.
    """
    parser = argparse.ArgumentParser(description="Load and store game data in DynamoDB.")
    parser.add_argument("-r", "--rooms", default="../data/test_rooms.json", help="Path to the Rooms JSON file.")
    parser.add_argument("-e", "--exits", default="../data/test_exits.json", help="Path to the Exits JSON file.")
    parser.add_argument("-a", "--archetypes", default="../data/test_archetypes.json", help="Path to the Archetypes JSON file.")
    parser.add_argument("-p", "--prototypes", default="../data/test_prototypes.json", help="Path to the Prototypes JSON file.")
    parser.add_argument("-region", default="us-east-1", help="AWS region for DynamoDB.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    try:
        dynamodb = boto3.resource("dynamodb", region_name=args.region)

        # Load and store exits
        exits_data = load_json(args.exits)
        store_exits(dynamodb, exits_data)

        # Load and store rooms
        rooms_data = load_json(args.rooms)
        store_rooms(dynamodb, rooms_data)

        # Load and store archetypes
        archetypes_data = load_json(args.archetypes)
        store_archetypes(dynamodb, archetypes_data)

        # Load and store item prototypes
        prototypes_data = load_json(args.prototypes)
        store_item_prototypes(dynamodb, prototypes_data)

        # Load data from DynamoDB and display
        loaded_exits = load_exits(dynamodb)
        display_exits(loaded_exits)

        loaded_rooms = load_rooms(dynamodb)
        display_rooms(loaded_rooms)

        loaded_archetypes = load_archetypes(dynamodb)
        display_archetypes(loaded_archetypes)

        loaded_prototypes = load_item_prototypes(dynamodb)
        display_item_prototypes(loaded_prototypes)

    except Exception as e:
        logging.error(f"An unexpected error occurred: {str(e)}")


if __name__ == "__main__":
    main()
