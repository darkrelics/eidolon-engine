"""
Archetype management utilities for Lambda functions.

Provides functions for loading and filtering player-available archetypes.
"""

from botocore.exceptions import ClientError

from eidolon.dynamo import dynamo
from eidolon.dynamo import TableName
from eidolon.environment import DEFAULT_ESSENCE
from eidolon.environment import DEFAULT_HEALTH
from eidolon.logger import get_logger

logger = get_logger(__name__)


def get_all_player_archetypes() -> list:
    """
    Load all player-available archetypes from DynamoDB.

    Returns:
        List of player archetypes with normalized data

    Raises:
        RuntimeError: If database scan fails
    """
    logger.info("Loading archetypes from DynamoDB")

    try:
        # Scan all archetypes (no pagination needed for < 50 items)
        items = dynamo.scan_all(TableName.ARCHETYPES)
    except ClientError as err:
        logger.error(
            "Failed to scan archetypes table",
            extra={"error": str(err), "error_code": err.response.get("Error", {}).get("Code", "Unknown")},
            exc_info=True,
        )
        raise RuntimeError(f"Failed to load archetypes: {str(err)}")

    # Filter for player archetypes
    player_archetypes = []
    for item in items:  # type: ignore
        # Check if Player field exists and is True
        if item.get("Player", False):
            # Normalize attribute and skill keys to lowercase
            attributes = item.get("Attributes", {})
            if attributes:
                attributes = {k.lower(): v for k, v in attributes.items()}

            skills = item.get("Skills", {})
            if skills:
                skills = {k.lower(): v for k, v in skills.items()}

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

    logger.info("Loaded player archetypes", extra={"count": len(player_archetypes)})
    return player_archetypes
