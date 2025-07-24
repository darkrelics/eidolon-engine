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
"""

import os
import sys

# Add parent directory to path to import eidolon modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eidolon.dynamo import get_table

# Define table names
TABLE_NAMES = {
    "players": os.environ.get("PLAYERS_TABLE", "players"),
    "characters": os.environ.get("CHARACTERS_TABLE", "characters"),
    "rooms": os.environ.get("ROOMS_TABLE", "rooms"),
    "exits": os.environ.get("EXITS_TABLE", "exits"),
    "items": os.environ.get("ITEMS_TABLE", "items"),
    "prototypes": os.environ.get("PROTOTYPES_TABLE", "prototypes"),
    "archetypes": os.environ.get("ARCHETYPES_TABLE", "archetypes"),
    "motd": os.environ.get("MOTD_TABLE", "motd"),
    "story": os.environ.get("STORY_TABLE", "story"),
    "segments": os.environ.get("SEGMENTS_TABLE", "segments"),
    "active_segments": os.environ.get("ACTIVE_SEGMENTS_TABLE", "active_segments"),
    "opponents": os.environ.get("OPPONENTS_TABLE", "opponents"),
    "character_history": os.environ.get("CHARACTER_HISTORY_TABLE", "character_history"),
}


def view_table(table_name, actual_table_name):
    """View contents of a DynamoDB table.

    Args:
        table_name: Logical name of the table (e.g., "players")
        actual_table_name: Actual DynamoDB table name
    """
    try:
        table = get_table(actual_table_name)
        response = table.scan()
        items = response["Items"]

        print(f"\nContents of table: {table_name} ({actual_table_name})")
        print("=" * 50)
        for item in items:
            print(item)
        print("=" * 50)
        print(f"Total items: {len(items)}")
        print()
    except Exception as err:
        print(f"Error scanning table {table_name}: {err}")


def main():
    try:
        # List all tables
        print("Available tables:")
        for logical_name, actual_name in TABLE_NAMES.items():
            print(f"  {logical_name}: {actual_name}")
        print("=" * 50)

        # View contents of each table
        for logical_name, actual_name in TABLE_NAMES.items():
            view_table(logical_name, actual_name)

    except Exception as err:
        print(f"Error connecting to DynamoDB: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
