"""
Segment polling support functions.

Provides functions for the segment processing poller.
"""

from botocore.exceptions import ClientError

from eidolon.constants import SEGMENT_RETRY_MIN_REMAINING_SECONDS, SEGMENT_STUCK_RETRY_SECONDS
from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger
from eidolon.state_machines import claim_segment_for_processing as state_machine_claim
from eidolon.time_utils import now_unix


def get_segments_approaching_expiry(max_segments: int) -> list:
    """
    Get ALL segments that will expire within 60 seconds.
    These need advancement (if processed) or recovery (if not processed).

    Args:
        max_segments: Maximum number of segments to retrieve

    Returns:
        List of segment records approaching expiry
    """
    current_time = now_unix()
    next_poll_buffer = current_time + 60

    try:
        segments: list = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="EndTimeIndex",
            KeyConditionExpression="#status = :status AND EndTime < :threshold",
            # NO ProcessingStatus filter - get ALL segments approaching expiry
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={
                ":status": "active",
                ":threshold": next_poll_buffer,
            },
            Limit=max_segments,
        )  # type: ignore
        logger.info(f"Found {len(segments)} segments approaching expiry")
        return segments

    except ClientError as err:
        logger.error(f"Failed to query segments approaching expiry Error: {err}", exc_info=True)
        raise  # Let Lambda retry


def get_stuck_mechanical_segments(max_segments: int) -> list:
    """
    Get mechanical segments stuck in pending/processing that have time to retry.

    Criteria:
    - StartTime more than SEGMENT_STUCK_RETRY_SECONDS ago (a worker normally
      finishes within seconds of StartTime, so the message was lost or the
      worker died)
    - EndTime more than SEGMENT_RETRY_MIN_REMAINING_SECONDS from now (enough
      time to process before expiry)
    - ProcessingStatus in (pending, processing)
    - SegmentType = mechanical

    Segments too short to ever satisfy both bounds are recovered at expiry
    instead: the poller requeues them once, then resolves them with the
    exceptional outcome (see ops_segment_poller).

    Args:
        max_segments: Maximum number of segments to retrieve

    Returns:
        List of stuck mechanical segment records
    """
    current_time = now_unix()
    stuck_cutoff = current_time - SEGMENT_STUCK_RETRY_SECONDS
    min_remaining_cutoff = current_time + SEGMENT_RETRY_MIN_REMAINING_SECONDS

    try:
        # Use scan since we need to filter on StartTime which isn't indexed
        response = dynamo.scan(
            TableName.ACTIVE_SEGMENTS,
            FilterExpression=(
                "#status = :status AND "
                "SegmentType = :mechanical AND "
                "StartTime < :old_time AND "
                "EndTime > :min_time AND "
                "ProcessingStatus IN (:pending, :processing)"
            ),
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={
                ":status": "active",
                ":mechanical": "mechanical",
                ":old_time": stuck_cutoff,
                ":min_time": min_remaining_cutoff,
                ":pending": "pending",
                ":processing": "processing",
            },
            Limit=max_segments,
        )

        segments = response.get("items", [])  # type: ignore
        logger.info(f"Found {len(segments)} stuck mechanical segments with time to retry")
        return segments

    except ClientError as err:
        logger.error(f"Failed to query stuck mechanical segments Error: {err}", exc_info=True)
        raise  # Let Lambda retry


def check_active_segments_exist() -> bool:
    """
    Check if any active segments exist in the system.

    Returns:
        True if active segments exist, False otherwise
    """
    try:
        segments: list = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="EndTimeIndex",
            KeyConditionExpression="#status = :status",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={":status": "active"},
            Limit=1,
        )  # type: ignore

        return len(segments) > 0

    except ClientError as err:
        logger.error(f"Failed to check for active segments Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to check for active segments: {err}") from err


def delete_active_segment(active_segment_id: str) -> None:
    """
    Delete an active segment from the database.

    Args:
        active_segment_id: Active segment UUID

    Raises:
        RuntimeError: If database operation fails
    """
    try:
        dynamo.delete_item(TableName.ACTIVE_SEGMENTS, Key={"ActiveSegmentID": active_segment_id})
        logger.info(f"Deleted active segment for {active_segment_id}")
    except ClientError as err:
        logger.error(f"Failed to delete active segment for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to delete active segment: {err}") from err


def get_active_segment_info(active_segment_id: str) -> dict:
    """
    Get active segment info for API response.

    Args:
        active_segment_id: Active segment UUID

    Returns:
        Active segment info with client-safe fields

    Raises:
        ValueError: If segment not found
        RuntimeError: If database operation fails
    """
    try:
        segment = dynamo.get_item(TableName.ACTIVE_SEGMENTS, {"ActiveSegmentID": active_segment_id})

        if not segment:
            raise ValueError(f"Active segment not found: {active_segment_id}")

        return {
            "ActiveSegmentID": segment.get("ActiveSegmentID"),
            "SegmentID": segment.get("SegmentID"),
            "SegmentType": segment.get("SegmentType"),
            "StartTime": segment.get("StartTime"),
            "EndTime": segment.get("EndTime"),
            "Status": segment.get("Status"),
            "Outcome": segment.get("Outcome"),
            "Decision": segment.get("Decision"),
            "DecisionOptions": segment.get("DecisionOptions", {}),
        }

    except ClientError as err:
        logger.error(f"Failed to get active segment info for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get active segment info: {err}") from err


def claim_segment_for_processing(active_segment_id: str) -> bool:
    """
    Attempt to claim a segment for processing using optimistic locking.

    Delegates to state machine implementation for atomic transition.

    Args:
        active_segment_id: Active segment UUID

    Returns:
        True if successfully claimed, False if already being processed
    """
    return state_machine_claim(active_segment_id)
