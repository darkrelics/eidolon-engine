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


Lambda function to list character names for an authenticated player.
Returns only character names and death status from the player table.
"""

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import get_logger
from eidolon.utilities import (
    build_lambda_response,
    extract_and_validate_player_id,
    handle_lambda_error,
    handle_preflight_if_options,
    log_lambda_invocation,
)

# Configure logging
logger = get_logger(__name__)


def list_characters_business_logic(player_id: str) -> tuple:
    """
    Business logic for listing player's characters.

    Args:
        player_id: Authenticated player ID

    Returns:
        Tuple of (response_data, error_message)
        If successful: (data_dict, None)
        If failed: (None, error_message_string)
    """
    # Get player data from players table
    player_data = dynamo.get_item(TableName.PLAYERS, {"PlayerID": player_id})

    if not player_data:
        logger.warning("Player not found in database", extra={"player_id": player_id})
        return None, "Player not found"

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

    return {"characters": characters}, None


def lambda_handler(event: dict, context: object):
    """
    Lambda handler for listing player characters.

    Args:
        event: API Gateway event with Cognito authorizer
        context: Lambda context

    Returns:
        API Gateway response
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
        response_data, error_message = list_characters_business_logic(player_id)

        if error_message:
            return build_lambda_response(404, {"error": error_message}, event)

        # Return success response
        return build_lambda_response(200, response_data, event)

    except Exception as err:
        return handle_lambda_error(err, context, event)
