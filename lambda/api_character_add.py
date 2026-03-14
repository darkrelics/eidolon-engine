"""
Eidolon Engine - Incremental Game

Copyright 2024-2026 Jason E. Robinson

Lambda function to add a new character for the incremental game.
Validates character name, checks bloom filter and character limit, then creates character.

Endpoint: POST /character/add
Authentication: Cognito (required)
"""

from eidolon.archetypes import get_archetype
from eidolon.bloom import character_name_filter
from eidolon.character_data import check_character_limit, create_character
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.requests import parse_event_body
from eidolon.validation import validate_character_name


def handle_character_creation(player_id: str, character_name: str, archetype_name: str) -> dict:
    """Handle the business logic for character creation.

    This function orchestrates the character creation process without
    performing any direct database operations.

    Args:
        player_id: Cognito user ID
        character_name: Name of the character
        archetype_name: Name of the archetype (or empty string for default)

    Returns:
        Dict containing:
            - character_id: str - The created character's ID
            - archetype_name: str - The final archetype name used

    Raises:
        ValueError: If character name is invalid, unavailable, or limit reached
        RuntimeError: If database operations fail
    """
    # Validate character name format - raises ValueError on failure
    validate_character_name(character_name)

    # Check bloom filter for restricted names (approve returns True when allowed)
    if not character_name_filter.approve(character_name.lower()):
        raise ValueError("409:Character name is not available")

    # Check character limit
    can_create = check_character_limit(player_id)
    if not can_create:
        raise ValueError("Character limit reached")

    # Look up requested archetype, falling back to default
    archetype_data: dict = {}

    if archetype_name:
        logger.info(f"Looking up archetype: {archetype_name}")
        try:
            archetype_data = get_archetype(archetype_name)
        except RuntimeError as err:
            logger.error(f"Failed to retrieve archetype: {err}")
            raise RuntimeError(f"Failed to retrieve archetype: {archetype_name}") from err
        if archetype_data:
            logger.info(f"Archetype {archetype_name} found")
        else:
            logger.warning(f"Invalid archetype '{archetype_name}' provided, falling back to default")

    if not archetype_data:
        archetype_name = "default"
        try:
            archetype_data = get_archetype("default")
        except RuntimeError as err:
            logger.error(f"Failed to load default archetype: {err}")
            raise RuntimeError("Failed to load default archetype") from err
        if not archetype_data:
            raise RuntimeError("Default archetype not configured in database")

    # Create the character using the eidolon library function
    result: dict = create_character(player_id, character_name, archetype_name, archetype_data)

    return {"character_id": result.get("character_id"), "archetype_name": result.get("archetype", "default")}


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """Lambda handler for incremental character creation API."""
    # Parse request body
    body = parse_event_body(event)

    character_name = body.get("CharacterName")
    if not character_name:
        logger.warning("Character creation request missing CharacterName")
        raise ValueError("CharacterName is required")

    archetype_name = body.get("ArchetypeName", "")

    logger.info(f"Character creation request received for {character_name}")

    # Call business logic
    result: dict = handle_character_creation(player_id, character_name, archetype_name)
    logger.info(
        f"Created character '{character_name}' ({result.get('character_id')}) "
        f"with archetype '{result.get('archetype_name', 'default')}' for player {player_id}"
    )

    # Return success response
    return {
        "status_code": 201,
        "body": {
            "CharacterID": result.get("character_id"),
            "CharacterName": character_name,
            "Archetype": result.get("archetype_name", "default"),
            "Message": "Character created successfully",
        },
    }
