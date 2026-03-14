"""
Eidolon Engine - Incremental Game

Copyright 2024-2026 Jason E. Robinson

Lambda function to get the status of an active segment.
Returns segment completion status and any available results.

Endpoint: GET /segment/status
Authentication: Cognito (required)
"""

import time

from eidolon.constants import RETRY_POLL_DELAY
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.requests import get_query_parameter
from eidolon.segment_core import map_outcome_to_key, validate_segment_outcome_results
from eidolon.story_active import get_active_story_segment_with_player_check
from eidolon.story_retrieval import get_story, get_story_segment
from eidolon.time_utils import coerce_unix_timestamp, from_unix
from eidolon.validation import validate_uuid


def filter_decision_options(raw_options: dict) -> dict:
    """
    Filter decision options to include only safe client-facing fields.

    Removes internal fields like Difficulty and Narrative that should
    not be exposed to the client.

    Args:
        raw_options: Raw decision options dict from segment definition

    Returns:
        Filtered dict with only Text, Description, and NextSegmentID
    """
    return {
        key: {"Text": option.get("Text"), "Description": option.get("Description"), "NextSegmentID": option.get("NextSegmentID")}
        for key, option in raw_options.items()
    }


def get_next_segment_preview(story_id: str, next_segment_id: str) -> dict:
    """Fetch preview data for the next segment. Returns empty dict on failure.

    Args:
        story_id: Story UUID
        next_segment_id: Next segment UUID

    Returns:
        Preview dict with segment metadata, or empty dict on failure
    """
    try:
        next_segment_def = get_story_segment(story_id, next_segment_id)
        if not next_segment_def:
            return {}
        return {
            "SegmentID": next_segment_id,
            "SegmentType": next_segment_def.get("SegmentType", "mechanical"),
            "SegmentDuration": next_segment_def.get("SegmentDuration", 60),
            "SegmentTitle": next_segment_def.get("SegmentTitle", "Processing..."),
            "SegmentActivity": next_segment_def.get("SegmentActivity", ""),
        }
    except Exception as err:
        logger.debug(f"Could not fetch next segment preview: {err}")
        return {}


def get_segment_status_business_logic(character_id: str, player_id: str) -> dict:
    """
    Business logic for getting segment status.

    Args:
        character_id: Character UUID
        player_id: Authenticated player ID

    Returns:
        Response data dict with segment status

    Raises:
        ValueError: If character not found or not owned
        RuntimeError: If database operations fail
    """
    # Get active segment (includes player ownership check via PlayerID filter)
    try:
        active_segment = get_active_story_segment_with_player_check(character_id, player_id)
    except ValueError as err:
        if "No active story found" in str(err):
            # Return a friendly response when no active segment exists
            # This can happen after a rollback or when no story is active
            logger.info(f"No active segment for character {character_id} - likely rolled back or not started")
            raise ValueError("404:No active segment found") from err
        raise err

    now = time.time()
    start_time_unix = coerce_unix_timestamp(active_segment.get("StartTime"), int(now))
    if start_time_unix is None:
        start_time_unix = int(now)

    end_time_unix = coerce_unix_timestamp(active_segment.get("EndTime"), None)
    if end_time_unix is None:
        # No EndTime stored, try to get duration from segment fields
        raw_duration = (
            active_segment.get("Duration") or active_segment.get("SegmentDuration") or active_segment.get("ExpectedDuration")
        )
        try:
            duration = int(raw_duration)  # type: ignore
        except TypeError as err:
            logger.debug(f"Duration type error: {err}")
            duration = 60
        except ValueError as err:
            logger.debug(f"Duration value error: {err}")
            duration = 60
        if duration <= 0:
            duration = 60
        end_time_unix = start_time_unix + duration
    else:
        # Calculate duration from stored times
        duration = max(60, end_time_unix - start_time_unix)

    # Calculate timer status
    time_remaining = max(0, int(end_time_unix - now))

    processing_status = active_segment.get("ProcessingStatus", "")

    # Calculate next poll time for client guidance using constant delay
    # Client uses ProcessingStatus to determine when backend is done
    # Client uses local timer (EndTime/TimeRemaining) to determine when to display results
    if processing_status != "processed":
        next_poll_delay = min(RETRY_POLL_DELAY, time_remaining)  # Cap at time remaining
        poll_after_unix = int(now + next_poll_delay)
        poll_after = from_unix(poll_after_unix)
    else:
        poll_after = None  # No more polling needed when processed

    response = {
        "ActiveSegmentID": active_segment.get("ActiveSegmentID"),
        "StoryID": active_segment.get("StoryID"),
        "StoryInstanceID": active_segment.get("StoryInstanceID"),
        "SegmentID": active_segment.get("SegmentID"),
        "Status": active_segment.get("Status", "active"),
        "TimeRemaining": time_remaining,
        "StartTime": from_unix(start_time_unix),
        "EndTime": from_unix(end_time_unix),
        "PollAfter": poll_after,  # When client should poll next
        "ProcessingStatus": processing_status,
        "SegmentType": active_segment.get("SegmentType"),
        "SegmentActivity": active_segment.get("SegmentActivity", ""),
        "SegmentTitle": active_segment.get("SegmentTitle", ""),
        "Duration": duration,
    }

    # Include result data if segment is fully processed
    # Results are included even if timer hasn't expired yet, so client has them ready
    # Client controls when to display completed card based on timer
    segment_type = active_segment.get("SegmentType", "").lower()
    story_id = active_segment.get("StoryID")
    segment_id = active_segment.get("SegmentID")

    segment_def = None

    # Include outcome/results data when processing is complete (even if timer not expired)
    # Client will display them when IsComplete=true (timer expires)
    if processing_status == "processed":
        # Include narrative and events for display
        response["SegmentTitle"] = active_segment.get("SegmentTitle")
        response["ClientEvents"] = active_segment.get("ClientEvents", [])
        response["ChallengeResults"] = active_segment.get("ChallengeResults", [])
        response["Outcome"] = active_segment.get("Outcome")
        response["CombatState"] = active_segment.get("CombatState")

        try:
            # Get segment definition for narrative text
            segment_def = get_story_segment(story_id, segment_id)  # type: ignore

            if segment_type == "mechanical":
                outcome = active_segment.get("Outcome", "normal")
                validated_result = validate_segment_outcome_results(segment_def, outcome)
                response["Narrative"] = validated_result.get("Narrative", "")
                response["Effects"] = validated_result.get("Effects", {})

                # Get next segment based on outcome
                results = segment_def.get("Results", {}) or {}
                next_segment_id = None
                if isinstance(results, dict):
                    outcome_key = map_outcome_to_key(outcome or "normal")
                    if outcome_key and isinstance(results.get(outcome_key), dict):
                        outcome_block = results.get(outcome_key, {})
                        branches = outcome_block.get("Branches", [])
                        if branches and isinstance(branches, list):
                            first_branch = branches[0]
                            if isinstance(first_branch, dict):
                                next_segment_id = first_branch.get("NextSegmentID")

                response["NextSegmentID"] = next_segment_id

            elif segment_type == "decision":
                decision = active_segment.get("Decision")
                decision_options = segment_def.get("DecisionOptions", {})
                selected_option = decision_options.get(decision, {}) if decision else {}
                response["NextSegmentID"] = selected_option.get("NextSegmentID") if selected_option else None
                response["Narrative"] = ""
                response["Effects"] = {}

            # Story is complete if NextSegmentID is None
            next_segment_id = response.get("NextSegmentID")
            response["StoryComplete"] = next_segment_id is None

            # Add NextSegmentPreview if there's a next segment
            if next_segment_id:
                preview = get_next_segment_preview(story_id, next_segment_id)  # type: ignore
                if preview:
                    response["NextSegmentPreview"] = preview

        except Exception as err:
            logger.warning(
                f"Failed to get narrative data for segment_id={segment_id}, character_id={character_id}: {err.__class__.__name__}: {err}"
            )
            # Continue without narrative - not critical
    else:
        # Segment is still processing - just return basic status
        response["SegmentTitle"] = response.get("SegmentTitle") or "Processing..."
        response.setdefault("SegmentActivity", "")

    if (not response.get("SegmentTitle") or not response.get("SegmentActivity")) and story_id and segment_id:
        try:
            if segment_def is None:
                segment_def = get_story_segment(story_id, segment_id)  # type: ignore
            response["SegmentTitle"] = response.get("SegmentTitle") or segment_def.get("SegmentTitle", "Processing...")
            response["SegmentActivity"] = response.get("SegmentActivity") or segment_def.get("SegmentActivity", "")
        except Exception as err:
            logger.debug(f"Could not enrich segment metadata for {segment_id}: {err}")

    # Include decision-specific data
    if segment_type == "decision":
        response["Decision"] = active_segment.get("Decision")

        # Enrich with DecisionText from segment definition if available
        if story_id and segment_id and segment_def is None:
            try:
                segment_def = get_story_segment(story_id, segment_id)  # type: ignore
            except Exception as err:
                logger.debug(f"Could not fetch segment definition for DecisionText: {err}")

        if segment_def:
            response["DecisionText"] = segment_def.get("DecisionText")
            # Build DecisionOptions without exposing Difficulty or Narrative
            raw_options = segment_def.get("DecisionOptions", {})
            response["DecisionOptions"] = filter_decision_options(raw_options)
        elif active_segment.get("DecisionOptions"):
            # Fallback to active segment data (filter same fields)
            raw_options = active_segment.get("DecisionOptions", {})
            response["DecisionOptions"] = filter_decision_options(raw_options)

    # Include story information for consistent display
    if story_id:
        try:
            story_data = get_story(story_id)
            if story_data:
                response["Story"] = {
                    "Title": story_data.get("Title", ""),
                    "Description": story_data.get("Description", ""),
                    "Type": story_data.get("StoryType", ""),
                    "StoryID": story_id,
                }
        except Exception as err:
            logger.debug(f"Could not fetch story data: {err}")
            # Not critical, continue without story data

    # Log successful status retrieval with key details for observability
    active_segment_id = response.get("ActiveSegmentID")
    status = response.get("Status")
    processing_status = response.get("ProcessingStatus")
    time_remaining = response.get("TimeRemaining")
    logger.info(
        f"Segment status for character={character_id}, segment={active_segment_id}: "
        f"Status={status}, ProcessingStatus={processing_status}, TimeRemaining={time_remaining}s"
    )

    return response


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """
    Get status of active segment.

    Lambda function to check the status of a character's active segment.
    Used by clients to poll for segment completion and retrieve results.

    Query Parameters:
        CharacterID: Character ID to check

    Returns:
        Dict with status_code and body
    """
    character_id = get_query_parameter(event, "CharacterID")
    if not character_id:
        raise ValueError("Missing CharacterID parameter")

    if not validate_uuid(character_id):
        raise ValueError("Invalid CharacterID format")

    logger.info(f"Checking segment status for character={character_id}")

    response_data = get_segment_status_business_logic(character_id, player_id)
    return {"status_code": 200, "body": response_data}
