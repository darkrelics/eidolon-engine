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
from eidolon.segment_polling import (
    check_active_segments_exist,
    get_segments_approaching_expiry,
    get_stuck_mechanical_segments,
)
from eidolon.segment_state import mark_segment_as_completed_exceptional, reset_segment_processing_status
from eidolon.sqs import send_message_batch


def poll_segments() -> None:
    """
    Poll for segments that need attention and route appropriately.
    
    Two main tasks:
    1. Find segments approaching expiry -> advance or recover them
    2. Find stuck mechanical segments -> retry them
    """
    # First check SSM parameter state
    poller_state = get_polling_state()

    segments_to_advance = 0
    segments_to_process = 0
    segments_marked_exceptional = 0
    
    # 1. Handle segments approaching expiry (within 90 seconds)
    try:
        expiring_segments = get_segments_approaching_expiry(MAX_SEGMENTS_PER_POLL)
        
        advancement_messages = []
        for segment in expiring_segments:
            active_segment_id = segment.get("ActiveSegmentID")
            processing_status = segment.get("ProcessingStatus")
            
            if processing_status == "processed":
                # Normal advancement
                advancement_messages.append({"body": active_segment_id})
                logger.debug(f"Segment ready for advancement: {active_segment_id}")
            else:
                # Not processed in time - mark exceptional to protect player
                try:
                    mark_segment_as_completed_exceptional(active_segment_id)
                    advancement_messages.append({"body": active_segment_id})
                    segments_marked_exceptional += 1
                    logger.warning(f"Marked unprocessed expiring segment as exceptional: {active_segment_id}")
                except Exception as err:
                    logger.error(f"Failed to mark segment as exceptional: {active_segment_id} Error: {err}")
        
        if advancement_messages:
            if not STORY_ADVANCEMENT_QUEUE_URL:
                raise RuntimeError("STORY_ADVANCEMENT_QUEUE_URL environment variable not set")
            
            result = send_message_batch(STORY_ADVANCEMENT_QUEUE_URL, advancement_messages)
            segments_to_advance = result.get("successful", 0)
            
    except Exception as err:
        logger.error(f"Failed to process expiring segments: {err}", exc_info=True)
    
    # 2. Handle stuck mechanical segments (>5 minutes old with time to retry)
    try:
        stuck_segments = get_stuck_mechanical_segments(MAX_SEGMENTS_PER_POLL)
        
        processing_messages = []
        for segment in stuck_segments:
            active_segment_id = segment.get("ActiveSegmentID")
            processing_status = segment.get("ProcessingStatus")
            
            # Reset if stuck in processing
            if processing_status == "processing":
                try:
                    reset_segment_processing_status(active_segment_id)
                    logger.info(f"Reset stuck processing segment: {active_segment_id}")
                except Exception as err:
                    logger.error(f"Failed to reset segment: {active_segment_id} Error: {err}")
                    continue
            
            processing_messages.append({"body": active_segment_id})
        
        if processing_messages:
            if not SEGMENT_QUEUE_URL:
                logger.error("SEGMENT_QUEUE_URL not set, cannot retry stuck segments")
            else:
                result = send_message_batch(SEGMENT_QUEUE_URL, processing_messages)
                segments_to_process = result.get("successful", 0)
                
    except Exception as err:
        logger.error(f"Failed to process stuck segments: {err}", exc_info=True)
    
    # Log statistics
    logger.info(f"Polling complete - Advanced: {segments_to_advance}, Retried: {segments_to_process}, Marked exceptional: {segments_marked_exceptional}")
    
    # Handle polling state transitions
    if poller_state == "run":
        # Check if there are still active segments
        if not check_active_segments_exist():
            # No segments to process - set parameter to "stop"
            update_polling_state("stop")
            logger.info("No active segments - parameter set to stop")
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
    Lambda handler to poll for segments needing attention.

    Triggered by EventBridge every minute to:
    1. Find segments approaching expiry and advance/recover them
    2. Find stuck mechanical segments and retry them

    Args:
        event: EventBridge event (scheduled)
        context: Lambda context

    Returns:
        Success response
    """
    # Log invocation
    log_lambda_statistics(event, context)

    try:
        # Run polling logic
        poll_segments()
        
        return {
            "statusCode": 200,
            "body": {"message": "Segment polling completed"}
        }

    except (ClientError, RuntimeError) as err:
        logger.error(f"Segment polling failed: {err}", exc_info=True)
        raise
    except Exception as err:
        logger.error(f"Unexpected error during segment polling: {err}", exc_info=True)
        raise
