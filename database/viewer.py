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

import sys

from eidolon.dynamo import tables


def view_table(table_name):
    if not hasattr(tables, table_name):
        print(f"Error: Table '{table_name}' does not exist.")
        return
    try:
        table = getattr(tables, table_name)
        response = table.scan()
        items = response["Items"]

        print(f"\nContents of table: {table_name}")
        print("=" * 50)
        for item in items:
            print(item)
        print("=" * 50)
        print(f"Total items: {len(items)}")
        print()
    except Exception as e:
        print(f"Error scanning table {table_name}: {e}")


def main():
    try:
        # List all tables
        table_names = [table for table in dir(tables) if not table.startswith("__")]

        print(f"Tables: {', '.join(table_names)}")
        print("=" * 50)

        # View contents of each table
        for table_name in table_names:
            view_table(table_name)

    except Exception as e:
        print(f"Error connecting to DynamoDB: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
