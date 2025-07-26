"""
Player management utilities for Lambda functions.

Provides functions for player authentication and validation.
"""

from botocore.exceptions import ClientError

from eidolon.dynamo import dynamo
from eidolon.dynamo import TableName
from eidolon.logger import get_logger

logger = get_logger(__name__)


def extract_player_id_from_event(event: dict) -> str:
    """
    Extract player ID from Cognito authorizer claims in API Gateway event.

    Args:
        event: API Gateway event with Cognito authorizer

    Returns:
        Player ID (sub claim) from JWT token

    Raises:
        ValueError: If player ID is not found in claims (unauthorized)
    """
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    player_id = claims.get("sub")

    if not player_id:
        logger.warning("No player ID found in request claims")
        raise ValueError("Unauthorized - No player ID in token")

    logger.debug("Extracted player ID from claims", extra={"player_id": player_id})
    return player_id


def validate_player_exists(player_id: str) -> bool:
    """
    Validate that a player exists in the database.

    Args:
        player_id: Cognito user ID to validate

    Returns:
        True if player exists, False otherwise

    Raises:
        RuntimeError: If database query fails
    """
    try:
        player = dynamo.get_item(TableName.PLAYERS, {"PlayerID": player_id})

        if not player:
            logger.warning("Player not found in database", extra={"player_id": player_id})
            return False

        logger.debug("Player validation successful", extra={"player_id": player_id})
        return True

    except ClientError as err:
        logger.error("Failed to validate player existence", extra={"player_id": player_id, "error": str(err)}, exc_info=True)
        raise RuntimeError(f"Failed to validate player: {str(err)}")


def get_player_data(player_id: str) -> dict:
    """
    Retrieve player data from DynamoDB.

    Args:
        player_id: Cognito user ID

    Returns:
        Player data dict

    Raises:
        ValueError: If player not found
        RuntimeError: If database query fails
    """
    try:
        player = dynamo.get_item(TableName.PLAYERS, {"PlayerID": player_id})

        if not player:
            logger.warning("Player not found", extra={"player_id": player_id})
            raise ValueError(f"Player {player_id} not found")

        logger.info(
            "Player data retrieved", extra={"player_id": player_id, "character_count": len(player.get("CharacterList", {}))}
        )
        return player

    except ClientError as err:
        logger.error("Failed to retrieve player data", extra={"player_id": player_id, "error": str(err)}, exc_info=True)
        raise RuntimeError(f"Failed to retrieve player data: {str(err)}")


def get_player_characters(player_id: str) -> dict:
    """
    Get character list for a player.

    Args:
        player_id: Cognito user ID

    Returns:
        Dictionary of character names to character info

    Raises:
        ValueError: If player not found
        RuntimeError: If database query fails
    """
    player = get_player_data(player_id)
    return player.get("CharacterList", {})


def update_player_timestamp(player_id: str, timestamp: str) -> None:
    """
    Update player's UpdatedAt timestamp.

    Args:
        player_id: Cognito user ID
        timestamp: ISO format timestamp

    Raises:
        RuntimeError: If database update fails
    """
    try:
        dynamo.update_item(
            TableName.PLAYERS,
            Key={"PlayerID": player_id},
            UpdateExpression="SET UpdatedAt = :timestamp",
            ExpressionAttributeValues={":timestamp": timestamp},
        )
        logger.debug("Updated player timestamp", extra={"player_id": player_id})

    except ClientError as err:
        logger.error("Failed to update player timestamp", extra={"player_id": player_id, "error": str(err)}, exc_info=True)
        raise RuntimeError(f"Failed to update player timestamp: {str(err)}")
