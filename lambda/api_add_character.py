"""Lambda function to add a new character for the incremental game."""

from eidolon.character import character_name_filter, check_character_limit, create_character, get_archetype
from eidolon.environment import MAX_CHARACTERS_PER_PLAYER
from eidolon.logger import logger, log_lambda_statistics
from eidolon.player import extract_player_id_from_event, validate_player_exists
from eidolon.requests import get_optional_field_flexible, get_required_field_flexible, parse_json_body
from eidolon.utilities import (
    build_lambda_response_pascal,
    handle_lambda_error_pascal,
    handle_preflight_if_options,
)
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
    limit_result = check_character_limit(player_id)
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
    archetype_data = {}

    if archetype_name:
        # Try to get the archetype data
        logger.info("Looking up archetype", extra={"archetype_name": archetype_name})
        archetype_data = get_archetype(archetype_name)
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
                "Archetype found",
                extra={
                    "archetype_name": archetype_name,
                    "has_attributes": bool(archetype_data.get("Attributes")),
                    "has_skills": bool(archetype_data.get("Skills")),
                    "health": archetype_data.get("Health"),
                    "essence": archetype_data.get("Essence"),
                    "available_stories": archetype_data.get("AvailableStories", []),
                },
            )
    else:
        # No archetype provided, use defaults
        logger.info("No archetype specified, using defaults")
        archetype_name = "default"

    # Create the character using the eidolon library function
    result = create_character(player_id, character_name, archetype_name, archetype_data)

    return {"character_id": result.get("character_id"), "archetype_name": result.get("archetype", "default")}


def lambda_handler(event: dict, context: object) -> dict:
    """Lambda handler for incremental character creation API."""
    # Log invocation
    log_lambda_statistics(event, context)

    # Handle preflight
    preflight_response = handle_preflight_if_options(event)
    if preflight_response:
        return preflight_response

    # Extract player ID from JWT
    try:
        player_id = extract_player_id_from_event(event)
    except ValueError as err:
        logger.error("Authentication failed", extra={"error": str(err)}, exc_info=True)
        return build_lambda_response_pascal(401, {"Error": "Unauthorized"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)

    # Validate player exists
    try:
        if not validate_player_exists(player_id):
            logger.error("Player not found in database", extra={"player_id": player_id})
            return build_lambda_response_pascal(401, {"Error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error("Failed to validate player", extra={"error": str(err)}, exc_info=True)
        return build_lambda_response_pascal(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)

    # Parse request body
    try:
        body = parse_json_body(event)
    except ValueError as err:
        return build_lambda_response_pascal(400, {"Error": str(err)}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)

    # Extract and validate required fields with flexible casing
    try:
        character_name = get_required_field_flexible(body, "CharacterName", "characterName")
    except ValueError as err:
        return build_lambda_response_pascal(400, {"Error": str(err)}, event)

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
        result = handle_character_creation(player_id, character_name, archetype_name)  # type: ignore
        logger.info("Lambda response", extra={"status_code": 201})
        return build_lambda_response_pascal(
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
        status_code = 409 if str(err) == "Character name is already taken" else 400
        return build_lambda_response_pascal(status_code, {"Error": str(err)}, event)
    except RuntimeError as err:
        # System errors (database failures, etc.)
        logger.error("Character creation system error", extra={"error": str(err)}, exc_info=True)
        return build_lambda_response_pascal(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)
