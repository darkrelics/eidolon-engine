"""
Request parsing utilities for Lambda functions.

Provides common request parsing and validation helpers for API Gateway
Lambda functions.
"""

import json

from eidolon.logger import logger


def parse_event_body(event: dict) -> dict:
    """
    Parse the body from an API Gateway event.

    Handles three cases:
    1. Body is already a dict (direct Lambda invocation)
    2. Body is a JSON string (API Gateway)
    3. Body is missing or invalid (returns empty dict)

    Args:
        event: API Gateway Lambda event

    Returns:
        Parsed body as a dict, or empty dict if parsing fails

    Raises:
        ValueError: If body exists but contains invalid JSON
    """
    body = event.get("body", {})

    # Case 1: Already a dict (direct invocation)
    if isinstance(body, dict):
        return body

    # Case 2: JSON string (API Gateway)
    if isinstance(body, str):
        if not body.strip():
            return {}
        try:
            return json.loads(body)
        except json.JSONDecodeError as err:
            logger.error(f"Failed to parse JSON body: {err}, Body: {body[:500]}")
            raise ValueError("Invalid JSON in request body") from err

    # Case 3: Unexpected type
    logger.warning(f"Unexpected body type: {type(body)}")
    return {}


def get_header(event: dict, header: str, required: bool = False):
    """
    Extract header from API Gateway event.

    Args:
        event: API Gateway Lambda event
        header: Header name (case-insensitive)
        required: Whether header is required

    Returns:
        Header value or None if not found and not required

    Raises:
        ValueError: If header is required but missing
    """
    headers = event.get("headers") or {}

    # Headers are case-insensitive
    header_lower = header.lower()
    for key, value in headers.items():
        if key.lower() == header_lower:
            return value

    if required:
        raise ValueError(f"Missing required header: {header}")

    return None


def get_query_parameter(event: dict, param: str, required: bool = False) -> str:
    """
    Extract query parameter from API Gateway event.

    Args:
        event: API Gateway Lambda event
        param: Parameter name
        required: Whether parameter is required

    Returns:
        Parameter value, or empty string if not found and not required. When
        required=True a non-empty str is guaranteed (or ValueError is raised).

    Raises:
        ValueError: If parameter is required but missing
    """
    params = event.get("queryStringParameters") or {}
    value = params.get(param, "").strip()

    if not value and required:
        raise ValueError(f"Missing required query parameter: {param}")

    return value
