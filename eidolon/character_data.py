"""
Character data management utilities for DynamoDB operations.

Provides functions for CRUD operations on character records.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from botocore.exceptions import ClientError

from eidolon.character_state import determine_character_state_from_wounds
from eidolon.constants import DEFAULT_DEATH_ROOM_ID, MAX_SKILL_LEVEL, CharState
from eidolon.dynamo import TABLE_ENV_MAP, TableName, dynamo
from eidolon.environment import DEFAULT_ESSENCE, DEFAULT_HEALTH, MAX_CHARACTERS_PER_PLAYER
from eidolon.items import create_items_from_prototypes
from eidolon.logger import logger
from eidolon.player_character import add_character_to_player_list
from eidolon.validation import validate_uuid


def generate_character_id() -> str:
    """
    Generate a UUID v4 for the character ID.

    Returns:
        A UUID string for the character ID.
    """
    character_uuid: str = str(uuid.uuid4())

    logger.debug(f"Generated character ID: {character_uuid}")

    return character_uuid


def check_character_limit(player_id: str) -> bool:
    """
    Check if player has reached character limit.

    Only counts non-dead characters toward the limit.

    Args:
        player_id: Cognito user ID.

    Returns:
        bool: True if player can create more characters, False if limit reached.

    Raises:
        ValueError: If player not found
        RuntimeError: If database error occurs
    """
    try:
        player = dynamo.get_item(TableName.PLAYERS, {"PlayerID": player_id})

        if not player:
            logger.error(f"Player not found for {player_id}")
            raise ValueError(f"Player {player_id} not found")

        character_list = player.get("CharacterList", {})

        # Count only non-dead characters toward the limit
        current_count = 0
        for char_name, char_info in character_list.items():
            if isinstance(char_info, dict) and not char_info.get("Dead", False):
                current_count += 1

        return current_count < MAX_CHARACTERS_PER_PLAYER

    except ClientError as err:
        logger.error(f"Error checking character limit for {player_id} Error: {err}")
        raise RuntimeError(f"Database error checking character limit: {err}") from err


def get_character(character_id: str) -> dict:
    """
    Get character by ID.

    Args:
        character_id: Character UUID

    Returns:
        Character dict with calculated Health field

    Raises:
        ValueError: If character ID invalid or not found
        RuntimeError: If database error occurs
    """
    if not validate_uuid(character_id):
        logger.warning(f"Invalid character ID format for {character_id}")
        raise ValueError("Invalid character ID format")

    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})

        if not character:
            logger.warning(f"Character not found for {character_id}")
            raise ValueError("Character not found")

    except ClientError as err:
        logger.error(f"Error retrieving character for {character_id} Error: {err}")
        raise RuntimeError(f"Failed to retrieve character: {err}") from err

    logger.info(f"Character retrieved successfully for {character_id}")

    # Calculate current health from MaxHealth and Wounds
    max_health = character.get("MaxHealth", 10)
    wounds = character.get("Wounds", [])
    character["Health"] = max_health - len(wounds)

    return character


def cleanup_expired_daily_stories(character: dict) -> dict:
    """
    Remove daily stories from CompletedStories where 24+ hours have passed.

    Similar to wound healing, this automatically cleans up expired daily story cooldowns
    using UTC time for consistency. One-time stories are kept permanently.

    Expected CompletedStories structure:
        [
            {
                "story-uuid-1": {
                    "StoryType": "daily",
                    "CompletedAt": 1234567890  # Unix timestamp
                }
            },
            {
                "story-uuid-2": {
                    "StoryType": "one-time",
                    "CompletedAt": 1234567890
                }
            }
        ]

    Each entry MUST be a dict with exactly one key (the story ID).
    Malformed entries are skipped with a warning.

    Args:
        character: Character dict from database

    Returns:
        Updated character dict with expired daily stories removed

    Raises:
        RuntimeError: If database update fails
    """
    completed_stories = character.get("CompletedStories", [])
    if not completed_stories:
        return character

    current_time = datetime.now(timezone.utc)
    current_timestamp = int(current_time.timestamp())

    # Filter out expired daily stories (24+ hours old)
    filtered_stories = []
    expired_count = 0

    for entry in completed_stories:
        # Each entry is {story_id: {"StoryType": "daily", "CompletedAt": timestamp}}
        # Defensive: validate entry structure before accessing
        if not isinstance(entry, dict) or len(entry) != 1:
            logger.warning(f"Malformed CompletedStories entry (expected dict with 1 key): {entry}")
            continue

        story_id = list(entry.keys())[0]
        story_data = entry[story_id]

        # Validate story_data structure
        if not isinstance(story_data, dict):
            logger.warning(f"Malformed story data for {story_id}: {story_data}")
            continue

        story_type = story_data.get("StoryType", "")
        completed_at = story_data.get("CompletedAt", 0)

        # Keep one-time stories permanently
        if story_type == "one-time":
            filtered_stories.append(entry)
            continue

        # Check if daily story has expired (24 hours = 86400 seconds)
        if story_type == "daily":
            time_elapsed = current_timestamp - completed_at
            if time_elapsed < 86400:
                # Still on cooldown, keep it
                filtered_stories.append(entry)
            else:
                # Expired, remove it
                expired_count += 1
                logger.debug(f"Removing expired daily story {story_id} from CompletedStories")

    # Update database if any stories expired
    if expired_count > 0:
        character_id = character.get("CharacterID")
        try:
            dynamo.update_item(
                TableName.CHARACTERS,
                Key={"CharacterID": character_id},
                UpdateExpression="SET CompletedStories = :stories",
                ExpressionAttributeValues={":stories": filtered_stories},
            )
            logger.info(f"Cleaned up {expired_count} expired daily story(ies) for character {character_id}")
            character["CompletedStories"] = filtered_stories
        except ClientError as err:
            logger.error(f"Failed to cleanup expired daily stories for {character_id}: {err}")
            raise RuntimeError(f"Failed to update character data: {err}") from err

    return character


def character_get(character_id: str, player_id: str) -> dict:
    """
    Get character by ID and verify ownership.

    Args:
        character_id: Character UUID
        player_id: Player ID for ownership verification

    Returns:
        Character dict with calculated Health field

    Raises:
        ValueError: If character ID invalid, not found, or not owned by player
        RuntimeError: If database error occurs
    """
    if not validate_uuid(character_id):
        logger.warning(f"Invalid character ID format: {character_id}")
        raise ValueError("Invalid character ID format")

    if not validate_uuid(player_id):
        logger.warning(f"Invalid player ID format: {player_id}")
        raise ValueError("Invalid player ID format")

    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})

        if not character:
            logger.warning(f"Character not found for {character_id}")
            raise ValueError("Character not found")

    except ClientError as err:
        logger.error(f"Error retrieving character for {character_id} Error: {err}")
        raise RuntimeError(f"Failed to retrieve character: {err}") from err

    logger.debug(f"Character retrieved successfully: {character_id}")

    # Heal expired wounds

    if character.get("Wounds") and character.get("CharState") != CharState.DEAD.value:
        wounds: list = character.get("Wounds", [])
        current_time: datetime = datetime.now(timezone.utc)

        remaining_wounds: list = []

        for wound in wounds:
            heal_at: str = wound.get("HealAt")

            try:
                if datetime.fromisoformat(heal_at.replace("Z", "+00:00")) > current_time:
                    remaining_wounds.append(wound)
            except AttributeError as err:
                logger.warning(f"Malformed wound heal time for character {character_id}: {heal_at}, Error: {err}")
                continue

        if len(remaining_wounds) < len(wounds):
            character["Wounds"] = remaining_wounds

            # Update character with healed wounds
            if character.get("CharState", CharState.STANDING.value) == CharState.UNCONSCIOUS.value:
                character["CharState"] = CharState.STANDING.value

            # Update the character's wounds in the database
            update_expression = "SET Wounds = :wounds, CharState = :state, UpdatedAt = :timestamp"
            expression_values: dict = {
                ":wounds": remaining_wounds,
                ":state": character.get("CharState", CharState.STANDING.value),
                ":timestamp": datetime.now(timezone.utc).isoformat(),
            }

            try:
                dynamo.update_item(
                    TableName.CHARACTERS,
                    Key={"CharacterID": character_id},
                    UpdateExpression=update_expression,
                    ExpressionAttributeValues=expression_values,
                )
                logger.info("Updated character wounds after healing")
            except ClientError as err:
                logger.error("Failed to update character.")
                raise RuntimeError(f"Failed to update character wounds: {err}") from err

    # Validate ownership
    if character.get("PlayerID") != player_id:
        logger.warning(f"Character ownership mismatch: {character_id} not owned by {player_id}")
        raise ValueError("Character not owned by player")

    # Calculate current health from MaxHealth and Wounds
    max_health = character.get("MaxHealth", 10)
    wounds = character.get("Wounds", [])
    character["Health"] = max_health - len(wounds)

    return character


def create_character_record(character_item: dict) -> bool:
    """
    Create character record in database.

    Note: Name uniqueness is primarily enforced by the query in create_character().
    The conditional here prevents overwriting an existing character with the
    same CharacterID (which shouldn't happen with UUID generation).

    Args:
        character_item: Complete character record to create

    Returns:
        True if created successfully

    Raises:
        ValueError: If character with this ID already exists
        RuntimeError: If database operation fails
    """
    try:
        # Conditional ensures we don't overwrite an existing character
        # Note: Name uniqueness is enforced by query check in create_character()
        dynamo.put_item(
            TableName.CHARACTERS,
            character_item,
            ConditionExpression="attribute_not_exists(CharacterID)",
        )
        logger.info(f"Character record created successfully for {character_item.get('CharacterID')}")
        return True
    except ClientError as err:
        if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            # CharacterID collision (extremely rare with UUIDs) or retry
            logger.warning(f"Character ID collision for {character_item.get('CharacterID')}")
            raise ValueError("Character creation failed - please try again") from err
        logger.error(f"Failed to create character record for {character_item.get('CharacterName')} Error: {err}")
        raise RuntimeError(f"Failed to create character record: {err}") from err


def create_character(player_id: str, character_name: str, archetype_name: str, archetype_data: dict) -> dict:
    """Create a new incremental character in DynamoDB.

    Args:
        player_id: Cognito user ID
        character_name: Name of the character
        archetype_name: Name of the archetype
        archetype_data: Archetype data from DynamoDB

    Returns:
        Dict containing:
            - character_id: str - The created character's ID
            - character_name: str - The character's name
            - archetype: str - The archetype used

    Raises:
        ValueError: If character name is already taken
        RuntimeError: If database operations fail
    """
    # Enforce name uniqueness using CharacterNameIndex (per schema)
    try:
        existing = dynamo.query(
            TableName.CHARACTERS,
            IndexName="CharacterNameIndex",
            KeyConditionExpression="CharacterName = :name",
            ExpressionAttributeValues={":name": character_name},
            ProjectionExpression="CharacterID",
        )
        if existing:
            raise ValueError("Character name is already taken")
    except ClientError as err:
        logger.error(f"Failed to check character name uniqueness for '{character_name}' Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to create character: {err}") from err

    character_id = generate_character_id()
    timestamp = datetime.now(timezone.utc).isoformat()

    logger.info(f"Creating new character for {character_name}")

    # Process starting items
    inventory = {}
    starting_items = archetype_data.get("StartingItems", [])
    if starting_items:
        logger.info(f"Processing starting items for character for {character_id}")
        inventory = create_items_from_prototypes(starting_items, character_id)
        logger.info(f"Starting items created for {character_id}")

    # Build character record (inlined)
    character_item = {
        "CharacterID": character_id,
        "PlayerID": player_id,
        "CharacterName": character_name,
        "Archetype": archetype_name,
        "Attributes": archetype_data.get("Attributes", {}),
        "Skills": archetype_data.get("Skills", {}),
        "MaxHealth": archetype_data.get("Health", DEFAULT_HEALTH),
        "Essence": archetype_data.get("Essence", DEFAULT_ESSENCE),
        "MaxEssence": archetype_data.get("Essence", DEFAULT_ESSENCE),
        "Wounds": [],
        "RoomID": archetype_data.get("StartRoom", 0),
        "Inventory": inventory,
        "Resources": {},
        "Progress": {},
        "AvailableStories": archetype_data.get("AvailableStories", []),
        # AbandonedStories and CompletedStories are not initialized here; created later via ADD ops
        "ActiveStoryID": None,
        "ActiveSegmentID": None,
        "Hidden": False,
        "CharState": CharState.STANDING.value,
        "GameMode": "None",
        "CreatedAt": timestamp,
        "UpdatedAt": timestamp,
        "LastPlayed": timestamp,
    }

    # Create character record
    try:
        create_character_record(character_item)
    except ValueError as err:
        # Name already taken - re-raise as-is for proper HTTP status
        raise err
    except RuntimeError as err:
        # Other database failures
        logger.error(f"Failed to create character record: {err}")
        raise RuntimeError(f"Failed to create character: {err}") from err

    # Add to player's character list
    try:
        add_character_to_player_list(
            player_id=player_id, character_name=character_name, character_id=character_id, timestamp=timestamp
        )
    except RuntimeError as err:
        raise RuntimeError(f"Failed to create character: {err}") from err

    logger.info(f"Character creation completed successfully for {character_name}")

    return {"character_id": character_id, "character_name": character_name, "archetype": archetype_name}


def apply_character_updates(character_id: str, updates: dict, current_character=None) -> None:
    """
    Apply accumulated updates to character.

    Handles skill increases, attribute increases, wounds, and room changes.
    SkillXP/AttributeXP contain direct skill level increases (not raw XP).

    Args:
        character_id: Character UUID
        updates: Dict containing CharacterUpdates from segment processing
        current_character: character dict to avoid extra DynamoDB read.
                          If not provided, will use DynamoDB ADD operation for atomic updates.

    Raises:
        RuntimeError: If database update fails
    """
    if not updates:
        logger.info(f"No character updates to apply for {character_id}")
        return

    logger.info(f"Applying character updates for {character_id}: {updates}")

    update_expressions = []
    expression_names = {}
    expression_values = {}

    # Apply skill increases using DynamoDB ADD for atomic increment
    skill_increases = updates.get("SkillXP", {})
    if skill_increases and current_character is None:
        # Use atomic ADD operation when we don't have current character data
        add_expressions = []
        for skill, increase_amount in skill_increases.items():
            if increase_amount > 0:
                safe_skill = skill.replace("-", "_")
                add_expressions.append(f"Skills.#skill_{safe_skill} :inc_{safe_skill}")
                expression_names[f"#skill_{safe_skill}"] = skill
                expression_values[f":inc_{safe_skill}"] = Decimal(str(increase_amount))
        if add_expressions:
            update_expressions.append("ADD " + ", ".join(add_expressions))
    elif skill_increases and current_character is not None:
        # Use SET operation when we have current character data to enforce max
        current_skills = current_character.get("Skills", {})
        for skill, increase_amount in skill_increases.items():
            if increase_amount > 0:
                current_level = float(current_skills.get(skill, 0))
                new_level = min(current_level + increase_amount, MAX_SKILL_LEVEL)
                safe_skill = skill.replace("-", "_")
                update_expressions.append(f"Skills.#skill_{safe_skill} = :level_{safe_skill}")
                expression_names[f"#skill_{safe_skill}"] = skill
                expression_values[f":level_{safe_skill}"] = Decimal(str(new_level))

    # Apply attribute increases using DynamoDB ADD for atomic increment
    attribute_increases = updates.get("AttributeXP", {})
    if attribute_increases and current_character is None:
        # Use atomic ADD operation when we don't have current character data
        add_expressions = []
        for attribute, increase_amount in attribute_increases.items():
            if increase_amount > 0:
                safe_attr = attribute.replace("-", "_")
                add_expressions.append(f"Attributes.#attr_{safe_attr} :inc_{safe_attr}")
                expression_names[f"#attr_{safe_attr}"] = attribute
                expression_values[f":inc_{safe_attr}"] = Decimal(str(increase_amount))
        if add_expressions:
            update_expressions.append("ADD " + ", ".join(add_expressions))
    elif attribute_increases and current_character is not None:
        # Use SET operation when we have current character data to enforce max
        current_attributes = current_character.get("Attributes", {})
        for attribute, increase_amount in attribute_increases.items():
            if increase_amount > 0:
                current_level = float(current_attributes.get(attribute, 0))
                new_level = min(current_level + increase_amount, MAX_SKILL_LEVEL)
                safe_attr = attribute.replace("-", "_")
                update_expressions.append(f"Attributes.#attr_{safe_attr} = :level_{safe_attr}")
                expression_names[f"#attr_{safe_attr}"] = attribute
                expression_values[f":level_{safe_attr}"] = Decimal(str(new_level))

    # Separate SET expressions from ADD expressions
    set_expressions = [expr for expr in update_expressions if not expr.startswith("ADD ")]
    add_expressions = [expr.replace("ADD ", "") for expr in update_expressions if expr.startswith("ADD ")]

    # Apply wounds
    wounds = updates.get("Wounds")
    if wounds:
        set_expressions.append("Wounds = list_append(Wounds, :new_wounds)")
        expression_values[":new_wounds"] = wounds

    # Apply room change
    room_id = updates.get("Room")
    if room_id is not None:
        set_expressions.append("RoomID = :room")
        expression_values[":room"] = room_id

    # Always update timestamp
    set_expressions.append("UpdatedAt = :updated_at")
    expression_values[":updated_at"] = datetime.now(timezone.utc).isoformat()

    # Execute update if there are changes
    if set_expressions or add_expressions:
        try:
            # Build update expression with SET and ADD clauses
            update_parts = []
            if set_expressions:
                update_parts.append("SET " + ", ".join(set_expressions))
            if add_expressions:
                update_parts.append("ADD " + ", ".join(add_expressions))

            update_expression = " ".join(update_parts)

            # Build kwargs to avoid passing None for iterable parameters
            update_kwargs = {
                "UpdateExpression": update_expression,
                "ExpressionAttributeValues": expression_values,
            }
            if expression_names:
                update_kwargs["ExpressionAttributeNames"] = expression_names

            dynamo.update_item(
                TableName.CHARACTERS,
                Key={"CharacterID": character_id},
                **update_kwargs,
            )

            logger.info(f"Character updates applied for {character_id}")
        except ClientError as err:
            logger.error(f"Failed to apply character updates for {character_id} Error: {err}", exc_info=True)
            raise RuntimeError(f"Failed to apply character updates: {err}") from err


def character_clear_story(character_id: str) -> None:
    """
    Clear story-related fields from a character record.

    This function is used to release a character from a broken story chain
    by clearing ActiveStoryID, ActiveSegmentID, and resetting GameMode to "None".

    Args:
        character_id: Character UUID
    """
    try:
        # Update the character to clear story fields and reset GameMode
        update_expression = """
            SET GameMode = :none,
                UpdatedAt = :updated_at
            REMOVE ActiveStoryID, ActiveSegmentID
        """

        expression_values = {":none": "None", ":updated_at": datetime.now(timezone.utc).isoformat()}

        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values,
        )

        logger.info(f"Cleared story fields for character {character_id}")

    except ClientError as err:
        logger.error(f"Failed to clear story for character {character_id} Error: {err}", exc_info=True)
        # Don't raise - just log and return


def apply_death_state(character_id: str, character: dict, new_state: str, timestamp: str) -> None:
    """Apply death state to character, updating both character and player tables atomically.

    If player info is available, uses a transaction to update both tables.
    Falls back to character-only update if player info is missing.

    Args:
        character_id: Character UUID
        character: Full character dict with PlayerID and CharacterName
        new_state: The new state value (should be CharState.DEAD.value)
        timestamp: ISO format timestamp

    Raises:
        ClientError: If database operation fails
    """
    player_id = character.get("PlayerID")
    character_name = character.get("CharacterName")

    if player_id and character_name:
        transact_items = [
            {
                "Update": {
                    "TableName": TABLE_ENV_MAP[TableName.CHARACTERS],
                    "Key": {"CharacterID": {"S": character_id}},
                    "UpdateExpression": "SET CharState = :state, UpdatedAt = :timestamp, RoomID = :room",
                    "ExpressionAttributeValues": {
                        ":state": {"S": new_state},
                        ":timestamp": {"S": timestamp},
                        ":room": {"N": str(DEFAULT_DEATH_ROOM_ID)},
                    },
                }
            },
            {
                "Update": {
                    "TableName": TABLE_ENV_MAP[TableName.PLAYERS],
                    "Key": {"PlayerID": {"S": player_id}},
                    "UpdateExpression": "SET CharacterList.#name.Dead = :dead, UpdatedAt = :timestamp",
                    "ExpressionAttributeNames": {"#name": character_name},
                    "ExpressionAttributeValues": {
                        ":dead": {"BOOL": True},
                        ":timestamp": {"S": timestamp},
                    },
                }
            },
        ]

        try:
            dynamo.transact_write_items(transact_items)
            logger.info(f"Atomically updated character state to dead and player CharacterList for {character_id}")
        except ClientError as err:
            logger.error(f"Failed to update death state for {character_id} Error: {err}", exc_info=True)
            raise RuntimeError(f"Failed to apply death state: {err}") from err
    else:
        logger.warning(f"Cannot update CharacterList - missing PlayerID or CharacterName for {character_id}")
        apply_character_state_change(character_id, new_state, timestamp, include_room_reset=True)


def apply_character_state_change(character_id: str, new_state: str, timestamp: str, include_room_reset: bool = False) -> None:
    """Apply a single character state change.

    Args:
        character_id: Character UUID
        new_state: New CharState value
        timestamp: ISO format timestamp
        include_room_reset: Whether to reset RoomID to default death room

    Raises:
        RuntimeError: If database operation fails
    """
    update_expr = "SET CharState = :state, UpdatedAt = :timestamp"
    expr_values: dict = {":state": new_state, ":timestamp": timestamp}

    if include_room_reset:
        update_expr += ", RoomID = :room"
        expr_values[":room"] = DEFAULT_DEATH_ROOM_ID

    try:
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values,
        )
        logger.info(f"Updated character state to {new_state} for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to update character state for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to update character state: {err}") from err


def apply_death_or_unconscious_outcome(character_id: str, outcome: str, wounds: list) -> str:
    """
    Apply death or unconscious state to character based on outcome and wounds.

    Args:
        character_id: Character UUID
        outcome: Segment outcome ("death", "failure", etc.)
        wounds: Current character wounds

    Returns:
        New character state that was applied

    Raises:
        RuntimeError: If database operation fails
    """
    if outcome != "death":
        return CharState.STANDING.value  # Only death outcomes change state

    try:
        character = get_character(character_id)
    except ClientError as err:
        logger.error(f"Failed to apply death/unconscious state for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to apply death/unconscious state: {err}") from err

    max_health = character.get("MaxHealth", DEFAULT_HEALTH)
    new_state = determine_character_state_from_wounds(max_health, wounds)

    if new_state == character.get("CharState", CharState.STANDING.value):
        return new_state

    timestamp = datetime.now(timezone.utc).isoformat()

    if new_state == CharState.DEAD.value:
        apply_death_state(character_id, character, new_state, timestamp)
    else:
        apply_character_state_change(character_id, new_state, timestamp)

    return new_state
