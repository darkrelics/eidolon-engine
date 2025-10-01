"""
Message validation utilities for SQS queue messages.

Provides validation functions for messages sent to the segment processing
and story advancement queues to ensure required fields are present.
"""

from eidolon.logger import logger


def validate_advancement_message(msg: dict) -> dict:
    """
    Validate a message for the story advancement queue.

    Ensures the ActiveSegmentID is present for story advancement.

    Args:
        msg: Message dictionary from SQS

    Returns:
        The validated message dictionary

    Raises:
        ValueError: If ActiveSegmentID is missing
    """
    if not msg.get("ActiveSegmentID"):
        raise ValueError("Missing required field: ActiveSegmentID")

    # Log optional fields if present for debugging
    optional_fields = ["CharacterID", "StoryID", "SegmentID"]
    present_optional = [k for k in optional_fields if msg.get(k)]
    if present_optional:
        logger.debug(f"Optional fields present in advancement message: {', '.join(present_optional)}")

    return msg
