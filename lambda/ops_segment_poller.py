"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to poll for completed segments.
Triggered by EventBridge to check active segments that have reached their end time.
"""

import json
import time

import boto3
from botocore.exceptions import ClientError

from eidolon.dynamo import dynamo
from eidolon.dynamo import TableName
from eidolon.environment import PROCESS_SEGMENT_FUNCTION
from eidolon.logger import get_logger
from eidolon.utilities import log_lambda_invocation

# Configure logging
logger = get_logger(__name__)

# Lambda client for invoking process_segment
lambda_client = boto3.client("lambda")


def get_completed_segments() -> list:
    """
    Query for active segments that have reached their end time.

    Returns:
        List of segments ready for processing

    Raises:
        RuntimeError: If database query fails
    """
    current_time = int(time.time())

    try:
        # Query using the CompletionTimeIndex GSI
        items = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="CompletionTimeIndex",
            KeyConditionExpression="#status = :status AND EndTime <= :current_time",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={":status": "active", ":current_time": current_time},
            Limit=50,  # Process up to 50 segments per invocation
        )
        return items  # type: ignore
    except ClientError as err:
        logger.error(
            "Failed to query completed segments",
            extra={
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown")
            },
            exc_info=True
        )
        raise RuntimeError(f"Failed to query completed segments: {str(err)}")


def invoke_process_segment(segment: dict) -> None:
    """
    Invoke the process_segment Lambda for a completed segment.

    Args:
        segment: Active segment data to process

    Raises:
        RuntimeError: If Lambda invocation fails
    """
    # Prepare payload for process_segment Lambda
    payload = {
        "activeSegmentId": segment.get("ActiveSegmentID"),
        "characterId": segment.get("CharacterID"),
        "storyId": segment.get("StoryID"),
        "segmentId": segment.get("SegmentID"),
        "segmentType": segment.get("SegmentType"),
    }

    try:
        # Invoke Lambda asynchronously
        response = lambda_client.invoke(
            FunctionName=PROCESS_SEGMENT_FUNCTION,
            InvocationType="Event",
            Payload=json.dumps(payload),  # Asynchronous invocation
        )

        logger.info(
            "Invoked process_segment Lambda",
            extra={
                "active_segment_id": segment.get("ActiveSegmentID"),
                "status_code": response.get("StatusCode"),
            },
        )

    except ClientError as err:
        logger.error(
            "Failed to invoke process_segment Lambda",
            extra={
                "active_segment_id": segment.get("ActiveSegmentID"),
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown")
            },
            exc_info=True
        )
        raise RuntimeError(f"Failed to invoke process_segment Lambda: {str(err)}")
    except Exception as err:
        logger.error(
            "Unexpected error invoking process_segment Lambda",
            extra={
                "active_segment_id": segment.get("ActiveSegmentID"),
                "error": str(err),
            },
            exc_info=True
        )
        raise RuntimeError(f"Failed to invoke process_segment Lambda: {str(err)}")


def poll_and_process_segments() -> dict:
    """
    Business logic to poll for and process completed segments.

    Returns:
        Dict with processing statistics

    Raises:
        RuntimeError: If database or Lambda operations fail
    """
    # Get completed segments
    completed_segments = get_completed_segments()

    logger.info(
        "Found completed segments", extra={"count": len(completed_segments)}
    )

    # Process each completed segment
    processed_count = 0
    failed_count = 0
    
    for segment in completed_segments:
        try:
            invoke_process_segment(segment)
            processed_count += 1
        except RuntimeError as err:
            # Log but continue processing other segments
            logger.error(
                "Failed to process segment, continuing with others",
                extra={
                    "active_segment_id": segment.get("ActiveSegmentID"),
                    "error": str(err)
                }
            )
            failed_count += 1

    logger.info(
        "Segment polling completed",
        extra={
            "segments_found": len(completed_segments),
            "segments_processed": processed_count,
            "segments_failed": failed_count,
        },
    )

    return {
        "segmentsFound": len(completed_segments),
        "segmentsProcessed": processed_count,
        "segmentsFailed": failed_count,
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
        result = poll_and_process_segments()

        # Build response
        response = {
            "statusCode": 200,
            "body": {
                "message": "Segment polling completed",
                **result
            },
        }

        logger.info("Lambda response", extra={"status_code": 200})
        return response

    except RuntimeError as err:
        logger.error(
            "Failed to poll segments",
            extra={"error": str(err)},
        )
        return {
            "statusCode": 500,
            "body": {"error": "Failed to poll segments", "message": str(err)},
        }
    except Exception as err:
        logger.error(
            "Unexpected error in lambda_handler",
            extra={"error": str(err)},
            exc_info=True,
        )
        return {
            "statusCode": 500,
            "body": {"error": "Internal server error", "message": str(err)},
        }
