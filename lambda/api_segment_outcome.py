"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to get the outcome of a completed or processed segment.
Returns the narrative text and any rewards/effects for the outcome.
"""

from eidolon.cognito import extract_player_id
from eidolon.cors import cors_handler
from eidolon.dynamo import TableName, dynamo
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import validate_player, verify_character_ownership
from eidolon.requests import get_query_parameter_flexible
from eidolon.responses import lambda_error, lambda_response
from eidolon.schema import normalize_segment_definition
from eidolon.segment_core import validate_segment_outcome_results
from eidolon.story import get_completed_segment_for_character, get_story_segment


def get_last_segment_history_record(character_id: str, segment_id: str, player_id: str) -> dict | None:
    """
    Fetch the latest segment_history record for a character and segment.

    Args:
        character_id: Character UUID
        segment_id: Segment UUID
        player_id: Player ID for verification

    Returns:
        The most recent matching history record or None if not found
    """
    try:
        items = dynamo.query(
            TableName.SEGMENT_HISTORY,
            KeyConditionExpression="CharacterID = :cid",
            ExpressionAttributeValues={":cid": character_id},
        )
    except Exception as err:
        logger.error(f"Failed to query segment history for {character_id} Error: {err}", exc_info=True)
        return None

    if not items:
        return None

    # Filter to this segment and player, then pick the latest by CompletedAt (fallback EndTime)
    candidates = [it for it in items if it.get("SegmentID") == segment_id and it.get("PlayerID") == player_id]
    if not candidates:
        return None

    def sort_key(it: dict):
        completed = it.get("CompletedAt") or ""
        end_time = it.get("EndTime") or 0
        # Prioritize presence of CompletedAt, then lexicographic timestamp, else EndTime numeric
        return (1, completed) if completed else (0, end_time)

    return max(candidates, key=sort_key)


def get_segment_outcome_business_logic(character_id: str, segment_id: str, player_id: str) -> dict:
    """
    Business logic for getting the outcome of a completed or processed segment.

    Args:
        character_id: Character UUID
        segment_id: Segment UUID
        player_id: Authenticated player ID

    Returns:
        Outcome data dict with narrative and effects

    Raises:
        ValueError: If character not found, segment not found, or segment not completed
        RuntimeError: If database operations fail
    """

    # Verify character ownership using player record
    if not verify_character_ownership(character_id, player_id):
        raise ValueError("Character not owned by player")

    # Get the segment; accepts either completed or processed (pre-completion outcomes allowed)
    try:
        active_segment = get_completed_segment_for_character(character_id, player_id, segment_id)
    except ValueError as err:
        # If the active record no longer exists, fall back to the latest segment_history record
        if "not found" in str(err).lower():
            history = get_last_segment_history_record(character_id, segment_id, player_id)
            if not history:
                raise
            # Use history record as the source for outcome fields
            active_segment = history
        else:
            raise
    active_segment_id = active_segment.get("ActiveSegmentID")
    segment_type = active_segment.get("SegmentType")
    story_id = active_segment.get("StoryID")

    # Get segment definition from Segments table
    segment = get_story_segment(story_id, segment_id)  # type: ignore
    # Normalize defensively
    segment = normalize_segment_definition(segment)

    # Build outcome data based on segment type
    outcome_data = {
        "SegmentType": segment_type,
        # Reflect actual status (may be "active" when ProcessingStatus="processed")
        "Status": active_segment.get("Status", "completed"),
    }

    if segment_type == "decision":
        # For decision segments, return the decision made
        decision = active_segment.get("Decision")
        decision_options = segment.get("DecisionOptions", {})

        outcome_data["Decision"] = decision
        outcome_data["NextSegmentID"] = decision_options.get(decision) if decision else None
        # Decision segments don't have narrative/effects in the response
        outcome_data["Outcome"] = "normal"
        outcome_data["Narrative"] = ""
        outcome_data["Effects"] = {}

    elif segment_type == "mechanical":
        # Get the outcome from the active segment
        outcome = active_segment.get("Outcome", "normal")

        # Validate and extract outcome results
        validated_result = validate_segment_outcome_results(segment, outcome)

        outcome_data["Outcome"] = outcome
        outcome_data["Narrative"] = validated_result["Narrative"]

        # Effects should already be PascalCase keys (Room, Items, Wounds)
        internal_effects = validated_result.get("Effects", {}) or {}
        outcome_data["Effects"] = internal_effects if isinstance(internal_effects, dict) else {}

        # Add challenge results for mechanical segments
        outcome_data["ChallengeResults"] = active_segment.get("ChallengeResults", [])

        # Add combat state if present
        if active_segment.get("CombatState"):
            outcome_data["CombatState"] = active_segment.get("CombatState", {})

        # Get next segment, prioritizing per-outcome NextSegmentID (PascalCase outcomes)
        results = segment.get("Results", {}) or {}
        next_by_outcome = None
        per_outcome_present = False
        if isinstance(results, dict):
            outcome_map = {
                "death": "Death",
                "failure": "Failure",
                "minimal": "Minimal",
                "normal": "Normal",
                "exceptional": "Exceptional",
            }
            outcome_key = outcome_map.get(str(outcome).lower())
            if outcome_key and isinstance(results.get(outcome_key), dict):
                outcome_block = results.get(outcome_key, {})
                if isinstance(outcome_block, dict) and "NextSegmentID" in outcome_block:
                    per_outcome_present = True
                    next_by_outcome = outcome_block.get("NextSegmentID")

        # Use per-outcome value if present (even when None => terminal). Only fall back if absent.
        if per_outcome_present:
            outcome_data["NextSegmentID"] = next_by_outcome
        elif "NextSegmentID" in segment:
            outcome_data["NextSegmentID"] = segment.get("NextSegmentID")

    elif segment_type == "rest":
        # Rest segments have simple completion
        outcome_data["Outcome"] = "normal"
        outcome_data["Narrative"] = "You have rested and recovered."
        outcome_data["Effects"] = {}
        outcome_data["NextSegmentID"] = segment.get("NextSegmentID")

    else:
        # Unknown segment type
        logger.warning(f"Unknown segment type: {segment_type}")
        outcome_data["Outcome"] = "normal"
        outcome_data["Narrative"] = ""
        outcome_data["Effects"] = {}

    logger.info(f"Segment outcome retrieved successfully for {active_segment_id}")

    return outcome_data


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to get the outcome of a completed segment.

    Query Parameters:
        characterId: Character UUID
        segmentId: Segment UUID

    Returns:
        200: Outcome data with narrative and effects
        404: Character or segment not found
        400: Invalid parameters
        401: Unauthorized
        409: Segment not yet completed
        500: Internal error
    """
    # Log invocation
    log_lambda_statistics(event, context)

    # Handle preflight
    preflight_response: dict = cors_handler.handle_preflight(event)
    if preflight_response:
        return preflight_response

    # Extract player ID from JWT
    try:
        player_id = extract_player_id(event)
    except ValueError as err:
        logger.error(f"Authentication failed Error: {err}", exc_info=True)
        return lambda_response(401, {"Error": "Unauthorized"}, event)
    except Exception as err:
        return lambda_error(event, err)

    # Validate player exists
    try:
        if not validate_player(player_id):
            logger.error(f"Player not found in database for {player_id}", exc_info=True)
            return lambda_response(401, {"Error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error(f"Failed to validate player Error: {err}", exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)

    # Get parameters from query (flexible: PascalCase or camelCase)
    character_id = get_query_parameter_flexible(event, "CharacterID", "characterId")
    if not character_id:
        return lambda_response(400, {"Error": "Missing CharacterID parameter"}, event)

    segment_id = get_query_parameter_flexible(event, "SegmentID", "segmentId")
    if not segment_id:
        return lambda_response(400, {"Error": "Missing SegmentID parameter"}, event)

    # Call business logic
    try:
        outcome_data = get_segment_outcome_business_logic(character_id, segment_id, player_id)  # type: ignore

        # Build response per API documentation with PascalCase
        response_data = {
            "Outcome": outcome_data.get("Outcome", "normal"),
            "Narrative": outcome_data.get("Narrative", ""),
            "Effects": outcome_data.get("Effects", {}),
        }

        # Add optional fields based on what's available
        if "NextSegmentID" in outcome_data:
            response_data["NextSegmentID"] = outcome_data["NextSegmentID"]

        if "Decision" in outcome_data:
            response_data["Decision"] = outcome_data["Decision"]

        if "ChallengeResults" in outcome_data:
            response_data["ChallengeResults"] = outcome_data["ChallengeResults"]

        if "CombatState" in outcome_data:
            response_data["CombatState"] = outcome_data["CombatState"]

        return lambda_response(200, response_data, event)

    except ValueError as err:
        logger.warning(f"Invalid request for {character_id} Error: {err}")
        error_msg = str(err)
        if "not found" in error_msg.lower():
            return lambda_response(
                404,
                {"Error": error_msg},
                event,
            )
        elif "not yet completed" in error_msg.lower():
            return lambda_response(
                409,
                {"Error": error_msg},
                event,
            )
        return lambda_response(
            400,
            {"Error": error_msg},
            event,
        )
    except RuntimeError as err:
        logger.error(
            f"Failed to get segment outcome for {character_id} Error: {err}",
            exc_info=True,
        )
        return lambda_response(
            500,
            {"Error": "Internal server error"},
            event,
        )

    except Exception as err:
        return lambda_error(event, err)
