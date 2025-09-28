"""
Segment response formatting utilities.

Provides functions for formatting segment data for API responses.
"""

from eidolon.time_utils import from_unix, now_unix


def new_segment_response(active_segment: dict, segment: dict) -> dict:
    """
    Format response per API documentation.

    Args:
        active_segment: Active segment record from database
        segment: Segment definition from Segments table

    Returns:
        Dict with success and segment data
    """
    # Use active segment times if available, otherwise calculate from now
    start_time_unix = active_segment.get("StartTime", now_unix())
    segment_duration = segment.get("SegmentDuration", 60)  # Default 60 seconds
    end_time_unix = active_segment.get("EndTime", start_time_unix + segment_duration)

    # Always convert to valid ISO strings - never empty
    start_time = from_unix(start_time_unix)
    end_time = from_unix(end_time_unix)

    duration = end_time_unix - start_time_unix

    # Build complete segment response matching segment status API format
    response = {
        "ActiveSegmentID": active_segment.get("ActiveSegmentID", ""),
        "StoryID": active_segment.get("StoryID", ""),
        "StoryInstanceID": active_segment.get("StoryInstanceID", ""),
        "SegmentID": active_segment.get("SegmentID", ""),
        "Status": active_segment.get("Status", "active"),
        "IsComplete": False,  # New segments are never complete initially
        "TimeRemaining": duration,  # Full duration initially
        "StartTime": start_time,
        "EndTime": end_time,
        "ProcessingStatus": active_segment.get("ProcessingStatus", "pending"),
        "SegmentType": segment.get("SegmentType", "mechanical"),
        "SegmentActivity": active_segment.get(
            "SegmentActivity", segment.get("SegmentActivity", "Starting your adventure...")
        ),
        "SegmentTitle": active_segment.get(
            "SegmentTitle", segment.get("SegmentTitle", "Processing...")
        ),
        "Duration": duration,
    }

    # Include segment-specific data
    segment_type = segment.get("SegmentType", "").lower()

    # Include decision options for decision segments
    if segment_type == "decision":
        response["DecisionOptions"] = segment.get("DecisionOptions", {})

    # Include client events if available
    response["ClientEvents"] = active_segment.get("ClientEvents", [])

    # Include challenge results if available
    response["ChallengeResults"] = active_segment.get("ChallengeResults", [])

    # Include combat state if available
    response["CombatState"] = active_segment.get("CombatState")

    # Include outcome if available
    response["Outcome"] = active_segment.get("Outcome")

    # Include character updates if available
    response["CharacterUpdates"] = active_segment.get("CharacterUpdates")

    return {
        "Success": True,
        "Segment": response,
    }
