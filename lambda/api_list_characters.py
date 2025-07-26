"""
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

Lambda function to list character names for an authenticated player.
Returns only character names and death status from the player table.
"""

from botocore.exceptions import ClientError

from eidolon.dynamo import dynamo
from eidolon.dynamo import TableName
from eidolon.logger import get_logger
from eidolon.utilities import build_lambda_response
from eidolon.utilities import extract_and_validate_player_id
from eidolon.utilities import handle_lambda_error
from eidolon.utilities import handle_preflight_if_options
from eidolon.utilities import log_lambda_invocation

# Configure logging
logger = get_logger(__name__)


def list_characters_business_logic(player_id: str) -> dict:
    """
    Business logic for listing player's characters.

    Args:
        player_id: Authenticated player ID

    Returns:
        Dict with characters list

    Raises:
        ValueError: If player not found
        RuntimeError: If database operations fail
    """
    # Get player data from players table
    try:
        player_data = dynamo.get_item(TableName.PLAYERS, {"PlayerID": player_id})
    except ClientError as err:
        logger.error(
            "Failed to get player data",
            extra={
                "error": str(err),
                "player_id": player_id,
                "error_code": err.response.get("Error", {}).get("Code", "Unknown")
            },
            exc_info=True
        )
        raise RuntimeError(f"Failed to retrieve player data: {str(err)}")

    if not player_data:
        logger.warning("Player not found in database", extra={"player_id": player_id})
        raise ValueError("Player not found")

    character_list = player_data.get("CharacterList", {})
    logger.info(
        "Player data retrieved",
        extra={"player_id": player_id, "character_count": len(character_list)},
    )

    # Build character list with proper field names
    characters = []
    for char_name, char_info in character_list.items():
        char_data = {
            "CharacterName": char_name,
            "CharacterID": char_info.get("UUID", ""),
            "Dead": char_info.get("Dead", False),
        }
        characters.append(char_data)

        logger.debug(
            "Processing character",
            extra={
                "character_name": char_name,
                "character_id": char_data["CharacterID"],
                "is_dead": char_data["Dead"],
            },
        )

    # Sort by name for consistent ordering
    characters.sort(key=lambda x: x["CharacterName"])

    logger.info(
        "Character list prepared successfully",
        extra={
            "player_id": player_id,
            "character_count": len(characters),
            "character_names": [c.get("CharacterName", "") for c in characters],
        },
    )

    return {"characters": characters}


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler for listing player characters.

    Args:
        event: API Gateway event with Cognito authorizer
        context: Lambda context

    Returns:
        API Gateway response with:
            200: List of characters
            404: Player not found
            401: Unauthorized
            500: Internal error
    """
    # Log invocation
    log_lambda_invocation(context, event)

    # Handle preflight
    preflight_response = handle_preflight_if_options(event)
    if preflight_response:
        return preflight_response

    try:
        # Extract and validate player ID
        player_id, auth_error = extract_and_validate_player_id(event)
        if auth_error:
            return auth_error

        # Call business logic
        try:
            response_data = list_characters_business_logic(player_id)
            return build_lambda_response(200, response_data, event)
        except ValueError as err:
            logger.warning(
                "Player not found",
                extra={"player_id": player_id, "error": str(err)},
            )
            return build_lambda_response(
                404,
                {"error": "Player not found"},
                event,
            )
        except RuntimeError as err:
            logger.error(
                "Failed to list characters",
                extra={"player_id": player_id, "error": str(err)},
            )
            return build_lambda_response(
                500,
                {"error": "Failed to retrieve character list"},
                event,
            )

    except Exception as err:
        return handle_lambda_error(err, context, event)
