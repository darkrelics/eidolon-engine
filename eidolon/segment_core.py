"""
Core segment operations and data access.

Provides fundamental functions for accessing and managing segments.
"""

from functools import cache

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, decimal_to_float, dynamo
from eidolon.logger import logger
from eidolon.schema import normalize_segment_definition

# Valid segment types for the incremental game
VALID_SEGMENT_TYPES = ["mechanical", "decision", "rest"]
MECHANICAL_ONLY_TYPES = ["mechanical"]


@cache
def is_mechanical_segment(segment_type: str) -> bool:
    """
    Check if a segment type should be processed as mechanical.

    Mechanical segments include challenges and/or combat and are
    processed by the ops_process_segment Lambda via SQS.

    Args:
        segment_type: Type of segment to check

    Returns:
        True if segment should be processed as mechanical
    """
    return segment_type.lower() in MECHANICAL_ONLY_TYPES


def is_simple_segment(segment_type: str) -> bool:
    """
    Check if a segment type can be processed directly by the poller.

    Simple segments (rest and decision) don't require complex processing
    and can be handled directly without queuing.

    Args:
        segment_type: Type of segment to check

    Returns:
        True if segment can be processed directly
    """
    return segment_type.lower() in ["rest", "decision"]


def get_active_segment(active_segment_id: str) -> dict:
    """
    Get active segment by ID.

    Args:
        active_segment_id: Active segment UUID

    Returns:
        Active segment data

    Raises:
        ValueError: If segment not found
        RuntimeError: If database operation fails
    """
    try:
        active_segment = dynamo.get_item(
            TableName.ACTIVE_SEGMENTS,
            {"ActiveSegmentID": active_segment_id},
        )
        if not active_segment:
            raise ValueError(f"Active segment not found: {active_segment_id}")
        # Convert DynamoDB Decimal values to native Python types
        return decimal_to_float(active_segment)  # type: ignore
    except ClientError as err:
        logger.error(f"Failed to get active segment for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get active segment: {err}") from err


def get_segment_definition(story_id: str, segment_id: str) -> dict:
    """
    Get segment definition from Segments table.

    Args:
        story_id: Story UUID
        segment_id: Segment ID

    Returns:
        Segment definition

    Raises:
        ValueError: If segment not found
        RuntimeError: If database operation fails
    """
    try:
        segment_def = dynamo.get_item(
            TableName.SEGMENTS,
            {"StoryID": story_id, "SegmentID": segment_id},
        )
        if not segment_def:
            raise ValueError(f"Segment definition not found: {segment_id}")
        # Normalize mixed-case inputs from content or tools
        normalized = normalize_segment_definition(segment_def)
        # Skip Pydantic validation for now to preserve normalized structure
        # The normalization already handles the key conversions we need
        results = normalized.get("Results", {})
        logger.info(f"Segment {segment_id} normalized Results keys: {list(results.keys())}")
        # Log the structure of one result to debug
        if results and "Normal" in results:
            normal_result = results["Normal"]
            logger.info(
                f"  'Normal' result keys: {list(normal_result.keys()) if isinstance(normal_result, dict) else 'not a dict'}"
            )
            if isinstance(normal_result, dict) and "NextSegmentID" in normal_result:
                logger.info(f"  'Normal' NextSegmentID: {normal_result['NextSegmentID']}")
        return normalized
    except ClientError as err:
        logger.error(f"Failed to get segment definition for {segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get segment definition: {err}") from err


def get_active_segment_info(active_segment_id: str) -> dict:
    """
    Get active segment information for processing.

    Args:
        active_segment_id: Active segment UUID

    Returns:
        Dict with segment data and metadata

    Raises:
        ValueError: If segment not found or invalid state
        RuntimeError: If database operations fail
    """
    # Get active segment
    active_segment = get_active_segment(active_segment_id)

    # Extract key fields
    story_id = active_segment.get("StoryID")
    segment_id = active_segment.get("SegmentID")
    segment_type = active_segment.get("SegmentType")

    if not story_id or not segment_id:
        raise ValueError(f"Active segment missing required fields: {active_segment_id}")

    # Get segment definition
    segment_def = get_segment_definition(story_id, segment_id)

    return {
        "active_segment": active_segment,
        "segment_def": segment_def,
        "segment_type": segment_type,
        "story_id": story_id,
        "segment_id": segment_id,
    }


def validate_segment_outcome_results(segment: dict, outcome: str) -> dict:
    """
    Validate and extract outcome data from segment Results field.

    Ensures the Results field and its contents are properly structured,
    providing safe defaults when data is missing or malformed.

    Args:
        segment: Segment definition from database
        outcome: Outcome string (e.g., "exceptional", "normal", "failure")

    Returns:
        Dict with validated narrative and effects, guaranteed to have PascalCase keys:
            - Narrative (str): The outcome narrative text
            - Effects (dict): Effects to apply (may be empty)
    """
    results = segment.get("Results")

    if results is None:
        logger.warning(f"Segment has no Results field for {segment.get('SegmentID')}")
        if outcome == "exceptional":
            return {"Narrative": "Your actions exceeded all expectations, achieving extraordinary results.", "Effects": {}}
        return {"Narrative": "", "Effects": {}}

    if not isinstance(results, dict):
        logger.error(f"Results field is not a dictionary for {segment.get('SegmentID')}")
        return {"Narrative": "", "Effects": {}}

    outcome_key = str(outcome).lower() if outcome else "normal"
    outcome_result = results.get(outcome_key)

    if outcome_result is None:
        logger.info(f"No specific result for outcome for {segment.get('SegmentID')}")
        if outcome == "exceptional":
            return {"Narrative": "Your actions exceeded all expectations, achieving extraordinary results.", "Effects": {}}
        return {"Narrative": "", "Effects": {}}

    if not isinstance(outcome_result, dict):
        logger.error(f"Outcome result is not a dictionary for {segment.get('SegmentID')}")
        return {"Narrative": "", "Effects": {}}

    narrative = outcome_result.get("Narrative", "")
    if not isinstance(narrative, str):
        logger.warning(f"Narrative is not a string for {segment.get('SegmentID')}")
    narrative = str(narrative) if narrative else ""

    effects = outcome_result.get("Effects", {})
    if not isinstance(effects, dict):
        logger.warning(f"Effects is not a dictionary for {segment.get('SegmentID')}")
        effects = {}

    return {"Narrative": narrative, "Effects": effects}


def extract_character_updates_from_results(results: dict, segment_def: dict, outcome: str) -> dict:
    """
    Extract all character updates for storage in ActiveSegments.

    Note: XP and wounds are applied immediately to the database during segment processing.
    This function extracts ALL updates for client display and history.

    Args:
        results: Results from segment processing
        segment_def: Segment definition containing outcome effects
        outcome: The calculated outcome

    Returns:
        Dict containing all character updates
    """
    updates = {}

    xp_updates = results.get("xpUpdates")
    if xp_updates:
        updates.update(xp_updates)

    wound_updates = results.get("woundUpdates")
    if wound_updates:
        updates.update(wound_updates)

    combat_state = results.get("combatState", {})
    if combat_state.get("opponentDefeated"):
        opponent_id = combat_state.get("opponentId")
        if opponent_id:
            try:
                opponent_data = dynamo.get_item(TableName.OPPONENTS, {"OpponentID": opponent_id})
                if opponent_data:
                    updates["CombatRewards"] = {
                        "opponentId": opponent_id,
                        "defeated": True,
                        "opponentData": opponent_data,
                    }
            except Exception as err:
                logger.error(f"Failed to get opponent data for rewards for {opponent_id} Error: {err}", exc_info=True)

    if outcome in ["death", "failure", "minimal", "normal", "exceptional"]:
        # Map outcome to PascalCase for Results lookup
        outcome_map = {
            "death": "Death",
            "failure": "Failure",
            "minimal": "Minimal",
            "normal": "Normal",
            "exceptional": "Exceptional",
        }
        outcome_key = outcome_map.get(outcome.lower(), outcome)
        outcome_results = segment_def.get("Results", {}).get(outcome_key, {})
        outcome_effects = outcome_results.get("Effects", {})  # PascalCase Effects
        if outcome_effects:
            updates["StoryEffects"] = outcome_effects

    return updates


@cache
def map_outcome_to_key(outcome: str) -> str:
    """
    Map a segment outcome to its corresponding key in the Results.

    Args:
        outcome: The segment outcome

    Returns:
        The corresponding key for the outcome
    """
    outcome_map = {"death": "Death", "failure": "Failure", "minimal": "Minimal", "normal": "Normal", "exceptional": "Exceptional"}
    result = outcome_map.get(outcome.lower(), outcome)
    return result
