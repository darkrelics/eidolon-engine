"""
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

This module adds a Message of the Day (MOTD) to the DynamoDB database.
"""

import argparse
import os
import sys
from uuid_extension import uuid7
from datetime import datetime, timezone

# Add parent directory to path to import eidolon modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo


def add_or_update_motd(message: str, active: bool = True) -> dict:
    """
    Adds a new MOTD or updates an existing one in the DynamoDB 'motd' table.

    Args:
        message (str): The message content for the MOTD.
        active (bool): Indicates whether the MOTD is active.

    Returns:
        dict: The MOTD item that was added.

    Raises:
        ValueError: If message is empty.
        RuntimeError: If DynamoDB operation fails.
    """
    if not message:
        raise ValueError("Message cannot be empty")

    # Use time-ordered UUIDv7 for better locality and sorting
    motd_id: str = str(uuid7())

    # Prepare the item data to put into the table
    motd_item = {
        "MotdID": motd_id,
        "Active": active,
        "Message": message,
        # RFC3339/ISO-8601 timestamp with UTC timezone offset
        "CreatedAt": datetime.now(timezone.utc).isoformat(),
    }

    try:
        dynamo.put_item(TableName.MOTD, motd_item)
        print("MOTD added successfully.")
        print(f"MOTD ID: {motd_id}")
        return motd_item
    except ClientError as err:
        raise RuntimeError(f"Failed to add MOTD to DynamoDB: {err}")
    except Exception as err:
        raise RuntimeError(f"Unexpected error adding MOTD: {err}")


def main() -> None:
    """
    Main function to parse command-line arguments and add/update the MOTD.

    Usage:
        python motd.py "Your message here" [--inactive]
    """
    parser = argparse.ArgumentParser(description="Add or update a Message of the Day (MOTD)")
    parser.add_argument("message", type=str, help="The MOTD message")
    parser.add_argument(
        "--inactive",
        action="store_true",
        help="Set this flag to make the MOTD inactive",
    )

    args = parser.parse_args()

    # The MOTD is active by default unless --inactive is specified
    is_active = not args.inactive

    # Add or update the MOTD
    try:
        add_or_update_motd(args.message, active=is_active)
    except ValueError as err:
        print(f"Invalid input: {err}")
        sys.exit(1)
    except RuntimeError as err:
        print(f"Error: {err}")
        sys.exit(1)


main()
