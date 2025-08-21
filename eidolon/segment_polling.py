"""
Segment polling support functions.

Provides functions for the segment processing poller.
"""

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger
from eidolon.time_utils import now_unix


def get_completed_segments(max_segments: int) -> list:
    """
    Get segments that have completed their timer period.

    Finds segments that are:
    - Status = 'active'
    - ProcessingStatus = 'processed'
    - EndTime < current time

    Args:
        max_segments: Maximum number of segments to retrieve

    Returns:
        List of completed segment records
    """
    current_time = now_unix()

    try:
        response = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="StatusEndTimeIndex",
            KeyConditionExpression="Status = :status AND EndTime < :current_time",
            FilterExpression="ProcessingStatus = :proc_status",
            ExpressionAttributeValues={
                ":status": "active",
                ":current_time": current_time,
                ":proc_status": "processed",
            },
            Limit=max_segments,
        )

        segments = response.get("Items", []) # type: ignore
        logger.info(f"Found {len(segments)} completed segments ready for advancement")
        return segments

    except ClientError as err:
        logger.error(f"Failed to query completed segments Error: {err}", exc_info=True)
        return []


def check_active_segments_exist() -> bool:
    """
    Check if any active segments exist in the system.

    Returns:
        True if active segments exist, False otherwise
    """
    try:
        response = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="StatusEndTimeIndex",
            KeyConditionExpression="Status = :status",
            ExpressionAttributeValues={":status": "active"},
            Limit=1,
        )

        return len(response.get("Items", [])) > 0 # type: ignore

    except ClientError as err:
        logger.error(f"Failed to check for active segments Error: {err}", exc_info=True)
        return False


def delete_active_segment(active_segment_id: str) -> None:
    """
    Delete an active segment from the database.

    Args:
        active_segment_id: Active segment UUID

    Raises:
        RuntimeError: If database operation fails
    """
    try:
        dynamo.delete_item(TableName.ACTIVE_SEGMENTS, {"ActiveSegmentID": active_segment_id})
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

    Args:
        active_segment_id: Active segment UUID

    Returns:
        True if successfully claimed, False if already being processed
    """
    try:
        dynamo.update_item(
            TableName.ACTIVE_SEGMENTS,
            Key={"ActiveSegmentID": active_segment_id},
            UpdateExpression="SET RunningFlag = :true",
            ConditionExpression="attribute_exists(ActiveSegmentID) AND (attribute_not_exists(RunningFlag) OR RunningFlag = :false)",
            ExpressionAttributeValues={":true": True, ":false": False},
        )
        logger.info(f"Successfully claimed segment for processing for {active_segment_id}")
        return True
    except ClientError as err:
        if err.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logger.info(f"Segment already being processed for {active_segment_id}")
            return False
        logger.error(f"Failed to claim segment for processing for {active_segment_id} Error: {err}", exc_info=True)
        return False