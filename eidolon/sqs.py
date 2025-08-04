"""
SQS queue utilities for Lambda functions.

Provides functions for sending messages to SQS queues.
"""

import json

import boto3
from botocore.exceptions import ClientError

from eidolon.logger import logger


# Initialize SQS client
sqs_client = boto3.client("sqs")


def send_message(queue_url: str, message_body: dict, message_attributes=None) -> str:
    """
    Send a single message to an SQS queue.

    Args:
        queue_url: URL of the SQS queue
        message_body: Message body as dict (will be JSON encoded)
        message_attributes: Optional message attributes

    Returns:
        Message ID of the sent message

    Raises:
        RuntimeError: If SQS operation fails
    """
    try:
        params = {
            "QueueUrl": queue_url,
            "MessageBody": json.dumps(message_body),
        }

        if message_attributes:
            params["MessageAttributes"] = message_attributes

        response = sqs_client.send_message(**params)

        message_id = response.get("MessageId")
        logger.debug(
            "Message sent to SQS",
            extra={"queue_url": queue_url, "message_id": message_id},
        )
        return message_id

    except ClientError as err:
        logger.error(
            "Failed to send message to SQS",
            extra={
                "queue_url": queue_url,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to send message to SQS: {str(err)}")


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
                logger.warning(
                    "Some messages failed to send",
                    extra={
                        "queue_url": queue_url,
                        "failed_messages": response.get("Failed"),
                    },
                )

        logger.info(
            "Batch messages sent to SQS",
            extra={
                "queue_url": queue_url,
                "successful": successful,
                "failed": failed,
                "total": len(messages),
            },
        )

        return {"successful": successful, "failed": failed}

    except ClientError as err:
        logger.error(
            "Failed to send batch messages to SQS",
            extra={
                "queue_url": queue_url,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to send batch messages to SQS: {str(err)}")
