"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to retrieve item brief information for IndexedDB caching.
Returns only ItemID and PrototypeID for lightweight item loading.

Endpoint: GET /item/brief
Authentication: Cognito (required)
"""

from eidolon.cognito import extract_player_id
from eidolon.cors import cors_handler
from eidolon.items import get_item_brief
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import validate_player
from eidolon.requests import get_query_parameter
from eidolon.responses import lambda_error, lambda_response
from eidolon.validation import validate_uuid


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler for getting item brief information.

    Args:
        event: API Gateway Lambda proxy event
        context: Lambda context

    Returns:
        API Gateway Lambda proxy response
    """
    log_lambda_statistics(event, context)

    preflight_response = cors_handler.handle_preflight(event)
    if preflight_response:
        return preflight_response

    try:
        player_id = extract_player_id(event)
    except ValueError as err:
        logger.warning(f"Authentication failed: {err}", exc_info=False)
        return lambda_response(401, {"Error": "Unauthorized"}, event)
    except Exception as err:
        logger.error(f"Failed to extract player ID: {err}", exc_info=True)
        return lambda_error(event, err)

    try:
        if not validate_player(player_id):
            logger.error(f"Player {player_id} not found in database")
            return lambda_response(401, {"Error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error(f"Failed to validate player: {err}", exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)

    item_id = get_query_parameter(event, "ItemID")

    if not item_id:
        return lambda_response(400, {"Error": "Missing ItemID parameter"}, event)

    if not validate_uuid(item_id):
        return lambda_response(400, {"Error": "Invalid ItemID format"}, event)

    try:
        result = get_item_brief(item_id)
        logger.info(f"Retrieved item brief for {item_id} for player {player_id}")
        return lambda_response(200, result, event)
    except ValueError as err:
        logger.warning(f"Item brief request failed: {err}")
        return lambda_response(404, {"Error": str(err)}, event)
    except RuntimeError as err:
        logger.error(f"Failed to retrieve item brief: {err}", exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)
