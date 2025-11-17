"""
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

Lambda function to list character names for an authenticated player.
Returns only character names and death status from the player table.
"""

from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.player import get_character_list


def list_characters(player_id: str) -> dict:
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
    # Get formatted character list from eidolon library
    characters: list = get_character_list(player_id)

    logger.debug(f"Characters retrieved: {characters}")

    return {"Characters": characters}


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """
    Lambda handler for listing player characters.

    Args:
        event: API Gateway event with Cognito authorizer
        context: Lambda context
        player_id: Authenticated player ID

    Returns:
        Dict with status_code and body containing list of characters
    """
    logger.info(f"Retrieving character list for player={player_id}")

    # Call business logic
    response_data: dict = list_characters(player_id)
    character_count = len(response_data.get("Characters", []))
    logger.info(f"Listed {character_count} characters for player={player_id}")

    return {"status_code": 200, "body": response_data}
