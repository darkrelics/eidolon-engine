"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to start a story for a character.
Validates character state, creates active segment, and returns first segment details.
"""

import time
import uuid
from datetime import datetime
from datetime import timezone

from botocore.exceptions import ClientError

from eidolon.character import get_character
from eidolon.character import validate_character_ownership
from eidolon.dynamo import dynamo
from eidolon.dynamo import TableName
from eidolon.logger import get_logger
from eidolon.requests import get_required_field
from eidolon.requests import parse_json_body
from eidolon.utilities import build_lambda_response
from eidolon.player import extract_player_id_from_event
from eidolon.player import validate_player_exists
from eidolon.utilities import handle_lambda_error
from eidolon.utilities import handle_preflight_if_options
from eidolon.utilities import log_lambda_invocation
from eidolon.validation import validate_uuid

# Configure logging
logger = get_logger(__name__)


def validate_story_available(character: dict, story_id: str) -> None:
    """
    Validate that the story is available to the character.

    Args:
        character: Character data
        story_id: Story UUID to start

    Raises:
        ValueError: If story not available to character
    """
    available_stories = character.get("AvailableStories", [])
    if story_id not in available_stories:
        raise ValueError("Story not available")


def get_story_and_first_segment(story_id: str) -> tuple:
    """
    Get story metadata and first segment details.

    Args:
        story_id: Story UUID

    Returns:
        Tuple of (story_data, first_segment)

    Raises:
        ValueError: If story or first segment not found
        RuntimeError: If database operations fail
    """
    try:
        # Get story metadata
        story = dynamo.get_item(TableName.STORY, {"StoryID": story_id})

        if not story:
            logger.warning("Story not found", extra={"story_id": story_id})
            raise ValueError("Story not found")

        # Get first segment
        first_segment_id = story.get("FirstSegmentID")
        if not first_segment_id:
            logger.error("Story has no first segment", extra={"story_id": story_id})
            raise ValueError("Story configuration error")

        segment = dynamo.get_item(TableName.SEGMENTS, {"StoryID": story_id, "SegmentID": first_segment_id})

        if not segment:
            logger.error(
                "First segment not found",
                extra={"story_id": story_id, "segment_id": first_segment_id},
            )
            raise ValueError("Story configuration error")

        return story, segment
    except ClientError as err:
        logger.error(
            "Failed to get story data",
            extra={"story_id": story_id, "error": str(err), "error_code": err.response.get("Error", {}).get("Code", "Unknown")},
            exc_info=True,
        )
        raise RuntimeError(f"Failed to get story data: {str(err)}")


def create_active_segment(character_id: str, player_id: str, story_id: str, story_title: str, segment: dict) -> dict:
    """
    Create an active segment record for tracking progress.

    Args:
        character_id: Character UUID
        player_id: Player UUID
        story_id: Story UUID
        story_title: Story title
        segment: Segment data from Segments table

    Returns:
        Active segment record

    Raises:
        RuntimeError: If database operation fails
    """
    segment_id = segment.get("SegmentID")
    segment_type = segment.get("SegmentType", "narrative")
    duration = int(segment.get("SegmentDuration", 300))  # Default 5 minutes

    current_time = int(time.time())
    end_time = current_time + duration

    # Generate unique ID for this active segment
    active_segment_id = str(uuid.uuid4())

    active_segment: dict = {
        "ActiveSegmentID": active_segment_id,
        "CharacterID": character_id,
        "PlayerID": player_id,
        "StoryID": story_id,
        "SegmentID": segment_id,
        "SegmentType": segment_type,
        "StoryTitle": story_title,
        "Status": "active",
        "StartTime": current_time,
        "EndTime": end_time,
    }

    # Add type-specific fields based on segment type
    if segment_type == "decision":
        active_segment["Decision"] = None
        active_segment["DecisionOptions"] = segment.get("DecisionOptions", {})
    elif segment_type == "narrative":
        active_segment["ChallengeResults"] = []
        active_segment["Outcome"] = None
    elif segment_type == "combat":
        combat_config = segment.get("Combat", {})
        active_segment["CombatState"] = {
            "round": 0,
            "playerWounds": [],
            "opponentHealth": None,
            "opponentId": combat_config.get("opponentId"),
        }

    # Store in DynamoDB
    try:
        dynamo.put_item(TableName.ACTIVE_SEGMENTS, active_segment)
    except ClientError as err:
        logger.error(
            "Failed to create active segment",
            extra={
                "active_segment_id": active_segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to create active segment: {str(err)}")

    return active_segment


def format_segment_response(segment: dict, active_segment: dict) -> dict:
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

    # Add type-specific fields based on documented schema
    if segment_type == "decision":
        # DecisionText contains the choice presented
        response["content"] = segment.get("DecisionText", "")
        # Format options from DecisionOptions map
        decision_options = segment.get("DecisionOptions", {})
        options = []
        for option_id, _ in decision_options.items():
            options.append({"id": option_id, "text": option_id.replace("-", " ").title()})  # Format option ID as display text
        response["options"] = options
    elif segment_type == "narrative":
        response["shortStatus"] = segment.get("ShortStatus", "Progressing through the story...")
        response["narrative"] = ""
    elif segment_type == "combat":
        response["shortStatus"] = segment.get("ShortStatus", "Engaged in combat!")
        response["opponentId"] = segment.get("Combat", {}).get("opponentId")

    return response


def create_history_entry(character_id: str, story_id: str, story_title: str, story_type: str) -> None:
    """
    Create initial history entry for story tracking.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        story_title: Story title
        story_type: Type of story (one-time, daily, repeatable)

    Raises:
        RuntimeError: If database operation fails
    """
    try:
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
        dynamo.put_item(TableName.HISTORY, history_entry)
    except ClientError as err:
        logger.error(
            "Failed to create history entry",
            extra={
                "character_id": character_id,
                "story_id": story_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to create history entry: {str(err)}")


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to start a story for a character.

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
        logger.error("Authentication failed", extra={"error": str(err)})
        return build_lambda_response(401, {"error": "Unauthorized"}, event)
    except Exception as err:
        return handle_lambda_error(err, context, event)
    
    # Validate player exists
    try:
        if not validate_player_exists(player_id):
            logger.error("Player not found in database", extra={"player_id": player_id})
            return build_lambda_response(401, {"error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error("Failed to validate player", extra={"error": str(err)})
        return build_lambda_response(500, {"error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error(err, context, event)

    # Parse request body
    body, parse_error = parse_json_body(event)
    if parse_error:
        return build_lambda_response(400, {"error": str(parse_error)}, event)

    # Get required fields
    character_id, char_error = get_required_field(body, "characterId")
    if char_error:
        return build_lambda_response(400, {"error": char_error}, event)

    story_id, story_error = get_required_field(body, "storyId")
    if story_error:
        return build_lambda_response(400, {"error": story_error}, event)

    # Validate UUIDs
    if character_id and not validate_uuid(character_id):
        return build_lambda_response(400, {"error": "Invalid character ID format"}, event)

    if story_id and not validate_uuid(story_id):
        return build_lambda_response(400, {"error": "Invalid story ID format"}, event)

    logger.info(
        "Starting story",
        extra={"character_id": character_id, "story_id": story_id},
    )

    # Call business logic
    try:
        response_data = start_story_business_logic(character_id, story_id, player_id)
        return build_lambda_response(200, response_data, event)
    except ValueError as err:
        logger.warning(
            "Invalid request",
            extra={"character_id": character_id, "story_id": story_id, "error": str(err)},
        )
        error_msg = str(err)
        if "not found" in error_msg.lower():
            return build_lambda_response(404, {"error": error_msg}, event)
        elif "already in" in error_msg.lower() and "mode" in error_msg.lower():
            return build_lambda_response(409, {"error": error_msg}, event)
        elif "not available" in error_msg.lower():
            return build_lambda_response(403, {"error": error_msg}, event)
        return build_lambda_response(400, {"error": error_msg}, event)
    except RuntimeError as err:
        logger.error(
            "Failed to start story",
            extra={"character_id": character_id, "story_id": story_id, "error": str(err)},
        )
        return build_lambda_response(500, {"error": "Failed to start story"}, event)
    except Exception as err:
        return handle_lambda_error(err, context, event)


def start_story_business_logic(character_id: str, story_id: str, player_id: str) -> dict:
    """
    Business logic for starting a story.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        player_id: Authenticated player ID

    Returns:
        Response data with segment information

    Raises:
        ValueError: If validation fails
        RuntimeError: If database operations fail
    """
    # Get character and verify ownership
    character = get_character(character_id)
    validate_character_ownership(character, player_id)

    # Check if character is already in a game mode
    game_mode = character.get("GameMode", "None")
    if game_mode != "None":
        logger.warning(
            "Character already in game mode",
            extra={"character_id": character_id, "game_mode": game_mode},
        )
        raise ValueError(f"Character is currently in {game_mode} mode")

    # Validate story is available
    validate_story_available(character, story_id)

    # Get story and first segment
    story, first_segment = get_story_and_first_segment(story_id)

    # Create active segment first to get the segment ID
    story_title = story.get("Title", "Unknown Story")
    active_segment = create_active_segment(character_id, player_id, story_id, story_title, first_segment)

    # Atomically update character to set GameMode, ActiveStoryID, ActiveSegmentID and remove from available list
    try:
        # Build update expression to set GameMode and remove from AvailableStories
        update_expression = (
            "SET GameMode = :mode, ActiveStoryID = :story_id, ActiveSegmentID = :segment_id "
            "REMOVE AvailableStories[" + str(character["AvailableStories"].index(story_id)) + "]"
        )

        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues={
                ":mode": "Incremental",
                ":none": "None",
                ":story_id": story_id,
                ":segment_id": active_segment["ActiveSegmentID"],
            },
            ConditionExpression="GameMode = :none",
        )

    except ClientError as err:
        # Rollback: Delete the active segment we just created
        try:
            dynamo.delete_item(
                TableName.ACTIVE_SEGMENTS,
                Key={"ActiveSegmentID": active_segment["ActiveSegmentID"]},
            )
        except Exception as rollback_err:
            logger.error(
                "Failed to rollback active segment",
                extra={
                    "active_segment_id": active_segment["ActiveSegmentID"],
                    "error": str(rollback_err),
                },
            )

        if err.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logger.warning(
                "Character state changed during story start",
                extra={"character_id": character_id},
            )
            raise ValueError("Character state conflict")
        logger.error(
            "Failed to update character state",
            extra={
                "character_id": character_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to update character state: {str(err)}")
    except Exception as err:
        # Rollback: Delete the active segment we just created
        try:
            dynamo.delete_item(
                TableName.ACTIVE_SEGMENTS,
                Key={"ActiveSegmentID": active_segment["ActiveSegmentID"]},
            )
        except Exception as rollback_err:
            logger.error(
                "Failed to rollback active segment",
                extra={
                    "active_segment_id": active_segment["ActiveSegmentID"],
                    "error": str(rollback_err),
                },
            )

        logger.error(
            "Failed to update character state",
            extra={"character_id": character_id, "error": str(err)},
        )
        raise RuntimeError(f"Failed to update character state: {str(err)}")

    # Create history entry
    story_type = story.get("StoryType", "repeatable")
    create_history_entry(character_id, story_id, story_title, story_type)

    # Format response
    segment_data = format_segment_response(first_segment, active_segment)

    logger.info(
        "Story started successfully",
        extra={
            "character_id": character_id,
            "story_id": story_id,
            "active_segment_id": active_segment["ActiveSegmentID"],
            "segment_type": first_segment.get("SegmentType"),
        },
    )

    return {"segment": segment_data}
