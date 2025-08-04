"""
Archetype management utilities for Lambda functions.

Provides functions for loading and filtering player-available archetypes.
"""

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.environment import DEFAULT_ESSENCE, DEFAULT_HEALTH
from eidolon.logger import logger


def get_archtypes() -> list:
    """
    Load all player-available archetypes from DynamoDB.

    Returns:
        List of player archetypes with normalized data

    Raises:
        RuntimeError: If database scan fails
    """
    logger.info("Loading archetypes from DynamoDB")

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
