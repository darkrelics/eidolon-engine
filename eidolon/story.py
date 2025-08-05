"""
Story management utilities for Lambda functions.

Provides common functions for story operations including starting, abandoning,
and managing story segments.
"""

import time
from datetime import datetime, timezone
from decimal import Decimal

from botocore.exceptions import ClientError
from uuid_extension import uuid7

from eidolon.character import apply_character_updates, character_get
from eidolon.dynamo import TableName, dynamo
from eidolon.environment import SEGMENT_QUEUE_URL
from eidolon.logger import logger
from eidolon.segment import (
    calculate_heal_time,
    complete_story,
    create_next_active_segment,
    delete_active_segment,
    determine_next_segment,
    get_segment_definition,
    record_segment_history,
    update_character_active_segment,
)
from eidolon.sqs import send_message


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
        logger.error(f"Failed to query active segments for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError from err

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
        logger.error(f"Failed to mark segment as abandoned for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to mark segment as abandoned: {err}") from err

    logger.info(f"Marked segment as abandoned for {active_segment_id}")


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
        history = dynamo.get_item(TableName.STORY_HISTORY, {"CharacterID": character_id, "StoryID": story_id})
    except ClientError as err:
        logger.error(f"Failed to get story history for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get story history: {err}") from err

    if history:
        abandoned_count = history.get("AbandonedCount", 0) + 1

        try:
            dynamo.update_item(
                TableName.STORY_HISTORY,
                Key={"CharacterID": character_id, "StoryID": story_id},
                UpdateExpression="SET FinishedAt = :finished, AbandonedCount = :count, FinalOutcome = :outcome",
                ExpressionAttributeValues={
                    ":finished": datetime.now(timezone.utc).isoformat(),
                    ":count": abandoned_count,
                    ":outcome": "abandoned",
                },
            )
        except ClientError as err:
            logger.error(f"Failed to update story history for {character_id} Error: {err}", exc_info=True)
            raise RuntimeError(f"Failed to update story history: {err}") from err

        logger.info(f"Updated story history with abandonment for {character_id}")


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
        logger.error(f"Failed to add story to abandoned list for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to add story to abandoned list: {err}") from err

    logger.info(f"Added story to abandoned list for {character_id}")


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
        logger.error(f"Failed to query active segments for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to query active segments: {err}") from err

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
        logger.error(f"Failed to get story for {story_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get story: {err}") from err


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
        logger.error(f"Failed to get segment for {segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get segment: {err}") from err


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
        logger.error(f"Failed to query active segments for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to query segments: {err}") from err

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
        history = dynamo.get_item(TableName.STORY_HISTORY, {"CharacterID": character_id, "StoryID": story_id})
        return history or {}
    except ClientError as err:
        logger.error(f"Failed to get story history for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get story history: {err}") from err


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
        logger.error(f"Error checking story cooldown Error: {err}")
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

    return True


def get_stories_for_character(character_id: str, player_id: str, available_story_ids: list) -> list:
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

    character = character_get(character_id, player_id)

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
                "Prerequisites": prerequisites,
                "DifficultyMap": story_data.get("DifficultyMap", {}),
                "RewardTiers": story_data.get("RewardTiers", {}),
                "BaseXPMultiplier": float(story_data.get("BaseXPMultiplier", 0.5)),
            }

            stories.append(formatted_story)
            logger.debug(f"Story processed for {story_id}")

        except ValueError:
            logger.warning(f"Story not found for {story_id}")
            continue
        except RuntimeError as err:
            logger.error(f"Error loading story for {story_id} Error: {err}")
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
        logger.error(f"Story has no first segment for {story_id}")
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

    segment_id = segment.get("SegmentID")
    segment_type = segment.get("SegmentType", "mechanical")
    duration = int(segment.get("SegmentDuration", 300))  # Default 5 minutes

    current_time = int(time.time())
    end_time = current_time + duration

    # Generate UUIDv7 for time-based ordering
    active_segment_id = str(uuid7())

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
    elif segment_type == "mechanical":
        # Mechanical segments can have challenges and/or combat
        active_segment["ChallengeResults"] = []
        active_segment["Outcome"] = None

        # If combat is configured, set up combat state
        combat_config = segment.get("Combat", {})
        if combat_config:
            opponent_id = combat_config.get("opponentId")

            # Load opponent to get initial health
            opponent_health = 5  # Default health
            if opponent_id:
                try:
                    opponent = dynamo.get_item(TableName.OPPONENTS, {"OpponentID": opponent_id})
                    if opponent:
                        opponent_health = opponent.get("Health", 5)
                except Exception as err:
                    logger.warning(f"Failed to load opponent for combat state init for {opponent_id} Error: {err}")

            active_segment["CombatState"] = {
                "round": 0,
                "playerWounds": [],
                "opponentWounds": [],
                "opponentHealth": opponent_health,
                "opponentId": opponent_id,
            }

    # Store in DynamoDB
    try:
        dynamo.put_item(TableName.ACTIVE_SEGMENTS, active_segment)
    except ClientError as err:
        logger.error(f"Failed to create active segment for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to create active segment: {err}") from err

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
        dynamo.put_item(TableName.STORY_HISTORY, history_entry)
    except ClientError as err:
        logger.error(f"Failed to create history entry for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to create history entry: {err}") from err


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

    # Get character and verify ownership
    character: dict = character_get(character_id, player_id)

    # Check if character is already in a game mode
    game_mode = character.get("GameMode", "None")
    if game_mode != "None":
        logger.warning(f"Character already in game mode for {character_id}")
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
            logger.error(f"Failed to rollback active segment for {active_segment.get('ActiveSegmentID')} Error: {rollback_err}")

        if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.warning(f"Character state changed during story start for {character_id}")
            raise ValueError("Character state conflict") from err

        logger.error(f"Failed to update character state for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to update character state: {err}") from err

    # Create history entry
    story_type = story.get("StoryType", "repeatable")
    create_story_history_entry(character_id, story_id, story_title, story_type)

    logger.info(f"Story started successfully for {character_id}")

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

    segment_type = segment.get("SegmentType", "mechanical")
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
    elif segment_type == "mechanical":
        response["ShortStatus"] = segment.get("ShortStatus", "Progressing through the story...")
        # Include combat opponent if configured
        combat_config = segment.get("Combat", {})
        if combat_config:
            response["OpponentID"] = combat_config.get("opponentID")

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
        logger.error(f"Failed to query active segments for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to query active segments: {err}") from err

    if not items:
        logger.warning(f"No active decision segment found for {character_id}")
        raise ValueError("No active decision segment found")

    active_segment = items[0]

    # Extra validation checks (should already be verified by query)
    if active_segment.get("PlayerID") != player_id:
        logger.warning(f"Active segment ownership mismatch for {active_segment.get('ActiveSegmentID')}")
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
        logger.warning(f"Decision already submitted for {active_segment.get('ActiveSegmentID')}")
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
        logger.error(f"Failed to update active segment for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to update active segment: {err}") from err


def get_next_segment_time(active_segment: dict, decision_id: str) -> int:
    """
    Calculate the next segment completion time based on the decision.

    Args:
        active_segment: Active segment data
        decision_id: Decision ID chosen by player

    Returns:
        Next segment completion time (0 if no next segment)
    """

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
        logger.error(f"Failed to get next segment for {next_segment_id} Error: {err}")
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

    # Verify character ownership
    # TODO: Read Player Record instead.
    character_get(character_id, player_id)

    logger.info(f"Submitting decision for {character_id}")

    # Get active segment for character and verify ownership
    active_segment = get_active_decision_segment(character_id, player_id)
    active_segment_id = active_segment.get("ActiveSegmentID")
    if not active_segment_id:
        raise ValueError("Active segment ID not found")

    # Validate decision is valid for this segment
    validate_decision_option(active_segment, decision_id)

    # Update active segment with decision and mark as completed
    update_segment_decision(active_segment_id, decision_id)

    # Record segment history before advancing
    story_id = active_segment.get("StoryID")
    if not story_id:
        raise ValueError("Story ID not found in active segment")

    # Mark outcome as normal for completed decision segments
    active_segment["Outcome"] = "normal"
    active_segment["Decision"] = decision_id
    active_segment["DecisionMadeAt"] = datetime.now(timezone.utc).isoformat()

    record_segment_history(character_id, story_id, active_segment_id, active_segment)

    # Get segment definition to determine next segment
    segment_id = active_segment.get("SegmentID")
    if not segment_id:
        raise ValueError("Segment ID not found in active segment")

    segment_def = get_segment_definition(str(story_id), str(segment_id))

    # Determine next segment based on decision
    next_segment_id = determine_next_segment(segment_def, active_segment, "normal")

    response_data: dict = {
        "Accepted": True,
    }

    if next_segment_id:
        # Create next segment
        try:
            next_segment_def = get_segment_definition(story_id, next_segment_id)  # type: ignore

            next_active_segment_id = create_next_active_segment(
                character_id,
                player_id,
                story_id,
                next_segment_def,
                active_segment.get("StoryTitle", "Unknown Story"),
            )

            # Update character with new active segment
            update_character_active_segment(character_id, next_active_segment_id)

            # Calculate next segment time
            next_segment_time = int(time.time()) + next_segment_def.get("SegmentDuration", 60)
            response_data["NextSegmentTime"] = next_segment_time

            logger.info(f"Advanced to next segment after decision for {character_id}")

            # Queue mechanical segments for immediate processing
            if next_segment_def.get("SegmentType") == "mechanical":
                try:
                    if SEGMENT_QUEUE_URL:
                        message_body = {
                            "ActiveSegmentID": next_active_segment_id,
                            "CharacterID": character_id,
                            "StoryID": story_id,
                            "SegmentID": next_segment_id,
                            "SegmentType": "mechanical",
                        }
                        send_message(SEGMENT_QUEUE_URL, message_body)
                        logger.info(f"Queued next mechanical segment for processing for {next_active_segment_id}")
                except Exception as err:
                    # Non-critical - segment will be picked up by poller
                    logger.warning(f"Failed to queue mechanical segment for {next_active_segment_id} Error: {err}")
        except Exception as err:
            logger.error(f"Failed to create next segment after decision for {next_segment_id} Error: {err}", exc_info=True)
            raise RuntimeError(f"Failed to create next segment: {err}") from err
    else:
        # Story complete
        complete_story(character_id, story_id, "normal")
        logger.info(f"Story completed after decision for {character_id}")

    # Delete processed segment
    delete_active_segment(active_segment_id)

    logger.info(f"Decision submitted and story advanced for {active_segment_id}")

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
            "Description": "",  # Will be set based on segment type
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

    elif segment_type == "mechanical":
        # Mechanical segments can contain skill challenges and/or combat
        response["Segment"]["Description"] = segment_data.get("Description", segment_data.get("Narrative", ""))
        response["Segment"]["Challenges"] = segment_data.get("Challenges", [])
        response["Segment"]["ChallengeResults"] = active_segment.get("ChallengeResults", [])

        # Combat is optional within mechanical segments
        if segment_data.get("Combat"):
            response["Segment"]["Combat"] = segment_data.get("Combat", {})
            response["Segment"]["CombatState"] = active_segment.get("CombatState", {})

        response["Segment"]["Outcome"] = active_segment.get("Outcome")

    elif segment_type == "rest":
        # Rest segments allow wound healing over time
        response["Segment"]["Description"] = segment_data.get("Description", segment_data.get("Narrative", ""))

    else:
        # Unknown segment type - add minimal data
        logger.warning(f"Unknown segment type for {active_segment.get('SegmentID')}")
        response["Segment"]["Description"] = segment_data.get("Description", segment_data.get("Narrative", ""))

    return response


def complete_story_for_character(character_id: str, story_id: str, final_outcome: str) -> None:
    """
    Mark a story as completed and clean up character state.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        final_outcome: Story outcome (death, failure, minimal, normal, exceptional)

    Raises:
        RuntimeError: If database operations fail
    """
    try:
        # Update character to clear GameMode and story references
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET GameMode = :none REMOVE ActiveStoryID, ActiveSegmentID",
            ExpressionAttributeValues={":none": "None"},
        )

        # Update story history with completion
        dynamo.update_item(
            TableName.STORY_HISTORY,
            Key={"CharacterID": character_id, "StoryID": story_id},
            UpdateExpression="SET FinishedAt = :finished, FinalOutcome = :outcome",
            ExpressionAttributeValues={
                ":finished": datetime.now(timezone.utc).isoformat(),
                ":outcome": final_outcome,
            },
        )

        logger.info(f"Story completed for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to complete story for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to complete story: {err}") from err


def calculate_story_rewards(story_metadata: dict, outcome: str, segments_completed: int) -> dict:
    """
    Calculate rewards based on story outcome and segments completed.

    Args:
        story_metadata: Story data from STORY table
        outcome: Final outcome (death, failure, minimal, normal, exceptional)
        segments_completed: Number of segments completed

    Returns:
        Dict with calculated rewards (xp, items, etc.)
    """
    rewards = {
        "xp": 0,
        "items": [],
        "currency": 0,
    }

    # No rewards for death
    if outcome == "death":
        return rewards

    # Get base XP multiplier and reward tiers
    base_xp_multiplier = float(story_metadata.get("BaseXPMultiplier", 0.5))
    reward_tiers = story_metadata.get("RewardTiers", {})

    # Calculate XP based on outcome
    outcome_multipliers = {
        "failure": 0.25,
        "minimal": 0.5,
        "normal": 1.0,
        "exceptional": 1.5,
    }

    outcome_multiplier = outcome_multipliers.get(outcome, 0)
    base_xp = story_metadata.get("EstimatedDuration", 300) * base_xp_multiplier

    # XP = base * outcome * (segments_completed / total_segments)
    total_segments = story_metadata.get("TotalSegments", 1)
    completion_ratio = min(1.0, segments_completed / max(1, total_segments))

    rewards["xp"] = int(base_xp * outcome_multiplier * completion_ratio)

    # Get items and currency from reward tiers
    tier_rewards = reward_tiers.get(outcome, {})
    rewards["items"] = tier_rewards.get("items", [])
    rewards["currency"] = tier_rewards.get("currency", 0)

    return rewards


def apply_story_rewards(character_id: str, rewards: dict) -> None:
    """
    Apply calculated rewards to a character.

    Args:
        character_id: Character UUID
        rewards: Dict containing xp, items, currency

    Raises:
        RuntimeError: If database operations fail
    """
    try:
        # Apply XP to character's story skill
        if rewards.get("xp", 0) > 0:
            dynamo.update_item(
                TableName.CHARACTERS,
                Key={"CharacterID": character_id},
                UpdateExpression="ADD #skills.#story :xp",
                ExpressionAttributeNames={
                    "#skills": "Skills",
                    "#story": "story",
                },
                ExpressionAttributeValues={
                    ":xp": rewards["xp"],
                },
            )

        logger.info(f"Applied story rewards for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to apply rewards for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to apply rewards: {err}") from err


def apply_combat_rewards(character_id: str, opponent_data: dict) -> None:
    """
    Apply rewards from defeating an opponent in combat.

    Args:
        character_id: Character UUID
        opponent_data: Opponent data including XPReward and LootTable

    Raises:
        RuntimeError: If database operations fail
    """
    try:
        # Apply XP reward to combat skill
        xp_reward = opponent_data.get("XPReward", 10)
        if xp_reward > 0:
            dynamo.update_item(
                TableName.CHARACTERS,
                Key={"CharacterID": character_id},
                UpdateExpression="ADD #skills.#combat :xp",
                ExpressionAttributeNames={
                    "#skills": "Skills",
                    "#combat": "combat",
                },
                ExpressionAttributeValues={
                    ":xp": xp_reward,
                },
            )

        loot_table = opponent_data.get("LootTable", [])

        logger.info(f"Applied combat rewards for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to apply combat rewards for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to apply combat rewards: {err}") from err


def add_segment_to_history(character_id: str, story_id: str, segment_id: str, outcome: str) -> None:
    """
    Add a completed segment to the story history.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        segment_id: Segment UUID
        outcome: Segment outcome

    Raises:
        RuntimeError: If database operations fail
    """
    try:
        segment_entry = {
            "segmentId": segment_id,
            "completedAt": datetime.now(timezone.utc).isoformat(),
            "outcome": outcome,
        }

        dynamo.update_item(
            TableName.STORY_HISTORY,
            Key={"CharacterID": character_id, "StoryID": story_id},
            UpdateExpression="SET SegmentHistory = list_append(SegmentHistory, :segment)",
            ExpressionAttributeValues={
                ":segment": [segment_entry],
            },
        )

        logger.info(f"Added segment to history for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to add segment to history for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to add segment to history: {err}") from err


def apply_story_outcome_effects(character_id: str, outcome_effects: dict) -> None:
    """
    Apply story outcome effects like room changes and item rewards.

    Args:
        character_id: Character UUID
        outcome_effects: Dict containing room changes, items, etc.

    Raises:
        RuntimeError: If database operations fail
    """
    try:
        update_expressions = []
        expression_attribute_names = {}
        expression_attribute_values = {}

        # Handle room change
        if "room" in outcome_effects:
            update_expressions.append("#room = :room")
            expression_attribute_names["#room"] = "RoomID"
            expression_attribute_values[":room"] = outcome_effects["room"]

        # Handle wounds from story outcomes
        if "wounds" in outcome_effects:

            # Add heal times to wounds
            wounds_with_heal_times = []
            for wound in outcome_effects["wounds"]:
                wound_data = wound.copy()
                if "HealAt" not in wound_data:
                    damage_type = wound_data.get("DamageType", "lethal")
                    wound_data["HealAt"] = calculate_heal_time(damage_type)
                wounds_with_heal_times.append(wound_data)

            # Apply wounds through character updates
            try:
                apply_character_updates(character_id, {"Wounds": wounds_with_heal_times})
                logger.info(f"Applied story outcome wounds for {character_id}")
            except Exception as err:
                logger.error(f"Failed to apply story wounds for {character_id} Error: {err}", exc_info=True)
                raise RuntimeError(f"Failed to apply story wounds: {err}") from err

        if update_expressions:
            update_expression: str = "SET " + ", ".join(update_expressions)

            dynamo.update_item(
                TableName.CHARACTERS,
                Key={"CharacterID": character_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_attribute_names,
                ExpressionAttributeValues=expression_attribute_values,
            )

            logger.info(f"Applied story outcome effects for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to apply outcome effects for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to apply outcome effects: {err}") from err


def update_story_history_xp(character_id: str, story_id: str, skill_xp: dict, attribute_xp: dict) -> None:
    """
    Update the story history with accumulated XP from this segment.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        skill_xp: Skill XP awarded in this segment
        attribute_xp: Attribute XP awarded in this segment

    Raises:
        RuntimeError: If database operation fails
    """
    if not skill_xp and not attribute_xp:
        # No XP to update
        return

    try:
        # Build update expressions for XP accumulation
        update_expressions = ["SegmentCount = SegmentCount + :one"]
        expression_names = {}
        expression_values = {":one": Decimal("1")}

        # Add skill XP updates
        for skill, xp_value in skill_xp.items():
            if xp_value > 0:
                safe_skill = skill.replace("-", "_")
                update_expressions.append(
                    f"SkillXPAwarded.#skill_{safe_skill} = if_not_exists(SkillXPAwarded.#skill_{safe_skill}, :zero) + :xp_{safe_skill}"
                )
                expression_names[f"#skill_{safe_skill}"] = skill
                expression_values[f":xp_{safe_skill}"] = Decimal(str(xp_value))

        # Add attribute XP updates
        for attribute, xp_value in attribute_xp.items():
            if xp_value > 0:
                safe_attr = attribute.replace("-", "_")
                update_expressions.append(
                    f"AttributeXPAwarded.#attr_{safe_attr} = if_not_exists(AttributeXPAwarded.#attr_{safe_attr}, :zero) + :xp_attr_{safe_attr}"
                )
                expression_names[f"#attr_{safe_attr}"] = attribute
                expression_values[f":xp_attr_{safe_attr}"] = Decimal(str(xp_value))

        # Add zero value if needed
        if ":zero" not in expression_values:
            expression_values[":zero"] = Decimal("0")

        # Execute update
        update_expression = "SET " + ", ".join(update_expressions)

        dynamo.update_item(
            TableName.STORY_HISTORY,
            Key={"CharacterID": character_id, "StoryID": story_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_names if expression_names else None,
            ExpressionAttributeValues=expression_values,
        )

        logger.info(f"Updated story history with XP for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to update story history XP for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to update story history XP: {err}") from err


def ensure_story_history_exists(character_id: str, story_id: str, story_title: str) -> None:
    """
    Ensure story history record exists.

    Creates a new story history record if one doesn't exist.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        story_title: Story title for display

    Raises:
        RuntimeError: If database operations fail
    """
    try:
        # Check if story history exists
        history = dynamo.get_item(
            TableName.STORY_HISTORY,
            {"CharacterID": character_id, "StoryID": story_id},
        )

        if not history:
            # Create new story history
            dynamo.put_item(
                TableName.STORY_HISTORY,
                {
                    "CharacterID": character_id,
                    "StoryID": story_id,
                    "StoryTitle": story_title,
                    "StartedAt": datetime.now(timezone.utc).isoformat(),
                    "SegmentCount": 0,
                },
            )
            logger.info(f"Created story history record for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to ensure story history exists for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to ensure story history exists: {err}") from err
