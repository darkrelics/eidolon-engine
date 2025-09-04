"""
Character data management utilities for DynamoDB operations.

Provides functions for CRUD operations on character records.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
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
    return str(uuid.uuid4())


def check_character_limit(player_id: str) -> dict:
    """
    Check if player has reached character limit.

    Args:
        player_id: Cognito user ID.

    Returns:
        Dict with:
            - can_create: bool - Whether player can create more characters
            - current_count: int - Current number of characters

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
        current_count = len(character_list)

        return {
            "can_create": current_count < MAX_CHARACTERS_PER_PLAYER,
            "current_count": current_count,
        }

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
    if character.get("Wounds") and character.get("CharState") != "dead":
        wounds: list = character.get("Wounds", [])
        current_time: datetime = datetime.now(timezone.utc)

        remaining_wounds: list = []

        for wound in wounds:
            heal_at: str = wound.get("HealedAt")

            try:
                if datetime.fromisoformat(heal_at.replace("Z", "+00:00")) > current_time:
                    remaining_wounds.append(wound)
            except AttributeError as err:
                logger.warning(f"Malformed wound heal time for character {character_id}: {heal_at}, Error: {err}")
                continue

        if len(remaining_wounds) < len(wounds):
            character["Wounds"] = remaining_wounds

            logger.info("It's a miracle!")

            # Update character with healed wounds
            if character.get("CharState", "standing") == "unconscious":
                character["CharState"] = "standing"

            # Update the character's wounds in the database
            update_expression = "SET Wounds = :wounds, CharState = :state, UpdatedAt = :timestamp"
            expression_values: dict = {
                ":wounds": remaining_wounds,
                ":state": character.get("CharState", "standing"),
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


# TODO - Move to Bloom Module
def check_character_name_availability(character_name: str) -> bool:
    """
    Check if a character name is available.

    Args:
        character_name: Name to check

    Returns:
        True if name is available, False if taken

    Raises:
        RuntimeError: If database query fails
    """
    logger.info(f"Checking character name availability for {character_name}")

    try:
        existing_chars = dynamo.query(
            TableName.CHARACTERS,
            IndexName="CharacterNameIndex",
            KeyConditionExpression="CharacterName = :name",
            ExpressionAttributeValues={":name": character_name},
            Limit=1,
        )

        if existing_chars:
            logger.info(f"Character name already taken for {character_name}")
            return False

        return True

    except ClientError as err:
        logger.error(f"Error checking character name availability for {character_name} Error: {err}")
        raise RuntimeError(f"Failed to check character name availability: {err}") from err


def build_character_record(
    character_id: str,
    player_id: str,
    character_name: str,
    archetype_name: str,
    archetype_data: dict,
    inventory: dict,
    timestamp: str,
) -> dict:
    """
    Build a character record with all required fields.

    Args:
        character_id: Generated character UUID
        player_id: Player UUID
        character_name: Character name
        archetype_name: Archetype name
        archetype_data: Archetype data from database
        inventory: Inventory items mapping
        timestamp: ISO format timestamp

    Returns:
        Complete character record dict
    """
    return {
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
        # AbandonedStories and CompletedStories are not initialized here
        # They will be created as DynamoDB sets when first used via ADD operations
        "ActiveStoryID": None,
        "ActiveSegmentID": None,
        "Hidden": False,
        "CharState": "standing",
        "GameMode": "None",
        "CreatedAt": timestamp,
        "UpdatedAt": timestamp,
        "LastPlayed": timestamp,
    }


def create_character_record(character_item: dict) -> bool:
    """
    Create character record in database with atomic name check.

    Args:
        character_item: Complete character record to create

    Returns:
        True if created successfully

    Raises:
        ValueError: If character name is already taken
        RuntimeError: If database operation fails
    """
    try:
        # Use conditional put - only succeeds if name doesn't exist
        dynamo.put_item(TableName.CHARACTERS, character_item, ConditionExpression="attribute_not_exists(CharacterName)")
        logger.info(f"Character record created successfully for {character_item.get('CharacterID')}")
        return True
    except ClientError as err:
        if err.response["Error"]["Code"] == "ConditionalCheckFailedException":
            # Name already taken - convert to ValueError for proper HTTP status
            logger.info(f"Character name '{character_item.get('CharacterName')}' already taken")
            raise ValueError("Character name is already taken") from err
        logger.error(f"Failed to create character record for {character_item.get('CharacterName')} Error: {err}")
        raise RuntimeError(f"Failed to create character record: {err}") from err


def rollback_character_creation(character_id: str) -> None:
    """
    Attempt to rollback a failed character creation.

    Args:
        character_id: Character UUID to delete
    """
    try:
        dynamo.delete_item(TableName.CHARACTERS, Key={"CharacterID": character_id})
        logger.info(f"Successfully rolled back character creation for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to rollback character creation for {character_id} Error: {err}")


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

    # Build character record
    character_item = build_character_record(
        character_id=character_id,
        player_id=player_id,
        character_name=character_name,
        archetype_name=archetype_name,
        archetype_data=archetype_data,
        inventory=inventory,
        timestamp=timestamp,
    )

    # Create character record
    try:
        create_character_record(character_item)
    except ValueError:
        # Name already taken - re-raise as-is for proper HTTP status
        raise
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
        # Rollback character creation
        rollback_character_creation(character_id)
        raise RuntimeError(f"Failed to create character: {err}") from err

    logger.info(f"Character creation completed successfully for {character_name}")

    return {"character_id": character_id, "character_name": character_name, "archetype": archetype_name}


def apply_character_updates(character_id: str, updates: dict) -> None:
    """
    Apply accumulated updates to character.

    Handles skill XP, attribute XP, wounds, and room changes.

    Args:
        character_id: Character UUID
        updates: Dict containing CharacterUpdates from segment processing

    Raises:
        RuntimeError: If database update fails
    """
    if not updates:
        logger.info(f"No character updates to apply for {character_id}")
        return

    update_expressions = []
    expression_names = {}
    expression_values = {}

    # Apply skill XP updates
    skill_xp = updates.get("SkillXP", {})
    for skill, xp_value in skill_xp.items():
        if xp_value > 0:
            safe_skill = skill.replace("-", "_")
            update_expressions.append(
                f"Skills.#skill_{safe_skill} = if_not_exists(Skills.#skill_{safe_skill}, :zero) + :xp_{safe_skill}"
            )
            expression_names[f"#skill_{safe_skill}"] = skill
            expression_values[f":xp_{safe_skill}"] = Decimal(str(xp_value))

    # Apply attribute XP updates
    attribute_xp = updates.get("AttributeXP", {})
    for attribute, xp_value in attribute_xp.items():
        if xp_value > 0:
            safe_attr = attribute.replace("-", "_")
            update_expressions.append(
                f"Attributes.#attr_{safe_attr} = if_not_exists(Attributes.#attr_{safe_attr}, :zero) + :xp_{safe_attr}"
            )
            expression_names[f"#attr_{safe_attr}"] = attribute
            expression_values[f":xp_{safe_attr}"] = Decimal(str(xp_value))

    # Apply wounds
    wounds = updates.get("Wounds", [])
    if wounds:
        update_expressions.append("Wounds = list_append(if_not_exists(Wounds, :empty_list), :new_wounds)")
        expression_values[":new_wounds"] = wounds
        expression_values[":empty_list"] = []

    # Apply room change
    room_id = updates.get("Room")
    if room_id is not None:
        update_expressions.append("RoomID = :room")
        expression_values[":room"] = room_id

    # Set common values
    if expression_values and ":zero" not in expression_values:
        expression_values[":zero"] = Decimal("0")

    # Execute update if there are changes
    if update_expressions:
        try:
            update_expression = "SET " + ", ".join(update_expressions)
            update_expression += ", UpdatedAt = :updated_at"
            expression_values[":updated_at"] = datetime.now(timezone.utc).isoformat()

            dynamo.update_item(
                TableName.CHARACTERS,
                Key={"CharacterID": character_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names if expression_names else None,
                ExpressionAttributeValues=expression_values,
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
