"""
Lambda function for character rest endpoint.

Allows characters to initiate a rest segment to heal wounds when not in combat.
"""

import json
import os
import time
from decimal import Decimal

import boto3
from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError

from eidolon.logger import logger
from eidolon.responses import (
    create_response,
    not_found_response,
)
from eidolon.utilities import log_lambda_invocation
from eidolon.uuid_utils import generate_uuid_v7

# Initialize clients
dynamodb = boto3.client("dynamodb")
deserializer = TypeDeserializer()

# Environment variables
CHARACTERS_TABLE = os.environ["CHARACTERS_TABLE"]
ACTIVE_SEGMENTS_TABLE = os.environ["ACTIVE_SEGMENTS_TABLE"]
SEGMENTS_TABLE = os.environ["SEGMENTS_TABLE"]
STORY_TABLE = os.environ["STORY_TABLE"]
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")

# Rest segment configuration
REST_SEGMENT_DURATION = 900  # 15 minutes (time to heal a bashing wound)
REST_SEGMENT_ID = "rest-segment-001"  # Standard rest segment


def lambda_handler(event, context):
    """
    Handle character rest request.
    
    Creates a rest segment for the character to heal wounds.
    
    Args:
        event: API Gateway event
        context: Lambda context
        
    Returns:
        API Gateway response
    """
    log_lambda_invocation(event, context)
    
    # Handle CORS preflight
    if event.get("httpMethod") == "OPTIONS":
        return create_response(200, {})
    
    try:
        # Extract player ID from authorizer
        player_id = event["requestContext"]["authorizer"]["claims"]["sub"]
        
        # Parse request body
        body = json.loads(event.get("body", "{}"))
        character_id = body.get("CharacterID")
        
        if not character_id:
            logger.warning("Missing CharacterID in request")
            return create_response(400, {"error": "CharacterID is required"})
        
        # Validate character ownership and state
        character = validate_character_for_rest(character_id, player_id)
        if isinstance(character, dict) and "statusCode" in character:
            return character
        
        # Rest is always available, regardless of wounds
        wounds = character.get("Wounds", [])
        
        # Create rest segment
        result = create_rest_segment(character)
        
        logger.info(
            "Rest initiated successfully",
            extra={
                "character_id": character_id,
                "segment_id": result["segment"]["activeSegmentId"],
                "wound_count": len(wounds)
            }
        )
        
        return create_response(200, result)
        
    except ClientError as err:
        error_code = err.response["Error"]["Code"]
        if error_code == "ResourceNotFoundException":
            return not_found_response("Resource")
        logger.error("DynamoDB error", exc_info=True)
        return create_response(500, {"error": "Internal server error"})
    except Exception as err:
        logger.error("Unexpected error", exc_info=True)
        return create_response(500, {"error": "Internal server error"})


def validate_character_for_rest(character_id, player_id):
    """
    Validate character ownership and state for rest.
    
    Args:
        character_id: Character ID
        player_id: Player ID from auth token
        
    Returns:
        Character data or error response
    """
    # Get character
    try:
        response = dynamodb.get_item(
            TableName=CHARACTERS_TABLE,
            Key={"CharacterID": {"S": character_id}}
        )
    except ClientError as err:
        logger.error(f"Failed to get character: {err}")
        raise
    
    if "Item" not in response:
        return not_found_response("Character")
    
    character = {k: deserializer.deserialize(v) for k, v in response["Item"].items()}
    
    # Verify ownership
    if character.get("PlayerID") != player_id:
        logger.warning(
            "Character ownership mismatch",
            extra={
                "character_id": character_id,
                "expected_player": player_id,
                "actual_player": character.get("PlayerID")
            }
        )
        return create_response(403, {"error": "Character not owned by player"})
    
    # Check game mode
    game_mode = character.get("GameMode", "None")
    if game_mode != "Incremental":
        logger.warning(
            "Character not in Incremental mode",
            extra={"character_id": character_id, "game_mode": game_mode}
        )
        return create_response(
            409, 
            {"error": f"Character is in {game_mode} mode, must be in Incremental mode"}
        )
    
    # Check if character has active story
    if not character.get("ActiveStoryID"):
        logger.warning(
            "Character has no active story",
            extra={"character_id": character_id}
        )
        return create_response(400, {"error": "No active story"})
    
    # Check for existing active segment
    if character.get("ActiveSegmentID"):
        # Verify segment doesn't exist or is completed
        try:
            segment_response = dynamodb.get_item(
                TableName=ACTIVE_SEGMENTS_TABLE,
                Key={"ActiveSegmentID": {"S": character["ActiveSegmentID"]}}
            )
            if "Item" in segment_response:
                logger.warning(
                    "Character already has active segment",
                    extra={
                        "character_id": character_id,
                        "segment_id": character["ActiveSegmentID"]
                    }
                )
                return create_response(409, {"error": "Character already has an active segment"})
        except ClientError:
            # Segment doesn't exist, which is fine
            pass
    
    return character


def create_rest_segment(character):
    """
    Create a rest segment for the character.
    
    Args:
        character: Character data
        
    Returns:
        Dict with segment creation result
    """
    character_id = character["CharacterID"]
    player_id = character["PlayerID"]
    story_id = character["ActiveStoryID"]
    
    # Get story title
    try:
        story_response = dynamodb.get_item(
            TableName=STORY_TABLE,
            Key={"StoryID": {"S": story_id}}
        )
        story_title = "Unknown Story"
        if "Item" in story_response:
            story_item = {k: deserializer.deserialize(v) for k, v in story_response["Item"].items()}
            story_title = story_item.get("Title", "Unknown Story")
    except ClientError:
        story_title = "Unknown Story"
    
    # Generate segment data with UUIDv7 for time-based sorting
    active_segment_id = str(generate_uuid_v7())
    current_time = int(time.time())
    end_time = current_time + REST_SEGMENT_DURATION
    
    # Create active segment record
    segment_data = {
        "ActiveSegmentID": {"S": active_segment_id},
        "CharacterID": {"S": character_id},
        "PlayerID": {"S": player_id},
        "StoryID": {"S": story_id},
        "StoryTitle": {"S": story_title},
        "SegmentID": {"S": REST_SEGMENT_ID},
        "SegmentType": {"S": "rest"},
        "DefaultStatus": {"S": "Resting to heal wounds"},
        "StartTime": {"N": str(current_time)},
        "EndTime": {"N": str(end_time)},
        "ProcessingStatus": {"S": "pending"},
        "CreatedAt": {"N": str(current_time)}
    }
    
    # Use transaction to update both character and create segment atomically
    try:
        dynamodb.transact_write_items(
            TransactItems=[
                {
                    "Update": {
                        "TableName": CHARACTERS_TABLE,
                        "Key": {"CharacterID": {"S": character_id}},
                        "UpdateExpression": "SET ActiveSegmentID = :segment_id",
                        "ExpressionAttributeValues": {
                            ":segment_id": {"S": active_segment_id}
                        }
                    }
                },
                {
                    "Put": {
                        "TableName": ACTIVE_SEGMENTS_TABLE,
                        "Item": segment_data,
                        "ConditionExpression": "attribute_not_exists(ActiveSegmentID)"
                    }
                }
            ]
        )
    except ClientError as err:
        logger.error(f"Failed to create rest segment: {err}")
        raise
    
    # Return segment info for client
    return {
        "success": True,
        "segment": {
            "activeSegmentId": active_segment_id,
            "segmentType": "rest",
            "startTime": current_time,
            "endTime": end_time,
            "shortStatus": "Resting to heal wounds",
            "duration": REST_SEGMENT_DURATION
        }
    }