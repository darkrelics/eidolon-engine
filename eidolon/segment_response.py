"""
Segment response formatting utilities.

Provides functions for formatting segment data for API responses.
"""

from eidolon.constants import INITIAL_POLL_DELAY
from eidolon.environment import DEFAULT_SEGMENT_DURATION
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
    segment_duration = segment.get("SegmentDuration", DEFAULT_SEGMENT_DURATION)
    end_time_unix = active_segment.get("EndTime", start_time_unix + segment_duration)

    # Always convert to valid ISO strings - never empty
    start_time = from_unix(start_time_unix)
    end_time = from_unix(end_time_unix)

    duration = end_time_unix - start_time_unix

    # Calculate when client should start polling
    # Use constant delay to prevent immediate polling and system overwhelm
    poll_delay = min(INITIAL_POLL_DELAY, duration)  # Cap at segment duration if shorter
    poll_after_unix = start_time_unix + poll_delay
    poll_after = from_unix(poll_after_unix)

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
        "PollAfter": poll_after,  # Tell client when to start polling
        "ProcessingStatus": active_segment.get("ProcessingStatus", "pending"),
        "SegmentType": segment.get("SegmentType", "mechanical"),
        "SegmentActivity": active_segment.get("SegmentActivity", segment.get("SegmentActivity", "Starting your adventure...")),
        "SegmentTitle": active_segment.get("SegmentTitle", segment.get("SegmentTitle", "Processing...")),
        "Duration": duration,
    }

    # Include segment-specific data
    segment_type = segment.get("SegmentType", "").lower()

    # Include decision options for decision segments
    if segment_type == "decision":
        response["DecisionOptions"] = segment.get("DecisionOptions", {})

    # Note: Do NOT include outcome/results data in initial response
    # These are only populated after processing completes
    # Client should poll segment-status API to get results

    return {
        "Success": True,
        "SchemaVersion": "1.0",
        "Segment": response,
    }
