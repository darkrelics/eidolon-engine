"""
Story and segment response formatting.

Provides functions for formatting API responses.
"""

import time

from eidolon.logger import logger


def format_segment_response(segment: dict, active_segment: dict) -> dict:
    """
    Format segment data for API response.

    Args:
        segment: Original segment from Segments table
        active_segment: Active segment record

    Returns:
        Formatted response data
    """
    segment_type = segment.get("SegmentType", "mechanical")
    time_remaining = max(0, active_segment.get("EndTime", 0) - int(time.time()))

    response = {
        "SegmentID": active_segment.get("ActiveSegmentID"),
        "StoryID": active_segment.get("StoryID"),
        "Type": segment_type,
        "TimeRemaining": time_remaining,
    }

    if segment_type == "decision":
        response["Content"] = segment.get("DecisionText", "")
        decision_options = segment.get("DecisionOptions", {})
        options = []
        for option_id, _ in decision_options.items():
            options.append({"Id": option_id, "Text": option_id.replace("-", " ").title()})
        response["Options"] = options
    elif segment_type == "mechanical":
        response["ShortStatus"] = segment.get("ShortStatus", "Progressing through the story...")
        combat_config = segment.get("Combat", {})
        if combat_config:
            opponent_id = combat_config.get("OpponentID") or combat_config.get("opponentId")
            if opponent_id:
                response["OpponentID"] = opponent_id

    return response


def format_story_segment_response(active_segment: dict, story_metadata: dict, segment_data: dict) -> dict:
    """
    Format story and segment data for API response.

    Args:
        active_segment: Active segment record from database
        story_metadata: Story metadata from STORY table
        segment_data: Segment definition from SEGMENTS table

    Returns:
        Formatted response dict with story and segment information
    """
    end_time = int(active_segment.get("EndTime", 0))
    current_time = int(time.time())
    time_remaining = max(0, end_time - current_time)

    response = {
        "Story": {
            "StoryID": active_segment.get("StoryID"),
            "Title": story_metadata.get("Title", ""),
            "Type": story_metadata.get("StoryType", ""),
            "TotalSegments": story_metadata.get("TotalSegments", 1),
            "CurrentSegmentIndex": segment_data.get("SegmentIndex", 0),
        },
        "Segment": {
            "SegmentID": active_segment.get("SegmentID"),
            "SegmentType": segment_data.get("SegmentType", ""),
            "ShortStatus": segment_data.get("ShortStatus", ""),
            "Description": "",
            "Duration": segment_data.get("SegmentDuration", 0),
            "TimeRemaining": time_remaining,
            "StartTime": active_segment.get("StartTime", 0),
            "EndTime": int(active_segment.get("EndTime", 0)),
        },
        "ActiveSegmentID": active_segment.get("ActiveSegmentID", ""),
        "Status": active_segment.get("Status", ""),
    }

    segment_type = segment_data.get("SegmentType", "")

    if segment_type == "decision":
        response["Segment"]["DecisionText"] = segment_data.get("DecisionText", "")
        decision_options = segment_data.get("DecisionOptions", {})
        options = []
        for option_id, _ in decision_options.items():
            options.append({"Id": option_id, "Text": option_id.replace("-", " ").title()})
        response["Segment"]["Options"] = options
        response["Segment"]["Decision"] = active_segment.get("Decision")

    elif segment_type == "mechanical":
        response["Segment"]["Description"] = segment_data.get("Description", segment_data.get("Narrative", ""))
        response["Segment"]["Challenges"] = segment_data.get("Challenges", [])
        response["Segment"]["ChallengeResults"] = active_segment.get("ChallengeResults", [])

        if segment_data.get("Combat"):
            response["Segment"]["Combat"] = segment_data.get("Combat", {})
            response["Segment"]["CombatState"] = active_segment.get("CombatState", {})

        response["Segment"]["Outcome"] = active_segment.get("Outcome")

    elif segment_type == "rest":
        response["Segment"]["Description"] = segment_data.get("Description", segment_data.get("Narrative", ""))

    else:
        logger.warning(f"Unknown segment type for {active_segment.get('SegmentID')}")
        response["Segment"]["Description"] = segment_data.get("Description", segment_data.get("Narrative", ""))

    return response