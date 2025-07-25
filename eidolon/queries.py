"""
DynamoDB query builder utilities.

Provides helper functions for common query patterns with
consistent error handling and logging.
"""

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from eidolon.dynamo import get_table
from eidolon.logger import get_logger

logger = get_logger(__name__)


def query_by_gsi(
    table_name: str,
    index_name: str,
    key_conditions: dict,
    filter_expression=None,
    expression_values=None,
    expression_names=None,
    limit=None,
) -> tuple:
    """
    Query a table using a Global Secondary Index.

    Args:
        table_name: DynamoDB table name
        index_name: GSI name
        key_conditions: Dictionary of key conditions (e.g., {"PartitionKey": value})
        filter_expression: Optional filter expression string
        expression_values: Optional expression attribute values
        expression_names: Optional expression attribute names
        limit: Optional query limit

    Returns:
        Tuple of (items_list, error_message)
        If successful: (items, None)
        If failed: (None, error_message)
    """
    try:
        table = get_table(table_name)

        # Build query parameters
        query_params = {
            "IndexName": index_name,
        }

        # Build key condition expression
        key_expressions = []
        for key, value in key_conditions.items():
            key_expressions.append(Key(key).eq(value))

        if len(key_expressions) == 1:
            query_params["KeyConditionExpression"] = key_expressions[0]
        else:
            # Combine multiple key conditions with AND
            query_params["KeyConditionExpression"] = key_expressions[0]
            for expr in key_expressions[1:]:
                query_params["KeyConditionExpression"] = (
                    query_params["KeyConditionExpression"] & expr
                )

        # Add optional parameters
        if filter_expression:
            query_params["FilterExpression"] = filter_expression

        if expression_values:
            query_params["ExpressionAttributeValues"] = expression_values

        if expression_names:
            query_params["ExpressionAttributeNames"] = expression_names

        if limit:
            query_params["Limit"] = limit

        # Execute query
        response = table.query(**query_params)
        items = response.get("Items", [])

        logger.info(
            "GSI query successful",
            extra={"table": table_name, "index": index_name, "item_count": len(items)},
        )

        return items, None

    except ClientError as err:
        logger.error(
            "GSI query failed",
            extra={"table": table_name, "index": index_name, "error": str(err)},
        )
        return None, f"Query failed: {err.response['Error']['Message']}"
    except Exception as err:
        logger.error(
            "Unexpected error in GSI query",
            extra={"table": table_name, "index": index_name, "error": str(err)},
        )
        return None, "Query failed"


def batch_get_items(table_name: str, keys: list) -> tuple:
    """
    Batch get multiple items from a table.

    Args:
        table_name: DynamoDB table name
        keys: List of key dictionaries

    Returns:
        Tuple of (items_dict, error_message)
        If successful: ({key: item}, None)
        If failed: (None, error_message)
    """
    if not keys:
        return {}, None

    try:
        table = get_table(table_name)

        # DynamoDB batch_get_item has a limit of 100 items
        results = {}
        for i in range(0, len(keys), 100):
            batch_keys = keys[i : i + 100]

            response = table.meta.client.batch_get_item(
                RequestItems={table_name: {"Keys": batch_keys}}
            )

            # Process responses
            items = response.get("Responses", {}).get(table_name, [])
            for item in items:
                # Create a key string for the results dict
                key_str = "_".join(str(v) for v in item.values())
                results[key_str] = item

            # Handle unprocessed keys
            unprocessed = (
                response.get("UnprocessedKeys", {}).get(table_name, {}).get("Keys", [])
            )
            if unprocessed:
                logger.warning(
                    "Some items were not processed",
                    extra={"table": table_name, "unprocessed_count": len(unprocessed)},
                )

        logger.info(
            "Batch get successful",
            extra={
                "table": table_name,
                "requested": len(keys),
                "retrieved": len(results),
            },
        )

        return results, None

    except ClientError as err:
        logger.error("Batch get failed", extra={"table": table_name, "error": str(err)})
        return None, f"Batch get failed: {err.response['Error']['Message']}"
    except Exception as err:
        logger.error(
            "Unexpected error in batch get",
            extra={"table": table_name, "error": str(err)},
        )
        return None, "Batch get failed"


def update_item_fields(
    table_name: str, key: dict, updates: dict, condition_expression=None
) -> tuple:
    """
    Update multiple fields in an item.

    Args:
        table_name: DynamoDB table name
        key: Item key dictionary
        updates: Dictionary of field updates {field_name: new_value}
        condition_expression: Optional condition expression

    Returns:
        Tuple of (success, error_message)
        If successful: (True, None)
        If failed: (False, error_message)
    """
    if not updates:
        return True, None

    try:
        table = get_table(table_name)

        # Build update expression
        update_parts = []
        expression_names = {}
        expression_values = {}

        for field, value in updates.items():
            # Use expression attribute names to handle reserved words
            field_placeholder = f"#{field}"
            value_placeholder = f":{field}"

            update_parts.append(f"{field_placeholder} = {value_placeholder}")
            expression_names[field_placeholder] = field
            expression_values[value_placeholder] = value

        update_expression = "SET " + ", ".join(update_parts)

        # Build update parameters
        update_params = {
            "Key": key,
            "UpdateExpression": update_expression,
            "ExpressionAttributeNames": expression_names,
            "ExpressionAttributeValues": expression_values,
            "ReturnValues": "UPDATED_NEW",
        }

        if condition_expression:
            update_params["ConditionExpression"] = condition_expression

        # Execute update
        response = table.update_item(**update_params)

        logger.info(
            "Item update successful",
            extra={
                "table": table_name,
                "key": key,
                "fields_updated": list(updates.keys()),
            },
        )

        return True, None

    except ClientError as err:
        if err.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logger.warning(
                "Update condition not met", extra={"table": table_name, "key": key}
            )
            return False, "Update condition not met"

        logger.error(
            "Item update failed",
            extra={"table": table_name, "key": key, "error": str(err)},
        )
        return False, f"Update failed: {err.response['Error']['Message']}"
    except Exception as err:
        logger.error(
            "Unexpected error in item update",
            extra={"table": table_name, "key": key, "error": str(err)},
        )
        return False, "Update failed"


def scan_with_filter(
    table_name: str,
    filter_expression: str,
    expression_values=None,
    expression_names=None,
    limit=None,
) -> tuple:
    """
    Scan table with filter expression.

    Args:
        table_name: DynamoDB table name
        filter_expression: Filter expression string
        expression_values: Optional expression attribute values
        expression_names: Optional expression attribute names
        limit: Optional scan limit

    Returns:
        Tuple of (items_list, error_message)
        If successful: (items, None)
        If failed: (None, error_message)
    """
    try:
        table = get_table(table_name)

        scan_params = {"FilterExpression": filter_expression}

        if expression_values:
            scan_params["ExpressionAttributeValues"] = expression_values

        if expression_names:
            scan_params["ExpressionAttributeNames"] = expression_names

        if limit:
            scan_params["Limit"] = limit

        # Handle pagination
        items = []
        last_evaluated_key = None

        while True:
            if last_evaluated_key:
                scan_params["ExclusiveStartKey"] = last_evaluated_key

            response = table.scan(**scan_params)
            items.extend(response.get("Items", []))

            last_evaluated_key = response.get("LastEvaluatedKey")
            if not last_evaluated_key or (limit and len(items) >= limit):
                break

        # Trim to limit if needed
        if limit and len(items) > limit:
            items = items[:limit]

        logger.info(
            "Table scan successful",
            extra={"table": table_name, "item_count": len(items)},
        )

        return items, None

    except ClientError as err:
        logger.error(
            "Table scan failed", extra={"table": table_name, "error": str(err)}
        )
        return None, f"Scan failed: {err.response['Error']['Message']}"
    except Exception as err:
        logger.error(
            "Unexpected error in table scan",
            extra={"table": table_name, "error": str(err)},
        )
        return None, "Scan failed"
