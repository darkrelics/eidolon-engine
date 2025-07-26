"""
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

Lambda function to cache and serve player-available archetypes.
The function loads all archetypes on cold start and filters for Player=true.
Lambda instances typically stay warm for 30 minutes to 2 hours after invocation.
"""

from botocore.exceptions import ClientError

from eidolon.cors import cors_handler
from eidolon.dynamo import dynamo
from eidolon.dynamo import TableName
from eidolon.environment import DEFAULT_ESSENCE
from eidolon.environment import DEFAULT_HEALTH
from eidolon.logger import get_logger
from eidolon.responses import create_response
from eidolon.responses import error_response

# Configure logging
logger = get_logger(__name__)

# Cache for player archetypes
player_archetypes_cache: list = []
cache_loaded: bool = False


def load_player_archetypes() -> list:
    """
    Load all archetypes from DynamoDB and filter for player-available ones.

    Returns:
        List of player archetypes with their data

    Raises:
        RuntimeError: If database scan fails
    """
    global player_archetypes_cache, cache_loaded

    if cache_loaded:
        logger.info("Returning cached player archetypes")
        return player_archetypes_cache

    logger.info("Loading archetypes from DynamoDB")

    try:
        # Scan the archetypes table
        items = []
        last_evaluated_key = None

        while True:
            scan_params = {}
            if last_evaluated_key:
                scan_params["ExclusiveStartKey"] = last_evaluated_key

            scan_result: dict = dynamo.scan(TableName.ARCHETYPES, **scan_params)  # type: ignore
            items.extend(scan_result.get("items", []))

            last_evaluated_key = scan_result.get("last_evaluated_key")
            if not last_evaluated_key:
                break

    except ClientError as err:
        logger.error(
            "Failed to scan archetypes table",
            extra={"error": str(err), "error_code": err.response.get("Error", {}).get("Code", "Unknown")},
            exc_info=True,
        )
        raise RuntimeError(f"Failed to load archetypes: {str(err)}")

    # Filter for player archetypes
    player_archetypes = []
    for item in items:
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
                }
            )

    # Sort by archetype name for consistent ordering
    player_archetypes.sort(key=lambda x: x["ArchetypeName"])

    # Cache the results
    player_archetypes_cache = player_archetypes
    cache_loaded = True

    logger.info("Loaded player archetypes", extra={"count": len(player_archetypes)})
    return player_archetypes


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to return player-available archetypes.

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
        # Load player archetypes (from cache if available)
        player_archetypes = load_player_archetypes()

        # Return successful response
        logger.info("Lambda response", extra={"status_code": 200})
        return cors_handler.add_cors_headers(
            create_response(
                200,
                {
                    "archetypes": player_archetypes,
                    "count": len(player_archetypes),
                },
            ),
            event,
        )

    except RuntimeError as err:
        logger.error("Failed to load archetypes", extra={"error": str(err)}, exc_info=True)
        logger.info("Lambda response", extra={"status_code": 500})
        return cors_handler.add_cors_headers(error_response("Failed to load archetypes", status_code=500), event)
    except Exception as err:
        logger.error("Unexpected error in lambda_handler", extra={"error": str(err)}, exc_info=True)
        logger.info("Lambda response", extra={"status_code": 500})
        return cors_handler.add_cors_headers(error_response("Internal server error", status_code=500), event)
