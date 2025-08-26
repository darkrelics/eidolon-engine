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

    return {
        "Success": True,
        "Segment": {
            "ActiveSegmentID": active_segment.get("ActiveSegmentID", ""),
            "SegmentType": segment.get("SegmentType", "mechanical"),
            "StartTime": start_time,
            "EndTime": end_time,
            "ShortStatus": segment.get("ShortStatus", "Starting your adventure..."),
            "Duration": duration,
            "ProcessingStatus": active_segment.get("ProcessingStatus", "pending"),
        },
    }