"""Lambda function to add a new character for the incremental game."""

import json
import pickle
import uuid
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from eidolon.character import check_character_limit, generate_character_id, get_archetype
from eidolon.cors import cors_handler
from eidolon.dynamo import convert_to_decimal, get_table
from eidolon.environment import (
    CHARACTERS_TABLE,
    DEFAULT_ESSENCE,
    DEFAULT_HEALTH,
    ITEMS_TABLE,
    MAX_CHARACTERS_PER_PLAYER,
    PLAYERS_TABLE,
    PROTOTYPES_TABLE,
)
from eidolon.logger import get_logger
from eidolon.queries import query_by_gsi
from eidolon.responses import create_response, error_response
from eidolon.validation import validate_character_name

# Configure logging
logger = get_logger(__name__)

# Load bloom filter for name validation
bloom_filter = None
try:
    with open("character_name_filter.pkl", "rb") as f:
        bloom_filter = pickle.load(f)
        logger.info("Loaded character name bloom filter")
except Exception as err:
    logger.error("Failed to load bloom filter", extra={"error": str(err)})


def create_items_from_prototypes(prototype_ids: list, character_id: str) -> dict:
    """
    Create item instances from prototype IDs.

    Args:
        prototype_ids: List of prototype IDs to instantiate
        player_id: Player ID for logging
        character_id: Character ID for logging

    Returns:
        Dict mapping slot numbers to item UUIDs
    """
    if not prototype_ids:
        return {}

    try:
        prototypes_table = get_table(PROTOTYPES_TABLE)
        items_table = get_table(ITEMS_TABLE)
        inventory = {}
        slot_num = 0

        for prototype_id in prototype_ids:
            # Get prototype data
            prototype = prototypes_table.get_item(Key={"PrototypeID": prototype_id}).get("Item")

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
                "Mass": convert_to_decimal(prototype.get("Mass", 0)),
                "Value": convert_to_decimal(prototype.get("Value", 0)),
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
            items_table.put_item(Item=item_data)

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
        "Attributes": convert_to_decimal(archetype_data.get("Attributes", {})),
        "Skills": convert_to_decimal(archetype_data.get("Skills", {})),
        "Health": archetype_data.get("Health", DEFAULT_HEALTH),
        "MaxHealth": archetype_data.get("Health", DEFAULT_HEALTH),
        "Essence": convert_to_decimal(archetype_data.get("Essence", DEFAULT_ESSENCE)),
        "MaxEssence": convert_to_decimal(archetype_data.get("Essence", DEFAULT_ESSENCE)),
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
        inventory = create_items_from_prototypes(starting_items, player_id, character_id) # type: ignore

        # Update character item with the inventory
        character_item["Inventory"] = inventory

        logger.info(
            "Starting items created",
            extra={"character_id": character_id, "inventory_slots": len(inventory)},
        )

    # Get table resources first
    players_table = None
    characters_table = None

    try:
        players_table = get_table(PLAYERS_TABLE)
        characters_table = get_table(CHARACTERS_TABLE)

        # First, check if character name already exists using GSI
        logger.info(
            "Checking if character name is available",
            extra={"character_name": character_name},
        )

        # Use query_by_gsi to check for existing character name
        existing_chars, error = query_by_gsi(
            table_name=CHARACTERS_TABLE, index_name="CharacterNameIndex", key_conditions={"CharacterName": character_name}, limit=1
        )

        if error:
            logger.error(
                "Error checking character name availability",
                extra={"error": error, "character_name": character_name},
            )
            return None, "Failed to check character name availability"

        if existing_chars:
            logger.info(
                "Character name already taken",
                extra={"character_name": character_name, "player_id": player_id},
            )
            return None, "Character name is already taken"

        # Character name is available, create the character record
        logger.info(
            "Character name available, creating character record",
            extra={"character_id": character_id},
        )

        try:
            characters_table.put_item(Item=character_item)
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

        players_table.update_item(
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
        if characters_table:
            try:
                characters_table.delete_item(Key={"CharacterID": character_id})
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
        claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
        player_id = claims.get("sub")

        if not player_id:
            return cors_handler.add_cors_headers(error_response("Unauthorized", status_code=401), event)

        # Parse request body
        try:
            body = json.loads(event.get("body", "{}"))
        except json.JSONDecodeError:
            return cors_handler.add_cors_headers(error_response("Invalid JSON", status_code=400), event)

        # Extract and validate required fields
        character_name = body.get("characterName", "").strip()
        archetype_name = body.get("archetypeName", "").strip()

        logger.info(
            "Character creation request received",
            extra={
                "player_id": player_id,
                "character_name": character_name,
                "archetype_name": archetype_name or "default",
            },
        )

        if not character_name:
            return cors_handler.add_cors_headers(
                error_response("Missing required field: characterName", status_code=400),
                event,
            )

        # Validate character name format
        is_valid, error_msg = validate_character_name(character_name)
        if not is_valid:
            return cors_handler.add_cors_headers(
                error_response(f"Invalid character name: {error_msg}", status_code=400),
                event,
            )

        # Check bloom filter for restricted names
        if bloom_filter and character_name.lower() in bloom_filter:
            return cors_handler.add_cors_headers(
                error_response("Character name is not available", status_code=400),
                event,
            )

        # Check character limit
        can_create, current_count = check_character_limit(player_id)
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
