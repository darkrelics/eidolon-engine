"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson
"""

import time

from eidolon.character import get_character
from eidolon.character import validate_character_ownership
from eidolon.logger import get_logger
from eidolon.player import extract_player_id_from_event
from eidolon.player import validate_player_exists
from eidolon.requests import get_query_parameter_flexible
from eidolon.story import get_active_story_segment_with_player_check
from eidolon.story import get_story_metadata
from eidolon.story import get_story_segment
from eidolon.utilities import build_lambda_response_pascal
from eidolon.utilities import handle_lambda_error_pascal
from eidolon.utilities import handle_preflight_if_options
from eidolon.utilities import log_lambda_invocation
from eidolon.validation import validate_uuid

logger = get_logger(__name__)


def _validate_and_get_character(character_id: str, player_id: str) -> dict:
    """
    Validate character ID and ownership.
    
    Args:
        character_id: Character UUID
        player_id: Authenticated player ID
        
    Returns:
        Character data dict
        
    Raises:
        ValueError: If character ID invalid or not owned by player
        RuntimeError: If database operations fail
    """
    if not validate_uuid(character_id):
        raise ValueError("Invalid character ID format")
    
    character = get_character(character_id)
    validate_character_ownership(character, player_id)
    return character


def _get_story_data(character_id: str, player_id: str) -> tuple:
    """
    Retrieve active segment and story metadata.
    
    Args:
        character_id: Character UUID
        player_id: Authenticated player ID
        
    Returns:
        Tuple of (active_segment, story_item, current_segment)
        
    Raises:
        ValueError: If no active story found
        RuntimeError: If database operations fail
    """
    active_segment = get_active_story_segment_with_player_check(character_id, player_id)
    story_id = active_segment.get("StoryID")
    segment_id = active_segment.get("SegmentID")
    
    story_item = get_story_metadata(story_id)  # type: ignore
    current_segment = get_story_segment(story_id, segment_id)  # type: ignore
    
    return active_segment, story_item, current_segment


def _calculate_time_remaining(active_segment: dict) -> int:
    """
    Calculate time remaining for the current segment.
    
    Args:
        active_segment: Active segment data
        
    Returns:
        Time remaining in seconds (minimum 0)
    """
    end_time = int(active_segment.get("EndTime", 0))
    current_time = int(time.time())
    return max(0, end_time - current_time)


def _build_base_response(active_segment: dict, story_item: dict, current_segment: dict, time_remaining: int) -> dict:
    """
    Build the base response structure.
    
    Args:
        active_segment: Active segment data
        story_item: Story metadata
        current_segment: Current segment data
        time_remaining: Calculated time remaining
        
    Returns:
        Base response dict with story and segment info
    """
    return {
        "Story": {
            "StoryID": active_segment.get("StoryID"),
            "Title": story_item.get("Title", ""),
            "Type": story_item.get("StoryType", ""),
            "TotalSegments": story_item.get("TotalSegments", 1),
            "CurrentSegmentIndex": current_segment.get("SegmentIndex", 0),
        },
        "Segment": {
            "SegmentID": active_segment.get("SegmentID"),
            "SegmentType": current_segment.get("SegmentType", ""),
            "ShortStatus": current_segment.get("ShortStatus", ""),
            "Narrative": "",  # Will be set by segment type handlers
            "Duration": current_segment.get("SegmentDuration", 0),
            "TimeRemaining": time_remaining,
            "StartTime": active_segment.get("StartTime", 0),
            "EndTime": int(active_segment.get("EndTime", 0)),
        },
        "ActiveSegmentID": active_segment.get("ActiveSegmentID", ""),
        "Status": active_segment.get("Status", ""),
    }


def _add_decision_segment_data(response_data: dict, current_segment: dict, active_segment: dict) -> None:
    """
    Add decision-specific data to response.
    
    Args:
        response_data: Response dict to modify
        current_segment: Current segment data
        active_segment: Active segment data
    """
    response_data["Segment"]["DecisionText"] = current_segment.get("DecisionText", "")
    
    # Format options from DecisionOptions map
    decision_options = current_segment.get("DecisionOptions", {})
    options = []
    for option_id, _ in decision_options.items():
        options.append({"Id": option_id, "Text": option_id.replace("-", " ").title()})
    
    response_data["Segment"]["Options"] = options
    response_data["Segment"]["Decision"] = active_segment.get("Decision")


def _add_narrative_segment_data(response_data: dict, current_segment: dict, active_segment: dict) -> None:
    """
    Add narrative-specific data to response.
    
    Args:
        response_data: Response dict to modify
        current_segment: Current segment data
        active_segment: Active segment data
    """
    response_data["Segment"]["Narrative"] = current_segment.get("Narrative", "")
    response_data["Segment"]["Challenges"] = current_segment.get("Challenges", [])
    response_data["Segment"]["ChallengeResults"] = active_segment.get("ChallengeResults", [])
    response_data["Segment"]["Outcome"] = active_segment.get("Outcome")


def _add_combat_segment_data(response_data: dict, current_segment: dict, active_segment: dict) -> None:
    """
    Add combat-specific data to response.
    
    Args:
        response_data: Response dict to modify
        current_segment: Current segment data
        active_segment: Active segment data
    """
    response_data["Segment"]["Narrative"] = current_segment.get("Narrative", "")
    response_data["Segment"]["Combat"] = current_segment.get("Combat", {})
    response_data["Segment"]["CombatState"] = active_segment.get("CombatState", {})


# Dispatch table for segment type handlers
SEGMENT_TYPE_HANDLERS = {
    "decision": _add_decision_segment_data,
    "narrative": _add_narrative_segment_data,
    "combat": _add_combat_segment_data,
}


def get_current_story_business_logic(character_id: str, player_id: str) -> dict:
    """
    Business logic for getting current active story and segment.

    Args:
        character_id: Character UUID
        player_id: Authenticated player ID

    Returns:
        Response data dict with story and segment information

    Raises:
        ValueError: If character not found, not owned, or no active story
        RuntimeError: If database operations fail
    """
    # Validate character and ownership
    _validate_and_get_character(character_id, player_id)
    
    # Get story data
    active_segment, story_item, current_segment = _get_story_data(character_id, player_id)
    
    # Calculate time remaining
    time_remaining = _calculate_time_remaining(active_segment)
    
    # Build base response
    response_data = _build_base_response(active_segment, story_item, current_segment, time_remaining)
    
    # Add segment type specific data
    segment_type = current_segment.get("SegmentType", "")
    handler = SEGMENT_TYPE_HANDLERS.get(segment_type)
    if handler:
        handler(response_data, current_segment, active_segment)
    
    # Log success
    logger.info(
        "Current story retrieved successfully",
        extra={
            "character_id": character_id,
            "story_id": active_segment.get("StoryID"),
            "segment_type": segment_type,
            "segment_id": active_segment.get("SegmentID"),
        },
    )
    
    return response_data


def lambda_handler(event: dict, context: object) -> dict:
    """Get current active story and segment for a character.

    Lambda function to get the current active story segment for a character.
    This function retrieves the current active segment if a character is in a story,
    along with relevant story metadata and segment details.

    Query Parameters:
        characterId: Character ID to check

    Returns:
        200: Current story and segment data
        404: No active story or character not found
        400: Missing parameters or invalid request
        401: Unauthorized
        500: Internal error
    """
    # Log invocation
    log_lambda_invocation(context, event)

    # Handle preflight
    preflight_response = handle_preflight_if_options(event)
    if preflight_response:
        return preflight_response

    try:
        # Extract player ID from JWT
        player_id = extract_player_id_from_event(event)
    except ValueError as err:
        logger.error("Authentication failed", extra={"error": str(err)})
        return build_lambda_response_pascal(401, {"error": "Unauthorized"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)

    # Validate player exists
    try:
        if not validate_player_exists(player_id):
            logger.error("Player not found in database", extra={"player_id": player_id})
            return build_lambda_response_pascal(401, {"error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error("Failed to validate player", extra={"error": str(err)})
        return build_lambda_response_pascal(500, {"error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)

    # Get character ID from query parameters (flexible: CharacterID or characterId)
    character_id = get_query_parameter_flexible(event, "CharacterID", "characterId")
    if not character_id:
        return build_lambda_response_pascal(400, {"error": "Missing CharacterID parameter"}, event)

    # Call business logic
    try:
        response_data = get_current_story_business_logic(character_id, player_id)  # type: ignore
        return build_lambda_response_pascal(200, response_data, event)
    except ValueError as err:
        logger.warning(
            "Invalid request or not found",
            extra={"character_id": character_id, "error": str(err)},
        )
        if "no active story" in str(err).lower():
            return build_lambda_response_pascal(
                404,
                {"error": "No active story found"},
                event,
            )
        elif "not found" in str(err).lower():
            return build_lambda_response_pascal(
                404,
                {"error": "Character not found"},
                event,
            )
        return build_lambda_response_pascal(
            400,
            {"error": str(err)},
            event,
        )
    except RuntimeError as err:
        logger.error(
            "Failed to get current story",
            extra={"character_id": character_id, "error": str(err)},
        )
        return build_lambda_response_pascal(
            500,
            {"error": "Internal server error"},
            event,
        )
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)
