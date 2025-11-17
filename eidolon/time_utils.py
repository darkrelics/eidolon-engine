"""
Time utilities for consistent ISO 8601 timestamp handling.

Provides functions for generating and parsing ISO 8601 timestamps,
ensuring consistency across all Lambda functions and API responses.
"""

from datetime import datetime, timedelta, timezone

from eidolon.logger import logger


def now_iso() -> str:
    """
    Get current UTC time as ISO 8601 string.

    Returns:
        Current UTC time in ISO 8601 format (e.g., "2025-01-18T10:30:00Z")
    """
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def future_iso(seconds: int) -> str:
    """
    Get future UTC time as ISO 8601 string.

    Args:
        seconds: Number of seconds in the future

    Returns:
        Future UTC time in ISO 8601 format
    """
    future_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    return future_time.isoformat().replace("+00:00", "Z")


def past_iso(seconds: int) -> str:
    """
    Get past UTC time as ISO 8601 string.

    Args:
        seconds: Number of seconds in the past

    Returns:
        Past UTC time in ISO 8601 format
    """
    past_time = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    return past_time.isoformat().replace("+00:00", "Z")


def parse_iso(iso_string: str) -> datetime:
    """
    Parse ISO 8601 string to datetime object.

    Args:
        iso_string: ISO 8601 formatted time string

    Returns:
        Datetime object in UTC

    Raises:
        ValueError: If string is not valid ISO 8601 format
    """
    # Handle both 'Z' suffix and '+00:00' formats
    if iso_string.endswith("Z"):
        iso_string = iso_string[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(iso_string)
        # Ensure timezone aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as err:
        logger.error(f"Failed to parse ISO 8601 string: {iso_string}", exc_info=True)
        raise ValueError(f"Invalid ISO 8601 format: {iso_string}") from err


def to_unix(iso_string: str) -> int:
    """
    Convert ISO 8601 string to Unix timestamp (seconds).

    Args:
        iso_string: ISO 8601 formatted time string

    Returns:
        Unix timestamp in seconds
    """
    dt = parse_iso(iso_string)
    return int(dt.timestamp())


def from_unix(unix_timestamp: int) -> str:
    """
    Convert Unix timestamp to ISO 8601 string.

    Args:
        unix_timestamp: Unix timestamp in seconds

    Returns:
        ISO 8601 formatted time string
    """
    dt = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def is_past(iso_string: str) -> bool:
    """
    Check if ISO 8601 time is in the past.

    Args:
        iso_string: ISO 8601 formatted time string

    Returns:
        True if time is in the past
    """
    dt = parse_iso(iso_string)
    return dt < datetime.now(timezone.utc)


def is_future(iso_string: str) -> bool:
    """
    Check if ISO 8601 time is in the future.

    Args:
        iso_string: ISO 8601 formatted time string

    Returns:
        True if time is in the future
    """
    dt = parse_iso(iso_string)
    return dt > datetime.now(timezone.utc)


def seconds_until(iso_string: str) -> int:
    """
    Calculate seconds until a future ISO 8601 time.

    Args:
        iso_string: ISO 8601 formatted time string

    Returns:
        Seconds until the time (0 if in the past)
    """
    dt = parse_iso(iso_string)
    delta = dt - datetime.now(timezone.utc)
    return max(0, int(delta.total_seconds()))


def seconds_since(iso_string: str) -> int:
    """
    Calculate seconds since a past ISO 8601 time.

    Args:
        iso_string: ISO 8601 formatted time string

    Returns:
        Seconds since the time (0 if in the future)
    """
    dt = parse_iso(iso_string)
    delta = datetime.now(timezone.utc) - dt
    return max(0, int(delta.total_seconds()))


def duration_between(start_iso: str, end_iso: str) -> int:
    """
    Calculate duration in seconds between two ISO 8601 times.

    Args:
        start_iso: Start time in ISO 8601 format
        end_iso: End time in ISO 8601 format

    Returns:
        Duration in seconds (positive if end > start)
    """
    start_dt = parse_iso(start_iso)
    end_dt = parse_iso(end_iso)
    delta = end_dt - start_dt
    return int(delta.total_seconds())


def now_unix() -> int:
    """
    Get current UTC time as Unix timestamp.

    Returns:
        Current UTC time as Unix timestamp in seconds
    """
    return int(datetime.now(timezone.utc).timestamp())


def future_unix(seconds: int) -> int:
    """
    Get future UTC time as Unix timestamp.

    Args:
        seconds: Number of seconds in the future

    Returns:
        Future UTC time as Unix timestamp in seconds
    """
    future_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    return int(future_time.timestamp())


def past_unix(seconds: int) -> int:
    """
    Get past UTC time as Unix timestamp.

    Args:
        seconds: Number of seconds in the past

    Returns:
        Past UTC time as Unix timestamp in seconds
    """
    past_time = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    return int(past_time.timestamp())


def coerce_unix_timestamp(timestamp_value: object, default=None) -> int | None:
    """
    Coerce various timestamp formats to Unix timestamp (int).

    Handles DynamoDB Decimal types, strings, ints, floats, and None/empty values.
    Used for robust timestamp handling when reading from DynamoDB.

    Args:
        timestamp_value: Timestamp value in various formats
        default: Default value to return if coercion fails

    Returns:
        Unix timestamp as int, or default if coercion fails

    Examples:
        >>> coerce_unix_timestamp(1234567890)
        1234567890
        >>> coerce_unix_timestamp("1234567890")
        1234567890
        >>> coerce_unix_timestamp(None, 0)
        0
        >>> from decimal import Decimal
        >>> coerce_unix_timestamp(Decimal("1234567890"))
        1234567890
    """
    # Handle None and empty values
    if timestamp_value in (None, "", 0, "0"):
        return default

    # Handle int/float
    if isinstance(timestamp_value, (int, float)):
        return int(timestamp_value)

    # Handle DynamoDB Decimal type (without importing)
    if "Decimal" in type(timestamp_value).__name__:
        try:
            return int(timestamp_value)  # type: ignore[arg-type]
        except Exception:
            return default

    # Handle string
    if isinstance(timestamp_value, str):
        try:
            return int(float(timestamp_value))
        except ValueError:
            return default

    # Unknown type
    return default
