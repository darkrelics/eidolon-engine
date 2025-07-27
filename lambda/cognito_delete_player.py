"""
Eidolon Engine - Player Deletion Handler

Copyright 2024-2025 Jason E. Robinson

Lambda function to handle complete player deletion including all associated
game data from both MUD and Incremental game tables. This ensures GDPR
compliance by removing all traces of user data.
"""

import json

from eidolon.logger import get_logger
from eidolon.player import delete_player_data_completely
from eidolon.player import extract_player_id_from_event
from eidolon.requests import parse_json_body
from eidolon.utilities import build_lambda_response
from eidolon.utilities import log_lambda_invocation

# Configure logging
logger = get_logger(__name__)


def delete_player_business_logic(player_id: str) -> dict:
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
    return delete_player_data_completely(player_id)


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
    log_lambda_invocation(context, event)

    try:
        player_id = None

        # Extract player ID based on event source
        if "detail" in event and "requestParameters" in event.get("detail", {}):
            # CloudWatch Events from Cognito
            player_id = event["detail"]["requestParameters"].get("username")
        elif "body" in event:
            # API Gateway or direct invocation
            try:
                body = parse_json_body(event) if isinstance(event.get("body"), str) else event.get("body", {})
            except ValueError:
                body = {}
            player_id = body.get("player_id") if body else None
        elif "player_id" in event:
            # Direct invocation
            player_id = event["player_id"]
        elif "requestContext" in event and "authorizer" in event["requestContext"]:
            # API Gateway with Cognito authorizer
            try:
                player_id = extract_player_id_from_event(event)
            except ValueError:
                player_id = None

        if not player_id:
            logger.error("No player ID provided in request")
            if "requestContext" in event:
                return build_lambda_response(400, {"error": "Player ID required"}, event)
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Player ID required"}),
            }

        logger.info("Starting deletion process", extra={"player_id": player_id})

        # Call business logic
        results = delete_player_business_logic(player_id)

        # Return appropriate response based on event source
        if "requestContext" in event:
            # API Gateway response format
            status_code = 200 if not results.get("errors", []) else 207
            logger.info("Lambda response", extra={"status_code": status_code})
            return build_lambda_response(status_code, results, event)
        return results

    except ValueError as err:
        logger.error("Invalid request", extra={"error": str(err)})
        if "requestContext" in event:
            return build_lambda_response(400, {"error": str(err)}, event)
        return {
            "statusCode": 400,
            "body": json.dumps({"error": str(err)}),
        }
    except RuntimeError as err:
        logger.error("Deletion operation failed", extra={"error": str(err)}, exc_info=True)
        if "requestContext" in event:
            return build_lambda_response(500, {"error": "Internal server error"}, event)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error"}),
        }
    except Exception as err:
        logger.error(
            "Unexpected error in lambda_handler",
            extra={"error": str(err)},
            exc_info=True,
        )
        logger.info("Lambda response", extra={"status_code": 500})

        if "requestContext" in event:
            return build_lambda_response(500, {"error": "Internal server error"}, event)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error"}),
        }
