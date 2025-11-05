"""Shared logging module for Lambda functions."""

import json
import logging

from eidolon.environment import APPLICATION_NAME, LOG_LEVEL

logger = logging.getLogger(APPLICATION_NAME)
logger.setLevel(LOG_LEVEL)


def sanitize_event_for_logging(event: dict) -> dict:
    """
    Sanitize Lambda event by removing sensitive data before logging.

    Removes or redacts:
    - Authorization headers
    - Cookie headers
    - JWT tokens
    - Other potentially sensitive headers

    Args:
        event: The Lambda event dict

    Returns:
        Sanitized copy of the event safe for logging
    """
    if not isinstance(event, dict):
        return event

    sanitized = event.copy()

    # Sanitize headers if present
    if "headers" in sanitized and isinstance(sanitized["headers"], dict):
        headers = sanitized["headers"].copy()
        # Remove or redact sensitive headers
        sensitive_headers = ["Authorization", "authorization", "Cookie", "cookie", "X-Amz-Security-Token"]
        for header in sensitive_headers:
            if header in headers:
                headers[header] = "[REDACTED]"
        sanitized["headers"] = headers

    # Sanitize multiValueHeaders if present
    if "multiValueHeaders" in sanitized and isinstance(sanitized["multiValueHeaders"], dict):
        multi_headers = sanitized["multiValueHeaders"].copy()
        sensitive_headers = ["Authorization", "authorization", "Cookie", "cookie", "X-Amz-Security-Token"]
        for header in sensitive_headers:
            if header in multi_headers:
                multi_headers[header] = ["[REDACTED]"]
        sanitized["multiValueHeaders"] = multi_headers

    # Keep requestContext but be cautious about claims (already logged separately)
    # The claims themselves don't contain tokens, just user attributes

    return sanitized


def log_lambda_statistics(event, context) -> None:
    """
    Logs statistics and details of a Lambda function execution.

    Args:
        event: The event that triggered the Lambda function.
        context: The context in which the Lambda function is running.
    """
    if context:
        logger.info(f"Function: {context.function_name}")
        logger.debug(f"Memory: {context.memory_limit_in_mb}")
        logger.debug(f"Time Remaining: {context.get_remaining_time_in_millis()}")

    if event:
        claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
        logger.info(f"User: {claims.get('cognito:username')}")

        # Sanitize event before logging to prevent credential exposure
        sanitized_event = sanitize_event_for_logging(event)
        logger.debug(f"Event: {json.dumps(sanitized_event, indent=2)}")
