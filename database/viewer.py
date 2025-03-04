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

import argparse
import sys

import boto3
from botocore.exceptions import ClientError


def view_table(dynamodb, table_name):
    try:
        table = dynamodb.Table(table_name)
        response = table.scan()
        items = response["Items"]

        print(f"\nContents of table: {table_name}")
        print("=" * 50)
        for item in items:
            print(item)
        print("=" * 50)
        print(f"Total items: {len(items)}")
        print()
    except ClientError as e:
        print(f"Error scanning table {table_name}: {e.response['Error']['Message']}")


def main(region):
    try:
        dynamodb = boto3.resource("dynamodb", region_name=region)
        client = boto3.client("dynamodb", region_name=region)

        # List all tables
        tables = client.list_tables()["TableNames"]

        print(f"Contents of DynamoDB in region: {region}")
        print("=" * 50)
        print(f"Tables: {', '.join(tables)}")
        print("=" * 50)

        # View contents of each table
        for table_name in tables:
            view_table(dynamodb, table_name)

    except ClientError as e:
        print(f"Error connecting to DynamoDB: {e.response['Error']['Message']}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="View contents of DynamoDB tables.")
    parser.add_argument("--region", default="us-east-1", help="AWS region for DynamoDB")
    args = parser.parse_args()

    main(args.region)
