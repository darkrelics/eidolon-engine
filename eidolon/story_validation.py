"""
Story validation and prerequisites.

Provides functions for checking story availability and prerequisites.
"""

from eidolon.constants import CharState
from eidolon.logger import logger


def check_story_prerequisites(character: dict, prerequisites: dict) -> bool:
    """
    Check if character meets story prerequisites.

    Args:
        character: Character data
        prerequisites: Story prerequisite requirements

    Returns:
        True if all prerequisites are met
    """
    min_skills = prerequisites.get("minSkills", {})
    character_skills = character.get("Skills", {})

    for skill, min_value in min_skills.items():
        if character_skills.get(skill, 0) < min_value:
            return False

    required_items = prerequisites.get("requiredItems", [])
    if required_items:
        inventory = character.get("Inventory", {})
        # Inventory is a dict where keys are slot numbers and values are item IDs
        inventory_item_ids = list(inventory.values())
        for required_item_id in required_items:
            if required_item_id not in inventory_item_ids:
                return False

    return True


def validate_story_available(character: dict, story_id: str) -> None:
    """
    Validate that the story is available to the character.

    Checks:
    1. Story is in character's AvailableStories list
    2. Story has not been completed already (for one-time stories)
    3. Story cooldown has expired (for daily stories)

    Args:
        character: Character data
        story_id: Story UUID to start

    Raises:
        ValueError: If story not available to character
    """
    available_stories = character.get("AvailableStories", [])
    if story_id not in available_stories:
        raise ValueError("Story not available")

    # Check if story has been completed
    completed_stories = character.get("CompletedStories", [])
    for entry in completed_stories:
        # Each entry is a single-key map: {story_id: {"StoryType": "daily", "CompletedAt": timestamp}}
        if story_id in entry:
            story_data = entry[story_id]
            story_type = story_data.get("StoryType", "")

            if story_type == "one-time":
                raise ValueError("Story already completed")

            if story_type == "daily":
                # This should have been cleaned up, but double-check as safety
                raise ValueError("Story available again tomorrow")


def story_eligibility(character: dict) -> bool:
    """
    Check if a character is in a valid state to start a story.

    Args:
        character: Character data from database

    Returns:
        True if character can start a new story, False otherwise
    """
    # Check death state first - dead characters cannot start stories
    char_state = character.get("CharState")
    if char_state == CharState.DEAD.value:
        return False

    # Existing GameMode validation continues unchanged
    game_mode = character.get("GameMode", "None")
    if game_mode == "None":
        return True

    if game_mode == "Incremental":
        # Allow if no active story/segment (recovery from inconsistent state)
        if not character.get("ActiveStoryID") and not character.get("ActiveSegmentID"):
            character_id = character.get("CharacterID")
            logger.info(f"Character {character_id} in Incremental mode but no active story/segment, allowing new story")
            return True

    return False
