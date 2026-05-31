"""
Eidolon Engine - Incremental Game

Copyright 2024-2026 Jason E. Robinson

Lambda function to abandon an active story.
Updates character state, marks active segments as abandoned, and updates history.

Endpoint: POST /story/abandon
Authentication: Cognito (required)
"""

from botocore.exceptions import ClientError

from eidolon.character_data import character_get
from eidolon.dynamo import TableName, dynamo
from eidolon.errors import ConflictError
from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.requests import parse_event_body
from eidolon.segment_history import record_abandoned_segment_history
from eidolon.story_active import get_active_story_segment, mark_segment_as_abandoned
from eidolon.story_history import record_story_abandonment
from eidolon.validation import validate_uuid


def abandon_story_business_logic(character_id: str, player_id: str) -> dict:
    """Business logic for abandoning an active story.

    Args:
        character_id: Character UUID
        player_id: Player ID for ownership verification

    Returns:
        Dict with response data for successful abandonment

    Raises:
        ValueError: If character not found, not owned, or not in a story (with status code prefix)
        RuntimeError: If database operations fail
    """
    character: dict = character_get(character_id, player_id)

    if character.get("GameMode", "None") != "Incremental":
        logger.warning(f"Character not in Incremental mode for {character_id}")
        raise ConflictError("Character not in Incremental mode")

    active_segment = get_active_story_segment(character_id)
    active_segment_id = active_segment.get("ActiveSegmentID")
    story_id = active_segment.get("StoryID")
    story_instance_id = active_segment.get("StoryInstanceID")

    if not active_segment_id or not story_id:
        logger.error(f"Active segment missing required fields for {character_id}")
        raise ConflictError("No active story to abandon")

    # Mark segment as abandoned (set Status to "abandoned")
    try:
        mark_segment_as_abandoned(active_segment_id)
    except ValueError as err:
        if "already completed or abandoned" in str(err).lower():
            logger.info(f"Segment {active_segment_id} already completed/abandoned, continuing")
            # Continue - idempotent operation, segment already transitioned
        else:
            logger.error(f"Failed to mark segment as abandoned for {active_segment_id} Error: {err}")
            # Continue anyway since we still want to update character state
    except RuntimeError as err:
        logger.error(f"Failed to mark segment as abandoned for {active_segment_id} Error: {err}")
        # Continue anyway since we still want to update character state

    # Record history BEFORE clearing character state (prevents data loss on failure)
    # Record story abandonment in story history if we have instance ID
    try:
        if story_instance_id:
            record_story_abandonment(character_id, story_instance_id)
        else:
            logger.warning(f"No StoryInstanceID found for {character_id}, skipping history update")
    except (ValueError, RuntimeError) as err:
        logger.error(f"Failed to update story history but continuing for {character_id} Error: {err}")

    # Record abandoned segment in history
    try:
        record_abandoned_segment_history(character_id, story_id, active_segment)
    except RuntimeError as err:
        logger.error(f"Failed to record segment history but continuing for {character_id} Error: {err}")

    # Update character: clear story state AFTER recording history
    try:
        # Clear GameMode, ActiveStoryID and ActiveSegmentID
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET GameMode = :none REMOVE ActiveSegmentID, ActiveStoryID",
            ExpressionAttributeValues={
                ":none": "None",
            },
        )
        logger.info(f"Reset character {character_id} to GameMode=None (story {story_id} abandoned)")

    except ClientError as err:
        logger.error(f"Failed to update character abandoned state for {character_id} Error: {err}")
        raise RuntimeError(f"Failed to update character state: {err}") from err

    # Note: We do NOT delete the active segment - it remains with status="abandoned"
    # This preserves the record for history and analytics
    # The segment is already marked as abandoned by mark_segment_as_abandoned() above

    logger.info(f"Story abandoned successfully for {character_id}")

    return {
        "CharacterID": character_id,
        "StoryID": story_id,
        "Abandoned": True,
        "Message": "Story abandoned successfully",
    }


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """Lambda handler to abandon an active story.

    Args:
        event: API Gateway Lambda proxy event
        context: Lambda context
        player_id: Authenticated player ID

    Returns:
        Dict with status_code and body
    """
    body = parse_event_body(event)
    character_id = body.get("CharacterID")

    if not character_id:
        raise ValueError("Missing CharacterID parameter")

    if not validate_uuid(character_id):
        raise ValueError("Invalid character ID format")

    # Call business logic
    logger.info(f"Abandoning story for {character_id}")
    result: dict = abandon_story_business_logic(character_id, player_id)
    return {"status_code": 200, "body": result}
