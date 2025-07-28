"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to process a completed segment.
Determines outcome, applies effects, and creates next segment if applicable.
"""

import json

from eidolon.environment import SSM_POLLER_STATE_PARAMETER
from eidolon.logger import get_logger
from eidolon.segment import check_active_segments_exist, process_segment_completely
from eidolon.ssm import put_parameter
from eidolon.utilities import build_lambda_response_pascal, handle_lambda_error_pascal, log_lambda_invocation

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
    Now handles SQS events instead of direct invocation.

    Args:
        event: SQS event or direct invocation event
        context: Lambda context

    Returns:
        Processing result
    """
    # Log invocation
    log_lambda_invocation(context, event)
    
    # Check if this is an SQS event
    if "Records" in event:
        # SQS batch event
        success_count = 0
        failure_count = 0
        batch_item_failures = []
        
        for record in event["Records"]:
            try:
                # Parse message body
                message_body = json.loads(record["body"])
                
                # Extract segment data
                active_segment_id = message_body.get("ActiveSegmentID", "")
                character_id = message_body.get("CharacterID")
                story_id = message_body.get("StoryID")
                segment_id = message_body.get("SegmentID")
                segment_type = message_body.get("SegmentType")
                
                if not all([active_segment_id, character_id, story_id, segment_id, segment_type]):
                    raise ValueError("Missing required segment data")
                
                logger.info(
                    "Processing SQS message",
                    extra={
                        "message_id": record.get("messageId"),
                        "active_segment_id": active_segment_id,
                        "segment_type": segment_type,
                    },
                )
                
                # Process the segment
                result = process_segment_business_logic(
                    active_segment_id=active_segment_id,
                    character_id=character_id,
                    story_id=story_id,
                    segment_id=segment_id,
                    segment_type=segment_type,
                )
                
                success_count += 1
                
                # If no next segment (story complete), check if we should update SSM
                if not result.get("nextSegment"):
                    # Check if any active segments remain
                    has_active_segments = check_active_segments_exist()
                    
                    if not has_active_segments:
                        # No more active segments, update SSM to stop polling
                        try:
                            put_parameter(SSM_POLLER_STATE_PARAMETER, "stop")
                            logger.info("Updated SSM poller state to stop - no active segments")
                        except Exception as ssm_err:
                            logger.warning(
                                "Failed to update SSM parameter",
                                extra={"error": str(ssm_err)},
                            )
                
            except Exception as err:
                logger.error(
                    "Failed to process SQS message",
                    extra={
                        "message_id": record.get("messageId"),
                        "error": str(err),
                    },
                    exc_info=True,
                )
                failure_count += 1
                # Add to batch item failures for SQS retry
                batch_item_failures.append({
                    "itemIdentifier": record["messageId"]
                })
        
        # Return response for SQS batch processing
        logger.info(
            "SQS batch processing completed",
            extra={
                "success_count": success_count,
                "failure_count": failure_count,
            },
        )
        
        return {
            "batchItemFailures": batch_item_failures
        }
    
    # Legacy direct invocation support (for testing)
    else:
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
                "Processing single segment (direct invocation)",
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
