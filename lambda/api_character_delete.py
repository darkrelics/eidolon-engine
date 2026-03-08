"""
Eidolon Engine

Copyright 2024-2026 Jason E. Robinson

Lambda function to delete a character for an authenticated player.
Ensures the character belongs to the player before deletion.

Endpoint: DELETE /character/delete
Authentication: Cognito (required)
"""

from eidolon.character_data import character_get
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.player_character import delete_character
from eidolon.requests import get_query_parameter
from eidolon.validation import validate_uuid


def character_deletion(player_id: str, character_id: str) -> dict:
    """
    Handle the business logic for character deletion.

    This function orchestrates the character deletion process without
    performing any AWS-specific operations.

    Args:
        player_id: Cognito user ID
        character_id: Character UUID

    Returns:
        Dict containing:
            - success: bool - Whether deletion was successful
            - character_name: str - Name of deleted character
            - deletion_result: dict - Detailed deletion results

    Raises:
        ValueError: If character not found, invalid ID, or not owned by player
        RuntimeError: If database operations fail
    """
    # Verify ownership
    character: dict = character_get(character_id, player_id)
    character_name = character.get("CharacterName", "Unknown")

    logger.info(f"Character ownership verified, proceeding with deletion for {character_id}")

    # Delete the character
    deletion_result: dict = delete_character(character_id, remove_from_player_list=True)

    # Check if deletion was successful
    if not deletion_result.get("CharacterDeleted", False):
        error_msg = "Failed to delete character"
        errors = deletion_result.get("Errors", [])
        if errors:
            error_msg = errors[0]
        raise RuntimeError(error_msg)

    return {"success": True, "character_name": character_name, "deletion_result": deletion_result}


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """
    Lambda handler for character deletion API.

    Args:
        event: API Gateway event with Cognito authorizer
        context: Lambda context
        player_id: Authenticated player ID

    Returns:
        Dict with status_code and body
    """
    # Get character ID from query parameters
    character_id: str = get_query_parameter(event, "CharacterID", required=True) or ""

    if not validate_uuid(character_id):
        raise ValueError("Invalid CharacterID format")

    # Call business logic
    result: dict = character_deletion(player_id, character_id)
    logger.info(f"Deleted character {character_id} for player {player_id}")

    return {
        "status_code": 200,
        "body": {
            "Message": "Character deleted successfully",
            "CharacterID": character_id,
            "CharacterName": result.get("character_name", "Unknown"),
            "ItemsDeleted": result.get("deletion_result", {}).get("ItemsDeleted", 0),
            "ActiveSegmentsDeleted": result.get("deletion_result", {}).get("ActiveSegmentsDeleted", 0),
        },
    }
