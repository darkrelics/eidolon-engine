"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to process a completed segment.
Determines outcome, applies effects, and creates next segment if applicable.
"""

from eidolon.logger import get_logger
from eidolon.segment import process_segment_completely
from eidolon.utilities import build_lambda_response_pascal
from eidolon.utilities import handle_lambda_error_pascal
from eidolon.utilities import log_lambda_invocation

# Configure logging
logger = get_logger(__name__)


def process_segment_business_logic(
    active_segment_id: str,
    character_id: str,
    story_id: str,
    segment_id: str,
    segment_type: str,
) -> dict:
    """
    Business logic for processing a completed segment.

    Args:
        active_segment_id: Active segment UUID
        character_id: Character UUID
        story_id: Story UUID
        segment_id: Segment UUID
        segment_type: Type of segment

    Returns:
        Dict with outcome and next segment ID

    Raises:
        ValueError: If required data not found
        RuntimeError: If database operations fail
    """
    # Use the eidolon library to process the segment
    return process_segment_completely(active_segment_id, character_id, story_id, segment_id, segment_type)


def process_segments_batch(segments: list) -> dict:
    """
    Process multiple segments in a single invocation.

    Args:
        segments: List of segment data dictionaries

    Returns:
        Dict with batch processing results
    """
    results = []
    success_count = 0
    failure_count = 0

    logger.info("Processing segment batch", extra={"batch_size": len(segments)})

    for segment_data in segments:
        try:
            active_segment_id = segment_data.get("ActiveSegmentID")
            character_id = segment_data.get("CharacterID")
            story_id = segment_data.get("StoryID")
            segment_id = segment_data.get("SegmentID")
            segment_type = segment_data.get("SegmentType")

            logger.info(
                "Processing segment in batch",
                extra={
                    "active_segment_id": active_segment_id,
                    "segment_type": segment_type,
                },
            )

            result = process_segment_business_logic(
                active_segment_id, character_id, story_id, segment_id, segment_type  # type: ignore
            )

            results.append(
                {
                    "SegmentID": active_segment_id,
                    "Success": True,
                    "Outcome": result["outcome"],
                    "NextSegment": result["nextSegment"],
                }
            )
            success_count += 1

        except Exception as err:
            logger.error(
                "Failed to process segment in batch",
                extra={
                    "active_segment_id": segment_data.get("ActiveSegmentID"),
                    "error": str(err),
                },
                exc_info=True,
            )
            results.append(
                {
                    "SegmentID": segment_data.get("ActiveSegmentID"),
                    "Success": False,
                    "Error": str(err),
                }
            )
            failure_count += 1

    logger.info(
        "Batch processing completed",
        extra={
            "batch_size": len(segments),
            "success_count": success_count,
            "failure_count": failure_count,
        },
    )

    return {
        "Message": "Batch processing completed",
        "BatchSize": len(segments),
        "SuccessCount": success_count,
        "FailureCount": failure_count,
        "Results": results,
    }


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to process completed segments.
    Supports both single segment and batch processing.

    Args:
        event: Event containing segment information or batch of segments
        context: Lambda context

    Returns:
        Processing result
    """
    # Log invocation
    log_lambda_invocation(context, event)

    # Check if this is a batch request
    if "segments" in event:
        try:
            batch_result = process_segments_batch(event["segments"])
            return build_lambda_response_pascal(200, batch_result, event)
        except Exception as err:
            return handle_lambda_error_pascal(err, context, event)

    # Single segment processing (original behavior)
    try:
        # Extract segment information from event
        active_segment_id: str = event.get("ActiveSegmentID", "")
        character_id = event.get("CharacterID")
        story_id = event.get("StoryID")
        segment_id = event.get("SegmentID")
        segment_type = event.get("SegmentType")

        if not active_segment_id:
            raise ValueError("ActiveSegmentID is required")
        if not character_id:
            raise ValueError("CharacterID is required")
        if not story_id:
            raise ValueError("StoryID is required")
        if not segment_id:
            raise ValueError("SegmentID is required")
        if not segment_type:
            raise ValueError("SegmentType is required")

        logger.info(
            "Processing single segment",
            extra={
                "active_segment_id": active_segment_id,
                "segment_type": segment_type,
            },
        )

        # Call business logic
        result = process_segment_business_logic(active_segment_id, character_id, story_id, segment_id, segment_type)  # type: ignore

        response_data = {
            "Message": "Segment processed successfully",
            "Outcome": result["outcome"],
            "NextSegment": result["nextSegment"],
        }

        logger.info("Lambda response", extra={"status_code": 200})
        return build_lambda_response_pascal(200, response_data, event)

    except ValueError as err:
        logger.error(
            "Invalid request",
            extra={"error": str(err)},
        )
        return build_lambda_response_pascal(400, {"error": str(err)}, event)
    except RuntimeError as err:
        logger.error(
            "Failed to process segment",
            extra={"error": str(err)},
        )
        return build_lambda_response_pascal(500, {"error": "Internal server error"}, event)
    except Exception as err:
        return handle_lambda_error_pascal(err, context, event)
