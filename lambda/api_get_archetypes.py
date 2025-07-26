"""
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

Lambda function to cache and serve player-available archetypes.
The function loads all archetypes on cold start and filters for Player=true.
Lambda instances typically stay warm for 30 minutes to 2 hours after invocation.
"""

from eidolon.archetypes import get_all_player_archetypes
from eidolon.cors import cors_handler
from eidolon.logger import get_logger
from eidolon.responses import create_response
from eidolon.responses import error_response

# Configure logging
logger = get_logger(__name__)

# Cache for player archetypes
player_archetypes_cache: list = []
cache_loaded: bool = False


def handle_get_archetypes() -> dict:
    """
    Handle the business logic for retrieving player archetypes.

    This function manages caching and orchestrates the archetype retrieval
    without performing any AWS-specific operations.

    Returns:
        Dict containing:
            - success: bool - Whether retrieval was successful
            - archetypes: list - List of player archetypes
            - count: int - Number of archetypes

    Raises:
        RuntimeError: If database operations fail
    """
    global player_archetypes_cache, cache_loaded

    if cache_loaded:
        logger.info("Returning cached player archetypes")
        return {"success": True, "archetypes": player_archetypes_cache, "count": len(player_archetypes_cache)}

    # Load archetypes from database using eidolon library
    try:
        player_archetypes = get_all_player_archetypes()

        # Cache the results
        player_archetypes_cache = player_archetypes
        cache_loaded = True

        return {"success": True, "archetypes": player_archetypes, "count": len(player_archetypes)}
    except RuntimeError as err:
        logger.error("Failed to load archetypes", extra={"error": str(err)})
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
    # Log Lambda invocation
    if hasattr(context, "aws_request_id"):
        logger.info(
            "Lambda invocation",
            extra={
                "request_id": context.aws_request_id,  # type: ignore
                "function_name": getattr(context, "function_name", "unknown"),
                "http_method": event.get("httpMethod"),
                "path": event.get("path"),
            },
        )

    # Handle preflight requests
    if event.get("httpMethod") == "OPTIONS":
        return cors_handler.handle_preflight(event)

    try:
        # Note: No authentication required for this public endpoint

        # Handle archetype retrieval through business logic function
        result = handle_get_archetypes()

        # Return successful response
        logger.info("Lambda response", extra={"status_code": 200})
        return cors_handler.add_cors_headers(
            create_response(
                200,
                {
                    "archetypes": result["archetypes"],
                    "count": result["count"],
                },
            ),
            event,
        )

    except RuntimeError as err:
        # Database or system failures
        logger.error("Failed to load archetypes", extra={"error": str(err)}, exc_info=True)
        logger.info("Lambda response", extra={"status_code": 500})
        return cors_handler.add_cors_headers(error_response("Failed to load archetypes", status_code=500), event)
    except Exception as err:
        # Catch ALL exceptions to prevent Lambda failures
        logger.error("Unexpected error in lambda_handler", extra={"error": str(err)}, exc_info=True)
        logger.info("Lambda response", extra={"status_code": 500})
        return cors_handler.add_cors_headers(error_response("Internal server error", status_code=500), event)
