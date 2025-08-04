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
from eidolon.logger import logger, log_lambda_statistics
from eidolon.polling import disable_polling_infrastructure, enable_polling_infrastructure, get_polling_state
from eidolon.responses import lambda_response
from eidolon.segment import (
    check_active_segments_exist,
    get_completed_segments,
    is_mechanical_segment,
    mark_segment_as_completed_exceptional,
    reset_segment_processing_status,
)
from eidolon.sqs import send_message_batch
from eidolon.utilities import handle_lambda_error_pascal


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
        end_time = int(segment.get("EndTime", 0))
        start_time = int(segment.get("StartTime", 0))
        time_since_end = current_time - end_time
        processing_status = segment.get("ProcessingStatus", "")

        # Skip segments already processed - they're waiting for advancement
        if processing_status == "processed":
            segments_for_advancement.append(segment)
            logger.debug(
                "Segment already processed, sending to advancement",
                extra={
                    "active_segment_id": segment.get("ActiveSegmentID"),
                    "segment_type": segment_type,
                },
            )
        # Check if mechanical segment is stuck (>15 minutes in processing state)
        # Only retry if there's at least 15 minutes remaining before end time
        elif is_mechanical_segment(segment_type) and processing_status == "processing":
            # Calculate how long it's been processing
            time_in_processing = current_time - start_time
            time_remaining = end_time - current_time

            if time_in_processing > 900 and time_remaining > 900:
                # Been processing >15 min AND >15 min remaining - retry it
                stuck_mechanical_segments.append(segment)
                stuck_count += 1
                logger.warning(
                    "Found stuck mechanical segment with time to retry",
                    extra={
                        "active_segment_id": segment.get("ActiveSegmentID"),
                        "minutes_processing": time_in_processing / 60,
                        "minutes_remaining": time_remaining / 60,
                    },
                )
            elif time_since_end > 0:
                # Past end time while still processing - mark as exceptional
                exhausted_segments.append(segment)
                exhausted_count += 1
                logger.warning(
                    "Found stuck segment past end time - marking as exceptional",
                    extra={
                        "active_segment_id": segment.get("ActiveSegmentID"),
                        "segment_type": segment_type,
                        "seconds_past_end": time_since_end,
                    },
                )
            # Otherwise, it's still processing within normal timeframe - let it continue
        # Any segment past its end time that isn't processed or completed should be marked exceptional
        # But NOT if it's already processed - those are just waiting for advancement
        elif time_since_end > 0 and processing_status not in ["processed", "completed"]:
            exhausted_segments.append(segment)
            exhausted_count += 1
            logger.warning(
                "Found exhausted segment - marking as exceptional to protect player from system failure",
                extra={
                    "active_segment_id": segment.get("ActiveSegmentID"),
                    "segment_type": segment_type,
                    "processing_status": processing_status,
                    "seconds_past_end": time_since_end,
                },
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
                    logger.error(
                        "Failed to clean stuck segment",
                        extra={"active_segment_id": segment.get("ActiveSegmentID"), "error": str(err)},
                    )

            if messages:
                result = send_message_batch(SEGMENT_QUEUE_URL, messages)
                logger.info(
                    "Retried stuck mechanical segments",
                    extra={"count": len(messages), "successful": result.get("successful", 0), "failed": result.get("failed", 0)},
                )

    # 3. Mark exhausted segments as done and send to advancement
    if exhausted_segments:
        messages = []
        for segment in exhausted_segments:
            try:
                # Mark as completed with exceptional outcome to protect player from system failures
                # If our processing failed repeatedly, give the player the best possible outcome
                mark_segment_as_completed_exceptional(segment.get("ActiveSegmentID"))
                segments_marked_done += 1

                # Queue for advancement to complete the story flow
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
                logger.error(
                    "Failed to mark exhausted segment as done",
                    extra={"active_segment_id": segment.get("ActiveSegmentID"), "error": str(err)},
                )

        if messages:
            result = send_message_batch(STORY_ADVANCEMENT_QUEUE_URL, messages)
            segments_queued += result.get("successful", 0)
            segments_failed += result.get("failed", 0)

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
            "stuck_count": stuck_count,
            "segments_cleaned": segments_cleaned,
            "exhausted_count": exhausted_count,
            "segments_marked_done": segments_marked_done,
            "current_state": poller_state,
        },
    )

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
        return lambda_response(200, response_data, event)

    except ClientError as err:
        logger.error(
            "AWS service error during segment polling",
            extra={"error": str(err)},
            exc_info=True,
        )
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except RuntimeError as err:
        logger.error(
            "Failed to poll segments",
            extra={"error": str(err)},
            exc_info=True,
        )
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)
