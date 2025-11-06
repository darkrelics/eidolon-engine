"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to retrieve complete item prototype definition for IndexedDB caching.
Returns full prototype data including all properties, stats, and metadata.

Endpoint: GET /item/prototype
Authentication: Cognito (required)
"""

from eidolon.cognito import extract_player_id
from eidolon.cors import cors_handler
from eidolon.dynamo import decimal_to_float
from eidolon.items import get_item_prototype_full
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import validate_player
from eidolon.requests import get_query_parameter
from eidolon.responses import lambda_error, lambda_response
from eidolon.validation import validate_uuid


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler for getting item prototype information.

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

    prototype_id = get_query_parameter(event, "PrototypeID")

    if not prototype_id:
        return lambda_response(400, {"Error": "Missing PrototypeID parameter"}, event)

    if not validate_uuid(prototype_id):
        return lambda_response(400, {"Error": "Invalid PrototypeID format"}, event)

    try:
        result = get_item_prototype_full(prototype_id)
        result_converted = decimal_to_float(result)
        logger.info(f"Retrieved item prototype for {prototype_id} for player {player_id}")
        return lambda_response(200, result_converted, event)  # type: ignore
    except ValueError as err:
        logger.warning(f"Item prototype request failed: {err}")
        return lambda_response(404, {"Error": str(err)}, event)
    except RuntimeError as err:
        logger.error(f"Failed to retrieve item prototype: {err}", exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)
