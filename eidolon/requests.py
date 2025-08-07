"""
Request parsing utilities for Lambda functions.

Provides common request parsing and validation helpers for API Gateway
Lambda functions.
"""


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


def get_query_parameter_flexible(event: dict, param_pascal: str, param_camel: str = "", required: bool = False):
    """
    Extract query parameter from API Gateway event with flexible casing.

    Tries PascalCase first, then camelCase if provided.

    Args:
        event: API Gateway Lambda event
        param_pascal: Parameter name in PascalCase (preferred)
        param_camel: Parameter name in camelCase (fallback)
        required: Whether parameter is required

    Returns:
        Parameter value or None if not found and not required

    Raises:
        ValueError: If parameter is required but missing
    """
    params = event.get("queryStringParameters") or {}

    # Try PascalCase first
    value = params.get(param_pascal, "").strip()

    # If not found and camelCase provided, try that
    if not value and param_camel:
        value = params.get(param_camel, "").strip()

    if not value and required:
        raise ValueError(f"Missing required query parameter: {param_pascal}")

    return value if value else None
