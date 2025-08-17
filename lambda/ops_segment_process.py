"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to process completed mechanical segments.
Triggered by SQS to process mechanical segments only.
Rest and Decision segments are handled directly by the poller.
"""

import json

from eidolon.logger import log_lambda_statistics, logger
from eidolon.responses import lambda_error, lambda_response
from eidolon.segment import is_mechanical_segment, process_segment_completely
from eidolon.validation_messages import validate_processing_message


def validate_segment_for_processing(segment_type: str) -> bool:
    """
    Validate that the segment type should be processed by this handler.

    Args:
        segment_type: Type of segment

    Returns:
        True if segment should be processed, False otherwise
    """
    # Only mechanical segments should be processed by this handler
    # Rest and Decision segments are handled directly by the poller
    return is_mechanical_segment(segment_type)


def process_segment_business_logic(
    active_segment_id: str,
    character_id: str,
    story_id: str,
    segment_id: str,
    segment_type: str,
) -> dict:
    """
    Business logic for processing a completed mechanical segment.

    Args:
        active_segment_id: Active segment UUID
        character_id: Character UUID
        story_id: Story UUID
        segment_id: Segment UUID
        segment_type: Type of segment

    Returns:
        Dict with outcome and next segment ID

    Raises:
        ValueError: If required data not found or invalid segment type
        RuntimeError: If database operations fail
    """
    # Validate segment type
    if not validate_segment_for_processing(segment_type):
        logger.warning(f"Invalid segment type for mechanical processing for {active_segment_id}")
        raise ValueError(f"Segment type '{segment_type}' should not be processed by this handler")

    # Log processing details
    logger.info(f"Processing mechanical segment for {active_segment_id}")

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

    logger.info(f"Processing segment batch for {len(segments)}")

    for segment_data in segments:
        try:
            active_segment_id = segment_data.get("ActiveSegmentID")
            character_id = segment_data.get("CharacterID")
            story_id = segment_data.get("StoryID")
            segment_id = segment_data.get("SegmentID")
            segment_type = segment_data.get("SegmentType")

            logger.info(f"Processing segment in batch for {active_segment_id}")

            result = process_segment_business_logic(active_segment_id, character_id, story_id, segment_id, segment_type)

            results.append(
                {
                    "SegmentID": active_segment_id,
                    "Success": True,
                    "Outcome": result.get("outcome"),
                    "NextSegment": result.get("nextSegment"),
                }
            )
            success_count += 1

        except Exception as err:
            logger.error(
                f"Failed to process segment in batch for {segment_data.get('ActiveSegmentID')} Error: {err}",
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

    logger.info(f"Batch processing completed for {len(segments)}")

    return {
        "Message": "Batch processing completed",
        "BatchSize": len(segments),
        "SuccessCount": success_count,
        "FailureCount": failure_count,
        "Results": results,
    }


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to process completed mechanical segments.

    Triggered by SQS to handle mechanical segments only.
    Rest and Decision segments are processed directly by the poller.

    Args:
        event: SQS event with segment data or direct invocation event
        context: Lambda context

    Returns:
        For SQS: batchItemFailures response
        For direct: Processing result with outcome
    """
    # Log invocation
    log_lambda_statistics(event, context)

    # Check if this is an SQS event
    if "Records" in event:
        # SQS batch event
        success_count = 0
        failure_count = 0
        invalid_count = 0
        batch_item_failures = []

        for record in event.get("Records", []):
            message_id = record.get("messageId", "unknown")

            try:
                # Parse message body
                message_body = json.loads(record.get("body", "{}"))

                # Validate message schema
                try:
                    validated_msg = validate_processing_message(message_body)
                except ValueError as validation_err:
                    # Invalid message - log and don't retry
                    logger.error(f"Invalid message schema for messageId={message_id}: {validation_err}")
                    invalid_count += 1
                    # Don't add to batch_item_failures - invalid messages should not be retried
                    continue

                # Extract validated segment data
                active_segment_id = validated_msg["ActiveSegmentID"]
                character_id = validated_msg["CharacterID"]
                story_id = validated_msg["StoryID"]
                segment_id = validated_msg["SegmentID"]
                segment_type = validated_msg["SegmentType"]

                # Check if segment type should be processed by this handler
                if not validate_segment_for_processing(segment_type):
                    logger.info(f"Skipping non-mechanical segment from SQS for {active_segment_id}: type={segment_type}")
                    # Don't fail the message, just skip it
                    success_count += 1
                    continue

                logger.info(f"Processing SQS message for {active_segment_id}")

                # Process the segment
                result = process_segment_business_logic(
                    active_segment_id=active_segment_id,
                    character_id=character_id,
                    story_id=story_id,
                    segment_id=segment_id,
                    segment_type=segment_type,
                )

                success_count += 1
                
                # No polling management needed here per design
                # ops-story-advance and ops-segment-poller handle all polling state

            except Exception as err:
                logger.error(
                    f"Failed to process SQS message Error: {err}",
                    exc_info=True,
                )
                failure_count += 1
                # Add to batch item failures for SQS retry
                batch_item_failures.append({"itemIdentifier": message_id})

        # Log summary
        if invalid_count > 0:
            logger.warning(f"Batch processing summary: Success={success_count}, Failed={failure_count}, Invalid={invalid_count}")
        else:
            logger.info(f"Batch processing summary: Success={success_count}, Failed={failure_count}")

        return {"batchItemFailures": batch_item_failures}

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

            logger.info(f"Processing single segment (direct invocation) for {active_segment_id}")

            # Call business logic
            result = process_segment_business_logic(active_segment_id, character_id, story_id, segment_id, segment_type)

            response_data = {
                "Message": "Segment processed successfully",
                "Outcome": result.get("outcome"),
                "NextSegment": result.get("nextSegment"),
            }

            return lambda_response(200, response_data, event)

        except ValueError as err:
            logger.error(
                f"Invalid request Error: {err}",
                exc_info=True,
            )
            return lambda_response(400, {"Error": str(err)}, event)
        except RuntimeError as err:
            logger.error(
                f"Failed to process segment Error: {err}",
                exc_info=True,
            )
            return lambda_response(500, {"Error": "Internal server error"}, event)
        except Exception as err:
            return lambda_error(event, err)
