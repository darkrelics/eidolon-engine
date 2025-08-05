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


def get_optional_field_flexible(body: dict, field_pascal: str, field_camel: str = "", field_type: type = str, default=None):
    """
    Extract optional field from request body with flexible casing.

    Tries PascalCase first, then camelCase if provided.

    Args:
        body: Parsed request body
        field_pascal: Field name in PascalCase (preferred)
        field_camel: Field name in camelCase (fallback)
        field_type: Expected type of the field (default: str)
        default: Default value if field is missing

    Returns:
        Field value or default

    Raises:
        ValueError: If field exists but has wrong type
    """
    # Try PascalCase first
    if field_pascal in body:
        value = body.get(field_pascal)
    elif field_camel and field_camel in body:
        value = body.get(field_camel)
    else:
        return default

    # Special handling for strings
    if field_type is str:
        if not isinstance(value, str):
            raise ValueError(f"Field '{field_pascal}' must be a string")
        value = value.strip()
        return value if value else default

    # Type validation
    if not isinstance(value, field_type):
        type_name = field_type.__name__
        raise ValueError(f"Field '{field_pascal}' must be a {type_name}")

    return value
