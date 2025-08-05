"""Lambda function to add a new character for the incremental game."""

from eidolon.archetypes import get_archetype
from eidolon.character import character_name_filter, check_character_limit, create_character
from eidolon.cors import cors_handler
from eidolon.environment import MAX_CHARACTERS_PER_PLAYER
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import extract_player_id, validate_player
from eidolon.requests import get_optional_field_flexible
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
    validate_character_name(character_name)

    # Check bloom filter for restricted names
    if character_name_filter.is_restricted(character_name):
        raise ValueError("Character name is not available")

    # Check character limit
    limit_result: dict = check_character_limit(player_id)
    can_create = limit_result.get("can_create", False)
    current_count = limit_result.get("current_count", 0)

    logger.info(
        "Character limit check",
        extra={
            "player_id": player_id,
            "current_count": current_count,
            "can_create": can_create,
            "max_allowed": MAX_CHARACTERS_PER_PLAYER,
        },
    )

    if not can_create:
        raise ValueError(f"Character limit reached ({current_count})")

    # Validate archetype or use defaults
    archetype_data: dict = {}

    if archetype_name:
        # Try to get the archetype data
        logger.info("Looking up archetype", extra={"archetype_name": archetype_name})
        try:
            archetype_data = get_archetype(archetype_name)
        except RuntimeError as err:
            logger.error(f"Failed to retrieve archetype: {err}")
            raise RuntimeError(f"Failed to retrieve archetype: {archetype_name}") from err
        if not archetype_data:
            # Invalid archetype provided, use defaults
            logger.info(
                "Invalid archetype provided, using defaults",
                extra={
                    "requested_archetype": archetype_name,
                    "player_id": player_id,
                },
            )
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
        logger.error("Authentication failed", extra={"error": str(err)}, exc_info=True)
        return lambda_response(401, {"Error": "Unauthorized"}, event)
    except Exception as err:
        return lambda_error(event, err)

    # Validate player exists
    try:
        if not validate_player(player_id):
            logger.error(f"Player not found in database: {player_id}")
            return lambda_response(401, {"Error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error(f"Failed to validate player: {err}", exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)

    # Parse request body
    try:
        body: dict = event.get("body", {})
    except ValueError:
        return lambda_response(400, {"Error": "Unable Parse Payload"}, event)
    except Exception as err:
        logger.error(f"Failed to parse request body: {err}", exc_info=True)
        return lambda_error(event, err)

    # Extract and validate required fields with flexible casing
    try:
        character_name: str = body.get("character_name") or body.get("CharacterName")  # type: ignore
    except ValueError as err:
        return lambda_response(400, {"Error": str(err)}, event)

    archetype_name = get_optional_field_flexible(body, "ArchetypeName", "archetypeName", default="")

    logger.info(
        "Character creation request received",
        extra={
            "player_id": player_id,
            "character_name": character_name,
            "archetype_name": archetype_name or "default",
        },
    )

    # Call business logic
    try:
        result: dict = handle_character_creation(player_id, character_name, archetype_name)  # type: ignore
        logger.info("Lambda response", extra={"status_code": 201})
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
        logger.warning("Character creation validation failed", extra={"error": str(err)})
        status_code: int = 409 if str(err) == "Character name is already taken" else 400
        return lambda_response(status_code, {"Error": str(err)}, event)
    except RuntimeError as err:
        # System errors (database failures, etc.)
        logger.error("Character creation system error", extra={"error": str(err)}, exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)
