"""
Eidolon Engine - Incremental Game

Copyright 2024-2026 Jason E. Robinson

Lambda function to retrieve complete item prototype definition for IndexedDB caching.
Returns full prototype data including all properties, stats, and metadata.

Endpoint: GET /item/prototype
Authentication: Cognito (required)
"""

from eidolon.dynamo import decimal_to_float
from eidolon.items import get_item_prototype_full
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.player import validate_player
from eidolon.requests import get_query_parameter
from eidolon.validation import validate_uuid


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """
    Lambda handler for getting item prototype information.

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

    # Get prototype ID from query parameters
    prototype_id = get_query_parameter(event, "PrototypeID")

    if not prototype_id:
        raise ValueError("Missing PrototypeID parameter")

    if not validate_uuid(prototype_id):
        raise ValueError("Invalid PrototypeID format")

    # Get item prototype data
    try:
        result = get_item_prototype_full(prototype_id)
        result_converted = decimal_to_float(result)
    except ValueError as err:
        logger.warning(f"Item prototype request failed: {err}")
        raise ValueError(f"404:{err}") from err

    logger.info(f"Retrieved item prototype for {prototype_id} for player {player_id}")
    return {"status_code": 200, "body": result_converted}
