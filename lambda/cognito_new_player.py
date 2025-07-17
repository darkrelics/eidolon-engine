"""
Eidolon Engine

Copyright 2024-2025 Jason Robinson

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.


Lambda function to create a new player record in DynamoDB after user registration.
"""

import os
from datetime import datetime, timezone


from eidolon.dynamo import get_table, get_item, put_item
from eidolon.logger import get_logger

# Configure logging
logger = get_logger(__name__)

# Get table name from environment
PLAYERS_TABLE = os.environ.get("PLAYERS_TABLE", "players")


def lambda_handler(event, context) -> dict:
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
        extra={"trigger_source": event.get("triggerSource"), "user_pool_id": event.get("userPoolId")},
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
        players_table = get_table(PLAYERS_TABLE)
        logger.debug("Checking for existing player", extra={"user_id": user_uuid, "table_name": PLAYERS_TABLE})
        existing_player = get_item(players_table, {"PlayerID": user_uuid})

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
        if put_item(players_table, player_item):
            logger.info("Created new player record", extra={"email": email, "user_id": user_uuid})
        else:
            logger.error("Failed to create player record", extra={"email": email, "user_id": user_uuid})

    except Exception as err:
        logger.error("Error processing user registration", extra={"error": str(err)}, exc_info=True)

    return event
