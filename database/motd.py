"""
This module adds a Message of the Day (MOTD) to the DynamoDB database.

It allows you to add a new MOTD or update an existing one.
"""

import argparse
import uuid
from datetime import datetime

import boto3
from botocore.exceptions import ClientError


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
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table("motd")  # type: ignore

    motd_id: str = str(uuid.uuid4())

    # Prepare the item data to put into the table
    motd_item = {
        "MotdID": motd_id,
        "Active": active,
        "Message": message,
        "CreatedAt": datetime.utcnow().isoformat(),
    }

    try:
        # Put the item into the 'motd' table
        _ = table.put_item(Item=motd_item)
        print("MOTD added successfully.")
        print(f"MOTD ID: {motd_id}")
        return motd_item
    except ClientError as e:
        error_message = e.response["Error"]["Message"]
        print(f"Error adding/updating MOTD: {error_message}")
        return {}
    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}")
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
