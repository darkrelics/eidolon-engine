"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to get a character for the incremental game.
Returns the full character data including active segments if any.
"""

from eidolon.character import get_active_segment_for_character, get_character, validate_character_ownership
from eidolon.dynamo import decimal_to_float
from eidolon.items import get_inventory_details
from eidolon.logger import get_logger
from eidolon.player import extract_player_id_from_event, validate_player_exists
from eidolon.requests import get_query_parameter_flexible
from eidolon.utilities import (
    build_lambda_response_pascal,
    handle_lambda_error_pascal,
    handle_preflight_if_options,
    log_lambda_invocation,
)
from eidolon.validation import validate_uuid

# Configure logging
logger = get_logger(__name__)


def get_character_business_logic(character_id: str, player_id: str) -> dict:
    """
    Business logic for getting character data.

    Args:
        character_id: Character UUID from query parameter
        player_id: Authenticated player ID

    Returns:
        Dict containing:
            - success: bool
            - data: dict (if success)
            - error: str (if failed)
            - status_code: int (if failed)
    """
    # Validate character ID format
    if not character_id:
        return {"success": False, "error": "Missing required parameter: characterId", "status_code": 400}

    if not validate_uuid(character_id):
        return {"success": False, "error": "Invalid character ID format", "status_code": 400}

    # Get character and validate ownership
    try:
        character = get_character(character_id)
        validate_character_ownership(character, player_id)
    except ValueError as err:
        if "not found" in str(err).lower():
            return {"success": False, "error": "Character not found", "status_code": 404}
        return {"success": False, "error": str(err), "status_code": 400}
    except RuntimeError as err:
        logger.error("Failed to get character", extra={"error": str(err), "character_id": character_id})
        return {"success": False, "error": "Failed to retrieve character data", "status_code": 500}

    # Check for active segments using eidolon library
    active_segment = {}
    try:
        active_segment = get_active_segment_for_character(character_id, player_id)
        if active_segment:
            logger.info(
                "Active segment found for character",
                extra={
                    "character_id": character_id,
                    "segment_type": active_segment.get("SegmentType"),
                    "story_id": active_segment.get("StoryID"),
                },
            )
    except RuntimeError as err:
        logger.error(
            "Error retrieving active segments",
            extra={
                "error": str(err),
                "character_id": character_id,
            },
        )
        # Continue without active segment data - not critical for response

    # Normalize attribute and skill keys to lowercase for consistency
    attributes = character.get("Attributes")
    if attributes:
        character["Attributes"] = {k.lower(): v for k, v in attributes.items()}

    skills = character.get("Skills")
    if skills:
        character["Skills"] = {k.lower(): v for k, v in skills.items()}

    # Enrich inventory with item details
    inventory = character.get("Inventory")
    if inventory:
        character["InventoryDetails"] = get_inventory_details(inventory)

    # Build response data with PascalCase keys
    response_data = {"Character": decimal_to_float(character)}

    # Add active segment if found
    if active_segment:
        response_data["ActiveSegment"] = decimal_to_float(active_segment)

    return {"success": True, "data": response_data}


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler for getting incremental character data.

    Args:
        event: API Gateway Lambda proxy event
        context: Lambda context

    Returns:
        API Gateway Lambda proxy response
    """
    # Log invocation
    log_lambda_invocation(context, event)

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

    # Get character ID from query parameters (flexible: CharacterID or characterId)
    character_id = get_query_parameter_flexible(event, "CharacterID", "characterId")
    if not character_id:
        return build_lambda_response_pascal(400, {"Error": "Missing CharacterID parameter"}, event)

    # Call business logic
    try:
        result = get_character_business_logic(character_id, player_id)  # type: ignore

        if result.get("success"):
            logger.info("Lambda response", extra={"status_code": 200})
            return build_lambda_response_pascal(200, result.get("data", {}), event)
        else:
            # Log the error if it's a server error
            status_code = result.get("status_code", 500)
            if status_code >= 500:
                logger.error(
                    "Business logic error",
                    extra={"character_id": character_id, "error": result.get("error", "Unknown error")},
                )
            return build_lambda_response_pascal(status_code, {"Error": result.get("error", "Unknown error")}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)
