"""Lambda function to add a new character for the incremental game."""

import json
import os
import pickle
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from eidolon.character import check_character_limit, generate_character_id, get_archetype
from eidolon.cors import cors_handler
from eidolon.dynamo import convert_to_decimal, get_table, put_item_if_not_exists
from eidolon.logger import get_logger
from eidolon.validation_utils import validate_character_name

# Configure logging
logger = get_logger(__name__)

# Get table names from environment
PLAYERS_TABLE = os.environ.get("PLAYERS_TABLE", "players")
CHARACTERS_TABLE = os.environ.get("CHARACTERS_TABLE", "characters")
ARCHETYPES_TABLE = os.environ.get("ARCHETYPES_TABLE", "archetypes")

# Get default health and essence from environment
DEFAULT_HEALTH = int(os.environ.get("DEFAULT_HEALTH", "10"))
DEFAULT_ESSENCE = int(os.environ.get("DEFAULT_ESSENCE", "3"))

# Load bloom filter for name validation
bloom_filter = None
try:
    with open("character_name_filter.pkl", "rb") as f:
        bloom_filter = pickle.load(f)
        logger.info("Loaded character name bloom filter")
except Exception as err:
    logger.error("Failed to load bloom filter", extra={"error": str(err)})


def create_character(player_id, character_name, archetype_name, archetype_data):
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
            "character_id": character_id
        }
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
        "Inventory": {},  # Use MUD inventory structure (slot -> itemID)
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

    # Get table resources first
    players_table = None
    characters_table = None
    
    try:
        players_table = get_table(PLAYERS_TABLE)
        characters_table = get_table(CHARACTERS_TABLE)

        # First, try to create the character record with conditional write
        logger.info("Attempting to create character record", extra={"character_id": character_id})
        success, error_msg = put_item_if_not_exists(characters_table, character_item, "CharacterName")
        if not success:
            if error_msg == "Item already exists":
                logger.info(
                    "Character name already taken",
                    extra={"character_name": character_name, "player_id": player_id},
                )
                return None, "Character name is already taken"
            else:
                logger.error(
                    "Failed to create character record",
                    extra={
                        "character_name": character_name,
                        "error": error_msg
                    }
                )
                return None, "Failed to create character"

        logger.info("Character record created successfully", extra={"character_id": character_id})

        # Update player's character list
        character_info = {"UUID": character_id, "Dead": False, "GameMode": "Incremental"}
        
        logger.info(
            "Updating player character list",
            extra={
                "player_id": player_id,
                "character_name": character_name,
                "character_info": character_info
            }
        )

        players_table.update_item(
            Key={"PlayerID": player_id},
            UpdateExpression="SET CharacterList.#name = :info, UpdatedAt = :timestamp",
            ExpressionAttributeNames={"#name": character_name},
            ExpressionAttributeValues={":info": character_info, ":timestamp": timestamp},
        )

        logger.info(
            "Character creation completed successfully",
            extra={
                "character_name": character_name,
                "character_id": character_id,
                "player_id": player_id,
                "archetype": archetype_name
            },
        )
        return character_id, None

    except ClientError as err:
        logger.error(
            "Error creating character", extra={"error": str(err), "character_name": character_name, "player_id": player_id}
        )
        # Attempt to rollback character creation if player update failed
        if characters_table:
            try:
                characters_table.delete_item(Key={"CharacterID": character_id})
            except ClientError as rollback_err:
                logger.error("Failed to rollback character creation", extra={"error": str(rollback_err), "character_id": character_id})
        return None, "Failed to create character"


def lambda_handler(event, context):
    """Lambda handler for incremental character creation API."""
    # Log Lambda invocation
    if hasattr(context, "aws_request_id"):
        logger.info(
            "Lambda invocation",
            extra={
                "request_id": context.aws_request_id,
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
            return cors_handler.add_cors_headers(
                {
                    "statusCode": 401,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": "Unauthorized"}),
                },
                event,
            )

        # Parse request body
        try:
            body = json.loads(event.get("body", "{}"))
        except json.JSONDecodeError:
            return cors_handler.add_cors_headers(
                {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": "Invalid JSON"}),
                },
                event,
            )

        # Extract and validate required fields
        character_name = body.get("characterName", "").strip()
        archetype_name = body.get("archetype", "").strip()
        
        logger.info(
            "Character creation request received",
            extra={
                "player_id": player_id,
                "character_name": character_name,
                "archetype_name": archetype_name or "default"
            }
        )

        if not character_name:
            return cors_handler.add_cors_headers(
                {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": "Missing required field: characterName"}),
                },
                event,
            )

        # Validate character name format
        is_valid, error_msg = validate_character_name(character_name)
        if not is_valid:
            return cors_handler.add_cors_headers(
                {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": f"Invalid character name: {error_msg}"}),
                },
                event,
            )

        # Check bloom filter for restricted names
        if bloom_filter and character_name.lower() in bloom_filter:
            return cors_handler.add_cors_headers(
                {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": "Character name is not available"}),
                },
                event,
            )

        # Check character limit
        players_table = get_table(PLAYERS_TABLE)
        can_create, current_count = check_character_limit(player_id, players_table)
        logger.info(
            "Character limit check",
            extra={
                "player_id": player_id,
                "current_count": current_count,
                "can_create": can_create,
                "max_allowed": os.environ.get("MAX_CHARACTERS_PER_PLAYER", "10")
            }
        )
        if not can_create:
            return cors_handler.add_cors_headers(
                {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": f"Character limit reached ({current_count})", "currentCount": current_count}),
                },
                event,
            )

        # Validate archetype or use defaults
        archetypes_table = get_table(ARCHETYPES_TABLE)
        archetype_data = {}

        if archetype_name:
            # Try to get the archetype data
            logger.info("Looking up archetype", extra={"archetype_name": archetype_name})
            archetype_data = get_archetype(archetype_name, archetypes_table)
            if not archetype_data:
                # Invalid archetype provided, use defaults
                logger.info(
                    "Invalid archetype provided, using defaults", 
                    extra={
                        "requested_archetype": archetype_name, 
                        "player_id": player_id
                    }
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
                        "essence": archetype_data.get("Essence", DEFAULT_ESSENCE)
                    }
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
                {
                    "statusCode": status_code,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": error_msg or "Failed to create character"}),
                },
                event,
            )

        # Return success response
        logger.info("Lambda response", extra={"status_code": 201})
        return cors_handler.add_cors_headers(
            {
                "statusCode": 201,
                "headers": {
                    "Content-Type": "application/json",
                },
                "body": json.dumps(
                    {
                        "characterId": character_id,
                        "characterName": character_name,
                        "archetype": archetype_name,
                        "message": "Character created successfully",
                    }
                ),
            },
            event,
        )

    except Exception as err:
        logger.error("Unexpected error in lambda_handler", extra={"error": str(err)}, exc_info=True)
        logger.info("Lambda response", extra={"status_code": 500})
        return cors_handler.add_cors_headers(
            {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Internal server error"}),
            },
            event,
        )
