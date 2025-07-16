"""DynamoDB utilities for Lambda functions."""

import os
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

from eidolon.logger import get_logger

logger = get_logger(__name__)


def get_table(table_name: str):
    """Get a DynamoDB table resource.

    Args:
        table_name: Name of the table

    Returns:
        DynamoDB table resource
    """
    dynamodb = boto3.resource("dynamodb")
    return dynamodb.Table(table_name)  # type: ignore


def convert_to_decimal(obj):
    """Convert float values to Decimal for DynamoDB."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: convert_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_decimal(v) for v in obj]
    return obj


def decimal_to_float(obj):
    """Convert Decimal values to float for JSON serialization."""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(v) for v in obj]
    elif isinstance(obj, set):
        return [decimal_to_float(v) for v in obj]
    return obj


def get_item(table, key: dict):
    """Safely get an item from DynamoDB table.

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
        logger.error("Error getting item from DynamoDB", extra={"error": str(err), "table": table.name, "key": key})
        return None


def put_item(table, item: dict) -> bool:
    """Safely put an item to DynamoDB table.

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
        logger.error("Error putting item to DynamoDB", extra={"error": str(err), "table": table.name})
        return False


def update_item(table, key: dict, update_expression: str, expression_values: dict, expression_names=None) -> bool:
    """Safely update an item in DynamoDB table.

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
        logger.error("Error updating item in DynamoDB", extra={"error": str(err), "table": table.name, "key": key})
        return False


def delete_item(table, key: dict) -> bool:
    """Safely delete an item from DynamoDB table.

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
        logger.error("Error deleting item from DynamoDB", extra={"error": str(err), "table": table.name, "key": key})
        return False


def update_item_with_condition(
    table, key: dict, update_expression: str, expression_values: dict, condition_expression: str, expression_names=None
):
    """Update an item in DynamoDB table with a condition.

    Args:
        table: DynamoDB table resource
        key: Primary key dict
        update_expression: UpdateExpression string
        expression_values: ExpressionAttributeValues dict
        condition_expression: ConditionExpression string
        expression_names: Optional ExpressionAttributeNames dict

    Returns:
        Tuple of (success, error_message)
    """
    try:
        kwargs = {
            "Key": key,
            "UpdateExpression": update_expression,
            "ExpressionAttributeValues": convert_to_decimal(expression_values),
            "ConditionExpression": condition_expression,
        }

        if expression_names:
            kwargs["ExpressionAttributeNames"] = expression_names

        table.update_item(**kwargs)
        return True, None
    except ClientError as err:
        if err.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logger.warning("Condition check failed", extra={"error": str(err), "table": table.name, "key": key})
            return False, "Condition not met"
        else:
            logger.error("Error updating item in DynamoDB", extra={"error": str(err), "table": table.name, "key": key})
            return False, "Database error"


def scan_all_items(table, filter_expression=None, expression_values=None, projection_expression=None, expression_names=None):
    """Scan all items from a DynamoDB table with pagination handling.

    Args:
        table: DynamoDB table resource
        filter_expression: Optional FilterExpression string
        expression_values: Optional ExpressionAttributeValues dict
        projection_expression: Optional ProjectionExpression string
        expression_names: Optional ExpressionAttributeNames dict

    Returns:
        Tuple of (success, items_or_error)
    """
    try:
        items = []
        kwargs = {}

        if filter_expression:
            kwargs["FilterExpression"] = filter_expression

        if expression_values:
            kwargs["ExpressionAttributeValues"] = convert_to_decimal(expression_values)

        if projection_expression:
            kwargs["ProjectionExpression"] = projection_expression

        if expression_names:
            kwargs["ExpressionAttributeNames"] = expression_names

        # Initial scan
        response = table.scan(**kwargs)
        items.extend(response.get("Items", []))

        # Handle pagination
        while "LastEvaluatedKey" in response:
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
            response = table.scan(**kwargs)
            items.extend(response.get("Items", []))

        return True, items
    except ClientError as err:
        logger.error("Error scanning table", extra={"error": str(err), "table": table.name})
        return False, "Database error"
