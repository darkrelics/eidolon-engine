"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to poll for completed segments.
Triggered by EventBridge to check active segments that have reached their end time.
"""

from eidolon.environment import MAX_SEGMENTS_PER_POLL, SEGMENT_QUEUE_URL, SSM_POLLER_STATE_PARAMETER
from eidolon.logger import get_logger
from eidolon.segment import check_active_segments_exist, get_completed_segments
from eidolon.sqs import send_message_batch
from eidolon.ssm import get_parameter, put_parameter
from eidolon.utilities import build_lambda_response_pascal, handle_lambda_error_pascal, log_lambda_invocation

# Configure logging
logger = get_logger(__name__)


def poll_and_process_segments_business_logic() -> dict:
    """
    Business logic to poll for and process completed segments.

    Returns:
        Dict with processing statistics

    Raises:
        RuntimeError: If database or SQS operations fail
    """
    # First check SSM parameter state
    try:
        poller_state = get_parameter(SSM_POLLER_STATE_PARAMETER)
    except ValueError:
        # Parameter doesn't exist, create it
        put_parameter(SSM_POLLER_STATE_PARAMETER, "run")
        poller_state = "run"
    
    # Get completed segments from eidolon library
    completed_segments = get_completed_segments(MAX_SEGMENTS_PER_POLL)

    logger.info(
        "Segment polling check",
        extra={
            "poller_state": poller_state,
            "segments_found": len(completed_segments),
        },
    )

    # Send to SQS if segments found
    processed_count = 0
    failed_count = 0
    
    if completed_segments:
        # Prepare messages for SQS
        messages = []
        for segment in completed_segments:
            messages.append({
                "body": {
                    "ActiveSegmentID": segment.get("ActiveSegmentID"),
                    "CharacterID": segment.get("CharacterID"),
                    "StoryID": segment.get("StoryID"),
                    "SegmentID": segment.get("SegmentID"),
                    "SegmentType": segment.get("SegmentType"),
                }
            })
        
        # Send to SQS
        if not SEGMENT_QUEUE_URL:
            raise RuntimeError("SEGMENT_QUEUE_URL environment variable not set")
            
        result = send_message_batch(SEGMENT_QUEUE_URL, messages)
        processed_count = result["successful"]
        failed_count = result["failed"]

    # Update SSM parameter based on state
    if poller_state == "stop":
        if completed_segments:
            # Found segments while stopped, switch to run
            put_parameter(SSM_POLLER_STATE_PARAMETER, "run")
            logger.info("Poller state changed from stop to run due to found segments")
    else:  # poller_state == "run"
        if not completed_segments:
            # No segments found, check if table is empty
            has_active_segments = check_active_segments_exist()
            
            if not has_active_segments:
                # No active segments at all, switch to stop
                put_parameter(SSM_POLLER_STATE_PARAMETER, "stop")
                logger.info("Poller state changed from run to stop - no active segments")

    logger.info(
        "Segment polling completed",
        extra={
            "segments_found": len(completed_segments),
            "messages_sent": processed_count,
            "messages_failed": failed_count,
            "current_state": poller_state,
        },
    )

    return {
        "SegmentsFound": len(completed_segments),
        "MessagesQueued": processed_count,
        "MessagesFailed": failed_count,
        "PollerState": poller_state,
    }


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to poll for completed segments.

    Args:
        event: EventBridge event (scheduled)
        context: Lambda context

    Returns:
        Response with processing summary
    """
    # Log invocation
    log_lambda_invocation(context, event)

    # Log event source for EventBridge events
    logger.info(
        "EventBridge trigger",
        extra={
            "event_source": event.get("source", "unknown"),
            "detail_type": event.get("detail-type", "unknown"),
        },
    )

    try:
        # Run polling logic
        result = poll_and_process_segments_business_logic()

        # Build response
        response_data = {"Message": "Segment polling completed", **result}

        logger.info("Lambda response", extra={"status_code": 200})
        return build_lambda_response_pascal(200, response_data, event)

    except RuntimeError as err:
        logger.error(
            "Failed to poll segments",
            extra={"error": str(err)},
        )
        return build_lambda_response_pascal(500, {"error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)
