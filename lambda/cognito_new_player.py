"""
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

Lambda function to create a new player record in DynamoDB after user registration.
"""

from eidolon.logger import get_logger
from eidolon.player import create_player_record
from eidolon.utilities import log_lambda_invocation

# Configure logging
logger = get_logger(__name__)


def create_player_business_logic(user_uuid: str, email: str) -> None:
    """
    Business logic for creating a new player record.

    Args:
        user_uuid: Cognito user UUID (sub)
        email: User's email address

    Raises:
        ValueError: If user_uuid or email is missing
        RuntimeError: If database operations fail
    """
    # Use the eidolon library to create the player record
    create_player_record(user_uuid, email)


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda function triggered by Cognito Post Confirmation.
    Creates a new player record in DynamoDB using the Cognito user's UUID.

    Args:
        event: The event dict from Cognito trigger
        context: Lambda context

    Returns:
        The original event for Cognito to continue processing
    """
    # Log invocation
    log_lambda_invocation(context, event)

    # Log Cognito trigger details
    logger.info(
        "Cognito post-confirmation trigger",
        extra={
            "trigger_source": event.get("triggerSource"),
            "user_pool_id": event.get("userPoolId"),
        },
    )

    try:
        # Extract user attributes from the Cognito event
        user_attributes: dict = event.get("request", {}).get("userAttributes", {})

        # Get the user's Cognito UUID (sub) and email
        user_uuid: str = user_attributes.get("sub")  # type: ignore
        email: str = user_attributes.get("email")  # type: ignore

        # Call business logic
        create_player_business_logic(user_uuid, email)

    except ValueError as err:
        logger.error(
            "Invalid user attributes",
            extra={"error": str(err)},
            exc_info=True,
        )
        # For Cognito triggers, we still return the event to allow the flow to continue
        # but log the error for monitoring
    except RuntimeError as err:
        logger.error(
            "Failed to process user registration",
            extra={"error": str(err)},
            exc_info=True,
        )
        # For Cognito triggers, we still return the event to allow the flow to continue
        # but log the error for monitoring
    except Exception as err:
        logger.error(
            "Unexpected error processing user registration",
            extra={"error": str(err)},
            exc_info=True,
        )
        # For Cognito triggers, we still return the event to allow the flow to continue
        # but log the error for monitoring

    return event
