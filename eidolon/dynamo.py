"""
Enhanced DynamoDB interface for Lambda functions.

Provides efficient connection management, retry logic, and type-safe table access.
"""

from decimal import Decimal
from enum import Enum
from functools import wraps
from math import ceil
from time import sleep

from boto3 import resource
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from eidolon.environment import (
    ACTIVE_SEGMENTS_TABLE,
    ARCHETYPES_TABLE,
    CHARACTER_HISTORY_TABLE,
    CHARACTERS_TABLE,
    EXITS_TABLE,
    ITEMS_TABLE,
    MOTD_TABLE,
    OPPONENTS_TABLE,
    PLAYERS_TABLE,
    PROTOTYPES_TABLE,
    ROOMS_TABLE,
    SEGMENT_HISTORY_TABLE,
    SEGMENTS_TABLE,
    STORY_HISTORY_TABLE,
    STORY_TABLE,
)
from eidolon.logger import logger




class TableName(Enum):
    """Enum for DynamoDB table names"""

    PLAYERS = "players"
    CHARACTERS = "characters"
    ARCHETYPES = "archetypes"
    ITEMS = "items"
    PROTOTYPES = "prototypes"
    STORY = "story"
    SEGMENTS = "segments"
    ACTIVE_SEGMENTS = "active_segments"
    CHARACTER_HISTORY = "character_history"
    STORY_HISTORY = "story_history"
    SEGMENT_HISTORY = "segment_history"
    OPPONENTS = "opponents"
    ROOMS = "rooms"
    EXITS = "exits"
    MOTD = "motd"


# Map environment variables to table names
TABLE_ENV_MAP = {
    TableName.PLAYERS: PLAYERS_TABLE,
    TableName.CHARACTERS: CHARACTERS_TABLE,
    TableName.ARCHETYPES: ARCHETYPES_TABLE,
    TableName.ITEMS: ITEMS_TABLE,
    TableName.PROTOTYPES: PROTOTYPES_TABLE,
    TableName.STORY: STORY_TABLE,
    TableName.SEGMENTS: SEGMENTS_TABLE,
    TableName.ACTIVE_SEGMENTS: ACTIVE_SEGMENTS_TABLE,
    TableName.CHARACTER_HISTORY: CHARACTER_HISTORY_TABLE,
    TableName.STORY_HISTORY: STORY_HISTORY_TABLE,
    TableName.SEGMENT_HISTORY: SEGMENT_HISTORY_TABLE,
    TableName.OPPONENTS: OPPONENTS_TABLE,
    TableName.ROOMS: ROOMS_TABLE,
    TableName.EXITS: EXITS_TABLE,
    TableName.MOTD: MOTD_TABLE,
}


class ExpectedDynamoErrors:
    """Expected errors that may occur during DynamoDB operations"""

    RETRY_ERRORS = []


class ExponentialBackoff:
    """
    Decorator for retrying a database operation with exponentially increasing wait times.

    Based on AWS best practices: https://docs.aws.amazon.com/general/latest/gr/api-retries.html
    Default retry count of 8 maximizes total wait time to 0.42s
    """

    def __init__(self, expected_errors=None, expected_error_factory=None, retry_count=8):
        self.retry_count = retry_count
        self.expected_errors = expected_errors if expected_errors else ()
        self.expected_error_factory = expected_error_factory or ExpectedDynamoErrors

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            success = False
            count = 0
            response = None

            while not success and count <= self.retry_count:
                if count > 0:
                    logger.info(
                        "DynamoDB exponential backoff retry",
                        extra={"count": count, "function": func.__name__},
                    )

                try:
                    response = func(*args, **kwargs)
                    success = True
                except self.expected_errors as err:
                    logger.info(
                        "DynamoDB expected error, retrying",
                        extra={"error": str(err), "count": count},
                    )
                    sleep(2 ** (count - 1) / 10)
                    count += 1
                except tuple(self.expected_error_factory.RETRY_ERRORS) as err:
                    logger.info(
                        "DynamoDB retry error",
                        extra={"error": str(err), "count": count},
                    )
                    sleep(2 ** (count - 1) / 10)
                    count += 1
                except ClientError as err:
                    error_code = err.response.get("Error", {}).get("Code", "")
                    # Check if this is a retryable error
                    if error_code in [
                        "ProvisionedThroughputExceededException",
                        "RequestLimitExceeded",
                        "InternalServerError",
                    ]:
                        logger.info(
                            "DynamoDB throttling error, retrying",
                            extra={"error_code": error_code, "count": count},
                        )
                        sleep(2 ** (count - 1) / 10)
                        count += 1
                    else:
                        # Non-retryable client error
                        logger.error(
                            "DynamoDB non-retryable client error",
                            extra={"error": str(err)},
                            exc_info=True,
                        )
                        raise
                except TypeError as err:
                    logger.error("DynamoDB type error", extra={"error": str(err)}, exc_info=True)
                    raise
                except Exception as err:
                    logger.error(
                        "DynamoDB unexpected error, cannot retry",
                        extra={"error": str(err), "function": func.__name__},
                        exc_info=True,
                    )
                    raise

            if not success:
                logger.error(
                    "DynamoDB retry count exceeded",
                    extra={"count": count, "function": func.__name__},
                )
                raise RuntimeError(f"Number of retries exceeded for {func.__name__}")

            return response

        return wrapper


class DynamoInterface:
    """
    Singleton interface for DynamoDB operations.

    Provides efficient connection management and retry logic for Lambda functions.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Only initialize once
        if not self._initialized:
            self._resource = resource("dynamodb")
            self._client = self._resource.meta.client  # type: ignore
            self._tables = {}
            self._connection_status = {}

            # Set up expected retry errors
            ExpectedDynamoErrors.RETRY_ERRORS = [
                self._client.exceptions.ProvisionedThroughputExceededException,
                self._client.exceptions.RequestLimitExceeded,
                self._client.exceptions.InternalServerError,
            ]

            # Try to connect to all tables
            for table_enum in TableName:
                self._connect_table(table_enum)

            self._initialized = True

            # Log connection summary
            connected = [t.value for t, status in self._connection_status.items() if status]
            failed = [t.value for t, status in self._connection_status.items() if not status]

            if connected:
                logger.info("Connected to DynamoDB tables", extra={"tables": connected})
            if failed:
                logger.error("Failed to connect to DynamoDB tables", extra={"tables": failed})

    def _connect_table(self, table_enum: TableName) -> bool:
        """
        Connect to a specific DynamoDB table.

        Args:
            table_enum: TableName enum value

        Returns:
            bool: True if connection successful
        """
        try:
            table_name = TABLE_ENV_MAP.get(table_enum)
            if not table_name:
                logger.error(
                    "No environment variable mapping for table",
                    extra={"table": table_enum.value},
                )
                self._connection_status[table_enum] = False
                return False

            table = self._resource.Table(table_name)  # type: ignore
            # Test the connection by loading the table
            table.load()

            self._tables[table_enum] = table
            self._connection_status[table_enum] = True
            logger.debug("Connected to table", extra={"table_name": table_name})
            return True

        except Exception as err:
            logger.error(
                "Failed to connect to table",
                extra={
                    "table": table_enum.value,
                    "error": str(err),
                    "table_name": TABLE_ENV_MAP.get(table_enum),
                },
            )
            self._connection_status[table_enum] = False
            return False

    def get_table(self, table_enum: TableName):
        """
        Get a connected table resource.

        Args:
            table_enum: TableName enum value

        Returns:
            Table resource

        Raises:
            ValueError: If table is not connected
        """
        if table_enum not in self._tables:
            raise ValueError(f"Table {table_enum.value} is not connected")
        return self._tables[table_enum]

    def is_connected(self, table_enum: TableName) -> bool:
        """Check if a table is connected."""
        return self._connection_status.get(table_enum, False)

    @ExponentialBackoff(expected_error_factory=ExpectedDynamoErrors)
    def get_item(self, table_enum: TableName, key: dict, **kwargs) -> dict:
        """
        Get an item from a table with retry logic and automatic type conversion.

        Args:
            table_enum: TableName enum value
            key: Primary key dict
            **kwargs: Additional arguments to pass to get_item

        Returns:
            Item dict with Decimals converted to floats, empty dict if not found
        """
        table = self.get_table(table_enum)
        logger.debug("DB Interface: Get Item", extra={"table": table_enum.value, "key": key})

        try:
            response = table.get_item(Key=key, **kwargs)
        except ClientError as err:
            logger.error(
                "Error getting item from DynamoDB",
                extra={"error": str(err), "table": table_enum.value, "key": key},
            )
            raise

        item = response.get("Item", {})
        if not item:
            logger.debug("DB Interface: Get Item: No item found", extra={"key": key})
            return {}

        # Convert Decimal to float for JSON compatibility
        result = decimal_to_float(item)
        logger.debug("DB Interface: Get Item: Return", extra={"result": result})
        return result  # type: ignore

    @ExponentialBackoff(expected_error_factory=ExpectedDynamoErrors)
    def put_item(self, table_enum: TableName, item: dict, **kwargs) -> None:
        """
        Put an item to a table with retry logic and automatic type cleaning.

        Args:
            table_enum: TableName enum value
            item: Item to put
            **kwargs: Additional arguments to pass to put_item

        Raises:
            ClientError: If DynamoDB operation fails
        """
        table = self.get_table(table_enum)
        logger.debug("DB Interface: Put Item", extra={"table": table_enum.value, "item": item})

        # Clean values for DynamoDB
        cleaned_item = clean_value(item)

        try:
            table.put_item(Item=cleaned_item, **kwargs)
        except ClientError as err:
            logger.error(
                "Error putting item to DynamoDB",
                extra={"error": str(err), "table": table_enum.value},
            )
            raise

        logger.debug("DB Interface: Put Item: Success")

    @ExponentialBackoff(expected_error_factory=ExpectedDynamoErrors)
    def update_item(self, table_enum: TableName, **kwargs) -> dict:
        """
        Update an item with retry logic and automatic type cleaning.

        Args:
            table_enum: TableName enum value
            **kwargs: Arguments to pass to update_item (Key, UpdateExpression, etc.)

        Returns:
            Response from DynamoDB update_item

        Raises:
            ClientError: If DynamoDB operation fails
        """
        table = self.get_table(table_enum)
        logger.debug(
            "DB Interface: Update Item",
            extra={"table": table_enum.value, "arguments": kwargs},
        )

        # Clean expression attribute values if present
        if "ExpressionAttributeValues" in kwargs:
            kwargs["ExpressionAttributeValues"] = clean_value(kwargs["ExpressionAttributeValues"])

        try:
            response = table.update_item(**kwargs)
        except ClientError as err:
            if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                logger.error(
                    "Condition check failed",
                    extra={
                        "error": str(err),
                        "table": table_enum.value,
                        "key": kwargs.get("Key"),
                    },
                )
                raise
            logger.error(
                "Error updating item in DynamoDB",
                extra={
                    "error": str(err),
                    "table": table_enum.value,
                    "key": kwargs.get("Key"),
                },
            )
            raise

        logger.debug("DB Interface: Update Item: Response", extra={"response": response})
        return response

    @ExponentialBackoff(expected_error_factory=ExpectedDynamoErrors)
    def delete_item(self, table_enum: TableName, **kwargs) -> dict:
        """
        Delete an item with retry logic.

        Args:
            table_enum: TableName enum value
            **kwargs: Arguments to pass to delete_item (Key required)

        Returns:
            Response from DynamoDB delete_item

        Raises:
            ClientError: If DynamoDB operation fails
        """
        table = self.get_table(table_enum)
        logger.debug(
            "DB Interface: Delete Item",
            extra={"table": table_enum.value, "arguments": kwargs},
        )

        try:
            response = table.delete_item(**kwargs)
        except ClientError as err:
            logger.error(
                "Error deleting item from DynamoDB",
                extra={
                    "error": str(err),
                    "table": table_enum.value,
                    "key": kwargs.get("Key"),
                },
            )
            raise

        logger.debug("DB Interface: Delete Item: Response", extra={"response": response})
        return response

    @ExponentialBackoff(expected_error_factory=ExpectedDynamoErrors)
    def query(self, table_enum: TableName, **kwargs) -> list:
        """
        Query a table with retry logic and automatic pagination.

        Args:
            table_enum: TableName enum value
            **kwargs: Query parameters

        Returns:
            List of items with Decimals converted to floats

        Raises:
            ClientError: If DynamoDB operation fails
        """
        table = self.get_table(table_enum)
        logger.debug(
            "DB Interface: Query",
            extra={"table": table_enum.value, "arguments": kwargs},
        )

        items = []

        try:
            response = table.query(**kwargs)
        except ClientError as err:
            logger.error(
                "Error querying DynamoDB",
                extra={"error": str(err), "table": table_enum.value},
            )
            raise

        items.extend(response.get("Items", []))

        # Handle pagination
        while "LastEvaluatedKey" in response and response.get("LastEvaluatedKey"):
            logger.debug("DB Interface: Query: Paginating...")
            kwargs["ExclusiveStartKey"] = response.get("LastEvaluatedKey")

            try:
                response = table.query(**kwargs)
            except ClientError as err:
                logger.error(
                    "Error querying DynamoDB during pagination",
                    extra={"error": str(err), "table": table_enum.value},
                )
                raise

            items.extend(response.get("Items", []))

        # Convert Decimal to float for JSON compatibility
        results = [decimal_to_float(item) for item in items]
        logger.debug("DB Interface: Query: Found items", extra={"count": len(results)})
        return results

    @ExponentialBackoff(expected_error_factory=ExpectedDynamoErrors)
    def scan(self, table_enum: TableName, **kwargs) -> dict:
        """
        Scan a table with retry logic.

        Args:
            table_enum: TableName enum value
            **kwargs: Scan parameters

        Returns:
            Dict with:
                - items: List of items with Decimals converted to floats
                - last_evaluated_key: Optional dict for pagination
                - count: Number of items scanned

        Raises:
            ClientError: If DynamoDB operation fails
        """
        table = self.get_table(table_enum)
        logger.debug("DB Interface: Scan", extra={"table": table_enum.value, "arguments": kwargs})

        try:
            response = table.scan(**kwargs)
        except ClientError as err:
            logger.error(
                "Error scanning DynamoDB",
                extra={"error": str(err), "table": table_enum.value},
            )
            raise

        items = response.get("Items", [])
        last_evaluated_key = response.get("LastEvaluatedKey")
        count = response.get("Count", 0)

        # Convert Decimal to float for JSON compatibility
        results = [decimal_to_float(item) for item in items]

        logger.info("DB Interface: Scan: Records Collected", extra={"count": count})
        return {
            "items": results,
            "last_evaluated_key": last_evaluated_key,
            "count": count,
        }

    @ExponentialBackoff(expected_error_factory=ExpectedDynamoErrors)
    def scan_all(self, table_enum: TableName, **kwargs) -> list:
        """
        Scan a table and return all items (no pagination needed for small tables).

        Args:
            table_enum: TableName enum value
            **kwargs: Scan parameters

        Returns:
            List of all items with Decimals converted to floats

        Raises:
            ClientError: If DynamoDB operation fails
        """
        table = self.get_table(table_enum)
        logger.debug("DB Interface: Scan All", extra={"table": table_enum.value, "arguments": kwargs})

        try:
            response = table.scan(**kwargs)
        except ClientError as err:
            logger.error(
                "Error scanning DynamoDB",
                extra={"error": str(err), "table": table_enum.value},
            )
            raise

        items = response.get("Items", [])
        count = response.get("Count", 0)

        # Convert Decimal to float for JSON compatibility
        results = [decimal_to_float(item) for item in items]

        logger.info("DB Interface: Scan All: Records Collected", extra={"count": count})
        return results

    @ExponentialBackoff(expected_error_factory=ExpectedDynamoErrors)
    def batch_get_items(self, table_enum: TableName, keys: list, attributes_to_get=None) -> list:
        """
        Perform a BatchGetItem operation on a single table.

        Args:
            table_enum: TableName enum value
            keys: List of primary key dicts
            attributes_to_get: Optional list of attributes to retrieve

        Returns:
            List of items with Decimals converted to floats

        Raises:
            ClientError: If DynamoDB operation fails
        """
        result = []
        page_size = 100  # AWS defined constant

        table = self.get_table(table_enum)
        table_name = table.table_name  # Cache to avoid repeated requests

        for i in range(ceil(len(keys) / page_size)):
            subset = keys[i * page_size : min(len(keys), (i + 1) * page_size)]
            request = {table_name: {"Keys": subset}}

            if attributes_to_get:
                request[table_name]["AttributesToGet"] = attributes_to_get

            try:
                response = self._resource.batch_get_items(RequestItems=request)  # type: ignore
            except ClientError as err:
                logger.error(
                    "Error in batch get operation",
                    extra={"error": str(err), "table": table_enum.value},
                )
                raise

            items = response.get("Responses", {}).get(table_name, [])
            result.extend([decimal_to_float(item) for item in items])

        return result

    def batch_write_with_retries(self, table_enum: TableName, items: list, operation: str = "put") -> list:
        """
        Perform batch write operations with automatic retry for unprocessed items.

        Args:
            table_enum: TableName enum value
            items: List of items to write
            operation: "put" or "delete"

        Returns:
            List of failed items
        """
        table = self.get_table(table_enum)
        failed_items = []

        try:
            with table.batch_writer() as batch:
                for item in items:
                    try:
                        if operation == "put":
                            batch.put_item(Item=clean_value(item))
                        elif operation == "delete":
                            batch.delete_item(Key=item)
                    except Exception as err:
                        logger.warning(
                            "Failed to process individual item in batch",
                            extra={"operation": operation, "error": str(err)},
                        )
                        failed_items.append(item)
        except Exception as err:
            logger.error(
                "Error creating batch writer",
                extra={"error": str(err), "table": table_enum.value},
            )
            raise

        return failed_items

    @ExponentialBackoff(expected_error_factory=ExpectedDynamoErrors)
    def query_by_gsi(self, table_enum: TableName, index_name: str, key_conditions: dict, **kwargs) -> list:
        """
        Query a table using a Global Secondary Index with Key conditions.

        Args:
            table_enum: TableName enum value
            index_name: GSI name
            key_conditions: Dictionary of key conditions (e.g., {"PartitionKey": value})
            **kwargs: Additional query parameters (FilterExpression, ExpressionAttributeValues, etc.)

        Returns:
            List of items with Decimals converted to floats

        Raises:
            ClientError: If DynamoDB operation fails
        """
        # Build key condition expression
        key_expressions = []
        for key, value in key_conditions.items():
            key_expressions.append(Key(key).eq(value))

        if len(key_expressions) == 1:
            key_condition_expression = key_expressions[0]
        else:
            # Combine multiple key conditions with AND
            key_condition_expression = key_expressions[0]
            for expr in key_expressions[1:]:
                key_condition_expression = key_condition_expression & expr

        # Add IndexName and KeyConditionExpression to kwargs
        kwargs["IndexName"] = index_name
        kwargs["KeyConditionExpression"] = key_condition_expression

        logger.debug(
            "DB Interface: GSI Query",
            extra={"table": table_enum.value, "index": index_name},
        )

        # Use the existing query method
        return self.query(table_enum, **kwargs)  # type: ignore

    def update_item_fields(self, table_enum: TableName, key: dict, updates: dict, condition_expression=None) -> dict:
        """
        Update multiple fields in an item with automatic expression building.

        Args:
            table_enum: TableName enum value
            key: Item key dictionary
            updates: Dictionary of field updates {field_name: new_value}
            condition_expression: Optional condition expression string

        Returns:
            Response from DynamoDB update_item

        Raises:
            ClientError: If DynamoDB operation fails
            ValueError: If updates dict is empty
        """
        if not updates:
            raise ValueError("Updates dictionary cannot be empty")

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

        logger.debug(
            "DB Interface: Update Fields",
            extra={
                "table": table_enum.value,
                "key": key,
                "fields": list(updates.keys()),
            },
        )

        # Use the existing update_item method
        return self.update_item(table_enum, **update_params)  # type: ignore


def clean_value(value: object) -> object:
    """Helper function to ensure all data passed to DynamoDB is formatted as expected by the SDK."""
    if isinstance(value, float):
        return Decimal(str(value))
    elif isinstance(value, Enum):
        return value.value
    elif isinstance(value, dict):
        return {k: clean_value(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [clean_value(v) for v in value]
    return value


def convert_to_decimal(obj: object) -> object:
    """Convert float values to Decimal for DynamoDB."""
    return clean_value(obj)


def decimal_to_float(obj: object) -> object:
    """Convert Decimal values to float for JSON serialization."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [decimal_to_float(v) for v in obj]
    if isinstance(obj, set):
        return [decimal_to_float(v) for v in obj]
    return obj


# Create singleton instance
dynamo = DynamoInterface()
