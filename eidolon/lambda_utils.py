"""
Lambda invocation utilities for Lambda functions.

Provides functions for invoking other Lambda functions.
"""

import json

import boto3
from botocore.exceptions import ClientError

from eidolon.logger import logger

# Lambda client for invoking functions
lambda_client = boto3.client("lambda")


def invoke_lambda_async(function_name: str, payload: dict) -> None:
    """
    Invoke a Lambda function asynchronously.

    Args:
        function_name: Name of the Lambda function to invoke
        payload: Payload to send to the Lambda function

    Raises:
        RuntimeError: If Lambda invocation fails
    """
    try:
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="Event",  # Asynchronous invocation
            Payload=json.dumps(payload),
        )

        logger.info(
            "Invoked Lambda function",
            extra={
                "function_name": function_name,
                "status_code": response.get("StatusCode"),
            },
        )

    except ClientError as err:
        logger.error(
            "Failed to invoke Lambda function",
            extra={
                "function_name": function_name,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to invoke Lambda function: {err}")
    except Exception as err:
        logger.error(
            "Unexpected error invoking Lambda function",
            extra={
                "function_name": function_name,
                "error": str(err),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to invoke Lambda function: {err}")


def invoke_process_segment(function_name: str, segment: dict) -> None:
    """
    Invoke the process_segment Lambda for a completed segment.

    Args:
        function_name: Name of the process_segment Lambda function
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

    logger.debug(
        "Invoking process_segment Lambda",
        extra={"active_segment_id": segment.get("ActiveSegmentID")},
    )

    invoke_lambda_async(function_name, payload)


def invoke_process_segments_batch(function_name: str, segments: list) -> dict:
    """
    Invoke process_segment Lambda with a batch of segments.

    Args:
        function_name: Name of the process_segment Lambda function
        segments: List of segments to process as a batch

    Returns:
        Dict with processed and failed counts

    Raises:
        RuntimeError: If Lambda invocation fails
    """
    # Prepare batch payload
    payload = {
        "segments": [
            {
                "activeSegmentId": seg.get("ActiveSegmentID"),
                "characterId": seg.get("CharacterID"),
                "storyId": seg.get("StoryID"),
                "segmentId": seg.get("SegmentID"),
                "segmentType": seg.get("SegmentType"),
            }
            for seg in segments
        ]
    }

    logger.debug(
        "Invoking batch process_segment Lambda",
        extra={
            "batch_size": len(segments),
            "segment_ids": [s.get("ActiveSegmentID") for s in segments],
        },
    )

    invoke_lambda_async(function_name, payload)

    # Since async invocation doesn't return results immediately,
    # we assume success if no exception was raised
    return {"processed": len(segments), "failed": 0}
