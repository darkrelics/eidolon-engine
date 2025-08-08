"""
Eidolon Engine - Player Deletion Handler

Copyright 2024-2025 Jason E. Robinson

Lambda function to handle complete player deletion including all associated
game data from both MUD and Incremental game tables. This ensures GDPR
compliance by removing all traces of user data.
"""

import json

from eidolon.cognito import extract_player_id
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import delete_player_data
from eidolon.responses import lambda_response


def delete_player(player_id: str) -> dict:
    """
    Business logic for deleting all player data.

    Args:
        player_id: Cognito user ID to delete

    Returns:
        dict: Deletion results with counts and any errors

    Raises:
        ValueError: If player_id is invalid
        RuntimeError: If deletion operations fail
    """
    # Use the eidolon library to orchestrate complete player deletion
    try:
        results: dict = delete_player_data(player_id)
    except ValueError as err:
        logger.error(f"Invalid player ID: {err}", exc_info=True)
        return {}

    logger.info(f"Player deletion completed: {player_id} results: {results}")

    return results


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler for complete player data deletion.

    Can be triggered by:
    1. Direct invocation with player_id in body
    2. CloudWatch Events from Cognito user deletion
    3. API Gateway with authenticated request

    Args:
        event: Lambda event
        context: Lambda context

    Returns:
        Response with deletion summary
    """
    # Log invocation
    log_lambda_statistics(event, context)

    try:
        player_id = ""

        # Extract player ID based on event source
        if "detail" in event and "requestParameters" in event.get("detail", {}):
            # CloudWatch Events from Cognito
            player_id: str = event.get("detail", {}).get("requestParameters", {}).get("username")
        elif "body" in event:
            # API Gateway or direct invocation
            body: dict = event.get("body", {})
            player_id = body.get("player_id", "") if body else ""
        elif "player_id" in event:
            # Direct invocation
            player_id = event.get("player_id", "")
        elif "requestContext" in event and "authorizer" in event.get("requestContext", {}):
            # API Gateway with Cognito authorizer
            try:
                player_id = extract_player_id(event)
            except ValueError:
                player_id = ""

        if not player_id:
            logger.error("No player ID provided in request")
            if "requestContext" in event:
                return lambda_response(400, {"Error": "Player ID required"}, event)
            return {
                "statusCode": 400,
                "body": json.dumps({"Error": "Player ID required"}),
            }

        logger.debug(f"Starting deletion process: {player_id}")

        # Call business logic
        results: dict = delete_player(player_id)

        # Return appropriate response based on event source
        if "requestContext" in event:
            # API Gateway response format
            status_code: int = 200 if not results.get("errors", []) else 207
            logger.info(f"Lambda response status_code: {status_code}")
            return lambda_response(status_code, results, event)
        return results

    except ValueError as err:
        logger.error(f"Invalid request: {err}", exc_info=True)
        if "requestContext" in event:
            return lambda_response(400, {"Error": "Request Error"}, event)
        return {
            "statusCode": 400,
            "body": json.dumps({"Error": "Error in request format"}),
        }
    except RuntimeError as err:
        logger.error(f"Deletion operation failed: {err}", exc_info=True)
        if "requestContext" in event:
            return lambda_response(500, {"Error": "Internal server error"}, event)
        return {
            "statusCode": 500,
            "body": json.dumps({"Error": "Internal server error"}),
        }
    except Exception as err:
        logger.error(f"Unexpected error in lambda_handler: {err}", exc_info=True)

        if "requestContext" in event:
            return lambda_response(500, {"Error": "Internal server error"}, event)
        return {
            "statusCode": 500,
            "body": json.dumps({"Error": "Internal server error"}),
        }
