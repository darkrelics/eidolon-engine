"""
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

Lambda function to cache and serve player-available archetypes.
The function loads all archetypes on cold start and filters for Player=true.
Lambda instances typically stay warm for 30 minutes to 2 hours after invocation.
"""

from eidolon.archetypes import get_archtypes
from eidolon.cors import cors_handler
from eidolon.logger import log_lambda_statistics, logger
from eidolon.responses import lambda_response, lambda_error

archetypes_cache: list = []

# Cache for player archetypes - populated at module load
try:
    logger.info("Loading player archetypes cache at module initialization")
    archetypes_cache = get_archtypes()
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
            - success: bool - Whether retrieval was successful
            - archetypes: list - List of player archetypes
            - count: int - Number of archetypes

    Raises:
        RuntimeError: If database operations fail and cache is empty
    """
    global archetypes_cache

    if archetypes_cache:
        logger.info("Returning pre-loaded player archetypes cache")
        return {"success": True, "archetypes": archetypes_cache, "count": len(archetypes_cache)}

    # Cache failed to load at module init, try again
    logger.warning("Cache not loaded at module init, attempting to load now")
    try:
        archetypes: list = get_archtypes()

        # Cache the results
        archetypes_cache: list = archetypes

        logger.info("Successfully loaded archetypes cache on demand")
        return {"success": True, "archetypes": archetypes, "count": len(archetypes)}
    except RuntimeError as err:
        logger.error(f"Failed to load archetypes on demand: {err}")
        raise


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to return player-available archetypes.

    This endpoint requires authentication via Cognito authorizer.

    Args:
        event: API Gateway event or direct invocation event
        context: Lambda context

    Returns:
        API Gateway response with player archetypes
    """
    # Log invocation
    log_lambda_statistics(event, context)

    # Handle preflight
    preflight_response: dict = cors_handler.handle_preflight(event)
    if preflight_response:
        return preflight_response

    # Note: Authentication is handled by API Gateway Cognito authorizer

    # Call business logic
    try:
        result: dict = handle_get_archetypes()
        logger.info("Lambda response", extra={"status_code": 200})
        return lambda_response(
            200,
            {
                "Archetypes": result.get("archetypes", []),
                "Count": result.get("count", 0),
            },
            event,
        )
    except RuntimeError as err:
        # Database or system failures
        logger.error("Failed to load archetypes", extra={"error": str(err)}, exc_info=True)
        return lambda_response(500, {"Error": "Failed to load archetypes"}, event)
    except Exception as err:
        return lambda_error(event, err)
