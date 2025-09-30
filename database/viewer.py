"""Simple CLI to display the contents of DynamoDB tables."""

import argparse
import os
import sys

from botocore.exceptions import ClientError

from eidolon.dynamo import TABLE_ENV_MAP, TableName, dynamo

# Ensure eidolon modules can be imported when run as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
    "story_history": TableName.STORY_HISTORY,
    "segment_history": TableName.SEGMENT_HISTORY,
}


def _sort_items_for_display(table_enum: TableName, items: list) -> list:
    """Sort items by schema primary key for readability when possible."""
    # Map known primary keys from documentation/schema.md
    pk_map = {
        TableName.PLAYERS: "PlayerID",
        TableName.CHARACTERS: "CharacterID",
        TableName.ROOMS: "RoomID",
        TableName.EXITS: "ExitID",
        TableName.ITEMS: "ItemID",
        TableName.PROTOTYPES: "PrototypeID",
        TableName.ARCHETYPES: "ArchetypeName",
        TableName.MOTD: "MotdID",
        TableName.STORY: "StoryID",
        # SEGMENTS has a composite key (StoryID + SegmentID)
    }

    if table_enum == TableName.SEGMENTS:
        return sorted(
            items,
            key=lambda it: (str(it.get("StoryID", "")), str(it.get("SegmentID", ""))),
        )

    pk = pk_map.get(table_enum)
    if pk:
        try:
            return sorted(items, key=lambda it: it.get(pk, ""))
        except Exception:
            return items
    return items


def view_table(table_name, table_enum):
    """View contents of a DynamoDB table.

    Args:
        table_name: Logical name of the table (e.g., "players")
        table_enum: TableName enum value
    """
    try:
        # Fetch all items; scan() returns a single page only
        items: list = dynamo.scan_all(table_enum)  # type: ignore
        items = _sort_items_for_display(table_enum, items)
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="View the contents of Eidolon DynamoDB tables.")
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region for DynamoDB (default: us-east-1)",
    )
    parser.add_argument(
        "tables",
        nargs="*",
        metavar="TABLE",
        help="Optional logical table names to display (defaults to all)",
    )
    return parser.parse_args()


def main(args: argparse.Namespace):
    """View contents of all DynamoDB tables."""
    try:
        dynamo.set_region(args.region)

        # List all tables
        print("Available tables:")
        for logical_name, table_enum in TABLE_NAMES.items():
            actual_name = TABLE_ENV_MAP.get(table_enum, "Not configured")
            print(f"  {logical_name}: {actual_name}")
        print("=" * 50)

        # View contents of each table
        tables_to_show = args.tables if args.tables else list(TABLE_NAMES.keys())
        for logical_name in tables_to_show:
            table_enum = TABLE_NAMES.get(logical_name)
            if not table_enum:
                print(f"Unknown table '{logical_name}'. Skipping.")
                continue
            view_table(logical_name, table_enum)

    except KeyError as err:
        print(f"Configuration error: {err}")
        sys.exit(1)
    except Exception as err:
        print(f"Error connecting to DynamoDB: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main(parse_args())
