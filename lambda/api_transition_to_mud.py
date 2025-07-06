"""
Eidolon Engine - Character Transition to MUD

This Lambda handles the transition of a character from the Incremental
game to the MUD after completing the customization phase.
"""

import json
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from eidolon.cors import cors_handler
from eidolon.logger import get_logger

# Configure logging
logger = get_logger(__name__)

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb")
characters_table = os.environ.get("CHARACTERS_TABLE", "characters")
characters_table = dynamodb.Table(characters_table)
players_table = os.environ.get("PLAYERS_TABLE", "players")
players_table = dynamodb.Table(players_table)

# Room selection based on archetype
ARCHETYPE_ROOMS = {
    "Wizard": 8,     # Mage's Guild
    "Rogue": 10,     # Thieves' Den
    "Warrior": 4,    # Training Grounds
    "Ranger": 12,    # Forest Edge
    "Cleric": 6,     # Temple
    "Bard": 14,      # Tavern
}

# Default room if archetype not found
DEFAULT_ROOM = 0  # Town Square


def get_character(character_id):
    """
    Retrieve character from database.
    
    Args:
        character_id: Character UUID
        
    Returns:
        Character data or None
    """
    try:
        response = characters_table.get_item(Key={"CharacterID": character_id})
        
        if "Item" not in response:
            logger.warning("Character not found", character_id=character_id)
            return None
            
        return response["Item"]
        
    except ClientError as err:
        logger.error("Error retrieving character", error=err, character_id=character_id)
        return None


def select_starting_room(character):
    """
    Select appropriate starting room for character.
    
    Args:
        character: Character data
        
    Returns:
        Room ID
    """
    archetype = character.get("Archetype", "")
    
    # Check if archetype has specific room
    if archetype in ARCHETYPE_ROOMS:
        return ARCHETYPE_ROOMS[archetype]
    
    # Check character progress for special conditions
    progress = character.get("Progress", {})
    
    # Example: If completed certain story paths, start in different locations
    if progress.get("completed_mage_trials"):
        return 8  # Mage's Guild
    elif progress.get("joined_thieves_guild"):
        return 10  # Thieves' Den
    elif progress.get("blessed_by_temple"):
        return 6  # Temple
    
    # Default to town square
    return DEFAULT_ROOM


def transition_character(character_id, player_id):
    """
    Transition character from Incremental to MUD.
    
    Args:
        character_id: Character UUID
        player_id: Player ID (must match character owner)
        
    Returns:
        dict: Result with success status and details
    """
    # Get character
    character = get_character(character_id)
    if not character:
        return {"success": False, "error": "Character not found"}
    
    # Verify ownership
    if character.get("PlayerID") != player_id:
        logger.warning("Player does not own character", player_id=player_id, character_id=character_id)
        return {"success": False, "error": "Unauthorized"}
    
    # Check if already transitioned
    if character.get("GameMode") == "MUD":
        return {"success": False, "error": "Character already in MUD"}
    
    # Select starting room
    room_id = select_starting_room(character)
    
    # Update character
    timestamp = datetime.now(timezone.utc).isoformat()
    
    try:
        characters_table.update_item(
            Key={"CharacterID": character_id},
            UpdateExpression="""
                SET GameMode = :mud,
                    RoomID = :room,
                    UpdatedAt = :timestamp,
                    #state = :standing
            """,
            ExpressionAttributeNames={
                "#state": "CharState"  # CharState is reserved word
            },
            ExpressionAttributeValues={
                ":mud": "MUD",
                ":room": room_id,
                ":timestamp": timestamp,
                ":standing": "Standing"
            },
            ConditionExpression="GameMode = :incremental",
            ExpressionAttributeValues={
                ":incremental": "Incremental",
                ":mud": "MUD",
                ":room": room_id,
                ":timestamp": timestamp,
                ":standing": "Standing"
            }
        )
        
        # Update player's character list to reflect MUD mode
        try:
            players_table.update_item(
                Key={"PlayerID": player_id},
                UpdateExpression="SET CharacterList.#name.GameMode = :mud",
                ExpressionAttributeNames={
                    "#name": character.get("CharacterName")
                },
                ExpressionAttributeValues={
                    ":mud": "MUD"
                }
            )
        except ClientError as player_err:
            # Log but don't fail - character is already transitioned
            logger.warning("Failed to update player character list",
                         error=player_err,
                         player_id=player_id,
                         character_name=character.get("CharacterName"))
        
        logger.info("Character transitioned to MUD",
                   character_id=character_id,
                   character_name=character.get("CharacterName"),
                   room_id=room_id)
        
        return {
            "success": True,
            "roomId": room_id,
            "message": "Character successfully transitioned to MUD"
        }
        
    except ClientError as err:
        if err.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return {"success": False, "error": "Character not in Incremental mode"}
        
        logger.error("Error transitioning character", error=err, character_id=character_id)
        return {"success": False, "error": "Failed to transition character"}


def lambda_handler(event, context):
    """
    Lambda handler for character transition API.
    
    Expected request:
    POST /characters/{characterId}/transition
    
    Args:
        event: API Gateway event with Cognito authorizer
        context: Lambda context
        
    Returns:
        API Gateway response
    """
    # Log Lambda invocation
    logger.log_lambda_event(event, context)
    
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
        
        # Extract character ID from path
        path_params = event.get("pathParameters", {})
        character_id = path_params.get("characterId", "")
        
        if not character_id:
            return cors_handler.add_cors_headers(
                {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": "Character ID required"}),
                },
                event,
            )
        
        # Transition the character
        result = transition_character(character_id, player_id)
        
        if result["success"]:
            logger.log_response(200)
            return cors_handler.add_cors_headers(
                {
                    "statusCode": 200,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({
                        "message": result["message"],
                        "roomId": result["roomId"]
                    }),
                },
                event,
            )
        else:
            status_code = 403 if result["error"] == "Unauthorized" else 400
            logger.log_response(status_code)
            return cors_handler.add_cors_headers(
                {
                    "statusCode": status_code,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": result["error"]}),
                },
                event,
            )
    
    except Exception as err:
        logger.error("Unexpected error in lambda_handler", error=err)
        logger.log_response(500)
        return cors_handler.add_cors_headers(
            {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Internal server error"}),
            },
            event,
        )