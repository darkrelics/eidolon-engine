"""
Lambda function for adding verified players to the player table.
"""

import json
import logging
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb")
player_table = dynamodb.Table("players")  # type: ignore


def lambda_handler(event, _) -> None:
    """
    Lambda function triggered by Cognito Post Confirmation.
    Creates a new player record in DynamoDB using the Cognito user's UUID.

    Args:
        event: The event dict from Cognito trigger

    Returns:
        The original event for Cognito to continue processing
    """
    logger.info(f"Received post confirmation event: {json.dumps(event)}")

    try:
        # Extract user attributes from the Cognito event
        user_attributes = event["request"]["userAttributes"]

        # Get the user's Cognito UUID (sub) and email
        user_uuid = user_attributes.get("sub")
        email = user_attributes.get("email")

        if not user_uuid or not email:
            logger.error("Missing required user attributes (sub or email)")
            return event

        # Check if player already exists
        try:
            response = player_table.get_item(Key={"PlayerID": user_uuid})
            if "Item" in response:
                logger.info(f"Player already exists: {user_uuid}")
                return event
        except ClientError as err:
            logger.error(f"Error checking for existing player: {err}")
            return event

        # Create new player entry
        timestamp: str = datetime.utcnow().isoformat()

        player_item: dict = {
            "PlayerID": user_uuid,
            "Email": email,
            "CharacterList": {},
            "SeenMotD": [],
            "CreatedAt": timestamp,
            "UpdatedAt": timestamp,
        }

        # Write to DynamoDB
        player_table.put_item(Item=player_item)
        logger.info(f"Created new player record for: {email} with UUID: {user_uuid}")

    except Exception as err:
        logger.error(f"Error processing user registration: {str(err)}")

    return
