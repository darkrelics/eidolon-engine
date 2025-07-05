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

This module adds a Message of the Day (MOTD) to the DynamoDB database.
"""

import argparse
import uuid
from datetime import datetime

from eidolon.dynamo import tables, safe_put_item


def add_or_update_motd(message: str, active: bool = True) -> dict:
    """
    Adds a new MOTD or updates an existing one in the DynamoDB 'motd' table.

    Args:
        message (str): The message content for the MOTD.
        active (bool): Indicates whether the MOTD is active.

    Returns:
        dict: The response from DynamoDB if the operation was successful.

    Raises:
        ClientError: If an error occurs during the DynamoDB operation.
    """
    motd_id: str = str(uuid.uuid4())

    # Prepare the item data to put into the table
    motd_item = {
        "MotdID": motd_id,
        "Active": active,
        "Message": message,
        "CreatedAt": datetime.utcnow().isoformat(),
    }

    if safe_put_item(tables.motd, motd_item):
        print("MOTD added successfully.")
        print(f"MOTD ID: {motd_id}")
        return motd_item
    else:
        print(f"Error adding/updating MOTD.")
        return {}


def main() -> None:
    """
    Main function to parse command-line arguments and add/update the MOTD.

    Usage:
        python motd.py "Your message here" [--inactive]
    """
    parser = argparse.ArgumentParser(description="Add or update a Message of the Day (MOTD)")
    parser.add_argument("message", type=str, help="The MOTD message")
    parser.add_argument("--inactive", action="store_true", help="Set this flag to make the MOTD inactive")

    args = parser.parse_args()

    # The MOTD is active by default unless --inactive is specified
    is_active = not args.inactive

    # Add or update the MOTD
    add_or_update_motd(args.message, active=is_active)


if __name__ == "__main__":
    main()
