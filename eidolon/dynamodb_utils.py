"""
DynamoDB utilities for Lambda functions.

Provides centralized DynamoDB table management and common operations.
"""

import os
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

from eidolon.logger import get_logger

logger = get_logger(__name__)


class DynamoDBTables:
    """Centralized DynamoDB table management for Lambda functions."""

    def __init__(self):
        """Initialize DynamoDB client and tables."""
        self.dynamodb = boto3.resource("dynamodb")
        self._tables = {}
        self._init_tables()

    def _init_tables(self):
        """Initialize table references from environment variables."""
        # Shared tables
        self._init_table("players", "PLAYERS_TABLE", "players")

        # MUD tables
        self._init_table("mud_characters", "CHARACTERS_TABLE", "mud-characters")
        self._init_table("mud_items", "ITEMS_TABLE", "mud-items")
        self._init_table("mud_archetypes", "ARCHETYPES_TABLE", "mud-archetypes")

        # Incremental tables
        self._init_table("incremental_characters", "INCREMENTAL_CHARACTERS_TABLE", "incremental_characters")
        self._init_table("incremental_progress", "INCREMENTAL_PROGRESS_TABLE", "incremental_progress")
        self._init_table("incremental_resources", "INCREMENTAL_RESOURCES_TABLE", "incremental_resources")
        self._init_table("active_segments", "ACTIVE_SEGMENTS_TABLE", "active_segments")

    def _init_table(self, name: str, env_var: str, default: str):
        """
        Initialize a single table reference.

        Args:
            name: Internal name for the table
            env_var: Environment variable name
            default: Default table name if env var not set
        """
        table_name = os.environ.get(env_var, default)
        try:
            self._tables[name] = self.dynamodb.Table(table_name) # type: ignore
            logger.debug(f"Initialized table {name}: {table_name}")
        except Exception as err:
            logger.error(f"Failed to initialize table {name}", error=err, table_name=table_name)
            self._tables[name] = None

    def __getattr__(self, name: str):
        """Get table by attribute name."""
        if name in self._tables:
            return self._tables[name]
        raise AttributeError(f"Table '{name}' not found")

    @property
    def players(self):
        """Get players table."""
        return self._tables.get("players")

    @property
    def mud_characters(self):
        """Get MUD characters table."""
        return self._tables.get("mud_characters")

    @property
    def mud_items(self):
        """Get MUD items table."""
        return self._tables.get("mud_items")

    @property
    def mud_archetypes(self):
        """Get MUD archetypes table."""
        return self._tables.get("mud_archetypes")

    @property
    def incremental_characters(self):
        """Get incremental characters table."""
        return self._tables.get("incremental_characters")

    @property
    def incremental_progress(self):
        """Get incremental progress table."""
        return self._tables.get("incremental_progress")

    @property
    def incremental_resources(self):
        """Get incremental resources table."""
        return self._tables.get("incremental_resources")

    @property
    def active_segments(self):
        """Get active segments table."""
        return self._tables.get("active_segments")


def convert_to_decimal(obj):
    """
    Convert float values to Decimal for DynamoDB.

    Args:
        obj: Object to convert

    Returns:
        Object with floats converted to Decimals
    """
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: convert_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_decimal(v) for v in obj]
    return obj


def decimal_to_float(obj):
    """
    Convert Decimal values to float for JSON serialization.

    Args:
        obj: Object to convert

    Returns:
        Object with Decimals converted to floats
    """
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(v) for v in obj]
    return obj


def safe_get_item(table, key: dict) -> dict | None:
    """
    Safely get an item from DynamoDB table.

    Args:
        table: DynamoDB table resource
        key: Primary key dict

    Returns:
        Item dict or None if not found
    """
    try:
        response = table.get_item(Key=key)
        return response.get("Item")
    except ClientError as err:
        logger.error("Error getting item from DynamoDB", error=err, table=table.name, key=key)
        return None


def safe_put_item(table, item: dict) -> bool:
    """
    Safely put an item to DynamoDB table.

    Args:
        table: DynamoDB table resource
        item: Item to put

    Returns:
        True if successful, False otherwise
    """
    try:
        table.put_item(Item=convert_to_decimal(item))
        return True
    except ClientError as err:
        logger.error("Error putting item to DynamoDB", error=err, table=table.name)
        return False


def safe_update_item(
    table, key: dict, update_expression: str, expression_values: dict, expression_names: dict | None = None
) -> bool:
    """
    Safely update an item in DynamoDB table.

    Args:
        table: DynamoDB table resource
        key: Primary key dict
        update_expression: UpdateExpression string
        expression_values: ExpressionAttributeValues dict
        expression_names: Optional ExpressionAttributeNames dict

    Returns:
        True if successful, False otherwise
    """
    try:
        kwargs = {
            "Key": key,
            "UpdateExpression": update_expression,
            "ExpressionAttributeValues": convert_to_decimal(expression_values),
        }

        if expression_names:
            kwargs["ExpressionAttributeNames"] = expression_names

        table.update_item(**kwargs)
        return True
    except ClientError as err:
        logger.error("Error updating item in DynamoDB", error=err, table=table.name, key=key)
        return False


def safe_delete_item(table, key: dict) -> bool:
    """
    Safely delete an item from DynamoDB table.

    Args:
        table: DynamoDB table resource
        key: Primary key dict

    Returns:
        True if successful, False otherwise
    """
    try:
        table.delete_item(Key=key)
        return True
    except ClientError as err:
        logger.error("Error deleting item from DynamoDB", error=err, table=table.name, key=key)
        return False


def batch_get_items(table, keys: list[dict]) -> list[dict]:
    """
    Batch get multiple items from DynamoDB table.

    Args:
        table: DynamoDB table resource
        keys: List of primary key dicts

    Returns:
        List of items found
    """
    if not keys:
        return []

    try:
        # Create a DynamoDB client for batch operations
        dynamodb = boto3.client("dynamodb")

        # Convert keys to DynamoDB format
        formatted_keys = []
        for key in keys:
            formatted_key = {}
            for k, v in key.items():
                if isinstance(v, str):
                    formatted_key[k] = {"S": v}
                elif isinstance(v, (int, float)):
                    formatted_key[k] = {"N": str(v)}
                else:
                    # For other types, we'll need more sophisticated handling
                    formatted_key[k] = {"S": str(v)}
            formatted_keys.append(formatted_key)

        response = dynamodb.batch_get_item(RequestItems={table.name: {"Keys": formatted_keys}})

        # Convert response back to regular format
        items = []
        for item in response.get("Responses", {}).get(table.name, []):
            converted_item = {}
            for k, v in item.items():
                if "S" in v:
                    converted_item[k] = v["S"]
                elif "N" in v:
                    converted_item[k] = Decimal(v["N"])
                elif "BOOL" in v:
                    converted_item[k] = v["BOOL"]
                # Add more type conversions as needed
            items.append(converted_item)

        return items
    except ClientError as err:
        logger.error("Error batch getting items from DynamoDB", error=err, table=table.name)
        return []


# Global instance for easy import
tables = DynamoDBTables()
