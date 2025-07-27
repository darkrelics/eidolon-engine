"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to poll for completed segments.
Triggered by EventBridge to check active segments that have reached their end time.
"""

from eidolon.environment import ENABLE_BATCH_PROCESSING
from eidolon.environment import MAX_SEGMENTS_PER_POLL
from eidolon.environment import PROCESS_SEGMENT_FUNCTION
from eidolon.environment import SEGMENT_BATCH_SIZE
from eidolon.lambda_utils import invoke_process_segment
from eidolon.lambda_utils import invoke_process_segments_batch
from eidolon.logger import get_logger
from eidolon.segment import get_completed_segments
from eidolon.utilities import build_lambda_response_pascal
from eidolon.utilities import handle_lambda_error_pascal
from eidolon.utilities import log_lambda_invocation

# Configure logging
logger = get_logger(__name__)


def poll_and_process_segments_business_logic() -> dict:
    """
    Business logic to poll for and process completed segments.

    Returns:
        Dict with processing statistics

    Raises:
        RuntimeError: If database or Lambda operations fail
    """
    # Get completed segments from eidolon library
    completed_segments = get_completed_segments(MAX_SEGMENTS_PER_POLL)

    logger.info("Found completed segments", extra={"count": len(completed_segments)})

    # Process segments based on configuration
    processed_count = 0
    failed_count = 0

    if ENABLE_BATCH_PROCESSING and len(completed_segments) > 0:
        # Process segments in batches
        for i in range(0, len(completed_segments), SEGMENT_BATCH_SIZE):
            batch = completed_segments[i : i + SEGMENT_BATCH_SIZE]

            try:
                result = invoke_process_segments_batch(PROCESS_SEGMENT_FUNCTION, batch)
                processed_count += result["processed"]
                failed_count += result["failed"]
            except RuntimeError as err:
                # If batch fails, fall back to individual processing
                logger.warning(
                    "Batch processing failed, falling back to individual processing",
                    extra={"batch_size": len(batch), "error": str(err)},
                )

                for segment in batch:
                    try:
                        invoke_process_segment(PROCESS_SEGMENT_FUNCTION, segment)
                        processed_count += 1
                    except RuntimeError as err:
                        logger.error(
                            "Failed to process segment individually",
                            extra={"active_segment_id": segment.get("ActiveSegmentID"), "error": str(err)},
                        )
                        failed_count += 1
    else:
        # Process segments individually (original behavior)
        for segment in completed_segments:
            try:
                invoke_process_segment(PROCESS_SEGMENT_FUNCTION, segment)
                processed_count += 1
            except RuntimeError as err:
                # Log but continue processing other segments
                logger.error(
                    "Failed to process segment, continuing with others",
                    extra={"active_segment_id": segment.get("ActiveSegmentID"), "error": str(err)},
                )
                failed_count += 1

    logger.info(
        "Segment polling completed",
        extra={
            "segments_found": len(completed_segments),
            "segments_processed": processed_count,
            "segments_failed": failed_count,
            "batch_processing_enabled": ENABLE_BATCH_PROCESSING,
            "batch_size": SEGMENT_BATCH_SIZE if ENABLE_BATCH_PROCESSING else "N/A",
        },
    )

    return {
        "SegmentsFound": len(completed_segments),
        "SegmentsProcessed": processed_count,
        "SegmentsFailed": failed_count,
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
