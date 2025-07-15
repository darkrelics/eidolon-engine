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

import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

from eidolon.cors import cors_handler

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

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

        # Scan the archetypes table
        response = archetypes_table.scan()
        items = response.get("Items", [])

        # Handle pagination if necessary
        while "LastEvaluatedKey" in response:
            response = archetypes_table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response.get("Items", []))

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

        logger.info(f"Loaded {len(player_archetypes)} player archetypes")
        return player_archetypes

    except ClientError as err:
        logger.error(f"Error loading archetypes from DynamoDB: {err}")
        raise
    except Exception as err:
        logger.error(f"Unexpected error loading archetypes: {err}")
        raise


def lambda_handler(event, _) -> dict:
    """
    Lambda handler to return player-available archetypes.

    Args:
        event: API Gateway event or direct invocation event
        _: Lambda context (unused)

    Returns:
        API Gateway response with player archetypes
    """
    try:
        # Load player archetypes (from cache if available)
        player_archetypes: list = load_player_archetypes()

        # Return successful response
        response: dict = {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
            },
            "body": json.dumps(
                {
                    "archetypes": player_archetypes,
                    "count": len(player_archetypes),
                }
            ),
        }
        return cors_handler.add_cors_headers(response, event)  # type: ignore

    except Exception as err:
        logger.error(f"Error in lambda_handler: {err}")
        response = {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
            },
            "body": json.dumps(
                {
                    "error": "Internal server error",
                    "message": str(err),
                }
            ),
        }
        return cors_handler.add_cors_headers(response, event)
