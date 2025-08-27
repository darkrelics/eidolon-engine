"""
Story validation and prerequisites.

Provides functions for checking story availability and prerequisites.
"""

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
        inventory_items = list(inventory.values())
        for item_id in required_items:
            if item_id not in inventory_items:
                return False

    return True


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


def story_eligibility(character: dict) -> bool:
    """
    Check if a character is in a valid state to start a story.

    Args:
        character: Character data from database

    Returns:
        True if character can start a new story, False otherwise
    """
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
