"""
Request parsing utilities for Lambda functions.

Provides common request parsing and validation helpers for API Gateway
Lambda functions.
"""

import json

from eidolon.logger import logger


def parse_json_body(event: dict) -> dict:
    """
    Parse JSON body from API Gateway event.

    Args:
        event: API Gateway Lambda event

    Returns:
        Parsed JSON body as dict. Empty dict if body is empty.

    Raises:
        ValueError: If body contains invalid JSON or is not a JSON object
    """
    body_content = event.get("body", "")

    # Handle empty body
    if not body_content:
        return {}

    try:
        body = json.loads(body_content)
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object")
        return body
    except json.JSONDecodeError as err:
        raise ValueError(f"Invalid JSON in request body: {str(err)}")


def get_required_field(body: dict, field: str, field_type: type = str):
    """
    Extract and validate required field from request body.

    Args:
        body: Parsed request body
        field: Field name to extract
        field_type: Expected type of the field (default: str)

    Returns:
        Field value of the expected type

    Raises:
        ValueError: If field is missing, wrong type, or empty string
    """
    if field not in body:
        raise ValueError(f"Missing required field: {field}")

    value = body.get(field)

    # Special handling for strings - strip whitespace
    if field_type is str:
        if not isinstance(value, str):
            raise ValueError(f"Field '{field}' must be a string")
        value = value.strip()
        if not value:
            raise ValueError(f"Field '{field}' cannot be empty")
        return value

    # Type validation for other types
    if not isinstance(value, field_type):
        type_name = field_type.__name__
        raise ValueError(f"Field '{field}' must be a {type_name}")

    return value


def get_optional_field(body: dict, field: str, field_type: type = str, default=None):
    """
    Extract optional field from request body with type validation.

    Args:
        body: Parsed request body
        field: Field name to extract
        field_type: Expected type of the field (default: str)
        default: Default value if field is missing

    Returns:
        Field value or default

    Raises:
        ValueError: If field exists but has wrong type
    """
    if field not in body:
        return default

    value = body[field]

    # Special handling for strings
    if field_type is str:
        if not isinstance(value, str):
            raise ValueError(f"Field '{field}' must be a string")
        value = value.strip()
        return value if value else default

    # Type validation
    if not isinstance(value, field_type):
        type_name = field_type.__name__
        raise ValueError(f"Field '{field}' must be a {type_name}")

    return value


def get_query_parameter(event: dict, param: str, required: bool = False):
    """
    Extract query parameter from API Gateway event.

    Args:
        event: API Gateway Lambda event
        param: Parameter name
        required: Whether parameter is required

    Returns:
        Parameter value or None if not found and not required

    Raises:
        ValueError: If parameter is required but missing
    """
    params = event.get("queryStringParameters") or {}
    value = params.get(param, "").strip()

    if not value and required:
        raise ValueError(f"Missing required query parameter: {param}")

    return value if value else None


def get_path_parameter(event: dict, param: str, required: bool = True):
    """
    Extract path parameter from API Gateway event.

    Args:
        event: API Gateway Lambda event
        param: Parameter name
        required: Whether parameter is required (default: True)

    Returns:
        Parameter value

    Raises:
        ValueError: If parameter is required but missing
    """
    params = event.get("pathParameters") or {}
    value = params.get(param)

    if not value and required:
        raise ValueError(f"Missing required path parameter: {param}")

    return value


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


def validate_content_type(event: dict, expected: str = "application/json") -> bool:
    """
    Validate request Content-Type header.

    Args:
        event: API Gateway Lambda event
        expected: Expected content type

    Returns:
        True if content type matches or is not present, False otherwise
    """
    content_type = get_header(event, "Content-Type")
    if not content_type:
        return True  # Assume correct content type if not specified

    # Extract just the media type, ignore parameters like charset
    media_type = content_type.split(";")[0].strip().lower()
    expected_type = expected.split(";")[0].strip().lower()

    return media_type == expected_type


def validate_required_fields(body: dict, required_fields: list) -> None:
    """
    Validate that all required fields are present in request body.

    Args:
        body: Parsed request body
        required_fields: List of required field names

    Raises:
        ValueError: If any required fields are missing or empty
    """
    missing_fields = []
    for field in required_fields:
        value = body.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing_fields.append(field)

    if missing_fields:
        raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")


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


def get_required_field_flexible(body: dict, field_pascal: str, field_camel: str = "", field_type: type = str):
    """
    Extract and validate required field from request body with flexible casing.

    Tries PascalCase first, then camelCase if provided.

    Args:
        body: Parsed request body
        field_pascal: Field name in PascalCase (preferred)
        field_camel: Field name in camelCase (fallback)
        field_type: Expected type of the field (default: str)

    Returns:
        Field value of the expected type

    Raises:
        ValueError: If field is missing, wrong type, or empty string
    """
    # Try PascalCase first
    if field_pascal in body:
        value = body.get(field_pascal)
    elif field_camel and field_camel in body:
        value = body.get(field_camel)
    else:
        raise ValueError(f"Missing required field: {field_pascal}")

    # Special handling for strings - strip whitespace
    if field_type is str:
        if not isinstance(value, str):
            raise ValueError(f"Field '{field_pascal}' must be a string")
        value = value.strip()
        if not value:
            raise ValueError(f"Field '{field_pascal}' cannot be empty")
        return value

    # Type validation for other types
    if not isinstance(value, field_type):
        type_name = field_type.__name__
        raise ValueError(f"Field '{field_pascal}' must be a {type_name}")

    return value


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
