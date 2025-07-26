"""
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

"""

import os
import sys

# Add parent directory to path to import eidolon modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from botocore.exceptions import ClientError

from eidolon.dynamo import dynamo  # noqa: E402
from eidolon.dynamo import TABLE_ENV_MAP
from eidolon.dynamo import TableName

# Define table names mapping
TABLE_NAMES = {
    "players": TableName.PLAYERS,
    "characters": TableName.CHARACTERS,
    "rooms": TableName.ROOMS,
    "exits": TableName.EXITS,
    "items": TableName.ITEMS,
    "prototypes": TableName.PROTOTYPES,
    "archetypes": TableName.ARCHETYPES,
    "motd": TableName.MOTD,
    "story": TableName.STORY,
    "segments": TableName.SEGMENTS,
    "active_segments": TableName.ACTIVE_SEGMENTS,
    "opponents": TableName.OPPONENTS,
    "character_history": TableName.CHARACTER_HISTORY,
    "history": TableName.HISTORY,
}


def view_table(table_name, table_enum):
    """View contents of a DynamoDB table.

    Args:
        table_name: Logical name of the table (e.g., "players")
        table_enum: TableName enum value
    """
    try:
        result: dict = dynamo.scan(table_enum)  # type: ignore
        items = result.get("items", [])
        actual_table_name = TABLE_ENV_MAP[table_enum]

        print(f"\nContents of table: {table_name} ({actual_table_name})")
        print("=" * 50)
        for item in items:
            print(item)
        print("=" * 50)
        print(f"Total items: {len(items)}")
        print()
    except ClientError as err:
        print(f"Error scanning table {table_name}: {err}")
    except Exception as err:
        print(f"Unexpected error scanning table {table_name}: {err}")


def main():
    """View contents of all DynamoDB tables."""
    try:
        # List all tables
        print("Available tables:")
        for logical_name, table_enum in TABLE_NAMES.items():
            actual_name = TABLE_ENV_MAP.get(table_enum, "Not configured")
            print(f"  {logical_name}: {actual_name}")
        print("=" * 50)

        # View contents of each table
        for logical_name, table_enum in TABLE_NAMES.items():
            view_table(logical_name, table_enum)

    except KeyError as err:
        print(f"Configuration error: {err}")
        sys.exit(1)
    except Exception as err:
        print(f"Error connecting to DynamoDB: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
