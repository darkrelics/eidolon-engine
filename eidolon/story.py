"""
Story management utilities for Lambda functions.

Provides common functions for story operations including starting, abandoning,
and managing story segments.
"""

from datetime import datetime, timezone

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import get_logger

logger = get_logger(__name__)


def get_active_story_segment(character_id: str) -> dict:
    """
    Get the active story segment for a character.

    Args:
        character_id: Character UUID

    Returns:
        Active segment data dict

    Raises:
        ValueError: If no active story found for character
        RuntimeError: If database query fails
    """
    if not character_id:
        raise ValueError("Character ID cannot be empty")

    try:
        items = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="CharacterID-index",
            KeyConditionExpression="CharacterID = :cid",
            FilterExpression="#status = :status",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={":cid": character_id, ":status": "active"},
        )
    except ClientError as err:
        logger.error(
            "Failed to query active segments",
            extra={
                "character_id": character_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to query active segments: {str(err)}")

    if not items:
        raise ValueError(f"No active story found for character {character_id}")

    return items[0]


def mark_segment_as_abandoned(active_segment_id: str) -> None:
    """
    Mark an active segment as abandoned.

    Args:
        active_segment_id: Active segment UUID

    Raises:
        ValueError: If active_segment_id is empty
        RuntimeError: If database update fails
    """
    if not active_segment_id:
        raise ValueError("Active segment ID cannot be empty")

    try:
        dynamo.update_item(
            TableName.ACTIVE_SEGMENTS,
            Key={"ActiveSegmentID": active_segment_id},
            UpdateExpression="SET #status = :status",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={":status": "abandoned"},
        )
    except ClientError as err:
        logger.error(
            "Failed to mark segment as abandoned",
            extra={
                "active_segment_id": active_segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to mark segment as abandoned: {str(err)}")

    logger.info("Marked segment as abandoned", extra={"active_segment_id": active_segment_id})


def record_story_abandonment(character_id: str, story_id: str) -> None:
    """
    Update history to record story abandonment.

    Args:
        character_id: Character UUID
        story_id: Story UUID

    Raises:
        ValueError: If character_id or story_id is empty
        RuntimeError: If database operations fail
    """
    if not character_id:
        raise ValueError("Character ID cannot be empty")
    if not story_id:
        raise ValueError("Story ID cannot be empty")

    try:
        history = dynamo.get_item(TableName.HISTORY, {"CharacterID": character_id, "StoryID": story_id})
    except ClientError as err:
        logger.error(
            "Failed to get story history",
            extra={"character_id": character_id, "story_id": story_id, "error": str(err)},
            exc_info=True,
        )
        raise RuntimeError(f"Failed to get story history: {str(err)}")

    if history:
        abandoned_count = history.get("AbandonedCount", 0) + 1

        try:
            dynamo.update_item(
                TableName.HISTORY,
                Key={"CharacterID": character_id, "StoryID": story_id},
                UpdateExpression="SET FinishedAt = :finished, AbandonedCount = :count, FinalOutcome = :outcome",
                ExpressionAttributeValues={
                    ":finished": datetime.now(timezone.utc).isoformat(),
                    ":count": abandoned_count,
                    ":outcome": "abandoned",
                },
            )
        except ClientError as err:
            logger.error(
                "Failed to update story history",
                extra={"character_id": character_id, "story_id": story_id, "error": str(err)},
                exc_info=True,
            )
            raise RuntimeError(f"Failed to update story history: {str(err)}")

        logger.info(
            "Updated story history with abandonment",
            extra={
                "character_id": character_id,
                "story_id": story_id,
                "abandoned_count": abandoned_count,
            },
        )


def add_story_to_abandoned_list(character_id: str, story_id: str) -> None:
    """
    Add a story to the character's AbandonedStories list.

    Uses DynamoDB's ADD operation which automatically handles duplicates,
    ensuring each story ID appears only once in the set.

    Args:
        character_id: Character UUID
        story_id: Story UUID to add to abandoned list

    Raises:
        ValueError: If character_id or story_id is empty
        RuntimeError: If database update fails
    """
    if not character_id:
        raise ValueError("Character ID cannot be empty")
    if not story_id:
        raise ValueError("Story ID cannot be empty")

    try:
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="ADD AbandonedStories :story",
            ExpressionAttributeValues={":story": {story_id}},
        )
    except ClientError as err:
        logger.error(
            "Failed to add story to abandoned list",
            extra={
                "character_id": character_id,
                "story_id": story_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to add story to abandoned list: {str(err)}")

    logger.info("Added story to abandoned list", extra={"character_id": character_id, "story_id": story_id})


def get_active_story_segment_with_player_check(character_id: str, player_id: str) -> dict:
    """
    Get the active story segment for a character with player ID verification.

    Args:
        character_id: Character UUID
        player_id: Player ID for verification

    Returns:
        Active segment data dict

    Raises:
        ValueError: If no active story found for character
        RuntimeError: If database query fails
    """
    if not character_id:
        raise ValueError("Character ID cannot be empty")
    if not player_id:
        raise ValueError("Player ID cannot be empty")

    try:
        items = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="CharacterID-index",
            KeyConditionExpression="CharacterID = :cid",
            FilterExpression="PlayerID = :pid AND #status = :status",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={
                ":cid": character_id,
                ":pid": player_id,
                ":status": "active",
            },
        )
    except ClientError as err:
        logger.error(
            "Failed to query active segments",
            extra={
                "character_id": character_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to query active segments: {str(err)}")

    if not items:
        raise ValueError("No active story found")

    return items[0]


def get_story_metadata(story_id: str) -> dict:
    """
    Get story metadata from the STORY table.

    Args:
        story_id: Story UUID

    Returns:
        Story metadata dict

    Raises:
        ValueError: If story not found
        RuntimeError: If database query fails
    """
    if not story_id:
        raise ValueError("Story ID cannot be empty")

    try:
        story_item = dynamo.get_item(TableName.STORY, {"StoryID": story_id})
        if not story_item:
            raise ValueError("Story not found")
        return story_item
    except ClientError as err:
        logger.error("Failed to get story", extra={"error": str(err), "story_id": story_id}, exc_info=True)
        raise RuntimeError(f"Failed to get story: {str(err)}")


def get_story_segment(story_id: str, segment_id: str) -> dict:
    """
    Get a specific segment from the SEGMENTS table.

    Args:
        story_id: Story UUID
        segment_id: Segment UUID

    Returns:
        Segment data dict

    Raises:
        ValueError: If segment not found
        RuntimeError: If database query fails
    """
    if not story_id:
        raise ValueError("Story ID cannot be empty")
    if not segment_id:
        raise ValueError("Segment ID cannot be empty")

    try:
        segment = dynamo.get_item(TableName.SEGMENTS, {"StoryID": story_id, "SegmentID": segment_id})
        if not segment:
            raise ValueError("Segment not found")
        return segment
    except ClientError as err:
        logger.error("Failed to get segment", extra={"error": str(err), "segment_id": segment_id}, exc_info=True)
        raise RuntimeError(f"Failed to get segment: {str(err)}")


def get_completed_segment_for_character(character_id: str, player_id: str, segment_id: str) -> dict:
    """
    Get a completed segment for a character with player ID verification.

    Args:
        character_id: Character UUID
        player_id: Player ID for verification
        segment_id: Segment UUID to find

    Returns:
        Active segment data dict

    Raises:
        ValueError: If segment not found or not completed
        RuntimeError: If database query fails
    """
    if not character_id:
        raise ValueError("Character ID cannot be empty")
    if not player_id:
        raise ValueError("Player ID cannot be empty")
    if not segment_id:
        raise ValueError("Segment ID cannot be empty")

    try:
        items = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="CharacterID-index",
            KeyConditionExpression="CharacterID = :cid",
            FilterExpression="PlayerID = :pid AND SegmentID = :sid AND #status = :status",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={
                ":cid": character_id,
                ":pid": player_id,
                ":sid": segment_id,
                ":status": "completed",
            },
        )
    except ClientError as err:
        logger.error(
            "Failed to query active segments",
            extra={
                "error": str(err),
                "character_id": character_id,
                "segment_id": segment_id,
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to query segments: {str(err)}")

    if not items:
        raise ValueError("Completed segment not found")

    active_segment = items[0]

    # Double-check segment is completed
    status = active_segment.get("Status")
    if status != "completed":
        raise ValueError("Segment not yet completed")

    return active_segment


def get_story_history(character_id: str, story_id: str) -> dict:
    """
    Get story history for a character.

    Args:
        character_id: Character UUID
        story_id: Story UUID

    Returns:
        History record dict or empty dict if not found

    Raises:
        RuntimeError: If database query fails
    """
    if not character_id:
        raise ValueError("Character ID cannot be empty")
    if not story_id:
        raise ValueError("Story ID cannot be empty")

    try:
        history = dynamo.get_item(TableName.HISTORY, {"CharacterID": character_id, "StoryID": story_id})
        return history or {}
    except ClientError as err:
        logger.error(
            "Failed to get story history",
            extra={"character_id": character_id, "story_id": story_id, "error": str(err)},
            exc_info=True,
        )
        raise RuntimeError(f"Failed to get story history: {str(err)}")


def get_story_cooldown(character_id: str, story_id: str, story_type: str):
    """
    Calculate cooldown remaining for a story based on its type and last completion.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        story_type: Type of story (one-time, daily, repeatable)

    Returns:
        Seconds remaining on cooldown, 0 if playable, -1 if permanently unavailable
    """
    if story_type == "repeatable":
        return 0

    try:
        history = get_story_history(character_id, story_id)

        if not history:
            return 0  # Never played

        # Check if story was completed or abandoned
        if not history.get("FinishedAt"):
            return 0  # Abandoned stories can be retried

        if story_type == "one-time":
            # Check if it was completed successfully
            outcome = history.get("FinalOutcome", "")
            if outcome in ["normal", "exceptional", "minimal"]:
                return -1  # Permanently unavailable
            return 0  # Failed/died, can retry

        if story_type == "daily":
            # Calculate time until midnight UTC
            finished_at = datetime.fromisoformat(history.get("FinishedAt", "").replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)

            # Check if completion was today
            if finished_at.date() == now.date():
                # Calculate seconds until midnight
                midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
                midnight = midnight.replace(day=midnight.day + 1)
                return int((midnight - now).total_seconds())

            return 0  # Completed on a previous day

    except Exception as err:
        logger.error("Error checking story cooldown", extra={"error": str(err)})
        return 0


def check_story_prerequisites(character: dict, prerequisites: dict) -> bool:
    """
    Check if character meets story prerequisites.

    Args:
        character: Character data
        prerequisites: Story prerequisite requirements

    Returns:
        True if all prerequisites are met
    """
    # Check minimum skills
    min_skills = prerequisites.get("minSkills", {})
    character_skills = character.get("Skills", {})

    for skill, min_value in min_skills.items():
        if character_skills.get(skill, 0) < min_value:
            return False

    # Check required items
    required_items = prerequisites.get("requiredItems", [])
    if required_items:
        inventory = character.get("Inventory", {})
        inventory_items = list(inventory.values())
        for item_id in required_items:
            if item_id not in inventory_items:
                return False

    # Check required rooms visited (not implemented yet)
    required_rooms = prerequisites.get("requiredRooms", [])
    if required_rooms:
        # TODO: Implement room visit tracking
        pass

    return True


def get_stories_for_character(character_id: str, available_story_ids: list) -> list:
    """
    Get story details for a list of story IDs, checking prerequisites and cooldowns.

    Args:
        character_id: Character UUID
        available_story_ids: List of story IDs available to the character

    Returns:
        List of story data dicts with availability information

    Raises:
        RuntimeError: If database operations fail
    """
    if not available_story_ids:
        return []

    stories = []

    # Need character data for prerequisite checking
    from eidolon.character import get_character

    character = get_character(character_id)

    for story_id in available_story_ids:
        try:
            story_data = get_story_metadata(story_id)

            # Check prerequisites
            prerequisites = story_data.get("Prerequisites", {})
            if not check_story_prerequisites(character, prerequisites):
                continue

            # Check cooldown
            story_type = story_data.get("StoryType", "repeatable")
            cooldown = get_story_cooldown(character_id, story_id, story_type)

            if cooldown == -1:  # Permanently unavailable
                continue

            # Format story for response with PascalCase
            formatted_story = {
                "StoryID": story_id,
                "Title": story_data.get("Title", "Unknown Story"),
                "Description": story_data.get("Description", ""),
                "Type": story_type,
                "Available": cooldown == 0,
                "CooldownRemaining": max(0, cooldown) if cooldown is not None else 0,
                "EstimatedDuration": int(story_data.get("EstimatedDuration", 0)),
            }

            stories.append(formatted_story)
            logger.debug(
                "Story processed",
                extra={
                    "story_id": story_id,
                    "story_type": story_type,
                    "available": formatted_story.get("Available"),
                    "cooldown": cooldown,
                },
            )

        except ValueError:
            logger.warning("Story not found", extra={"story_id": story_id})
            continue
        except RuntimeError as err:
            logger.error(
                "Error loading story",
                extra={"story_id": story_id, "error": str(err)},
            )
            continue

    return stories


def validate_story_available(character: dict, story_id: str) -> None:
    """
    Validate that the story is available to the character.

    Args:
        character: Character data
        story_id: Story UUID to start

    Raises:
        ValueError: If story not available to character
    """
    available_stories = character.get("AvailableStories", [])
    if story_id not in available_stories:
        raise ValueError("Story not available")


def get_story_and_first_segment(story_id: str) -> tuple:
    """
    Get story metadata and first segment details.

    Args:
        story_id: Story UUID

    Returns:
        Tuple of (story_data, first_segment)

    Raises:
        ValueError: If story or first segment not found
        RuntimeError: If database operations fail
    """
    # Get story metadata
    story = get_story_metadata(story_id)

    # Get first segment
    first_segment_id = story.get("FirstSegmentID")
    if not first_segment_id:
        logger.error("Story has no first segment", extra={"story_id": story_id})
        raise ValueError("Story configuration error")

    first_segment = get_story_segment(story_id, first_segment_id)
    return story, first_segment


def create_active_segment(character_id: str, player_id: str, story_id: str, story_title: str, segment: dict) -> dict:
    """
    Create an active segment record for tracking progress.

    Args:
        character_id: Character UUID
        player_id: Player UUID
        story_id: Story UUID
        story_title: Story title
        segment: Segment data from Segments table

    Returns:
        Active segment record

    Raises:
        RuntimeError: If database operation fails
    """
    import time
    import uuid

    segment_id = segment.get("SegmentID")
    segment_type = segment.get("SegmentType", "narrative")
    duration = int(segment.get("SegmentDuration", 300))  # Default 5 minutes

    current_time = int(time.time())
    end_time = current_time + duration

    # Generate unique ID for this active segment
    active_segment_id = str(uuid.uuid4())

    active_segment = {
        "ActiveSegmentID": active_segment_id,
        "CharacterID": character_id,
        "PlayerID": player_id,
        "StoryID": story_id,
        "SegmentID": segment_id,
        "SegmentType": segment_type,
        "StoryTitle": story_title,
        "Status": "active",
        "StartTime": current_time,
        "EndTime": end_time,
    }

    # Add type-specific fields based on segment type
    if segment_type == "decision":
        active_segment["Decision"] = None
        active_segment["DecisionOptions"] = segment.get("DecisionOptions", {})
    elif segment_type == "narrative":
        active_segment["ChallengeResults"] = []
        active_segment["Outcome"] = None
    elif segment_type == "combat":
        combat_config = segment.get("Combat", {})
        active_segment["CombatState"] = {
            "round": 0,
            "playerWounds": [],
            "opponentHealth": None,
            "opponentId": combat_config.get("opponentId"),
        }

    # Store in DynamoDB
    try:
        dynamo.put_item(TableName.ACTIVE_SEGMENTS, active_segment)
    except ClientError as err:
        logger.error(
            "Failed to create active segment",
            extra={
                "active_segment_id": active_segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to create active segment: {str(err)}")

    return active_segment


def create_story_history_entry(character_id: str, story_id: str, story_title: str, story_type: str) -> None:
    """
    Create initial history entry for story tracking.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        story_title: Story title
        story_type: Type of story (one-time, daily, repeatable)

    Raises:
        RuntimeError: If database operation fails
    """
    try:
        history_entry = {
            "CharacterID": character_id,
            "StoryID": story_id,
            "StoryTitle": story_title,
            "StartedAt": datetime.now(timezone.utc).isoformat(),
            "StoryType": story_type,
            "SegmentHistory": [],
            "AbandonedCount": 0,
        }

        # Put item (will overwrite if exists - handles retries)
        dynamo.put_item(TableName.HISTORY, history_entry)
    except ClientError as err:
        logger.error(
            "Failed to create history entry",
            extra={
                "character_id": character_id,
                "story_id": story_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to create history entry: {str(err)}")


def start_story_for_character(character_id: str, story_id: str, player_id: str) -> dict:
    """
    Start a story for a character with atomic state updates.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        player_id: Player UUID

    Returns:
        Dict with active_segment data

    Raises:
        ValueError: If validation fails
        RuntimeError: If database operations fail
    """
    from eidolon.character import get_character, validate_character_ownership

    # Get character and verify ownership
    character = get_character(character_id)
    validate_character_ownership(character, player_id)

    # Check if character is already in a game mode
    game_mode = character.get("GameMode", "None")
    if game_mode != "None":
        logger.warning(
            "Character already in game mode",
            extra={"character_id": character_id, "game_mode": game_mode},
        )
        raise ValueError(f"Character is currently in {game_mode} mode")

    # Validate story is available
    validate_story_available(character, story_id)

    # Get story and first segment
    story, first_segment = get_story_and_first_segment(story_id)

    # Create active segment first to get the segment ID
    story_title = story.get("Title", "Unknown Story")
    active_segment = create_active_segment(character_id, player_id, story_id, story_title, first_segment)

    # Atomically update character to set GameMode, ActiveStoryID, ActiveSegmentID and remove from available list
    try:
        # Build update expression to set GameMode and remove from AvailableStories
        available_stories = character.get("AvailableStories", [])
        if story_id in available_stories:
            story_index = available_stories.index(story_id)
            update_expression = (
                "SET GameMode = :mode, ActiveStoryID = :story_id, ActiveSegmentID = :segment_id "
                f"REMOVE AvailableStories[{story_index}]"
            )
        else:
            # Story not in list anymore (race condition), just update the mode
            update_expression = "SET GameMode = :mode, ActiveStoryID = :story_id, ActiveSegmentID = :segment_id"

        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues={
                ":mode": "Incremental",
                ":none": "None",
                ":story_id": story_id,
                ":segment_id": active_segment.get("ActiveSegmentID"),
            },
            ConditionExpression="GameMode = :none",
        )

    except ClientError as err:
        # Rollback: Delete the active segment we just created
        try:
            dynamo.delete_item(
                TableName.ACTIVE_SEGMENTS,
                Key={"ActiveSegmentID": active_segment.get("ActiveSegmentID")},
            )
        except Exception as rollback_err:
            logger.error(
                "Failed to rollback active segment",
                extra={
                    "active_segment_id": active_segment.get("ActiveSegmentID"),
                    "error": str(rollback_err),
                },
            )

        if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.warning(
                "Character state changed during story start",
                extra={"character_id": character_id},
            )
            raise ValueError("Character state conflict")

        logger.error(
            "Failed to update character state",
            extra={
                "character_id": character_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to update character state: {str(err)}")

    # Create history entry
    story_type = story.get("StoryType", "repeatable")
    create_story_history_entry(character_id, story_id, story_title, story_type)

    logger.info(
        "Story started successfully",
        extra={
            "character_id": character_id,
            "story_id": story_id,
            "active_segment_id": active_segment.get("ActiveSegmentID"),
            "segment_type": first_segment.get("SegmentType"),
        },
    )

    return {"active_segment": active_segment, "segment": first_segment, "story": story}


def format_segment_response(segment: dict, active_segment: dict) -> dict:
    """
    Format segment data for API response.

    Args:
        segment: Original segment from Segments table
        active_segment: Active segment record

    Returns:
        Formatted response data
    """
    import time

    segment_type = segment.get("SegmentType", "narrative")
    time_remaining = max(0, active_segment.get("EndTime", 0) - int(time.time()))

    response = {
        "SegmentID": active_segment.get("ActiveSegmentID"),
        "StoryID": active_segment.get("StoryID"),
        "Type": segment_type,
        "TimeRemaining": time_remaining,
    }

    # Add type-specific fields based on documented schema
    if segment_type == "decision":
        # DecisionText contains the choice presented
        response["Content"] = segment.get("DecisionText", "")
        # Format options from DecisionOptions map
        decision_options = segment.get("DecisionOptions", {})
        options = []
        for option_id, _ in decision_options.items():
            options.append({"Id": option_id, "Text": option_id.replace("-", " ").title()})  # Format option ID as display text
        response["Options"] = options
    elif segment_type == "narrative":
        response["ShortStatus"] = segment.get("ShortStatus", "Progressing through the story...")
        response["Narrative"] = ""
    elif segment_type == "combat":
        response["ShortStatus"] = segment.get("ShortStatus", "Engaged in combat!")
        response["OpponentID"] = segment.get("Combat", {}).get("opponentID")

    return response


def get_active_decision_segment(character_id: str, player_id: str) -> dict:
    """
    Get active decision segment for a character and verify ownership.

    Args:
        character_id: Character UUID
        player_id: Cognito user ID for ownership verification

    Returns:
        Active segment data

    Raises:
        ValueError: If no active decision segment found or validation fails
        RuntimeError: If database query fails
    """
    try:
        # Query by CharacterID to find active segment
        items = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="CharacterID-index",
            KeyConditionExpression="CharacterID = :cid",
            FilterExpression="PlayerID = :pid AND #status = :status AND SegmentType = :type",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={
                ":cid": character_id,
                ":pid": player_id,
                ":status": "active",
                ":type": "decision",
            },
        )
    except ClientError as err:
        logger.error(
            "Failed to query active segments",
            extra={
                "error": str(err),
                "character_id": character_id,
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to query active segments: {str(err)}")

    if not items:
        logger.warning("No active decision segment found", extra={"character_id": character_id})
        raise ValueError("No active decision segment found")

    active_segment = items[0]

    # Extra validation checks (should already be verified by query)
    if active_segment.get("PlayerID") != player_id:
        logger.warning(
            "Active segment ownership mismatch",
            extra={
                "active_segment_id": active_segment.get("ActiveSegmentID"),
                "player_id": player_id,
            },
        )
        raise ValueError("Active segment not found")

    return active_segment


def validate_decision_option(active_segment: dict, decision_id: str) -> None:
    """
    Validate that the decision is valid for this segment.

    Args:
        active_segment: Active segment data
        decision_id: Decision ID submitted by player

    Raises:
        ValueError: If decision is not valid for this segment
    """
    decision_options = active_segment.get("DecisionOptions", {})
    if decision_id not in decision_options:
        raise ValueError("Invalid decision option")

    # Check if decision was already made
    if active_segment.get("Decision"):
        logger.warning(
            "Decision already submitted",
            extra={
                "active_segment_id": active_segment.get("ActiveSegmentID"),
                "existing_decision": active_segment.get("Decision"),
            },
        )
        raise ValueError("Decision already submitted")


def update_segment_decision(active_segment_id: str, decision_id: str) -> dict:
    """
    Update the active segment with the player's decision.

    Args:
        active_segment_id: Active segment UUID
        decision_id: Decision ID chosen by player

    Returns:
        Updated active segment data

    Raises:
        RuntimeError: If database update fails
    """
    try:
        # Update the decision field and mark as completed
        dynamo.update_item(
            TableName.ACTIVE_SEGMENTS,
            Key={"ActiveSegmentID": active_segment_id},
            UpdateExpression="SET #decision = :decision, #status = :status",
            ExpressionAttributeNames={"#decision": "Decision", "#status": "Status"},
            ExpressionAttributeValues={":decision": decision_id, ":status": "completed"},
        )

        # Get updated item
        updated_segment = dynamo.get_item(TableName.ACTIVE_SEGMENTS, {"ActiveSegmentID": active_segment_id})
        if not updated_segment:
            raise RuntimeError("Failed to retrieve updated segment")

        return updated_segment
    except ClientError as err:
        logger.error(
            "Failed to update active segment",
            extra={
                "active_segment_id": active_segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to update active segment: {str(err)}")


def get_next_segment_time(active_segment: dict, decision_id: str) -> int:
    """
    Calculate the next segment completion time based on the decision.

    Args:
        active_segment: Active segment data
        decision_id: Decision ID chosen by player

    Returns:
        Next segment completion time (0 if no next segment)
    """
    import time

    decision_options = active_segment.get("DecisionOptions", {})
    next_segment_id = decision_options.get(decision_id)

    if not next_segment_id:
        return 0

    try:
        # Get next segment to calculate completion time
        story_id = active_segment.get("StoryID")
        if not story_id:
            return 0
        next_segment = get_story_segment(story_id, next_segment_id)

        # Next segment will start after processing completes
        # Add segment duration to get completion time
        duration = int(next_segment.get("SegmentDuration", 300))
        return int(time.time()) + duration

    except (ValueError, RuntimeError) as err:
        logger.error(
            "Failed to get next segment",
            extra={
                "story_id": active_segment.get("StoryID", ""),
                "segment_id": next_segment_id,
                "error": str(err),
            },
        )
        # Continue without next segment time
        return 0


def submit_decision_for_character(character_id: str, decision_id: str, player_id: str) -> dict:
    """
    Submit a decision for a character's active decision segment.

    Args:
        character_id: Character UUID
        decision_id: Decision ID chosen by player
        player_id: Authenticated player ID

    Returns:
        Dict with accepted status and optional next segment time

    Raises:
        ValueError: If validation fails
        RuntimeError: If database operations fail
    """
    from eidolon.character import get_character, validate_character_ownership
    from eidolon.validation import validate_uuid

    # Validate character ID format
    if not validate_uuid(character_id):
        raise ValueError("Invalid character ID format")

    # Verify character ownership
    character = get_character(character_id)
    validate_character_ownership(character, player_id)

    logger.info(
        "Submitting decision",
        extra={"character_id": character_id, "decision": decision_id},
    )

    # Get active segment for character and verify ownership
    active_segment = get_active_decision_segment(character_id, player_id)
    active_segment_id = active_segment.get("ActiveSegmentID")
    if not active_segment_id:
        raise ValueError("Active segment ID not found")

    # Validate decision is valid for this segment
    validate_decision_option(active_segment, decision_id)

    # Update active segment with decision
    update_segment_decision(active_segment_id, decision_id)

    # Calculate next segment time if applicable
    next_segment_time = get_next_segment_time(active_segment, decision_id)

    # Build response per documentation with PascalCase
    response_data: dict = {
        "Accepted": True,
    }

    if next_segment_time > 0:
        response_data["NextSegmentTime"] = next_segment_time

    logger.info(
        "Decision submitted successfully",
        extra={
            "active_segment_id": active_segment_id,
            "decision_id": decision_id,
            "has_next_segment": next_segment_time > 0,
        },
    )

    return response_data


def format_story_segment_response(active_segment: dict, story_metadata: dict, segment_data: dict) -> dict:
    """
    Format story and segment data for API response.

    Args:
        active_segment: Active segment record from database
        story_metadata: Story metadata from STORY table
        segment_data: Segment definition from SEGMENTS table

    Returns:
        Formatted response dict with story and segment information
    """
    import time

    # Calculate time remaining
    end_time = int(active_segment.get("EndTime", 0))
    current_time = int(time.time())
    time_remaining = max(0, end_time - current_time)

    # Build base response
    response = {
        "Story": {
            "StoryID": active_segment.get("StoryID"),
            "Title": story_metadata.get("Title", ""),
            "Type": story_metadata.get("StoryType", ""),
            "TotalSegments": story_metadata.get("TotalSegments", 1),
            "CurrentSegmentIndex": segment_data.get("SegmentIndex", 0),
        },
        "Segment": {
            "SegmentID": active_segment.get("SegmentID"),
            "SegmentType": segment_data.get("SegmentType", ""),
            "ShortStatus": segment_data.get("ShortStatus", ""),
            "Narrative": "",  # Will be set based on segment type
            "Duration": segment_data.get("SegmentDuration", 0),
            "TimeRemaining": time_remaining,
            "StartTime": active_segment.get("StartTime", 0),
            "EndTime": int(active_segment.get("EndTime", 0)),
        },
        "ActiveSegmentID": active_segment.get("ActiveSegmentID", ""),
        "Status": active_segment.get("Status", ""),
    }

    # Add segment type specific data
    segment_type = segment_data.get("SegmentType", "")
    
    if segment_type == "decision":
        response["Segment"]["DecisionText"] = segment_data.get("DecisionText", "")
        # Format options from DecisionOptions map
        decision_options = segment_data.get("DecisionOptions", {})
        options = []
        for option_id, _ in decision_options.items():
            options.append({"Id": option_id, "Text": option_id.replace("-", " ").title()})
        response["Segment"]["Options"] = options
        response["Segment"]["Decision"] = active_segment.get("Decision")
        
    elif segment_type == "narrative":
        response["Segment"]["Narrative"] = segment_data.get("Narrative", "")
        response["Segment"]["Challenges"] = segment_data.get("Challenges", [])
        response["Segment"]["ChallengeResults"] = active_segment.get("ChallengeResults", [])
        response["Segment"]["Outcome"] = active_segment.get("Outcome")
        
    elif segment_type == "mechanical":
        # Mechanical segments can contain skill challenges and/or combat
        response["Segment"]["Narrative"] = segment_data.get("Narrative", "")
        response["Segment"]["Challenges"] = segment_data.get("Challenges", [])
        response["Segment"]["ChallengeResults"] = active_segment.get("ChallengeResults", [])
        
        # Combat is optional within mechanical segments
        if segment_data.get("Combat"):
            response["Segment"]["Combat"] = segment_data.get("Combat", {})
            response["Segment"]["CombatState"] = active_segment.get("CombatState", {})
        
        response["Segment"]["Outcome"] = active_segment.get("Outcome")
        
    elif segment_type == "rest":
        # Rest segments allow wound healing over time
        response["Segment"]["Narrative"] = segment_data.get("Narrative", "")
        response["Segment"]["RestBenefit"] = segment_data.get("RestBenefit", {})
        response["Segment"]["HealingApplied"] = active_segment.get("HealingApplied", {})
        
    else:
        # Unknown segment type - add minimal data
        logger.warning(
            "Unknown segment type",
            extra={"segment_type": segment_type, "segment_id": active_segment.get("SegmentID")},
        )
        response["Segment"]["Narrative"] = segment_data.get("Narrative", "")

    return response
