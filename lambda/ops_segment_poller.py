"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to poll for completed segments.
Triggered by EventBridge to check active segments that have reached their end time.
Handles different segment types appropriately and manages polling state.
"""

import time

from eidolon.environment import MAX_SEGMENTS_PER_POLL, STORY_ADVANCEMENT_QUEUE_URL
from eidolon.logger import get_logger
from eidolon.polling import (
    disable_polling_infrastructure,
    enable_polling_infrastructure,
    get_polling_state,
)
from eidolon.segment import (
    check_active_segments_exist,
    get_completed_segments,
    is_mechanical_segment,
)
from eidolon.sqs import send_message_batch
from eidolon.utilities import build_lambda_response_pascal, handle_lambda_error_pascal, log_lambda_invocation

# Configure logging
logger = get_logger(__name__)


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
    current_time = int(time.time())

    # Get completed segments (including stuck segments 15+ minutes past EndTime)
    completed_segments = get_completed_segments(MAX_SEGMENTS_PER_POLL)

    logger.info(
        "Segment polling check",
        extra={
            "poller_state": poller_state,
            "segments_found": len(completed_segments),
            "current_time": current_time,
        },
    )

    # Count segment types for logging
    mechanical_count = 0
    simple_count = 0

    for segment in completed_segments:
        segment_type = segment.get("SegmentType", "").lower()
        end_time = int(segment.get("EndTime", 0))
        is_stuck = (current_time - end_time) > 900  # 15 minutes

        if is_stuck:
            logger.warning(
                "Found stuck segment",
                extra={
                    "active_segment_id": segment.get("ActiveSegmentID"),
                    "segment_type": segment_type,
                    "end_time": end_time,
                    "overdue_seconds": current_time - end_time,
                },
            )

        if is_mechanical_segment(segment_type):
            mechanical_count += 1
        else:
            simple_count += 1

    # Queue ALL segments to story advancement queue
    segments_queued = 0
    segments_failed = 0

    if completed_segments:
        # Prepare messages for SQS
        messages = []
        for segment in completed_segments:
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

        # Send to story advancement queue
        if not STORY_ADVANCEMENT_QUEUE_URL:
            raise RuntimeError("STORY_ADVANCEMENT_QUEUE_URL environment variable not set")

        result = send_message_batch(STORY_ADVANCEMENT_QUEUE_URL, messages)
        segments_queued = result.get("successful", 0)
        segments_failed = result.get("failed", 0)

    # Update SSM parameter and EventBridge rule based on state
    if poller_state == "stop":
        if completed_segments:
            # Found segments while stopped, switch to run
            enable_polling_infrastructure()
            logger.info("Poller state changed from stop to run due to found segments")
    else:  # poller_state == "run"
        if not completed_segments:
            # No segments found, check if table is empty
            has_active_segments = check_active_segments_exist()

            if not has_active_segments:
                # No active segments at all, switch to stop
                disable_polling_infrastructure()
                logger.info("Poller state changed from run to stop - no active segments")

    logger.info(
        "Segment polling completed",
        extra={
            "segments_found": len(completed_segments),
            "mechanical_count": mechanical_count,
            "simple_count": simple_count,
            "segments_queued": segments_queued,
            "segments_failed": segments_failed,
            "current_state": poller_state,
        },
    )

    return {
        "SegmentsFound": len(completed_segments),
        "MechanicalCount": mechanical_count,
        "SimpleCount": simple_count,
        "SegmentsQueued": segments_queued,
        "SegmentsFailed": segments_failed,
        "PollerState": poller_state,
    }


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to poll for completed segments.

    Triggered by EventBridge every 30 seconds to find segments ready for processing.
    Handles different segment types appropriately and manages polling state.

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
            "time": event.get("time", "unknown"),
        },
    )

    try:
        # Run polling logic
        result = poll_and_process_segments_business_logic()

        # Build response with PascalCase fields
        response_data = {
            "Message": "Segment polling completed",
            **result,
        }

        logger.info(
            "Lambda response",
            extra={
                "status_code": 200,
                "segments_found": result.get("SegmentsFound", 0),
                "segments_queued": result.get("SegmentsQueued", 0),
            },
        )
        return build_lambda_response_pascal(200, response_data, event)

    except RuntimeError as err:
        logger.error(
            "Failed to poll segments",
            extra={"error": str(err)},
            exc_info=True,
        )
        return build_lambda_response_pascal(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)
