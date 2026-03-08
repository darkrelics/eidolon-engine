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
from botocore.exceptions import ClientError

from eidolon.environment import (
    ACTIVE_SEGMENTS_TABLE,
    ARCHETYPES_TABLE,
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
    STORY_HISTORY = "story_history"
    SEGMENT_HISTORY = "segment_history"
    OPPONENTS = "opponents"
    ROOMS = "rooms"
    EXITS = "exits"
    MOTD = "motd"


# Map environment variables to table names
TABLE_ENV_MAP: dict = {
    TableName.PLAYERS: PLAYERS_TABLE,
    TableName.CHARACTERS: CHARACTERS_TABLE,
    TableName.ARCHETYPES: ARCHETYPES_TABLE,
    TableName.ITEMS: ITEMS_TABLE,
    TableName.PROTOTYPES: PROTOTYPES_TABLE,
    TableName.STORY: STORY_TABLE,
    TableName.SEGMENTS: SEGMENTS_TABLE,
    TableName.ACTIVE_SEGMENTS: ACTIVE_SEGMENTS_TABLE,
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
    Default retry count of 8 maximizes total wait time to ~25.5s with proper exponential backoff
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
                    logger.info("DynamoDB exponential backoff retry")

                try:
                    response = func(*args, **kwargs)
                    success = True
                except self.expected_errors as err:
                    logger.info(f"DynamoDB expected error, retrying Error: {err}")
                    sleep(2**count / 10)
                    count += 1
                except tuple(self.expected_error_factory.RETRY_ERRORS) as err:
                    logger.info(f"DynamoDB retry error Error: {err}")
                    sleep(2**count / 10)
                    count += 1
                except ClientError as err:
                    error_code = err.response.get("Error", {}).get("Code", "")
                    # Check if this is a retryable error
                    if error_code in [
                        "ProvisionedThroughputExceededException",
                        "RequestLimitExceeded",
                        "InternalServerError",
                    ]:
                        logger.info("DynamoDB throttling error, retrying")
                        sleep(2**count / 10)
                        count += 1
                    else:
                        # Non-retryable client error
                        logger.error(f"DynamoDB non-retryable client error Error: {err}", exc_info=True)
                        raise err
                except TypeError as err:
                    logger.error(f"DynamoDB type error Error: {err}", exc_info=True)
                    raise err
                except Exception as err:
                    logger.error(f"DynamoDB unexpected error, cannot retry Error: {err}", exc_info=True)
                    raise err

            if not success:
                logger.error("DynamoDB retry count exceeded")
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
                self.connect_table(table_enum)

            self._initialized = True

            # Log connection summary
            connected = [t.value for t, status in self._connection_status.items() if status]
            failed = [t.value for t, status in self._connection_status.items() if not status]

            if connected:
                logger.info(f"Connected to DynamoDB tables: {', '.join(connected)}")
            if failed:
                logger.error(f"Failed to connect to DynamoDB tables: {', '.join(failed)}")

    def connect_table(self, table_enum: TableName) -> bool:
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
                logger.error(f"No environment variable mapping for table {table_enum.value}")
                self._connection_status[table_enum] = False
                return False

            table = self._resource.Table(table_name)  # type: ignore
            # Test the connection by loading the table
            table.load()

            self._tables[table_enum] = table
            self._connection_status[table_enum] = True
            logger.debug(f"Connected to table {table_name}")
            return True

        except Exception as err:
            logger.error(f"Failed to connect to table {table_enum.value} Error: {err}")
            self._connection_status[table_enum] = False
            return False

    def set_region(self, region: str) -> None:
        """Reinitialize the DynamoDB client for a specific AWS region."""

        sanitized = (region or "").strip().lower()
        if not sanitized:
            return

        current_region = getattr(self._client, "meta", None)
        current_region = getattr(current_region, "region_name", None)
        if current_region == sanitized:
            return

        logger.info(f"Reinitializing DynamoDB interface for region {sanitized}")

        self._resource = resource("dynamodb", region_name=sanitized)
        self._client = self._resource.meta.client  # type: ignore
        self._tables = {}
        self._connection_status = {}

        ExpectedDynamoErrors.RETRY_ERRORS = [
            self._client.exceptions.ProvisionedThroughputExceededException,
            self._client.exceptions.RequestLimitExceeded,
            self._client.exceptions.InternalServerError,
        ]

        for table_enum in TableName:
            self.connect_table(table_enum)

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
        logger.debug(f"DB Interface: Get Item for {table_enum.value}")

        try:
            response = table.get_item(Key=key, **kwargs)
        except ClientError as err:
            logger.error(f"Error getting item from DynamoDB for {table_enum.value} Error: {err}")
            raise err

        item = response.get("Item", {})
        if not item:
            logger.debug("DB Interface: Get Item: No item found")
            return {}

        # Convert Decimal to float for JSON compatibility
        result = decimal_to_float(item)
        logger.debug("DB Interface: Get Item: Return")
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
        logger.debug(f"DB Interface: Put Item for {table_enum.value}")

        # Clean values for DynamoDB
        cleaned_item = clean_value(item)

        try:
            table.put_item(Item=cleaned_item, **kwargs)
        except ClientError as err:
            logger.error(f"Error putting item to DynamoDB for {table_enum.value} Error: {err}")
            raise err

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
        logger.debug(f"DB Interface: Update Item for {table_enum.value}")

        # Clean expression attribute values if present
        if "ExpressionAttributeValues" in kwargs:
            kwargs["ExpressionAttributeValues"] = clean_value(kwargs["ExpressionAttributeValues"])

        try:
            response = table.update_item(**kwargs)
        except ClientError as err:
            if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                logger.error(f"Condition check failed for {table_enum.value} Error: {err}")
                raise err
            logger.error(f"Error updating item in DynamoDB for {table_enum.value} Error: {err}")
            raise err

        logger.debug("DB Interface: Update Item: Response")
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
        logger.debug(f"DB Interface: Delete Item for {table_enum.value}")

        try:
            response = table.delete_item(**kwargs)
        except ClientError as err:
            logger.error(f"Error deleting item from DynamoDB for {table_enum.value} Error: {err}")
            raise err

        logger.debug("DB Interface: Delete Item: Response")
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
        logger.debug(f"DB Interface: Query for {table_enum.value}")

        items = []

        while True:
            try:
                response = table.query(**kwargs)
            except ClientError as err:
                logger.error(f"Error querying DynamoDB for {table_enum.value} Error: {err}")
                raise err

            items.extend(response.get("Items", []))

            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            kwargs["ExclusiveStartKey"] = last_key
            logger.debug("DB Interface: Query: Paginating...")

        # Convert Decimal to float for JSON compatibility
        results = [decimal_to_float(item) for item in items]
        logger.debug(f"DB Interface: Query: Found {len(results)} items")
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
                - last_evaluated_key: dict for pagination
                - count: Number of items scanned

        Raises:
            ClientError: If DynamoDB operation fails
        """
        table = self.get_table(table_enum)
        logger.debug(f"DB Interface: Scan for {table_enum.value}")

        try:
            response = table.scan(**kwargs)
        except ClientError as err:
            logger.error(f"Error scanning DynamoDB for {table_enum.value} Error: {err}")
            raise err

        items = response.get("Items", [])
        last_evaluated_key = response.get("LastEvaluatedKey")
        count = response.get("Count", 0)

        # Convert Decimal to float for JSON compatibility
        results = [decimal_to_float(item) for item in items]

        logger.info(f"DB Interface: Scan: Records Collected {count}")
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
        logger.debug(f"DB Interface: Scan All for {table_enum.value}")

        try:
            response = table.scan(**kwargs)
        except ClientError as err:
            logger.error(f"Error scanning DynamoDB for {table_enum.value} Error: {err}")
            raise err

        items = response.get("Items", [])
        count = response.get("Count", 0)

        # Convert Decimal to float for JSON compatibility
        results = [decimal_to_float(item) for item in items]

        logger.info(f"DB Interface: Scan All: Records Collected {count}")
        return results

    @ExponentialBackoff(expected_error_factory=ExpectedDynamoErrors)
    def batch_get_items(self, table_enum: TableName, keys: list, attributes_to_get=None) -> list:
        """
        Perform a BatchGetItem operation on a single table.

        Args:
            table_enum: TableName enum value
            keys: List of primary key dicts
            attributes_to_get: list of attributes to retrieve

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
                response = self._client.batch_get_item(RequestItems=request)  # type: ignore
            except ClientError as err:
                logger.error(f"Error in batch get operation for {table_enum.value} Error: {err}")
                raise err

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
                    success = write_single_batch_item(batch, item, operation)
                    if not success:
                        failed_items.append(item)
        except Exception as err:
            logger.error(f"Error creating batch writer for {table_enum.value} Error: {err}")
            raise err

        return failed_items

    @ExponentialBackoff(expected_error_factory=ExpectedDynamoErrors)
    def transact_write_items(self, transact_items: list) -> dict:
        """
        Perform a transactional write across multiple tables atomically.

        All operations in a transaction either succeed together or fail together.
        Useful for ensuring data consistency when writing to multiple tables.

        Args:
            transact_items: List of transaction operations, each containing one of:
                - Put: {"TableName": str, "Item": dict, "ConditionExpression": str (optional)}
                - Update: {"TableName": str, "Key": dict, "UpdateExpression": str, ...}
                - Delete: {"TableName": str, "Key": dict, "ConditionExpression": str (optional)}
                - ConditionCheck: {"TableName": str, "Key": dict, "ConditionExpression": str}

        Returns:
            Response from DynamoDB transact_write_items

        Raises:
            ClientError: If transaction fails (e.g., condition check failed)

        Example:
            transact_items = [
                {
                    "Put": {
                        "TableName": TABLE_ENV_MAP[TableName.STORY_HISTORY],
                        "Item": history_item,
                    }
                },
                {
                    "Put": {
                        "TableName": TABLE_ENV_MAP[TableName.ACTIVE_SEGMENTS],
                        "Item": segment_item,
                    }
                },
                {
                    "Update": {
                        "TableName": TABLE_ENV_MAP[TableName.CHARACTERS],
                        "Key": {"CharacterID": character_id},
                        "UpdateExpression": "SET ActiveStoryID = :story",
                        "ConditionExpression": "attribute_not_exists(ActiveStoryID)",
                        "ExpressionAttributeValues": {":story": story_id},
                    }
                },
            ]
            dynamo.transact_write_items(transact_items)
        """
        logger.debug(f"DB Interface: TransactWriteItems with {len(transact_items)} operations")

        # Clean all items in the transaction
        cleaned_items = []
        for item in transact_items:
            cleaned_item = {}
            for op_type, op_data in item.items():
                cleaned_op = {}
                for key, value in op_data.items():
                    if key == "Item":
                        cleaned_op[key] = clean_value(value)
                    elif key == "ExpressionAttributeValues":
                        cleaned_op[key] = clean_value(value)
                    else:
                        cleaned_op[key] = value
                cleaned_item[op_type] = cleaned_op
            cleaned_items.append(cleaned_item)

        try:
            response = self._client.transact_write_items(TransactItems=cleaned_items)
        except ClientError as err:
            error_code = err.response.get("Error", {}).get("Code", "")
            if error_code == "TransactionCanceledException":
                # Extract cancellation reasons for debugging
                reasons = err.response.get("CancellationReasons", [])
                reason_codes = [r.get("Code", "Unknown") for r in reasons if r.get("Code")]
                logger.error(f"Transaction cancelled: {reason_codes}")
            logger.error(f"Error in transact_write_items Error: {err}")
            raise err

        logger.debug("DB Interface: TransactWriteItems: Success")
        return response


def write_single_batch_item(batch, item: dict, operation: str) -> bool:
    """Write or delete a single item within a batch writer context.

    Args:
        batch: Active batch writer context
        item: Item data to write or key to delete
        operation: "put" or "delete"

    Returns:
        True if successful, False if failed
    """
    try:
        if operation == "put":
            batch.put_item(Item=clean_value(item))
        elif operation == "delete":
            batch.delete_item(Key=item)
        return True
    except Exception as err:
        logger.warning(f"Failed to process individual item in batch for {operation} Error: {err}")
        return False


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
