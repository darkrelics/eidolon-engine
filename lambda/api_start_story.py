"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason Robinson

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.


Lambda function to start a story for a character.
Validates character state, creates active segment, and returns first segment details.
"""

import os
import uuid
import time
from datetime import datetime, timezone
from eidolon.cors import cors_handler
from eidolon.dynamo import (
    get_item,
    get_table,
    put_item,
    update_item_with_condition,
)
from botocore.exceptions import ClientError
from eidolon.logger import get_logger
from eidolon.requests import extract_player_id, parse_json_body, get_required_field
from eidolon.responses import create_response, error_response, not_found_response
from eidolon.validation_utils import validate_uuid

# Configure logging
logger = get_logger(__name__)

# Get table names from environment
CHARACTERS_TABLE = os.environ.get("CHARACTERS_TABLE", "characters")
STORY_TABLE = os.environ.get("STORY_TABLE", "story")
SEGMENTS_TABLE = os.environ.get("SEGMENTS_TABLE", "segments")
ACTIVE_SEGMENTS_TABLE = os.environ.get("ACTIVE_SEGMENTS_TABLE", "active_segments")
HISTORY_TABLE = os.environ.get("HISTORY_TABLE", "history")


def get_character_and_verify_ownership(character_id, player_id):
    """
    Get character by UUID and verify ownership.

    Args:
        character_id: Character UUID
        player_id: Cognito user ID for ownership verification

    Returns:
        Character data or None if not found or not owned by player
    """
    characters_table = get_table(CHARACTERS_TABLE)
    character = get_item(characters_table, {"CharacterID": character_id})

    if not character:
        logger.warning("Character not found", extra={"character_id": character_id})
        return None

    # Verify ownership
    if character.get("PlayerID") != player_id:
        logger.warning(
            "Character ownership mismatch",
            extra={"character_id": character_id, "player_id": player_id},
        )
        return None

    return character


def validate_story_available(character, story_id):
    """
    Validate that the story is available to the character.

    Args:
        character: Character data
        story_id: Story UUID to start

    Returns:
        True if available, False otherwise
    """
    available_stories = character.get("AvailableStories", [])
    return story_id in available_stories


def get_story_and_first_segment(story_id):
    """
    Get story metadata and first segment details.

    Args:
        story_id: Story UUID

    Returns:
        Tuple of (story_data, first_segment) or (None, None) if not found
    """
    # Get story metadata
    story_table = get_table(STORY_TABLE)
    story = get_item(story_table, {"StoryID": story_id})
    
    if not story:
        logger.warning("Story not found", extra={"story_id": story_id})
        return None, None

    # Get first segment
    first_segment_id = story.get("FirstSegmentID")
    if not first_segment_id:
        logger.error("Story has no first segment", extra={"story_id": story_id})
        return None, None

    segments_table = get_table(SEGMENTS_TABLE)
    segment = get_item(segments_table, {"StoryID": story_id, "SegmentID": first_segment_id})
    
    if not segment:
        logger.error(
            "First segment not found",
            extra={"story_id": story_id, "segment_id": first_segment_id},
        )
        return None, None

    return story, segment


def create_active_segment(character_id, player_id, story_id, segment, story_title):
    """
    Create an active segment record for tracking progress.

    Args:
        character_id: Character UUID
        player_id: Player UUID
        story_id: Story UUID
        segment: Segment data
        story_title: Story title for display

    Returns:
        Active segment record
    """
    segment_id = segment.get("SegmentID")
    segment_type = segment.get("SegmentType", "narrative")
    duration = int(segment.get("SegmentDuration", 300))  # Default 5 minutes
    
    current_time = int(time.time())
    end_time = current_time + duration
    
    # Generate unique ID for this active segment
    active_segment_id = str(uuid.uuid4())
    
    # Create TTL for auto-cleanup (24 hours after end time)
    ttl = end_time + 86400
    
    active_segment = {
        "ActiveSegmentID": active_segment_id,
        "CharacterID": character_id,
        "PlayerID": player_id,
        "StoryID": story_id,
        "StoryTitle": story_title,
        "SegmentID": segment_id,
        "SegmentType": segment_type,
        "StartTime": current_time,
        "EndTime": end_time,
        "Status": "active",
        "TTL": ttl,
    }
    
    # Add type-specific fields
    if segment_type == "decision":
        active_segment["Decision"] = None  # Will be set when player decides
        active_segment["Options"] = segment.get("Options", [])
    elif segment_type == "combat":
        combat_config = segment.get("Combat", {})
        active_segment["CombatState"] = {
            "round": 0,
            "playerWounds": [],
            "opponentHealth": None,  # Will be set when combat starts
        }
    
    # Store in DynamoDB
    active_segments_table = get_table(ACTIVE_SEGMENTS_TABLE)
    put_item(active_segments_table, active_segment)
    
    return active_segment


def format_segment_response(segment, active_segment):
    """
    Format segment data for API response.

    Args:
        segment: Original segment from Segments table
        active_segment: Active segment record

    Returns:
        Formatted response data
    """
    segment_type = segment.get("SegmentType", "narrative")
    time_remaining = max(0, active_segment["EndTime"] - int(time.time()))
    
    response = {
        "segmentId": active_segment["ActiveSegmentID"],
        "storyId": active_segment["StoryID"],
        "type": segment_type,
        "timeRemaining": time_remaining,
    }
    
    # Add type-specific fields
    if segment_type == "decision":
        response["content"] = segment.get("Narrative", "")
        response["options"] = segment.get("Options", [])
    elif segment_type == "narrative":
        response["shortStatus"] = segment.get("ShortStatus", "Progressing through the story...")
        response["narrative"] = segment.get("Narrative", "")
    elif segment_type == "combat":
        response["shortStatus"] = segment.get("ShortStatus", "Engaged in combat!")
        response["opponentId"] = segment.get("Combat", {}).get("opponentId")
    
    return response


def create_history_entry(character_id, story_id, story_title, story_type):
    """
    Create initial history entry for story tracking.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        story_title: Story title
        story_type: Type of story (one-time, daily, repeatable)
    """
    history_table = get_table(HISTORY_TABLE)
    
    history_entry = {
        "CharacterID": character_id,
        "StoryID": story_id,
        "StoryTitle": story_title,
        "StartedAt": datetime.now(timezone.utc).isoformat(),
        "StoryType": story_type,
        "SegmentHistory": [],
        "AbandonedCount": 0,
    }
    
    # Put item (will overwrite if exists - handles retries)
    put_item(history_table, history_entry)


def lambda_handler(event, context):
    """
    Lambda handler to start a story for a character.

    Args:
        event: API Gateway Lambda proxy event
        context: Lambda context

    Returns:
        API Gateway Lambda proxy response
    """
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
        # Extract player ID from authorizer
        player_id, auth_error = extract_player_id(event)
        if auth_error:
            logger.error("Authentication failed", extra={"error": auth_error})
            return cors_handler.add_cors_headers(error_response(auth_error, status_code=401), event)

        logger.info("Player authenticated", extra={"player_id": player_id})

        # Parse request body
        body, parse_error = parse_json_body(event)
        if parse_error:
            return cors_handler.add_cors_headers(parse_error, event)

        # Get required fields
        character_id, char_error = get_required_field(body, "characterId")
        if char_error:
            return cors_handler.add_cors_headers(
                error_response(char_error, status_code=400), event
            )

        story_id, story_error = get_required_field(body, "storyId")
        if story_error:
            return cors_handler.add_cors_headers(
                error_response(story_error, status_code=400), event
            )

        # Validate UUIDs
        if character_id and not validate_uuid(character_id):
            return cors_handler.add_cors_headers(
                error_response("Invalid character ID format", status_code=400), event
            )

        if story_id and not validate_uuid(story_id):
            return cors_handler.add_cors_headers(
                error_response("Invalid story ID format", status_code=400), event
            )

        logger.info(
            "Starting story",
            extra={"character_id": character_id, "story_id": story_id},
        )

        # Get character and verify ownership
        character = get_character_and_verify_ownership(character_id, player_id)
        if not character:
            return cors_handler.add_cors_headers(not_found_response("Character"), event)

        # Check if character is already in a game mode
        game_mode = character.get("GameMode", "None")
        if game_mode != "None":
            logger.warning(
                "Character already in game mode",
                extra={"character_id": character_id, "game_mode": game_mode},
            )
            return cors_handler.add_cors_headers(
                error_response(f"Character is currently in {game_mode} mode", status_code=409),
                event,
            )

        # Validate story is available
        if not validate_story_available(character, story_id):
            logger.warning(
                "Story not available to character",
                extra={"character_id": character_id, "story_id": story_id},
            )
            return cors_handler.add_cors_headers(
                error_response("Story not available", status_code=403), event
            )

        # Get story and first segment
        story, first_segment = get_story_and_first_segment(story_id)
        if not story or not first_segment:
            return cors_handler.add_cors_headers(
                error_response("Story configuration error", status_code=500), event
            )

        # Atomically update character to set GameMode and remove story from available list
        try:
            characters_table = get_table(CHARACTERS_TABLE)
            
            # Build update expression to set GameMode and remove from AvailableStories
            update_expression = "SET GameMode = :mode REMOVE AvailableStories[" + str(
                character["AvailableStories"].index(story_id)
            ) + "]"
            
            update_item_with_condition(
                characters_table,
                {"CharacterID": character_id},
                update_expression,
                {":mode": "Incremental", ":none": "None"},
                "GameMode = :none",
            )
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                logger.warning(
                    "Character state changed during story start",
                    extra={"character_id": character_id},
                )
                return cors_handler.add_cors_headers(
                    error_response("Character state conflict", status_code=409), event
                )
            else:
                raise
        except Exception as err:
            logger.error(
                "Failed to update character state",
                extra={"character_id": character_id, "error": str(err)},
            )
            return cors_handler.add_cors_headers(
                error_response("Failed to start story", status_code=500), event
            )

        # Create active segment
        story_title = story.get("Title", "Unknown Story")
        active_segment = create_active_segment(
            character_id, player_id, story_id, first_segment, story_title
        )

        # Create history entry
        story_type = story.get("StoryType", "repeatable")
        create_history_entry(character_id, story_id, story_title, story_type)

        # Format response
        segment_data = format_segment_response(first_segment, active_segment)
        
        logger.info(
            "Story started successfully",
            extra={
                "status_code": 200,
                "character_id": character_id,
                "story_id": story_id,
                "active_segment_id": active_segment["ActiveSegmentID"],
                "segment_type": first_segment.get("SegmentType"),
            },
        )

        return cors_handler.add_cors_headers(
            create_response(200, {"segment": segment_data}), event
        )

    except Exception as err:
        logger.error("Unexpected error in lambda_handler", extra={"error": str(err)}, exc_info=True)
        logger.info("Lambda response", extra={"status_code": 500})
        return cors_handler.add_cors_headers(
            error_response("Internal server error", status_code=500), event
        )