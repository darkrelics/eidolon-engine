"""
Response formatting utilities for Lambda functions.

Provides consistent response formatting for API Gateway Lambda functions.
"""

import json
from decimal import Decimal

from eidolon.cors import cors_handler
from eidolon.logger import logger


def decimal_to_json_serializable(obj):
    """Convert Decimal types to JSON-serializable format (deep)."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, list):
        return [decimal_to_json_serializable(v) for v in obj]
    if isinstance(obj, dict):
        return {k: decimal_to_json_serializable(v) for k, v in obj.items()}
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
    response_headers = {"Content-Type": "application/json"}

    if headers:
        response_headers.update(headers)

    # Handle different data types
    if data is None:
        body = json.dumps({"Success": True})
    elif isinstance(data, str):
        body = json.dumps({"Message": data})
    else:
        data = decimal_to_json_serializable(data)
        body = json.dumps(data)

    return {
        "statusCode": status_code,
        "headers": response_headers,
        "body": body,
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


def create_response(status_code: int, body: dict) -> dict:
    """
    Create a generic API response with proper formatting.

    Args:
        status_code: HTTP status code.
        body: Response body dict.

    Returns:
        API Gateway response dict.
    """
    body_jsonable = decimal_to_json_serializable(body)
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body_jsonable),
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
    response_headers: dict = {"Content-Type": "application/json"}

    if headers:
        response_headers.update(headers)

    error_body: dict = {"Error": error}
    if details:
        error_body.update(details)

    return {
        "statusCode": status_code,
        "headers": response_headers,
        "body": json.dumps(error_body),
    }


def lambda_response(status_code: int, body: dict, event: dict) -> dict:
    """
    Build Lambda response.

    Args:
        status_code: HTTP status code
        body: Response body dict
        event: Lambda event dict

    Returns:
        Formatted response with CORS headers
    """
    logger.debug(f"Lambda response for status {status_code}")

    return cors_handler.add_cors_headers(create_response(status_code, body), event)


def lambda_error(event: dict, err: Exception) -> dict:
    """
    Handle Lambda function errors with proper logging and CORS response.

    Args:
        event: Lambda event dict
        err: Exception that occurred

    Returns:
        Error response with CORS headers.
    """
    logger.error(
        f"Unexpected error in lambda_handler {err}",
        exc_info=True,
    )

    return cors_handler.add_cors_headers(error_response("Internal server error", status_code=500), event)
