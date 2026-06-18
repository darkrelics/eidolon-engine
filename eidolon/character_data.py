"""
Character data management utilities for DynamoDB operations.

Provides functions for CRUD operations on character records.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from botocore.exceptions import ClientError

from eidolon.character_state import determine_character_state_from_wounds
from eidolon.constants import DAILY_STORY_COOLDOWN_SECONDS, DEFAULT_DEATH_ROOM_ID, MAX_SKILL_LEVEL, CharState
from eidolon.dynamo import TABLE_ENV_MAP, TableName, dynamo, to_attribute_value
from eidolon.environment import DEFAULT_ESSENCE, DEFAULT_HEALTH, MAX_CHARACTERS_PER_PLAYER
from eidolon.errors import AccessDeniedError, NotFoundError, ValidationError
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


def fetch_character_record(character_id: str) -> dict:
    """Fetch a raw character record by ID, without healing or derived fields.

    Args:
        character_id: Character UUID

    Returns:
        The raw character dict as stored.

    Raises:
        ValueError: If the character ID is invalid or the character is missing.
        RuntimeError: If the database read fails.
    """
    if not validate_uuid(character_id):
        logger.warning(f"Invalid character ID format for {character_id}")
        raise ValueError("Invalid character ID format")

    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
    except ClientError as err:
        logger.error(f"Error retrieving character for {character_id} Error: {err}")
        raise RuntimeError(f"Failed to retrieve character: {err}") from err

    if not character:
        logger.warning(f"Character not found for {character_id}")
        raise ValueError("Character not found")

    return character


def get_character(character_id: str) -> dict:
    """Get a character by ID with expired wounds healed in memory only.

    Used by the ops and segment workers. This is a write-free read: expired
    wounds are removed from the returned dict so the derived ``Health`` and any
    death determination ignore wounds that should have healed, but the database
    is not modified here. The persisting heal runs on the mutating
    segment-processing tick via ``persist_healed_wounds``.

    Args:
        character_id: Character UUID

    Returns:
        Character dict with expired wounds healed in memory and a derived Health.

    Raises:
        ValueError: If character ID invalid or not found
        RuntimeError: If database error occurs
    """
    character = fetch_character_record(character_id)

    logger.info(f"Character retrieved successfully for {character_id}")

    heal_expired_wounds_in_memory(character)

    # Calculate current health from MaxHealth and remaining Wounds
    max_health = character.get("MaxHealth", 10)
    character["Health"] = max_health - len(character.get("Wounds", []))

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

        # Check if daily story has expired (shared rule with validate_story_available)
        if story_type == "daily":
            time_elapsed = current_timestamp - completed_at
            if time_elapsed < DAILY_STORY_COOLDOWN_SECONDS:
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


def heal_expired_wounds_in_memory(character: dict) -> bool:
    """Remove wounds whose HealAt time has passed from a character dict in place.

    Pure in-memory operation with no database write: filters the wound list and,
    when an unconscious character heals below its wound threshold, returns it to
    standing. A dead character is left untouched. Malformed wound entries are
    dropped with a warning.

    Args:
        character: Character dict loaded from DynamoDB.

    Returns:
        True if the wound list changed, False otherwise.
    """
    wounds: list = character.get("Wounds", [])
    if not wounds or character.get("CharState") == CharState.DEAD.value:
        return False

    current_time = datetime.now(timezone.utc)
    remaining_wounds: list = []
    for wound in wounds:
        heal_at = wound.get("HealAt")
        try:
            if datetime.fromisoformat(heal_at.replace("Z", "+00:00")) > current_time:
                remaining_wounds.append(wound)
        except AttributeError as err:
            logger.warning(f"Malformed wound heal time: {heal_at}, Error: {err}")
            continue

    if len(remaining_wounds) == len(wounds):
        return False

    character["Wounds"] = remaining_wounds
    if character.get("CharState", CharState.STANDING.value) == CharState.UNCONSCIOUS.value:
        character["CharState"] = CharState.STANDING.value

    return True


def write_healed_wounds(character_id: str, character: dict) -> None:
    """Persist an already-healed wound list and state to DynamoDB.

    Args:
        character_id: Character UUID.
        character: Character dict whose Wounds and CharState were healed in memory.

    Raises:
        RuntimeError: If the update fails.
    """
    expression_values: dict = {
        ":wounds": character.get("Wounds", []),
        ":state": character.get("CharState", CharState.STANDING.value),
        ":timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET Wounds = :wounds, CharState = :state, UpdatedAt = :timestamp",
            ExpressionAttributeValues=expression_values,
        )
        logger.info(f"Persisted healed wounds for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to persist healed wounds for {character_id}")
        raise RuntimeError(f"Failed to update character wounds: {err}") from err


def persist_healed_wounds(character_id: str) -> dict:
    """Heal a character's expired wounds and persist the result.

    For mutating paths only (the segment-processing tick). Fetches the character,
    removes expired wounds in memory, and writes the healed wound list and state
    back only when something changed. Reads should use ``get_character`` or
    ``character_get``, which heal in memory without writing.

    Args:
        character_id: Character UUID.

    Returns:
        Character dict with expired wounds healed and a derived Health field.

    Raises:
        ValueError: If the character ID is invalid or the character is missing.
        RuntimeError: If a database operation fails.
    """
    character = fetch_character_record(character_id)

    if heal_expired_wounds_in_memory(character):
        write_healed_wounds(character_id, character)
        logger.info(f"Healed expired wounds for {character_id}")

    max_health = character.get("MaxHealth", 10)
    character["Health"] = max_health - len(character.get("Wounds", []))

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
        raise ValidationError("Invalid character ID format")

    if not validate_uuid(player_id):
        logger.warning(f"Invalid player ID format: {player_id}")
        raise ValidationError("Invalid player ID format")

    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})

        if not character:
            logger.warning(f"Character not found for {character_id}")
            raise NotFoundError("Character not found")

    except ClientError as err:
        logger.error(f"Error retrieving character for {character_id} Error: {err}")
        raise RuntimeError(f"Failed to retrieve character: {err}") from err

    logger.debug(f"Character retrieved successfully: {character_id}")

    # Validate ownership before any state change, so a request for a character
    # the caller does not own cannot trigger a wound-healing write on it.
    if character.get("PlayerID") != player_id:
        logger.warning(f"Character ownership mismatch: {character_id} not owned by {player_id}")
        raise AccessDeniedError("Character not owned by player")

    # Heal expired wounds in memory only; reads must not write (ARC-1). The
    # persisting heal runs on the mutating segment-processing tick.
    heal_expired_wounds_in_memory(character)

    # Calculate current health from MaxHealth and remaining Wounds
    max_health = character.get("MaxHealth", 10)
    character["Health"] = max_health - len(character.get("Wounds", []))

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

    # Process starting items. The character is the base container: its Contents
    # holds equipped items, containers, and loose items. Worn starting items are
    # assigned equipment slots so they are effective from creation.
    equipment = {"Contents": [], "LeftHandID": None, "RightHandID": None, "WornSlots": {}}
    starting_items = archetype_data.get("StartingItems", [])
    if starting_items:
        logger.info(f"Processing starting items for character for {character_id}")
        equipment = create_items_from_prototypes(starting_items, character_id)
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
        "Contents": equipment.get("Contents", []),
        "WornSlots": equipment.get("WornSlots", {}),
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

    # Persist a hand slot only when a starting item occupies it, so an empty hand
    # satisfies the attribute_not_exists guard used when equipping later.
    for hand_field in ("LeftHandID", "RightHandID"):
        hand_item = equipment.get(hand_field)
        if hand_item:
            character_item[hand_field] = hand_item

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


def build_group_level_updates(group: str, increases: dict, current_members) -> tuple:
    """Build the SET/ADD expression parts for one level group (Skills or Attributes).

    With ``current_members`` (the character's current levels) the increase is a
    clamped ``SET``; without it, an atomic ``ADD`` that ``clamp_levels_to_max``
    caps after the write. Placeholders are prefixed by the group so Skills and
    Attributes never collide. Returns ``(set_parts, add_parts, names, values)``.

    Args:
        group: "Skills" or "Attributes".
        increases: Map of member name to level increase.
        current_members: Current levels for a clamped SET, or None for atomic ADD.
    """
    set_parts: list = []
    add_parts: list = []
    names: dict = {}
    values: dict = {}
    for member, increase in increases.items():
        if increase <= 0:
            continue
        safe = f"{group}_{member}".replace("-", "_")
        names[f"#m_{safe}"] = member
        if current_members is None:
            add_parts.append(f"{group}.#m_{safe} :v_{safe}")
            values[f":v_{safe}"] = Decimal(str(increase))
        else:
            new_level = min(float(current_members.get(member, 0)) + increase, MAX_SKILL_LEVEL)
            set_parts.append(f"{group}.#m_{safe} = :v_{safe}")
            values[f":v_{safe}"] = Decimal(str(new_level))
    return set_parts, add_parts, names, values


def execute_character_update(character_id: str, set_parts: list, add_parts: list, names: dict, values: dict) -> None:
    """Apply the assembled SET/ADD expressions to the character record.

    When an atomic ADD is present, requests the post-update values and clamps any
    level that overflowed ``MAX_SKILL_LEVEL`` (the ADD cannot cap itself).

    Raises:
        RuntimeError: If the database update fails.
    """
    if not set_parts and not add_parts:
        return

    update_parts = []
    if set_parts:
        update_parts.append("SET " + ", ".join(set_parts))
    if add_parts:
        update_parts.append("ADD " + ", ".join(add_parts))

    update_kwargs = {"UpdateExpression": " ".join(update_parts), "ExpressionAttributeValues": values}
    if names:
        update_kwargs["ExpressionAttributeNames"] = names
    if add_parts:
        update_kwargs["ReturnValues"] = "UPDATED_NEW"

    try:
        response = dynamo.update_item(TableName.CHARACTERS, Key={"CharacterID": character_id}, **update_kwargs)
        if add_parts:
            # update_item(ReturnValues=UPDATED_NEW) nests the changed Skills/Attributes
            # maps under the response's "Attributes" key; clamp expects those maps at
            # the top level. Passing the raw response made it iterate the group maps as
            # if they were level values (float(dict) -> TypeError), failing every XP apply.
            clamp_levels_to_max(character_id, (response or {}).get("Attributes", {}))
        logger.info(f"Character updates applied for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to apply character updates for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to apply character updates: {err}") from err


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

    set_parts: list = []
    add_parts: list = []
    names: dict = {}
    values: dict = {}

    current_skills = current_character.get("Skills", {}) if current_character is not None else None
    current_attributes = current_character.get("Attributes", {}) if current_character is not None else None

    for group, increases, current_members in (
        ("Skills", updates.get("SkillXP", {}), current_skills),
        ("Attributes", updates.get("AttributeXP", {}), current_attributes),
    ):
        if not increases:
            continue
        group_set, group_add, group_names, group_values = build_group_level_updates(group, increases, current_members)
        set_parts.extend(group_set)
        add_parts.extend(group_add)
        names.update(group_names)
        values.update(group_values)

    wounds = updates.get("Wounds")
    if wounds:
        set_parts.append("Wounds = list_append(Wounds, :new_wounds)")
        values[":new_wounds"] = wounds

    room_id = updates.get("Room")
    if room_id is not None:
        set_parts.append("RoomID = :room")
        values[":room"] = room_id

    set_parts.append("UpdatedAt = :updated_at")
    values[":updated_at"] = datetime.now(timezone.utc).isoformat()

    execute_character_update(character_id, set_parts, add_parts, names, values)


def clamp_levels_to_max(character_id: str, updated_attributes: dict) -> None:
    """Clamp any skill or attribute that exceeded MAX_SKILL_LEVEL.

    Atomic ``ADD`` increments cannot cap their result, so after the increment the
    post-update values are inspected and any that overflowed are set back down to
    the ceiling. Non-fatal: a failure here leaves the increment intact.

    Args:
        character_id: Character UUID.
        updated_attributes: The DynamoDB ``UPDATED_NEW`` response, holding the
            changed ``Skills`` and ``Attributes`` maps.
    """
    set_parts: list = []
    names: dict = {}
    values: dict = {}
    for group in ("Skills", "Attributes"):
        members = updated_attributes.get(group)
        if not isinstance(members, dict):
            continue
        for name, level in members.items():
            if level is not None and float(level) > MAX_SKILL_LEVEL:
                safe = f"{group}_{name}".replace("-", "_")
                set_parts.append(f"{group}.#m_{safe} = :v_{safe}")
                names[f"#m_{safe}"] = name
                values[f":v_{safe}"] = Decimal(str(MAX_SKILL_LEVEL))

    if not set_parts:
        return

    try:
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET " + ", ".join(set_parts),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
        logger.info(f"Clamped {len(set_parts)} over-cap level(s) for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to clamp over-cap levels for {character_id} Error: {err}", exc_info=True)


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
                        ":state": to_attribute_value(new_state),
                        ":timestamp": to_attribute_value(timestamp),
                        ":room": to_attribute_value(DEFAULT_DEATH_ROOM_ID),
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
                        ":dead": to_attribute_value(True),
                        ":timestamp": to_attribute_value(timestamp),
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
    except (ValueError, RuntimeError) as err:
        logger.error(f"Failed to apply death/unconscious state for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to apply death/unconscious state: {err}") from err

    max_health = character.get("MaxHealth", DEFAULT_HEALTH)
    new_state = determine_character_state_from_wounds(max_health, wounds)

    # A "death" outcome means the character died even when the segment inflicted
    # no wounds - e.g. a skill-check death (any sigma <= SIGMA_CRITICAL_FAILURE,
    # or an average below SIGMA_DEATH_AVG). The wound-derived state only reflects
    # combat damage, so a death outcome that leaves the wound track non-lethal
    # would otherwise leave the character standing and able to start new stories.
    if new_state == CharState.STANDING.value:
        new_state = CharState.DEAD.value

    if new_state == character.get("CharState", CharState.STANDING.value):
        return new_state

    timestamp = datetime.now(timezone.utc).isoformat()

    if new_state == CharState.DEAD.value:
        apply_death_state(character_id, character, new_state, timestamp)
    else:
        apply_character_state_change(character_id, new_state, timestamp)

    return new_state
