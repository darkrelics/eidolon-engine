"""
Response formatting utilities for Lambda functions.

Provides consistent response formatting for API Gateway Lambda functions.
"""

import json
from decimal import Decimal


def decimal_to_json_serializable(obj):
    """
    Convert Decimal types to JSON serializable format.

    Args:
        obj: Object to convert

    Returns:
        JSON serializable object
    """
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_json_serializable(v) for v in obj]
    return obj


def success_response(data=None, status_code: int = 200, headers=None) -> dict:
    """
    Create standardized success response for API Gateway.

    Args:
        data: Response data (will be JSON encoded)
        status_code: HTTP status code (default 200)
        headers: Additional headers to include

    Returns:
        API Gateway response dict
    """
    response_headers = {
        "Content-Type": "application/json",
    }

    if headers:
        response_headers.update(headers)

    # Handle different data types
    if data is None:
        body = json.dumps({"success": True})
    elif isinstance(data, str):
        body = json.dumps({"message": data})
    else:
        # Convert any Decimal types for JSON serialization
        data = decimal_to_json_serializable(data)
        body = json.dumps(data)

    return {
        "statusCode": status_code,
        "headers": response_headers,
        "body": body,
    }


def error_response(error: str, status_code: int = 400, details=None, headers=None) -> dict:
    """
    Create standardized error response for API Gateway.

    Args:
        error: Error message
        status_code: HTTP status code (default 400)
        details: Additional error details
        headers: Additional headers to include

    Returns:
        API Gateway response dict
    """
    response_headers = {
        "Content-Type": "application/json",
    }

    if headers:
        response_headers.update(headers)

    error_body = {"error": error}

    if details:
        error_body.update(details)

    return {
        "statusCode": status_code,
        "headers": response_headers,
        "body": json.dumps(error_body),
    }


def created_response(data: dict, location=None) -> dict:
    """
    Create standardized 201 Created response.

    Args:
        data: Created resource data
        location: Optional Location header value

    Returns:
        API Gateway response dict
    """
    headers = {}
    if location:
        headers["Location"] = location

    return success_response(data, status_code=201, headers=headers)


def no_content_response() -> dict:
    """
    Create standardized 204 No Content response.

    Returns:
        API Gateway response dict
    """
    return {
        "statusCode": 204,
        "headers": {"Content-Type": "application/json"},
        "body": "",
    }


def not_found_response(resource=None) -> dict:
    """
    Create standardized 404 Not Found response.

    Args:
        resource: Optional resource description

    Returns:
        API Gateway response dict
    """
    error_msg = f"{resource} not found" if resource else "Resource not found"
    return error_response(error_msg, status_code=404)


def validation_error_response(field: str, message: str) -> dict:
    """
    Create standardized validation error response.

    Args:
        field: Field that failed validation
        message: Validation error message

    Returns:
        API Gateway response dict
    """
    return error_response("Validation error", status_code=400, details={"field": field, "message": message})


def internal_error_response(request_id=None) -> dict:
    """
    Create standardized 500 Internal Server Error response.

    Args:
        request_id: Optional request ID for error tracking

    Returns:
        API Gateway response dict
    """
    details = {}
    if request_id:
        details["request_id"] = request_id

    return error_response("Internal server error", status_code=500, details=details)
