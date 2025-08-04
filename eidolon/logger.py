"""Shared logging module for Lambda functions."""

import json
import logging

from eidolon.environment import LOG_LEVEL, APPLICATION_NAME

# Initialize logger for the application
logger = logging.getLogger(APPLICATION_NAME)
logger.setLevel(LOG_LEVEL)


def log_lambda_statistics(event, context) -> None:
    """
    Logs statistics and details of a Lambda function execution.

    Args:
        event: The event that triggered the Lambda function.
        context: The context in which the Lambda function is running.
    """
    # Log basic Lambda function details
    if context:
        logger.info(f"Function: {context.function_name}")
        logger.debug(f"Memory: {context.memory_limit_in_mb}")
        logger.debug(f"Time Remaining: {context.get_remaining_time_in_millis()}")

    # Log details from the event, particularly for authentication and authorization
    if event:
        claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
        logger.info(f"User: {claims.get('cognito:username')}")
        logger.debug(f"Event: {json.dumps(event, indent=2)}")
