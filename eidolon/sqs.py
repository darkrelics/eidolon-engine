"""
SQS queue utilities for Lambda functions.

Provides functions for sending messages to SQS queues.
"""

import json

import boto3
from botocore.exceptions import ClientError

from eidolon.environment import SEGMENT_QUEUE_URL
from eidolon.logger import logger

sqs_client = boto3.client("sqs")


def send_message(queue_url: str, message_body, message_attributes=None) -> str:
    """
    Send a single message to an SQS queue.

    Args:
        queue_url: URL of the SQS queue
        message_body: Message body (dict will be JSON encoded, string sent as-is)
        message_attributes: Optional message attributes

    Returns:
        Message ID of the sent message

    Raises:
        RuntimeError: If SQS operation fails
    """
    try:
        # Handle both dict and string message bodies
        if isinstance(message_body, dict):
            body = json.dumps(message_body)
        else:
            body = str(message_body)
            
        params = {
            "QueueUrl": queue_url,
            "MessageBody": body,
        }

        if message_attributes:
            params["MessageAttributes"] = message_attributes

        response = sqs_client.send_message(**params)

        message_id = response.get("MessageId")
        logger.debug(f"Message sent to SQS for {queue_url}")
        return message_id

    except ClientError as err:
        logger.error(f"Failed to send message to SQS for {queue_url} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to send message to SQS: {err}") from err


def send_message_batch(queue_url: str, messages: list) -> dict:
    """
    Send multiple messages to an SQS queue in a batch.

    Args:
        queue_url: URL of the SQS queue
        messages: List of message dicts, each with 'body' and optional 'attributes'

    Returns:
        Dict with successful and failed message counts

    Raises:
        RuntimeError: If SQS operation fails
    """
    try:
        # Prepare batch entries
        entries = []
        for i, msg in enumerate(messages):
            entry = {
                "Id": str(i),
                "MessageBody": json.dumps(msg.get("body")),
            }
            if "attributes" in msg:
                entry["MessageAttributes"] = msg.get("attributes")
            entries.append(entry)

        # Send in batches of 10 (SQS limit)
        successful = 0
        failed = 0

        for i in range(0, len(entries), 10):
            batch = entries[i : i + 10]
            response = sqs_client.send_message_batch(QueueUrl=queue_url, Entries=batch)

            successful += len(response.get("Successful", []))
            failed += len(response.get("Failed", []))

            if response.get("Failed"):
                logger.warning(f"Some messages failed to send for {queue_url}")

        logger.info(f"Batch messages sent to SQS for {queue_url}")

        return {"successful": successful, "failed": failed}

    except ClientError as err:
        logger.error(f"Failed to send batch messages to SQS for {queue_url} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to send batch messages to SQS: {err}") from err


def queue_segment_for_processing(active_segment: dict) -> None:
    """
    Queue mechanical segment to SQS for processing.

    Args:
        active_segment: Active segment record containing segment details
        
    Raises:
        RuntimeError: If SEGMENT_QUEUE_URL not configured
    """
    if not SEGMENT_QUEUE_URL:
        logger.error("SEGMENT_QUEUE_URL not configured")
        raise RuntimeError("Segment processing queue not configured")

    active_segment_id = active_segment.get("ActiveSegmentID", "")
    
    try:
        # Send just the ActiveSegmentID as plain text
        send_message(SEGMENT_QUEUE_URL, active_segment_id)
        logger.info(f"Queued mechanical segment for processing for {active_segment_id}")
    except RuntimeError as err:
        # Non-critical - segment will be picked up by ops-segment-poller
        logger.warning(f"Failed to queue segment for processing for {active_segment_id} Error: {err}")
