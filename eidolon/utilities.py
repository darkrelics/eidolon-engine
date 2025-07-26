"""
Lambda utility functions for common patterns.

Provides helper functions to reduce boilerplate in Lambda handlers
while keeping the handler function visible in each Lambda file.
"""

from eidolon.cors import cors_handler
from eidolon.logger import get_logger
from eidolon.requests import extract_player_id
from eidolon.responses import create_response, error_response, unauthorized_response

logger = get_logger(__name__)


def log_lambda_invocation(context: object, event: dict) -> None:
    """
    Log Lambda function invocation details.

    Args:
        context: Lambda context object
        event: Lambda event dict
    """
    if hasattr(context, "aws_request_id"):
        logger.info(
            "Lambda invocation",
            extra={
                "request_id": context.aws_request_id,  # type: ignore
                "function_name": getattr(context, "function_name", "unknown"),
                "http_method": event.get("httpMethod"),
                "path": event.get("path"),
            },
        )


def handle_preflight_if_options(event: dict) -> dict:
    """
    Handle CORS preflight request if HTTP method is OPTIONS.

    Args:
        event: Lambda event dict

    Returns:
        CORS preflight response dict if OPTIONS, empty dict otherwise
    """
    if event.get("httpMethod") == "OPTIONS":
        return cors_handler.handle_preflight(event)
    return {}


def extract_and_validate_player_id(event: dict) -> tuple:
    """
    Extract player ID from event and return with CORS-wrapped error if needed.

    Args:
        event: Lambda event dict

    Returns:
        Tuple of (player_id, error_response_with_cors)
        If successful: (player_id, None)
        If failed: (None, error_response_dict)
    """
    player_id, auth_error = extract_player_id(event)
    if auth_error:
        logger.error("Authentication failed", extra={"error": auth_error})
        return None, cors_handler.add_cors_headers(unauthorized_response(auth_error), event)

    logger.info("Player authenticated", extra={"player_id": player_id})
    return player_id, None


def wrap_response_with_cors(response: dict, event: dict) -> dict:
    """
    Add CORS headers to response.

    Args:
        response: Response dict
        event: Lambda event dict

    Returns:
        Response with CORS headers added
    """
    return cors_handler.add_cors_headers(response, event)


def handle_lambda_error(err: Exception, context: object, event: dict, custom_message = None) -> dict:
    """
    Handle Lambda function errors with proper logging and CORS response.

    Args:
        err: Exception that occurred
        context: Lambda context
        event: Lambda event dict
        custom_message: Optional custom error message

    Returns:
        Error response with CORS headers
    """
    logger.error(
        custom_message or "Unexpected error in lambda_handler",
        extra={"error": str(err)},
        exc_info=True,
    )
    logger.info("Lambda response", extra={"status_code": 500})

    return cors_handler.add_cors_headers(error_response("Internal server error", status_code=500), event)


def build_lambda_response(status_code: int, body: dict, event: dict) -> dict:
    """
    Build Lambda response with proper formatting and CORS headers.

    Args:
        status_code: HTTP status code
        body: Response body dict
        event: Lambda event dict

    Returns:
        Formatted response with CORS headers
    """
    logger.info("Lambda response", extra={"status_code": status_code})
    return cors_handler.add_cors_headers(create_response(status_code, body), event)
