"""
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

Lambda function to create a new player record in DynamoDB after user registration.
"""

from datetime import datetime
from datetime import timezone

from botocore.exceptions import ClientError

from eidolon.dynamo import dynamo
from eidolon.dynamo import TableName
from eidolon.logger import get_logger
from eidolon.utilities import log_lambda_invocation

# Configure logging
logger = get_logger(__name__)


def create_player_record(user_uuid: str, email: str) -> None:
    """
    Create a new player record in DynamoDB.

    Args:
        user_uuid: Cognito user UUID (sub)
        email: User's email address

    Raises:
        ValueError: If user_uuid or email is missing
        RuntimeError: If database operations fail
    """
    if not user_uuid or not email:
        raise ValueError("Missing required user attributes (sub or email)")

    # Check if player already exists
    logger.debug("Checking for existing player", extra={"user_id": user_uuid})

    try:
        existing_player = dynamo.get_item(TableName.PLAYERS, {"PlayerID": user_uuid})

        if existing_player:
            logger.info("Player already exists", extra={"user_id": user_uuid})
            return

    except ClientError as err:
        logger.error(
            "Failed to check for existing player",
            extra={
                "user_id": user_uuid,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown")
            },
            exc_info=True
        )
        raise RuntimeError(f"Failed to check for existing player: {str(err)}")

    # Create new player entry
    timestamp: str = datetime.now(timezone.utc).isoformat()

    player_item: dict = {
        "PlayerID": user_uuid,
        "Email": email,
        "CharacterList": {},
        "SeenMotD": [],
        "CreatedAt": timestamp,
        "UpdatedAt": timestamp,
    }

    # Write to DynamoDB
    try:
        dynamo.put_item(TableName.PLAYERS, player_item)
        logger.info(
            "Created new player record",
            extra={"email": email, "user_id": user_uuid},
        )
    except ClientError as err:
        logger.error(
            "Failed to create player record",
            extra={
                "email": email,
                "user_id": user_uuid,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown")
            },
            exc_info=True
        )
        raise RuntimeError(f"Failed to create player record: {str(err)}")


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
        user_uuid:str = user_attributes.get("sub") # type: ignore
        email:str = user_attributes.get("email") # type: ignore

        # Create player record
        create_player_record(user_uuid, email)

    except ValueError as err:
        logger.error(
            "Invalid user attributes",
            extra={"error": str(err)},
        )
        # For Cognito triggers, we still return the event to allow the flow to continue
        # but log the error for monitoring
    except RuntimeError as err:
        logger.error(
            "Failed to process user registration",
            extra={"error": str(err)},
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
