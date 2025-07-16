"""
Eidolon Engine

Copyright 2024-2025 Jason Robinson

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.


Lambda function to cache and serve player-available archetypes.
The function loads all archetypes on cold start and filters for Player=true.
Lambda instances typically stay warm for 30 minutes to 2 hours after invocation.
"""

import os

import boto3

from eidolon.cors import cors_handler
from eidolon.dynamo import scan_all_items
from eidolon.logger import get_logger
from eidolon.responses import create_response, error_response

# Configure logging
logger = get_logger(__name__)

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb")
ARCHETYPES_TABLE: str = os.environ.get("ARCHETYPES_TABLE", "archetypes")
archetypes_table = dynamodb.Table(ARCHETYPES_TABLE)  # type: ignore

# Cache for player archetypes
player_archetypes_cache: list = []
cache_loaded: bool = False


def load_player_archetypes() -> list:
    """
    Load all archetypes from DynamoDB and filter for player-available ones.

    Returns:
        List of player archetypes with their data
    """
    global player_archetypes_cache, cache_loaded  # kill the global variables

    if cache_loaded:
        logger.info("Returning cached player archetypes")
        return player_archetypes_cache

    try:
        logger.info("Loading archetypes from DynamoDB")

        # Scan the archetypes table with pagination
        success, result = scan_all_items(archetypes_table)

        if not success:
            logger.error("Failed to load archetypes", error=result)
            return []

        items = result

        # Filter for player archetypes
        player_archetypes: list = []
        for item in items:
            # Check if Player field exists and is True
            if item.get("Player", False):
                # Normalize attribute and skill keys to lowercase
                if "Attributes" in item:
                    item["Attributes"] = {k.lower(): v for k, v in item["Attributes"].items()}
                if "Skills" in item:
                    item["Skills"] = {k.lower(): v for k, v in item["Skills"].items()}

                player_archetypes.append(
                    {
                        "ArchetypeName": item.get("ArchetypeName", ""),
                        "Description": item.get("Description", ""),
                        "Attributes": item.get("Attributes", {}),
                        "Skills": item.get("Skills", {}),
                        "StartRoom": item.get("StartRoom", 0),
                        "StartingItems": item.get("StartingItems", []),
                        "Health": item.get("Health", 0),
                        "Essence": item.get("Essence", 0),
                    }
                )

        # Sort by archetype name for consistent ordering
        player_archetypes.sort(key=lambda x: x["ArchetypeName"])

        # Cache the results
        player_archetypes_cache = player_archetypes
        cache_loaded = True

        logger.info("Loaded player archetypes", count=len(player_archetypes))
        return player_archetypes

    except Exception as err:
        logger.error("Error loading archetypes", error=err)
        raise


def lambda_handler(event, context) -> dict:
    """
    Lambda handler to return player-available archetypes.

    Args:
        event: API Gateway event or direct invocation event
        context: Lambda context

    Returns:
        API Gateway response with player archetypes
    """
    # Log Lambda invocation
    logger.log_lambda_event(event, context)
    try:
        # Load player archetypes (from cache if available)
        player_archetypes: list = load_player_archetypes()

        # Return successful response
        logger.log_response(200)
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

    except Exception as err:
        logger.error("Error in lambda_handler", error=err)
        logger.log_response(500)
        return cors_handler.add_cors_headers(error_response("Internal server error", status_code=500), event)
