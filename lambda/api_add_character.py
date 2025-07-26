"""Lambda function to add a new character for the incremental game."""

import uuid
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from eidolon.character import character_name_filter, check_character_limit, generate_character_id, get_archetype
from eidolon.cors import cors_handler
from eidolon.environment import (
    DEFAULT_ESSENCE,
    DEFAULT_HEALTH,
    MAX_CHARACTERS_PER_PLAYER,
)
from eidolon.logger import get_logger
from eidolon.dynamo import TableName, dynamo
from eidolon.requests import extract_player_id, get_required_field, parse_json_body
from eidolon.responses import create_response, error_response
from eidolon.validation import validate_character_name

# Configure logging
logger = get_logger(__name__)


def create_items_from_prototypes(prototype_ids: list, character_id: str) -> dict:
    """
    Create item instances from prototype IDs.

    Args:
        prototype_ids: List of prototype IDs to instantiate
        character_id: Character ID for logging

    Returns:
        Dict mapping slot numbers to item UUIDs
    """
    if not prototype_ids:
        return {}

    try:
        inventory = {}
        slot_num = 0

        for prototype_id in prototype_ids:
            # Get prototype data
            prototype = dynamo.get_item(TableName.PROTOTYPES, {"PrototypeID": prototype_id})

            if not prototype:
                logger.warning(
                    "Prototype not found",
                    extra={"prototype_id": prototype_id, "character_id": character_id},
                )
                continue

            # Create new item from prototype
            item_id = str(uuid.uuid4())
            item_data = {
                "ItemID": item_id,
                "PrototypeID": prototype_id,
                "Name": prototype.get("Name", "Unknown Item"),
                "Description": prototype.get("Description", ""),
                "Mass": prototype.get("Mass", 0),
                "Value": prototype.get("Value", 0),
                "Stackable": prototype.get("Stackable", False),
                "MaxStack": prototype.get("MaxStack", 1),
                "Quantity": prototype.get("Quantity", 1),
                "Wearable": prototype.get("Wearable", False),
                "WornOn": prototype.get("WornOn", ""),
                "Verbs": prototype.get("Verbs", {}),
                "Overrides": prototype.get("Overrides", {}),
                "TraitMods": prototype.get("TraitMods", {}),
                "Container": prototype.get("Container", False),
                "Contents": [],
                "IsWorn": False,
                "CanPickUp": prototype.get("CanPickUp", True),
                "Metadata": prototype.get("Metadata", {}),
            }

            # Put item in Items table
            dynamo.put_item(TableName.ITEMS, item_data)

            # Add to inventory
            inventory[str(slot_num)] = item_id
            slot_num += 1

            logger.info(
                "Created item from prototype",
                extra={
                    "item_id": item_id,
                    "prototype_id": prototype_id,
                    "item_name": item_data["Name"],
                    "character_id": character_id,
                    "slot": str(slot_num - 1),
                },
            )

        return inventory

    except Exception as err:
        logger.error(
            "Error creating items from prototypes",
            extra={
                "error": str(err),
                "character_id": character_id,
                "prototype_count": len(prototype_ids),
            },
        )
        return {}


def create_character(player_id: str, character_name: str, archetype_name: str, archetype_data: dict) -> tuple:
    """Create a new incremental character in DynamoDB.

    Args:
        player_id: Cognito user ID
        character_name: Name of the character
        archetype_name: Name of the archetype
        archetype_data: Archetype data from DynamoDB

    Returns:
        Tuple of (character_id, error_message)
        - If successful: (character_id, None)
        - If failed: (None, error_message)
    """
    character_id = generate_character_id()
    timestamp = datetime.now(timezone.utc).isoformat()

    logger.info(
        "Creating new character",
        extra={
            "player_id": player_id,
            "character_name": character_name,
            "archetype_name": archetype_name,
            "character_id": character_id,
        },
    )

    # Build character record
    character_item = {
        "CharacterID": character_id,
        "PlayerID": player_id,
        "CharacterName": character_name,
        "Archetype": archetype_name,
        "Attributes": archetype_data.get("Attributes", {}),
        "Skills": archetype_data.get("Skills", {}),
        "Health": archetype_data.get("Health", DEFAULT_HEALTH),
        "MaxHealth": archetype_data.get("Health", DEFAULT_HEALTH),
        "Essence": archetype_data.get("Essence", DEFAULT_ESSENCE),
        "MaxEssence": archetype_data.get("Essence", DEFAULT_ESSENCE),
        "Wounds": [],
        "RoomID": archetype_data.get("StartRoom", 0),  # Use archetype's StartRoom or default to 0
        "Inventory": {},  # Will be populated with starting items below
        "Resources": {},
        "Progress": {},  # Track story progress flags and achievements
        "StoryState": {  # Track current position in stories
            "currentStoryId": None,
            "currentPassageId": None,
            "startTime": None,
            "abandoned": False,
        },
        "Hidden": False,
        "CharState": "Standing",
        "GameMode": "Incremental",  # Mark as Incremental game character
        "CreatedAt": timestamp,
        "UpdatedAt": timestamp,
        "LastPlayed": timestamp,
    }

    # Process starting items from archetype
    starting_items = archetype_data.get("StartingItems", [])
    if starting_items:
        logger.info(
            "Processing starting items for character",
            extra={
                "character_id": character_id,
                "archetype": archetype_name,
                "item_count": len(starting_items),
            },
        )

        # Create items from prototypes and get inventory mapping
        inventory = create_items_from_prototypes(starting_items, character_id)

        # Update character item with the inventory
        character_item["Inventory"] = inventory

        logger.info(
            "Starting items created",
            extra={"character_id": character_id, "inventory_slots": len(inventory)},
        )

    try:

        # First, check if character name already exists using GSI
        logger.info(
            "Checking if character name is available",
            extra={"character_name": character_name},
        )

        # Use query to check for existing character name
        try:
            existing_chars = dynamo.query(
                TableName.CHARACTERS,
                IndexName="CharacterNameIndex",
                KeyConditionExpression="CharacterName = :name",
                ExpressionAttributeValues={":name": character_name},
                Limit=1
            )

            if existing_chars:
                logger.info(
                    "Character name already taken",
                    extra={"character_name": character_name, "player_id": player_id},
                )
                return None, "Character name is already taken"
        except Exception as err:
            logger.error(
                "Error checking character name availability",
                extra={"error": str(err), "character_name": character_name},
            )
            return None, "Failed to check character name availability"

        # Character name is available, create the character record
        logger.info(
            "Character name available, creating character record",
            extra={"character_id": character_id},
        )

        try:
            dynamo.put_item(TableName.CHARACTERS, character_item)
        except ClientError as err:
            logger.error(
                "Failed to create character record",
                extra={"character_name": character_name, "error": str(err)},
            )
            return None, "Failed to create character"

        logger.info(
            "Character record created successfully",
            extra={"character_id": character_id},
        )

        # Update player's character list
        character_info = {
            "UUID": character_id,
            "Dead": False,
            "GameMode": "Incremental",
        }

        logger.info(
            "Updating player character list",
            extra={
                "player_id": player_id,
                "character_name": character_name,
                "character_info": character_info,
            },
        )

        dynamo.update_item(
            TableName.PLAYERS,
            Key={"PlayerID": player_id},
            UpdateExpression="SET CharacterList.#name = :info, UpdatedAt = :timestamp",
            ExpressionAttributeNames={"#name": character_name},
            ExpressionAttributeValues={
                ":info": character_info,
                ":timestamp": timestamp,
            },
        )

        logger.info(
            "Character creation completed successfully",
            extra={
                "character_name": character_name,
                "character_id": character_id,
                "player_id": player_id,
                "archetype": archetype_name,
            },
        )
        return character_id, None

    except ClientError as err:
        logger.error(
            "Error creating character",
            extra={
                "error": str(err),
                "character_name": character_name,
                "player_id": player_id,
            },
        )
        # Attempt to rollback character creation if player update failed
        try:
            dynamo.delete_item(TableName.CHARACTERS, Key={"CharacterID": character_id})
        except ClientError as rollback_err:
            logger.error(
                "Failed to rollback character creation",
                extra={"error": str(rollback_err), "character_id": character_id},
            )
        return None, "Failed to create character"


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

        # Validate character name format
        try:
            validate_character_name(character_name)
        except ValueError as err:
            return cors_handler.add_cors_headers(
                error_response(f"Invalid character name: {str(err)}", status_code=400),
                event,
            )

        # Check bloom filter for restricted names
        if character_name_filter.is_restricted(character_name):
            return cors_handler.add_cors_headers(
                error_response("Character name is not available", status_code=400),
                event,
            )

        # Check character limit
        try:
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
                return cors_handler.add_cors_headers(
                    error_response(f"Character limit reached ({current_count})", status_code=400),
                    event,
                )
        except (ValueError, RuntimeError) as err:
            logger.error(
                "Failed to check character limit",
                extra={"player_id": player_id, "error": str(err)},
            )
            return cors_handler.add_cors_headers(
                error_response("Failed to check character limit", status_code=500),
                event,
            )

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
                        "health": archetype_data.get("Health", DEFAULT_HEALTH),
                        "essence": archetype_data.get("Essence", DEFAULT_ESSENCE),
                    },
                )
        else:
            # No archetype provided, use defaults
            logger.info("No archetype specified, using defaults")
            archetype_name = "default"

        # Create the character
        character_id, error_msg = create_character(player_id, character_name, archetype_name, archetype_data)
        if not character_id:
            status_code = 409 if error_msg == "Character name is already taken" else 500
            return cors_handler.add_cors_headers(
                error_response(error_msg or "Failed to create character", status_code=status_code),
                event,
            )

        # Return success response
        logger.info("Lambda response", extra={"status_code": 201})
        return cors_handler.add_cors_headers(
            create_response(
                201,
                {
                    "characterId": character_id,
                    "characterName": character_name,
                    "archetype": archetype_name,
                    "message": "Character created successfully",
                },
            ),
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
