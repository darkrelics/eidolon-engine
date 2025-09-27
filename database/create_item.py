"""Utility to create an item from a prototype in the Items table."""

import argparse
import os
import sys
import uuid
from decimal import Decimal

# Ensure repo root is on path before importing eidolon modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eidolon.dynamo import TableName, dynamo


def display_prototypes() -> list:
    """
    Fetches and displays all item prototypes from the 'prototypes' DynamoDB table.

    Returns:
        A list of prototype dictionaries.
    """
    try:
        prototypes = dynamo.scan_all(TableName.PROTOTYPES)
        if not prototypes:
            print("No prototypes found.")
            return []

        print("Available Prototypes:")
        for prototype in prototypes:
            prototype_id = prototype.get("PrototypeID", "No ID")
            name = prototype.get("PrototypeName", "No Name")
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
    # Pick a single slot string for Items.WornOn per schema (string, not list)
    worn_on_value = ""
    prototype_worn_on = prototype.get("WornOn")
    if isinstance(prototype_worn_on, list) and prototype_worn_on:
        # Use the first declared slot as a default
        worn_on_value = str(prototype_worn_on[0])
    elif isinstance(prototype_worn_on, str):
        worn_on_value = prototype_worn_on

    new_item: dict = {
        "ItemID": str(uuid.uuid4()),
        "PrototypeID": prototype.get("PrototypeID", "No ID"),
        "Name": prototype.get("PrototypeName", "Unnamed Item"),
        "Description": prototype.get("Description", ""),
        "Mass": Decimal(str(prototype.get("Mass", 0))),
        "Value": Decimal(str(prototype.get("Value", 0))),
        "Stackable": prototype.get("Stackable", False),
        "MaxStack": Decimal(str(prototype.get("MaxStack", 1))),
        "Quantity": Decimal("1"),
        "Wearable": prototype.get("Wearable", False),
        "WornOn": worn_on_value,
        "Verbs": prototype.get("Verbs", {}),
        "Overrides": prototype.get("Overrides", {}),
        "TraitMods": {k: Decimal(str(v)) for k, v in prototype.get("TraitMods", {}).items()},
        "Container": prototype.get("Container", False),
        "Contents": [],
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
        print(f"Successfully added item '{new_item['Name']}' to Items table.")
        return True
    except Exception as err:
        print(f"Error saving new item to Items table: {err}")
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an item from a prototype in DynamoDB.")
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region for DynamoDB (default: us-east-1)",
    )
    return parser.parse_args()


def main(args: argparse.Namespace) -> None:
    """
    Allows the user to select a prototype and then creates an item in the Items table.
    Conforms to documentation/schema.md field names. Does not link items to rooms.
    """

    dynamo.set_region(args.region)

    while True:
        try:
            prototypes: list = display_prototypes()
            if not prototypes:
                print("No item prototypes found. Please add some prototypes first.")
                break

            prototype_id: str = prompt_for_prototype()
            if not prototype_id:
                print("No prototype selected. Exiting.")
                break

            selected_prototype = next((p for p in prototypes if p.get("PrototypeID") == prototype_id), None)
            if not selected_prototype:
                print("Prototype not found.")
                continue

            print(f"Selected prototype: {selected_prototype}")

            new_item: dict = create_new_item_from_prototype(selected_prototype)
            print(f"New item created: {new_item}")

            try:
                add_item_to_table(new_item)
            except (ValueError, RuntimeError) as err:
                print(f"Failed to add item to table: {err}")
                continue

        except RuntimeError as err:
            print(f"Database error: {err}")
            continue
        except Exception as err:
            print(f"Unexpected error: {err}")
            continue
if __name__ == "__main__":
    main(parse_args())
