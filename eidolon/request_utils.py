"""
Request parsing utilities for Lambda functions.

Provides common request parsing and validation helpers for API Gateway
Lambda functions.
"""

import json


def parse_json_body(event: dict) -> tuple[dict | None, dict | None]:
    """
    Parse JSON body from API Gateway event.

    Args:
        event: API Gateway Lambda event

    Returns:
        Tuple of (body, error_response)
        - If successful: (parsed_body, None)
        - If error: (None, error_response_dict)
    """
    body_str = event.get("body", "")

    # Handle empty body
    if not body_str:
        return {}, None

    try:
        body = json.loads(body_str)
        if not isinstance(body, dict):
            error_response = {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Request body must be a JSON object"}),
            }
            return None, error_response
        return body, None
    except json.JSONDecodeError:
        error_response = {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Invalid JSON in request body"}),
        }
        return None, error_response


def get_required_field(body: dict, field: str, field_type: type = str):
    """
    Extract and validate required field from request body.

    Args:
        body: Parsed request body
        field: Field name to extract
        field_type: Expected type of the field (default: str)

    Returns:
        Tuple of (value, error_message)
        - If successful: (value, None)
        - If error: (None, error_message)
    """
    if field not in body:
        return None, f"Missing required field: {field}"

    value = body[field]

    # Special handling for strings - strip whitespace
    if field_type is str:
        if not isinstance(value, str):
            return None, f"Field '{field}' must be a string"
        value = value.strip()
        if not value:
            return None, f"Field '{field}' cannot be empty"
        return value, None

    # Type validation for other types
    if not isinstance(value, field_type):
        type_name = field_type.__name__
        return None, f"Field '{field}' must be a {type_name}"

    return value, None


def get_optional_field(body: dict, field: str, field_type: type = str, default = None):
    """
    Extract optional field from request body with type validation.

    Args:
        body: Parsed request body
        field: Field name to extract
        field_type: Expected type of the field (default: str)
        default: Default value if field is missing

    Returns:
        Field value or default
    """
    if field not in body:
        return default

    value = body[field]

    # Special handling for strings
    if field_type is str and isinstance(value, str):
        value = value.strip()
        return value if value else default

    # Type validation
    if not isinstance(value, field_type):
        return default

    return value


def get_query_parameter(event: dict, param: str, required: bool = False) -> tuple[str | None, str | None]:
    """
    Extract query parameter from API Gateway event.

    Args:
        event: API Gateway Lambda event
        param: Parameter name
        required: Whether parameter is required

    Returns:
        Tuple of (value, error_message)
        - If successful: (value, None)
        - If error and required: (None, error_message)
        - If missing and not required: (None, None)
    """
    params = event.get("queryStringParameters") or {}
    value = params.get(param, "").strip()

    if not value and required:
        return None, f"Missing required query parameter: {param}"

    return value if value else None, None


def get_path_parameter(event: dict, param: str) -> str | None:
    """
    Extract path parameter from API Gateway event.

    Args:
        event: API Gateway Lambda event
        param: Parameter name

    Returns:
        Parameter value or None
    """
    params = event.get("pathParameters") or {}
    return params.get(param)


def get_header(event: dict, header: str, required: bool = False) -> tuple[str | None, str | None]:
    """
    Extract header from API Gateway event.

    Args:
        event: API Gateway Lambda event
        header: Header name (case-insensitive)
        required: Whether header is required

    Returns:
        Tuple of (value, error_message)
    """
    headers = event.get("headers") or {}

    # Headers are case-insensitive
    header_lower = header.lower()
    for key, value in headers.items():
        if key.lower() == header_lower:
            return value, None

    if required:
        return None, f"Missing required header: {header}"

    return None, None


def validate_content_type(event: dict, expected: str = "application/json") -> bool:
    """
    Validate request Content-Type header.

    Args:
        event: API Gateway Lambda event
        expected: Expected content type

    Returns:
        True if content type matches or is not present, False otherwise
    """
    content_type, _ = get_header(event, "Content-Type")
    if not content_type:
        return True  # Assume correct content type if not specified

    # Extract just the media type, ignore parameters like charset
    media_type = content_type.split(";")[0].strip().lower()
    expected_type = expected.split(";")[0].strip().lower()

    return media_type == expected_type
