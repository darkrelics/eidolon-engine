"""
Archetype management utilities for Lambda functions.

Provides functions for loading and filtering player-available archetypes.
"""

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.environment import DEFAULT_ESSENCE, DEFAULT_HEALTH
from eidolon.logger import logger


def get_archetypes() -> list:
    """
    Load all player-available archetypes from DynamoDB.

    Returns:
        List of player archetypes with normalized data

    Raises:
        RuntimeError: If database scan fails
    """
    try:
        # Scan all archetypes
        items: list = dynamo.scan_all(TableName.ARCHETYPES)  # type: ignore
    except ClientError as err:
        logger.error(f"Failed to scan archetypes table: {err.response.get('Error', {}).get('Message', 'Unknown error')}")
        raise RuntimeError(f"Failed to load archetypes: {err}") from err

    # Filter for player archetypes
    player_archetypes: list = []
    for item in items:  # type: ignore
        # Check if Player field exists and is True
        if item.get("Player", False):
            attributes = item.get("Attributes", {})
            skills = item.get("Skills", {})

            player_archetypes.append(
                {
                    "ArchetypeName": item.get("ArchetypeName", ""),
                    "Description": item.get("Description", ""),
                    "Attributes": attributes,
                    "Skills": skills,
                    "StartRoom": item.get("StartRoom", 0),
                    "StartingItems": item.get("StartingItems", []),
                    "Health": item.get("Health", DEFAULT_HEALTH),
                    "Essence": item.get("Essence", DEFAULT_ESSENCE),
                    "AvailableStories": item.get("AvailableStories", []),
                }
            )

    # Sort by archetype name for consistent ordering
    player_archetypes.sort(key=lambda x: x["ArchetypeName"])

    logger.info(f"Loaded player archetypes {len(player_archetypes)}")
    return player_archetypes


def get_archetype(archetype_name: str) -> dict:
    """
    Retrieve and validate an archetype from DynamoDB.

    Args:
        archetype_name: Name of the archetype.

    Returns:
        Archetype data dict. Empty dict if not found/not player-available.

    Raises:
        RuntimeError: If archetype retrieval fails.
    """
    try:
        archetype = dynamo.get_item(TableName.ARCHETYPES, {"ArchetypeName": archetype_name})

        if not archetype:
            logger.warning(f"Archetype: {archetype_name} not found")
            return {}

        if not archetype.get("Player", False):
            logger.info(f"Archetype: {archetype_name} not available to players")
            return {}

        return archetype

    except ClientError as err:
        logger.error(f"Error retrieving archetype: {err}")
        raise RuntimeError(f"Failed to retrieve archetype: {archetype_name}") from err
