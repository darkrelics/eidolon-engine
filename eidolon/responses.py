"""
Response formatting utilities for Lambda functions.

Provides consistent response formatting for API Gateway Lambda functions.
"""

import json
from decimal import Decimal

from eidolon.cors import cors_handler
from eidolon.logger import logger


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
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(decimal_to_json_serializable(body)),
    }


def error_response(error: str, status_code: int = 400, details=None, headers=None) -> dict:
    """
    Create standardized error response with PascalCase fields for API Gateway.

    Args:
        error: Error message
        status_code: HTTP status code (default 400)
        details: Additional error details
        headers: Additional headers to include

    Returns:
        API Gateway response dict with PascalCase error field
    """
    response_headers: dict = {
        "Content-Type": "application/json",
    }

    if headers:
        response_headers.update(headers)

    error_body: dict = {"Error": error}

    if details:
        # Convert detail keys to PascalCase
        pascal_details: dict = {}
        for key, value in details.items():
            # Simple conversion: capitalize first letter of each word
            pascal_key: str = "".join(word.capitalize() for word in key.split("_"))
            pascal_details[pascal_key] = value
        error_body.update(pascal_details)

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
        Formatted response with CORS headers and PascalCase field names
    """
    logger.info(f"Lambda response for status {status_code}")

    # If it's an error response with lowercase "error" key, convert to PascalCase
    if "error" in body and status_code >= 400:

        error_msg = body.get("error", "")
        # Remove the error key and treat rest as details
        details: dict = {k: v for k, v in body.items() if k != "error"}
        response: dict = error_response(error_msg, status_code, details if details else None)
        return cors_handler.add_cors_headers(response, event)

    return cors_handler.add_cors_headers(create_response(status_code, body), event)


def lambda_error(event: dict, err: Exception) -> dict:
    """
    Handle Lambda function errors with proper logging and CORS response using PascalCase.

    Args:
        err: Exception that occurred
        context: Lambda context
        event: Lambda event dict

    Returns:
        Error response with CORS headers and PascalCase fields
    """
    logger.error(
        f"Unexpected error in lambda_handler {err}",
        exc_info=True,
    )
    logger.info("Lambda response for status 500")

    return cors_handler.add_cors_headers(error_response("Internal server error", status_code=500), event)
