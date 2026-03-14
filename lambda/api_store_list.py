"""
Eidolon Engine - Incremental Game

Copyright 2024-2026 Jason E. Robinson

Lambda function to list available store items.
Returns store inventory with items available for purchase based on character level.

Endpoint: GET /store/list
Authentication: Cognito (required)
"""

from eidolon.character_data import character_get
from eidolon.dynamo import decimal_to_float
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.player import validate_player
from eidolon.requests import get_query_parameter
from eidolon.store import get_store_items
from eidolon.validation import validate_uuid


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """
    Lambda handler for listing store items.

    Query Parameters:
        - StoreID: Store identifier (default: "general-store")
        - CharacterID: Character UUID (for level-based filtering)

    Args:
        event: API Gateway Lambda proxy event
        context: Lambda context
        player_id: Authenticated player ID

    Returns:
        Dict with status_code and body containing store items
    """
    # Validate player exists
    if not validate_player(player_id):
        logger.error(f"Player {player_id} not found in database")
        raise ValueError("401:Unauthorized")

    # Get store ID (default to general-store)
    store_id = get_query_parameter(event, "StoreID") or "general-store"

    # Get character ID for level-based filtering
    character_id = get_query_parameter(event, "CharacterID")

    character_level = 0

    if character_id:
        if not validate_uuid(character_id):
            raise ValueError("Invalid CharacterID format")

        # Get character and verify ownership
        try:
            character = character_get(character_id, player_id)
            character_level = character.get("Level", 0)
            logger.info(f"Fetching store for character {character_id} (Level {character_level})")
        except ValueError as err:
            # Character not found or not owned by player
            logger.warning(f"Character access denied: {err}")
            raise ValueError(f"403:{err}") from err

    # Get store items
    try:
        store_data = get_store_items(store_id, character_level)
        store_data_converted = decimal_to_float(store_data)
    except ValueError as err:
        logger.warning(f"Store listing failed: {err}")
        raise ValueError(f"404:{err}") from err

    logger.info(f"Retrieved {len(store_data.get('Items', []))} items from store '{store_id}' for player {player_id}")

    return {"status_code": 200, "body": store_data_converted}
