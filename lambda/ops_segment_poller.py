"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason Robinson

Lambda function to poll for completed segments.
Triggered by EventBridge to check active segments that have reached their end time.
"""

import json
import time

import boto3

from eidolon.dynamo import dynamo
from eidolon.dynamo import TableName
from eidolon.environment import PROCESS_SEGMENT_FUNCTION
from eidolon.logger import get_logger

# Configure logging
logger = get_logger(__name__)

# Lambda client for invoking process_segment
lambda_client = boto3.client("lambda")


def get_completed_segments() -> list:
    """
    Query for active segments that have reached their end time.

    Returns:
        List of segments ready for processing
    """
    current_time = int(time.time())

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


def invoke_process_segment(segment: dict) -> None:
    """
    Invoke the process_segment Lambda for a completed segment.

    Args:
        segment: Active segment data to process
    """
    try:
        # Prepare payload for process_segment Lambda
        payload = {
            "activeSegmentId": segment.get("ActiveSegmentID"),
            "characterId": segment.get("CharacterID"),
            "storyId": segment.get("StoryID"),
            "segmentId": segment.get("SegmentID"),
            "segmentType": segment.get("SegmentType"),
        }

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

    except Exception as err:
        logger.error(
            "Failed to invoke process_segment Lambda",
            extra={
                "active_segment_id": segment.get("ActiveSegmentID"),
                "error": str(err),
            },
        )


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to poll for completed segments.

    Args:
        event: EventBridge event (scheduled)
        context: Lambda context

    Returns:
        Response with processing summary
    """
    # Log Lambda invocation
    if hasattr(context, "aws_request_id"):
        logger.info(
            "Lambda invocation",
            extra={
                "request_id": context.aws_request_id,  # type: ignore
                "function_name": getattr(context, "function_name", "unknown"),
                "event_source": event.get("source", "unknown"),
            },
        )

    try:
        # Get completed segments
        completed_segments = get_completed_segments()

        logger.info(
            "Found completed segments", extra={"count": len(completed_segments)}
        )

        # Process each completed segment
        processed_count = 0
        for segment in completed_segments:
            invoke_process_segment(segment)
            processed_count += 1

        # Build response
        response = {
            "statusCode": 200,
            "body": {
                "message": "Segment polling completed",
                "segmentsFound": len(completed_segments),
                "segmentsProcessed": processed_count,
            },
        }

        logger.info(
            "Segment polling completed",
            extra={
                "segments_found": len(completed_segments),
                "segments_processed": processed_count,
            },
        )

        logger.info("Lambda response", extra={"status_code": 200})
        return response

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
