"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to retrieve item brief information for IndexedDB caching.
Returns only ItemID and PrototypeID for lightweight item loading.

Endpoint: GET /item/brief
Authentication: Cognito (required)
"""

from eidolon.items import get_item_brief
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.player import validate_player
from eidolon.requests import get_query_parameter
from eidolon.validation import validate_uuid


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """
    Lambda handler for getting item brief information.

    Args:
        event: API Gateway Lambda proxy event
        context: Lambda context
        player_id: Authenticated player ID

    Returns:
        Dict with status_code and body
    """
    # Validate player exists
    if not validate_player(player_id):
        logger.error(f"Player {player_id} not found in database")
        raise ValueError("401:Unauthorized")

    # Get item ID from query parameters
    item_id = get_query_parameter(event, "ItemID")

    if not item_id:
        raise ValueError("Missing ItemID parameter")

    if not validate_uuid(item_id):
        raise ValueError("Invalid ItemID format")

    # Get item brief data
    try:
        result = get_item_brief(item_id)
    except ValueError as err:
        logger.warning(f"Item brief request failed: {err}")
        raise ValueError(f"404:{err}") from err

    logger.info(f"Retrieved item brief for {item_id} for player {player_id}")
    return {"status_code": 200, "body": result}
