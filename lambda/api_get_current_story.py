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
    # Validate character ID format
    if not validate_uuid(character_id):
        raise ValueError("Invalid character ID format")

    # Verify character ownership
    character = get_character(character_id)
    validate_character_ownership(character, player_id)

    # Get active segment for character with player check
    active_segment = get_active_story_segment_with_player_check(character_id, player_id)
    story_id = active_segment.get("StoryID")
    segment_id = active_segment.get("SegmentID")

    # Get story metadata
    story_item = get_story_metadata(story_id)  # type: ignore

    # Get the current segment from Segments table
    current_segment = get_story_segment(story_id, segment_id)  # type: ignore

    total_segments = story_item.get("TotalSegments", 1)
    current_segment_index = current_segment.get("SegmentIndex", 0)

    # Calculate time remaining
    end_time = int(active_segment.get("EndTime", 0))
    current_time = int(time.time())
    time_remaining = max(0, end_time - current_time)

    # Build response with PascalCase
    response_data = {
        "Story": {
            "StoryId": story_id,
            "Title": story_item.get("Title", ""),
            "Type": story_item.get("StoryType", ""),
            "TotalSegments": total_segments,
            "CurrentSegmentIndex": current_segment_index,
        },
        "Segment": {
            "SegmentId": segment_id,
            "SegmentType": current_segment.get("SegmentType", ""),
            "ShortStatus": current_segment.get("ShortStatus", ""),
            "Narrative": (current_segment.get("Narrative", "") if current_segment.get("SegmentType") != "decision" else ""),
            "Duration": current_segment.get("SegmentDuration", 0),
            "TimeRemaining": time_remaining,
            "StartTime": active_segment.get("StartTime", 0),
            "EndTime": end_time,
        },
        "ActiveSegmentId": active_segment.get("ActiveSegmentID", ""),
        "Status": active_segment.get("Status", ""),
    }

    # Add decision options if this is a decision segment
    if current_segment.get("SegmentType") == "decision":
        response_data["Segment"]["DecisionText"] = current_segment.get("DecisionText", "")
        # Format options from DecisionOptions map
        decision_options = current_segment.get("DecisionOptions", {})
        options = []
        for option_id, _ in decision_options.items():
            options.append({"Id": option_id, "Text": option_id.replace("-", " ").title()})
        response_data["Segment"]["Options"] = options
        response_data["Segment"]["Decision"] = active_segment.get("Decision")

    # Add challenge info if this is a narrative segment
    if current_segment.get("SegmentType") == "narrative":
        response_data["Segment"]["Challenges"] = current_segment.get("Challenges", [])
        response_data["Segment"]["ChallengeResults"] = active_segment.get("ChallengeResults", [])
        response_data["Segment"]["Outcome"] = active_segment.get("Outcome")

    # Add combat info if this is a combat segment
    if current_segment.get("SegmentType") == "combat":
        response_data["Segment"]["Combat"] = current_segment.get("Combat", {})
        response_data["Segment"]["CombatState"] = active_segment.get("CombatState", {})

    logger.info(
        "Current story retrieved successfully",
        extra={
            "character_id": character_id,
            "story_id": story_id,
            "segment_type": current_segment.get("SegmentType"),
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

    # Get character ID from query parameters (flexible: CharacterId or characterId)
    character_id = get_query_parameter_flexible(event, "CharacterId", "characterId")
    if not character_id:
        return build_lambda_response_pascal(400, {"error": "Missing CharacterId parameter"}, event)

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
