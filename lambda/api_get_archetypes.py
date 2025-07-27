"""
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

Lambda function to cache and serve player-available archetypes.
The function loads all archetypes on cold start and filters for Player=true.
Lambda instances typically stay warm for 30 minutes to 2 hours after invocation.
"""

from eidolon.archetypes import get_all_player_archetypes
from eidolon.logger import get_logger
from eidolon.utilities import build_lambda_response
from eidolon.utilities import handle_lambda_error
from eidolon.utilities import handle_preflight_if_options
from eidolon.utilities import log_lambda_invocation

# Configure logging
logger = get_logger(__name__)

# Cache for player archetypes - populated at module load
try:
    logger.info("Loading player archetypes cache at module initialization")
    player_archetypes_cache = get_all_player_archetypes()
    cache_loaded = True
    logger.info(
        "Player archetypes cache loaded successfully",
        extra={"count": len(player_archetypes_cache)}
    )
except Exception as err:
    logger.error(
        "Failed to load archetypes cache at module initialization",
        extra={"error": str(err)},
        exc_info=True
    )
    player_archetypes_cache = []
    cache_loaded = False


def handle_get_archetypes() -> dict:
    """
    Handle the business logic for retrieving player archetypes.

    Returns the cached archetypes that were loaded at module initialization.
    If the cache failed to load, attempts to load it now.

    Returns:
        Dict containing:
            - success: bool - Whether retrieval was successful
            - archetypes: list - List of player archetypes
            - count: int - Number of archetypes

    Raises:
        RuntimeError: If database operations fail and cache is empty
    """
    global player_archetypes_cache, cache_loaded

    if cache_loaded:
        logger.info("Returning pre-loaded player archetypes cache")
        return {"success": True, "archetypes": player_archetypes_cache, "count": len(player_archetypes_cache)}

    # Cache failed to load at module init, try again
    logger.warning("Cache not loaded at module init, attempting to load now")
    try:
        player_archetypes = get_all_player_archetypes()

        # Cache the results
        player_archetypes_cache = player_archetypes
        cache_loaded = True

        logger.info("Successfully loaded archetypes cache on demand")
        return {"success": True, "archetypes": player_archetypes, "count": len(player_archetypes)}
    except RuntimeError as err:
        logger.error("Failed to load archetypes on demand", extra={"error": str(err)})
        raise


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to return player-available archetypes.

    This endpoint does not require authentication as archetype data is public.

    Args:
        event: API Gateway event or direct invocation event
        context: Lambda context

    Returns:
        API Gateway response with player archetypes
    """
    # Log invocation
    log_lambda_invocation(context, event)

    # Handle preflight
    preflight_response = handle_preflight_if_options(event)
    if preflight_response:
        return preflight_response

    # Note: No authentication required for this public endpoint
    
    # Call business logic
    try:
        result = handle_get_archetypes()
        return build_lambda_response(
            200,
            {
                "archetypes": result["archetypes"],
                "count": result["count"],
            },
            event,
        )
    except RuntimeError as err:
        # Database or system failures
        logger.error("Failed to load archetypes", extra={"error": str(err)}, exc_info=True)
        return build_lambda_response(500, {"error": "Failed to load archetypes"}, event)
    except Exception as err:
        return handle_lambda_error(err, context, event)
