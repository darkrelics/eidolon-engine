"""
Eidolon Engine

Copyright 2024-2026 Jason E. Robinson

Lambda function to cache and serve player-available archetypes.
The function loads all archetypes on cold start and filters for Player=true.
Lambda instances typically stay warm for 30 minutes to 2 hours after invocation.

Endpoint: GET /archetype/list
Authentication: Cognito (required)
"""

from eidolon.archetypes import get_archetypes
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger

archetypes_cache = []

# Cache for player archetypes - populated at module load
try:
    archetypes_cache = get_archetypes()
    logger.info(f"Player archetypes cache loaded successfully: count: {len(archetypes_cache)}")
except Exception as err:
    logger.error(f"Failed to load archetypes cache at module initialization: {err}", exc_info=True)


def handle_get_archetypes() -> dict:
    """
    Handle the business logic for retrieving player archetypes.

    Returns the cached archetypes that were loaded at module initialization.
    If the cache failed to load, attempts to load it now.

    Returns:
        Dict containing:
            - archetypes: list - List of player archetypes
            - count: int - Number of archetypes

    Raises:
        RuntimeError: If database operations fail and cache is empty
    """
    global archetypes_cache

    if archetypes_cache:
        logger.info(f"Returning pre-loaded player archetypes cache: {len(archetypes_cache)} archetypes")
        return {"archetypes": archetypes_cache, "count": len(archetypes_cache)}

    # Cache failed to load at module init, try again
    logger.warning("Cache not loaded at module init, attempting to load now")
    archetypes: list = get_archetypes()

    # Cache the results
    archetypes_cache = archetypes

    logger.info(f"Successfully loaded archetypes cache on demand: {len(archetypes)} archetypes")
    return {"archetypes": archetypes, "count": len(archetypes)}


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """
    Lambda handler to return player-available archetypes.

    This endpoint requires authentication via Cognito authorizer.

    Args:
        event: API Gateway event or direct invocation event
        context: Lambda context
        player_id: Authenticated player ID (not used but required by decorator)

    Returns:
        Dict with status_code and body containing archetypes
    """
    # Note: Authentication is handled by decorator

    # Call business logic
    result: dict = handle_get_archetypes()
    return {
        "status_code": 200,
        "body": {
            "Archetypes": result.get("archetypes", []),
            "Count": result.get("count", 0),
        },
    }
