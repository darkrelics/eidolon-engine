"""
Validation utilities for Lambda functions.

Provides common validation functions for user input.
"""

import re

# Character name validation constants
NAME_PATTERN = re.compile(r"^[a-zA-Z'-]+$")
MIN_NAME_LENGTH: int = 4
MAX_NAME_LENGTH: int = 20


def validate_character_name(name: str) -> None:
    """
    Validate character name according to game rules.

    Rules:
    - 4-20 characters long
    - Only letters, hyphens, and apostrophes
    - Cannot start or end with special characters
    - No consecutive special characters
    - No more than 2 consecutive identical characters
    - Must be primarily letters

    Args:
        name: Character name to validate

    Raises:
        ValueError: If name violates any validation rules
    """
    if not name:
        raise ValueError("Name cannot be empty")

    if len(name) < MIN_NAME_LENGTH:
        raise ValueError(f"Name must be at least {MIN_NAME_LENGTH} characters")

    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"Name must be {MAX_NAME_LENGTH} characters or fewer")

    if not NAME_PATTERN.match(name):
        raise ValueError("Name must contain only letters, hyphens, and apostrophes")

    # Check for special characters at start/end
    if name[0] in "-'" or name[-1] in "-'":
        raise ValueError("Name cannot start or end with special characters")

    # Check for consecutive special characters
    for i in range(len(name) - 1):
        if name[i] in "-'" and name[i + 1] in "-'":
            raise ValueError("Name cannot have consecutive special characters")

    # Check for excessive repetition
    for i in range(len(name) - 2):
        if name[i] == name[i + 1] == name[i + 2]:
            raise ValueError("Name cannot have more than 2 consecutive identical characters")

    # Check letter ratio for short names with special chars
    if len(name) <= 3 and any(c in "-'" for c in name):
        raise ValueError("Short names cannot contain special characters")

    # Ensure reasonable letter-to-special-character ratio
    letter_count: int = sum(1 for c in name if c.isalpha())
    if letter_count / len(name) < 0.5:
        raise ValueError("Name must be primarily letters")

    # Check reserved prefixes
    name_lower: str = name.lower()
    reserved_prefixes: list = ["gm_", "admin_", "mod_", "system_", "server_", "npc_"]
    for prefix in reserved_prefixes:
        if name_lower.startswith(prefix):
            raise ValueError("Name uses reserved prefix")

    # Check reserved exact names
    reserved_names: list = ["admin", "administrator", "moderator", "gamemaster", "system"]
    if name_lower in reserved_names:
        raise ValueError("Name is reserved")


def validate_uuid(uuid_value: str) -> bool:
    """
    Validate UUID format.

    Args:
        uuid_value: UUID string to validate

    Returns:
        True if valid UUID format, False otherwise
    """
    pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    return bool(pattern.match(uuid_value.lower()))
