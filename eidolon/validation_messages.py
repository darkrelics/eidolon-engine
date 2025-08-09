"""
Message validation utilities for SQS queue messages.

Provides validation functions for messages sent to the segment processing
and story advancement queues to ensure required fields are present.
"""

from eidolon.logger import logger


def validate_processing_message(msg: dict) -> dict:
    """
    Validate a message for the segment processing queue.

    Ensures all required fields are present for mechanical segment processing.

    Args:
        msg: Message dictionary from SQS

    Returns:
        The validated message dictionary

    Raises:
        ValueError: If required fields are missing or invalid
    """
    # Check for required fields
    required = ["ActiveSegmentID", "CharacterID", "StoryID", "SegmentID", "SegmentType"]
    missing = [k for k in required if not msg.get(k)]

    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")

    # Validate SegmentType is one of the expected values
    segment_type = str(msg.get("SegmentType", "")).lower()
    if segment_type not in ["mechanical", "decision", "rest"]:
        raise ValueError(f"Invalid SegmentType '{msg.get('SegmentType')}': must be one of mechanical, decision, or rest")

    return msg


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


def validate_batch_messages(messages: list, validator_func) -> tuple:
    """
    Validate a batch of messages and separate valid from invalid.

    Args:
        messages: List of message dictionaries
        validator_func: Validation function to apply to each message

    Returns:
        Tuple of (valid_messages, invalid_messages) where invalid_messages
        contains tuples of (message, error_string)
    """
    valid = []
    invalid = []

    for msg in messages:
        try:
            validated = validator_func(msg)
            valid.append(validated)
        except ValueError as err:
            invalid.append((msg, str(err)))

    return valid, invalid
