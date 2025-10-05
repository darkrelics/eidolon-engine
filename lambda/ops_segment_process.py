"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to process segments.
Triggered by SQS with ActiveSegmentID messages.
"""

from eidolon.character_data import get_character
from eidolon.logger import log_lambda_statistics, logger
from eidolon.responses import lambda_response
from eidolon.segment_core import get_active_segment, get_segment_definition
from eidolon.segment_polling import claim_segment_for_processing
from eidolon.segment_processing import route_segment_processing
from eidolon.segment_state import update_active_segment_outcome
from eidolon.validation import validate_uuid


def process_segment(active_segment: dict) -> None:
    """
    Orchestrate segment processing.

    Args:
        active_segment: Active segment record

    Raises:
        ValueError: If data validation fails
        RuntimeError: If processing fails
    """
    active_segment_id = active_segment.get("ActiveSegmentID")

    # Check idempotency
    if active_segment.get("ProcessingStatus") == "processed":
        logger.info(f"Segment already processed: {active_segment_id}")
        return

    # Claim the segment for processing (atomic operation)
    if not claim_segment_for_processing(active_segment_id):  # type: ignore
        logger.info(f"Segment already being processed by another worker: {active_segment_id}")
        return

    # Get segment definition
    try:
        segment_def = get_segment_definition(
            active_segment.get("StoryID"),  # type: ignore
            active_segment.get("SegmentID"),  # type: ignore
        )
    except (ValueError, RuntimeError) as err:
        logger.error(f"Failed to get segment definition for {active_segment.get('SegmentID')}: {err}", exc_info=True)
        raise

    # Get character
    character = get_character(active_segment.get("CharacterID"))  # type: ignore

    # Process based on type
    outcome, results = route_segment_processing(segment_def, character, active_segment)

    # Persist results
    try:
        update_active_segment_outcome(active_segment_id, outcome, results, segment_def)  # type: ignore
    except (ValueError, RuntimeError) as err:
        logger.error(f"Failed to update segment outcome for {active_segment_id}: {err}", exc_info=True)
        raise

    logger.info(f"Segment {active_segment_id} processed with outcome: {outcome}")


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to process segments.

    Triggered by SQS with ActiveSegmentID messages.
    Processes all segment types (mechanical, decision).

    Args:
        event: SQS event with ActiveSegmentID messages
        context: Lambda context

    Returns:
        Lambda response with processing status
    """
    # Log invocation
    log_lambda_statistics(event, context)

    # Check if this is an SQS event
    if "Records" not in event:
        # Not an SQS event
        return lambda_response(400, {"Error": "Invalid event format"}, event)

    for record in event.get("Records", []):
        message_id = record.get("messageId", "unknown")

        # Parse message body
        active_segment_id = record.get("body", "").strip()

        if not active_segment_id:
            logger.warning(f"Empty message body for messageId={message_id}")
            continue

        # Validate UUID format
        if not validate_uuid(active_segment_id):
            logger.warning(f"Invalid UUID format for messageId={message_id}: {active_segment_id}")
            continue

        # Fetch the full active segment record from DynamoDB
        try:
            active_segment = get_active_segment(active_segment_id)
        except ValueError as err:
            logger.warning(f"Active segment {active_segment_id} not found: {err}")
            # Don't retry - segment doesn't exist
            continue
        except RuntimeError as err:
            logger.error(f"Database error fetching active segment {active_segment_id}: {err}")
            # Don't retry - DB errors need investigation
            continue

        logger.info(f"Processing segment: {active_segment_id}")

        # Process the segment
        try:
            process_segment(active_segment)
        except Exception as err:
            logger.error(f"Failed to process segment {active_segment_id}: {err}", exc_info=True)
            # Continue - poller will handle cleanup

    # Return empty dict for successful SQS batch processing
    return {}
