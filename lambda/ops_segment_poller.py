"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to poll for completed segments.
Triggered by EventBridge to check active segments that have reached their end time.
Handles different segment types appropriately and manages polling state.
"""

import time

from botocore.exceptions import ClientError

from eidolon.environment import MAX_SEGMENTS_PER_POLL, SEGMENT_QUEUE_URL, STORY_ADVANCEMENT_QUEUE_URL
from eidolon.logger import log_lambda_statistics, logger
from eidolon.polling import get_polling_state, manage_eventbridge_rule, update_polling_state
from eidolon.responses import lambda_error, lambda_response
from eidolon.segment import (
    check_active_segments_exist,
    get_completed_segments,
    is_mechanical_segment,
    mark_segment_as_completed_exceptional,
    reset_segment_processing_status,
)
from eidolon.sqs import send_message_batch
from eidolon.time_utils import now_iso, seconds_since


def poll_and_process_segments_business_logic() -> dict:
    """
    Business logic to poll for and process completed segments.

    Sends all completed segments to the story advancement queue for processing.
    No longer processes any segments directly in the poller.

    Returns:
        Dict with processing statistics

    Raises:
        RuntimeError: If database or SQS operations fail
    """
    # First check SSM parameter state
    poller_state = get_polling_state()

    # Calculate time window for segment polling
    current_time_iso = now_iso()

    # Get completed segments (including stuck segments 15+ minutes past EndTime)
    completed_segments = get_completed_segments(MAX_SEGMENTS_PER_POLL)

    # Categorize segments by their processing needs
    segments_for_advancement = []  # Recently completed (within 30 seconds)
    stuck_mechanical_segments = []  # Mechanical segments stuck >15 minutes
    exhausted_segments = []  # Segments past their time window

    mechanical_count = 0
    simple_count = 0
    stuck_count = 0
    exhausted_count = 0

    for segment in completed_segments:
        segment_type = segment.get("SegmentType", "").lower()
        end_time = segment.get("EndTime", "")
        start_time = segment.get("StartTime", "")
        time_since_end = seconds_since(end_time) if end_time else 0
        processing_status = segment.get("ProcessingStatus", "")

        # Skip segments already processed - they're waiting for advancement
        if processing_status == "processed":
            segments_for_advancement.append(segment)
            logger.debug(f"Segment already processed, sending to advancement for {segment.get('ActiveSegmentID')}")
        # Check if mechanical segment is stuck (>15 minutes in processing state)
        # Only retry if there's at least 15 minutes remaining before end time
        elif is_mechanical_segment(segment_type) and processing_status == "processing":
            # Calculate how long it's been processing
            time_in_processing = seconds_since(start_time) if start_time else 0
            time_remaining = -time_since_end  # Negative of time_since_end is time_until

            if time_in_processing > 900 and time_remaining > 900:
                # Been processing >15 min AND >15 min remaining - retry it
                stuck_mechanical_segments.append(segment)
                stuck_count += 1
                logger.warning(f"Found stuck mechanical segment with time to retry for {segment.get('ActiveSegmentID')}")
            elif time_since_end > 0:
                # Past end time while still processing - mark as exceptional
                exhausted_segments.append(segment)
                exhausted_count += 1
                logger.warning(f"Found stuck segment past end time - marking as exceptional for {segment.get('ActiveSegmentID')}")
            # Otherwise, it's still processing within normal timeframe - let it continue
        # Any segment past its end time that isn't processed or completed should be marked exceptional
        # But NOT if it's already processed - those are just waiting for advancement
        elif time_since_end > 0 and processing_status not in ["processed", "completed"]:
            exhausted_segments.append(segment)
            exhausted_count += 1
            logger.warning(
                f"Found exhausted segment - marking as exceptional to protect player from system failure for {segment.get('ActiveSegmentID')}"
            )
        # Normal segments within their time window
        else:
            segments_for_advancement.append(segment)

        if is_mechanical_segment(segment_type):
            mechanical_count += 1
        else:
            simple_count += 1

    # Process each category
    segments_queued = 0
    segments_failed = 0
    segments_cleaned = 0
    segments_marked_done = 0

    # 1. Send recently completed segments to advancement queue
    if segments_for_advancement:
        messages = []
        for segment in segments_for_advancement:
            messages.append(
                {
                    "body": {
                        "ActiveSegmentID": segment.get("ActiveSegmentID"),
                        "CharacterID": segment.get("CharacterID"),
                        "StoryID": segment.get("StoryID"),
                        "SegmentID": segment.get("SegmentID"),
                        "SegmentType": segment.get("SegmentType"),
                    }
                }
            )

        if not STORY_ADVANCEMENT_QUEUE_URL:
            raise RuntimeError("STORY_ADVANCEMENT_QUEUE_URL environment variable not set")

        result = send_message_batch(STORY_ADVANCEMENT_QUEUE_URL, messages)
        segments_queued += result.get("successful", 0)
        segments_failed += result.get("failed", 0)

    # 2. Clean and retry stuck mechanical segments
    if stuck_mechanical_segments:
        if not SEGMENT_QUEUE_URL:
            logger.error("SEGMENT_QUEUE_URL not set, cannot retry stuck segments")
        else:
            messages = []
            for segment in stuck_mechanical_segments:
                # Clear processing flag by updating segment
                try:
                    reset_segment_processing_status(segment.get("ActiveSegmentID"))
                    segments_cleaned += 1

                    # Queue for reprocessing
                    messages.append(
                        {
                            "body": {
                                "ActiveSegmentID": segment.get("ActiveSegmentID"),
                                "CharacterID": segment.get("CharacterID"),
                                "StoryID": segment.get("StoryID"),
                                "SegmentID": segment.get("SegmentID"),
                                "SegmentType": segment.get("SegmentType"),
                            }
                        }
                    )
                except Exception as err:
                    logger.error(f"Failed to clean stuck segment for {segment.get('ActiveSegmentID')} Error: {err}")

            if messages:
                result = send_message_batch(SEGMENT_QUEUE_URL, messages)

    # 3. Mark exhausted segments as done (no advancement needed - they're completed)
    if exhausted_segments:
        for segment in exhausted_segments:
            try:
                # Mark as completed with exceptional outcome to protect player from system failures
                # If our processing failed repeatedly, give the player the best possible outcome
                # This sets Status="completed" so the segment won't be picked up again
                mark_segment_as_completed_exceptional(segment.get("ActiveSegmentID"))
                segments_marked_done += 1
                logger.info(f"Marked exhausted segment as exceptional - no further processing needed for {segment.get('ActiveSegmentID')}")
            except Exception as err:
                logger.error(f"Failed to mark exhausted segment as done for {segment.get('ActiveSegmentID')} Error: {err}")

    # Handle polling state transitions based on your design
    if poller_state == "run":
        # Parameter is "run"
        if not completed_segments:
            # No segments to process - set parameter to "stop"
            update_polling_state("stop")
            logger.info("Parameter set to stop - no segments to process")
    else:  # poller_state == "stop"
        # Parameter is "stop" - check for active segments
        has_active_segments = check_active_segments_exist()
        
        if has_active_segments:
            # Found active segments - return to "run"
            update_polling_state("run")
            logger.info("Active segments found - parameter set back to run")
        else:
            # No active segments - disable the EventBridge rule
            try:
                manage_eventbridge_rule(False)
                logger.info("No active segments - EventBridge rule disabled")
            except Exception as err:
                logger.warning(f"Failed to disable EventBridge rule: {err}")

    return {
        "SegmentsFound": len(completed_segments),
        "MechanicalCount": mechanical_count,
        "SimpleCount": simple_count,
        "SegmentsQueued": segments_queued,
        "SegmentsFailed": segments_failed,
        "StuckCount": stuck_count,
        "SegmentsCleaned": segments_cleaned,
        "ExhaustedCount": exhausted_count,
        "SegmentsMarkedDone": segments_marked_done,
        "PollerState": poller_state,
    }


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to poll for completed segments.

    Triggered by EventBridge every minute to find segments ready for processing.
    Handles different segment types appropriately and manages polling state.

    Args:
        event: EventBridge event (scheduled)
        context: Lambda context

    Returns:
        Response with processing summary
    """
    # Log invocation
    log_lambda_statistics(event, context)

    try:
        # Run polling logic
        result = poll_and_process_segments_business_logic()

        # Build response with PascalCase fields
        response_data = {
            "Message": "Segment polling completed",
            **result,
        }

        return lambda_response(200, response_data, event)

    except ClientError as err:
        logger.error(f"AWS service error during segment polling Error: {err}", exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except RuntimeError as err:
        logger.error(f"Failed to poll segments Error: {err}", exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)
