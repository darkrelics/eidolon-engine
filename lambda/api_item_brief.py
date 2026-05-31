"""
Eidolon Engine - Incremental Game

Copyright 2024-2026 Jason E. Robinson

Lambda function to retrieve item brief information for IndexedDB caching.
Returns only ItemID and PrototypeID for lightweight item loading.

Endpoint: GET /item/brief
Authentication: Cognito (required)
"""

from eidolon.errors import NotFoundError, UnauthorizedError
from eidolon.items import get_item_brief
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.player import player_owns_item, validate_player
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
        raise UnauthorizedError("Unauthorized")

    # Get item ID from query parameters
    item_id = get_query_parameter(event, "ItemID")

    if not item_id:
        raise ValueError("Missing ItemID parameter")

    if not validate_uuid(item_id):
        raise ValueError("Invalid ItemID format")

    # Enforce ownership: an item brief leaks PrototypeID, Container, Contents,
    # IsWorn, and Quantity, so a player may only read items they own. Return 404
    # rather than 403 so the endpoint does not confirm items the caller cannot see.
    if not player_owns_item(player_id, item_id):
        logger.warning(f"Item access denied: {item_id} not owned by {player_id}")
        raise NotFoundError("Item not found")

    # Get item brief data (raises NotFoundError if the item is missing)
    result = get_item_brief(item_id)

    logger.info(f"Retrieved item brief for {item_id} for player {player_id}")
    return {"status_code": 200, "body": result}
