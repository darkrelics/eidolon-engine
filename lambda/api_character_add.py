"""Lambda function to add a new character for the incremental game."""

from eidolon.archetypes import get_archetype
from eidolon.bloom import character_name_filter
from eidolon.character_data import check_character_limit, create_character
from eidolon.cognito import extract_player_id
from eidolon.cors import cors_handler
from eidolon.logger import log_lambda_statistics, logger
from eidolon.requests import parse_event_body
from eidolon.responses import lambda_error, lambda_response
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
    # Validate character name format - let it raise ValueError
    try:
        validate_character_name(character_name)
    except ValueError as err:
        logger.warning(f"Character name validation failed for '{character_name}': {err}")
        raise ValueError(f"Invalid character name: {err}") from err

    # Check bloom filter for restricted names (approve returns True when allowed)
    if not character_name_filter.approve(character_name.lower()):
        raise ValueError("Character name is not available")

    # Check character limit
    can_create = check_character_limit(player_id)

    logger.debug(f"Character limit check for {player_id}")

    if not can_create:
        raise ValueError("Character limit reached")

    # Validate archetype or use defaults
    archetype_data: dict = {}

    if archetype_name:
        # Try to get the archetype data
        logger.info(f"Looking up archetype: {archetype_name}")
        try:
            archetype_data = get_archetype(archetype_name)
        except RuntimeError as err:
            logger.error(f"Failed to retrieve archetype: {err}")
            raise RuntimeError(f"Failed to retrieve archetype: {archetype_name}") from err
        if not archetype_data:
            # Invalid archetype provided, use defaults
            logger.info(f"Invalid archetype '{archetype_name}' provided, using defaults")
            archetype_data = {}
            archetype_name = "default"
        else:
            logger.info(
                f"Archetype {archetype_name} found",
            )
    else:
        # No archetype provided, use defaults
        logger.info("No archetype specified, using defaults")
        archetype_name = "default"

    # Create the character using the eidolon library function
    result: dict = create_character(player_id, character_name, archetype_name, archetype_data)

    return {"character_id": result.get("character_id"), "archetype_name": result.get("archetype", "default")}


def lambda_handler(event: dict, context: object) -> dict:
    """Lambda handler for incremental character creation API."""
    # Log invocation
    log_lambda_statistics(event, context)

    # Handle preflight
    preflight_response: dict = cors_handler.handle_preflight(event)
    if preflight_response:
        return preflight_response

    # Extract player ID from JWT
    try:
        player_id: str = extract_player_id(event)
    except ValueError as err:
        logger.warning(f"Authentication failed: {err}", exc_info=False)
        return lambda_response(401, {"Error": "Unauthorized"}, event)
    except Exception as err:
        return lambda_error(event, err)

    # Parse request body
    try:
        body = parse_event_body(event)
    except ValueError as err:
        logger.error(f"Failed to parse request body: {err}", exc_info=False)
        return lambda_response(400, {"Error": str(err)}, event)
    except Exception as err:
        logger.error(f"Failed to parse request body: {err}", exc_info=True)
        return lambda_error(event, err)

    character_name = body.get("CharacterName")
    if not character_name:
        logger.warning("Character creation request missing CharacterName")
        return lambda_response(400, {"Error": "CharacterName is required"}, event)

    archetype_name = body.get("ArchetypeName", "")

    logger.info(f"Character creation request received for {character_name}")

    # Call business logic
    try:
        result: dict = handle_character_creation(player_id, character_name, archetype_name)  # type: ignore
        logger.info(
            f"Created character '{character_name}' ({result.get('character_id')}) with archetype '{result.get('archetype_name', 'default')}' for player {player_id}"
        )
        return lambda_response(
            201,
            {
                "CharacterID": result.get("character_id"),
                "CharacterName": character_name,
                "Archetype": result.get("archetype_name", "default"),
                "Message": "Character created successfully",
            },
            event,
        )
    except ValueError as err:
        # Business logic errors (invalid name, limit reached, name taken)
        logger.warning(f"Character creation validation failed Error: {err}")
        status_code: int = 409 if str(err) == "Character name is already taken" else 400
        return lambda_response(status_code, {"Error": str(err)}, event)
    except RuntimeError as err:
        # System errors (database failures, etc.)
        logger.error(f"Character creation system error Error: {err}", exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)
