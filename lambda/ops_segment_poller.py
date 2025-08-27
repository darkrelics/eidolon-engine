"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to poll for completed segments.
Triggered by EventBridge to check active segments that have reached their end time.
Handles different segment types appropriately and manages polling state.
"""

from time import time

from botocore.exceptions import ClientError

from eidolon.environment import MAX_SEGMENTS_PER_POLL, SEGMENT_QUEUE_URL, STORY_ADVANCEMENT_QUEUE_URL
from eidolon.logger import log_lambda_statistics, logger
from eidolon.polling import get_polling_state, manage_eventbridge_rule, update_polling_state
from eidolon.responses import lambda_error, lambda_response
from eidolon.segment_core import is_mechanical_segment
from eidolon.segment_polling import check_active_segments_exist, get_completed_segments
from eidolon.segment_state import mark_segment_as_completed_exceptional, reset_segment_processing_status
from eidolon.sqs import send_message_batch


def poll_segments() -> dict:
    """
    Poll for segments that have reached their end time and route appropriately.

    Returns:
        Dict with processing statistics

    Raises:
        RuntimeError: If database or SQS operations fail
    """
    # First check SSM parameter state
    poller_state = get_polling_state()

    # Get completed segments (including stuck segments 5+ minutes past EndTime)
    completed_segments = get_completed_segments(MAX_SEGMENTS_PER_POLL)

    # Categorize segments by their processing needs
    segments_for_advancement = []  # Processed segments ready for story advancement
    segments_for_processing = []  # Mechanical segments that need processing
    stuck_mechanical_segments = []  # Mechanical segments stuck in processing >5 minutes
    exhausted_segments = []  # Segments past their time window without processing

    mechanical_count = 0
    simple_count = 0
    stuck_count = 0
    exhausted_count = 0

    now = time()
    
    for segment in completed_segments:
        segment_type = segment.get("SegmentType", "")
        end_time = segment.get("EndTime", 0)  # Unix timestamp
        start_time = segment.get("StartTime", 0)  # Unix timestamp
        time_since_end = int(now - end_time) if end_time else 0
        processing_status = segment.get("ProcessingStatus", "")

        # Processed segments ready for advancement
        if processing_status == "processed":
            segments_for_advancement.append(segment)
            logger.debug(f"Segment processed, ready for advancement: {segment.get('ActiveSegmentID')}")
        # Check if mechanical segment is stuck (>5 minutes in processing state)
        elif is_mechanical_segment(segment_type) and processing_status == "processing":
            # Calculate how long it's been processing
            time_in_processing = int(now - start_time) if start_time else 0
            time_remaining = -time_since_end  # Negative of time_since_end is time_until

            if time_in_processing > 300:
                # Been processing >5 min - retry it
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
        elif time_since_end > 0 and processing_status not in ["processed", "completed"]:
            exhausted_segments.append(segment)
            exhausted_count += 1
            logger.warning(
                f"Found exhausted segment - marking as exceptional to protect player from system failure for {segment.get('ActiveSegmentID')}"
            )
        # Pending segments within 30 seconds of end time or past it
        elif processing_status == "pending" and time_since_end >= -30:
            if is_mechanical_segment(segment_type):
                # Mechanical segments need processing first
                segments_for_processing.append(segment)
                logger.debug(f"Pending mechanical segment ready for processing: {segment.get('ActiveSegmentID')}")
            else:
                # Rest/decision segments go straight to advancement
                segments_for_advancement.append(segment)
                logger.debug(f"Pending {segment_type} segment ready for advancement: {segment.get('ActiveSegmentID')}")
        # Completed segments should go to advancement  
        elif processing_status == "completed":
            segments_for_advancement.append(segment)
            logger.debug(f"Completed segment ready for advancement: {segment.get('ActiveSegmentID')}")

        if is_mechanical_segment(segment_type):
            mechanical_count += 1
        else:
            simple_count += 1

    # Process each category
    segments_to_process = 0
    segments_to_advance = 0
    segments_failed = 0
    segments_cleaned = 0
    segments_marked_exceptional = 0

    # Send pending mechanical segments to processing queue
    if segments_for_processing:
        if not SEGMENT_QUEUE_URL:
            logger.error("SEGMENT_QUEUE_URL not set, cannot process mechanical segments")
        else:
            messages = []
            for segment in segments_for_processing:
                messages.append({"body": segment.get("ActiveSegmentID")})
            
            result = send_message_batch(SEGMENT_QUEUE_URL, messages)
            segments_to_process += result.get("successful", 0)
            segments_failed += result.get("failed", 0)

    # Send processed segments to advancement queue
    if segments_for_advancement:
        messages = []
        for segment in segments_for_advancement:
            messages.append({"body": segment.get("ActiveSegmentID")})

        if not STORY_ADVANCEMENT_QUEUE_URL:
            raise RuntimeError("STORY_ADVANCEMENT_QUEUE_URL environment variable not set")

        result = send_message_batch(STORY_ADVANCEMENT_QUEUE_URL, messages)
        segments_to_advance += result.get("successful", 0)
        segments_failed += result.get("failed", 0)

    # Clean and retry stuck mechanical segments
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
                    messages.append({"body": segment.get("ActiveSegmentID")})
                except Exception as err:
                    logger.error(f"Failed to clean stuck segment for {segment.get('ActiveSegmentID')} Error: {err}")

            if messages:
                result = send_message_batch(SEGMENT_QUEUE_URL, messages)

    # Mark exhausted segments as exceptional (protection for system failures)
    if exhausted_segments:
        for segment in exhausted_segments:
            try:
                # Mark as completed with exceptional outcome to protect player from system failures
                # If our processing failed repeatedly, give the player the best possible outcome
                # This sets Status="completed" so the segment won't be picked up again
                mark_segment_as_completed_exceptional(segment.get("ActiveSegmentID"))
                segments_marked_exceptional += 1
                logger.info(
                    f"Marked exhausted segment as exceptional - no further processing needed for {segment.get('ActiveSegmentID')}"
                )
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
        "SegmentsToAdvance": segments_to_advance,
        "SegmentsToProcess": segments_to_process,
        "SegmentsFailed": segments_failed,
        "StuckCount": stuck_count,
        "SegmentsCleaned": segments_cleaned,
        "ExhaustedCount": exhausted_count,
        "SegmentsMarkedExceptional": segments_marked_exceptional,
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
        result = poll_segments()

        # Build response with PascalCase fields
        response_data = {
            "Message": "Segment polling completed",
            **result,
        }

        return response_data

    except (ClientError, RuntimeError) as err:
        logger.error(f"Segment polling failed: {err}", exc_info=True)
        raise
    except Exception as err:
        logger.error(f"Unexpected error during segment polling: {err}", exc_info=True)
        raise
