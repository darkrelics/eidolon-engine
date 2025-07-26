"""
Eidolon Engine

Copyright 2024-2025 Jason Robinson

Lambda function to create a new player record in DynamoDB after user registration.
"""

from datetime import datetime
from datetime import timezone

from eidolon.dynamo import dynamo
from eidolon.dynamo import TableName
from eidolon.logger import get_logger

# Configure logging
logger = get_logger(__name__)


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
    # Log Lambda invocation (without exposing sensitive event data)
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
        user_uuid = user_attributes.get("sub")
        email = user_attributes.get("email")

        if not user_uuid or not email:
            logger.error("Missing required user attributes (sub or email)")
            return event

        # Check if player already exists
        logger.debug("Checking for existing player", extra={"user_id": user_uuid})
        existing_player = dynamo.get_item(TableName.PLAYERS, {"PlayerID": user_uuid})

        if existing_player:
            logger.info("Player already exists", extra={"user_id": user_uuid})
            return event

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
        except Exception as err:
            logger.error(
                "Failed to create player record",
                extra={"email": email, "user_id": user_uuid, "error": str(err)},
            )

    except Exception as err:
        logger.error(
            "Error processing user registration",
            extra={"error": str(err)},
            exc_info=True,
        )

    return event
