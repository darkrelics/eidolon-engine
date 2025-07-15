"""
Character management utilities for Lambda functions.

Provides common functions for character creation and management.
"""

import os
import uuid

from botocore.exceptions import ClientError

from eidolon.logger import get_logger

logger = get_logger(__name__)


def generate_character_id() -> str:
    """
    Generate a UUID v4 for the character ID.
    
    Returns:
        A UUID string for the character ID.
    """
    return str(uuid.uuid4())


def get_archetype(archetype_name: str, archetypes_table):
    """
    Retrieve and validate an archetype from DynamoDB.

    Args:
        archetype_name: Name of the archetype.
        archetypes_table: DynamoDB table resource for archetypes.

    Returns:
        Archetype data or None if not found/not player-available.
    """
    try:
        response = archetypes_table.get_item(Key={"ArchetypeName": archetype_name})

        if "Item" not in response:
            logger.warning("Archetype not found", archetype_name=archetype_name)
            return None

        archetype = response["Item"]

        # Check if archetype is available to players
        if not archetype.get("Player", False):
            logger.warning("Archetype not available to players", archetype_name=archetype_name)
            return None

        return archetype

    except ClientError as err:
        logger.error("Error retrieving archetype", error=err, archetype_name=archetype_name)
        return None


def check_character_limit(player_id: str, players_table) -> tuple:
    """
    Check if player has reached character limit.

    Args:
        player_id: Cognito user ID.
        players_table: DynamoDB table resource for players.

    Returns:
        Tuple of (can_create, current_count).
    """
    max_characters = int(os.environ.get("MAX_CHARACTERS_PER_PLAYER", "10"))

    try:
        # Get player record
        response = players_table.get_item(Key={"PlayerID": player_id})

        if "Item" not in response:
            logger.error("Player not found", player_id=player_id)
            return False, 0

        player = response["Item"]
        character_list = player.get("CharacterList", {})
        current_count = len(character_list)

        return current_count < max_characters, current_count

    except ClientError as err:
        logger.error("Error checking character limit", error=err, player_id=player_id)
        return False, 0


