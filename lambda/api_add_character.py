"""Lambda function to add a new character for the incremental game."""

from eidolon.character import character_name_filter, check_character_limit, get_archetype, create_character
from eidolon.cors import cors_handler
from eidolon.environment import MAX_CHARACTERS_PER_PLAYER
from eidolon.logger import get_logger
from eidolon.requests import extract_player_id, get_required_field, parse_json_body
from eidolon.responses import create_response, error_response
from eidolon.validation import validate_character_name

# Configure logging
logger = get_logger(__name__)


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
    can_create = limit_result["can_create"]
    current_count = limit_result["current_count"]

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
    character_id, error_msg = create_character(player_id, character_name, archetype_name, archetype_data)

    if not character_id:
        # Convert the error message to appropriate exception
        if error_msg == "Character name is already taken":
            raise ValueError(error_msg)
        else:
            raise RuntimeError(error_msg or "Failed to create character")

    return {"character_id": character_id, "archetype_name": archetype_name}


def lambda_handler(event: dict, context: object) -> dict:
    """Lambda handler for incremental character creation API."""
    # Log Lambda invocation
    if hasattr(context, "aws_request_id"):
        logger.info(
            "Lambda invocation",
            extra={
                "request_id": context.aws_request_id,  # type: ignore
                "function_name": getattr(context, "function_name", "unknown"),
                "http_method": event.get("httpMethod"),
                "path": event.get("path"),
            },
        )

    # Handle preflight requests
    if event.get("httpMethod") == "OPTIONS":
        return cors_handler.handle_preflight(event)

    try:
        # Extract player ID from Cognito authorizer
        player_id, auth_error = extract_player_id(event)
        if auth_error:
            logger.error("Authentication failed", extra={"error": auth_error})
            return cors_handler.add_cors_headers(error_response(auth_error, status_code=401), event)

        # Parse request body
        body, parse_error = parse_json_body(event)
        if parse_error:
            return cors_handler.add_cors_headers(parse_error, event)

        # Extract and validate required fields
        character_name, name_error = get_required_field(body, "characterName")
        if name_error:
            return cors_handler.add_cors_headers(error_response(name_error, status_code=400), event)

        character_name = character_name.strip()
        archetype_name = body.get("archetypeName", "").strip()

        logger.info(
            "Character creation request received",
            extra={
                "player_id": player_id,
                "character_name": character_name,
                "archetype_name": archetype_name or "default",
            },
        )

        # Handle character creation through business logic function
        try:
            result = handle_character_creation(player_id, character_name, archetype_name)

            # Return success response
            logger.info("Lambda response", extra={"status_code": 201})
            return cors_handler.add_cors_headers(
                create_response(
                    201,
                    {
                        "characterId": result["character_id"],
                        "characterName": character_name,
                        "archetype": result["archetype_name"],
                        "message": "Character created successfully",
                    },
                ),
                event,
            )
        except ValueError as err:
            # Business logic errors (invalid name, limit reached, name taken)
            logger.error("Character creation validation failed", extra={"error": str(err)})
            status_code = 409 if str(err) == "Character name is already taken" else 400
            return cors_handler.add_cors_headers(
                error_response(str(err), status_code=status_code),
                event,
            )
        except RuntimeError as err:
            # System errors (database failures, etc.)
            logger.error("Character creation system error", extra={"error": str(err)}, exc_info=True)
            return cors_handler.add_cors_headers(
                error_response(str(err), status_code=500),
                event,
            )

    except Exception as err:
        logger.error(
            "Unexpected error in lambda_handler",
            extra={"error": str(err)},
            exc_info=True,
        )
        logger.info("Lambda response", extra={"status_code": 500})
        return cors_handler.add_cors_headers(error_response("Internal server error", status_code=500), event)
