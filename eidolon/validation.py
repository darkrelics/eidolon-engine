"""
Validation utilities for Lambda functions.

Provides common validation functions for user input.
"""

from re import compile, search

# Character name validation constants
NAME_PATTERN = compile(r"^[a-zA-Z'-]+$")
MIN_NAME_LENGTH = 4
MAX_NAME_LENGTH = 20


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
    letter_count = sum(1 for c in name if c.isalpha())
    if letter_count / len(name) < 0.5:
        raise ValueError("Name must be primarily letters")

    # Check reserved prefixes
    name_lower = name.lower()
    reserved_prefixes = ["gm_", "admin_", "mod_", "system_", "server_", "npc_"]
    for prefix in reserved_prefixes:
        if name_lower.startswith(prefix):
            raise ValueError("Name uses reserved prefix")

    # Check reserved exact names
    reserved_names = ["admin", "administrator", "moderator", "gamemaster", "system"]
    if name_lower in reserved_names:
        raise ValueError("Name is reserved")


def validate_email(email: str) -> bool:
    """
    Validate email format.

    Args:
        email: Email address to validate

    Returns:
        True if valid email format, False otherwise
    """
    pattern = compile(r"^[\w\.-]+@([\w-]+\.)+[\w-]{2,63}$")
    return bool(pattern.match(email))


def validate_uuid(uuid_value: str) -> bool:
    """
    Validate UUID format.

    Args:
        uuid_value: UUID string to validate

    Returns:
        True if valid UUID format, False otherwise
    """
    pattern = compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    return bool(pattern.match(uuid_value.lower()))


def validate_positive_integer(value: int, min_value: int = 1, max_value=None) -> None:
    """
    Validate positive integer within range.

    Args:
        value: Value to validate
        min_value: Minimum allowed value (default: 1)
        max_value: Maximum allowed value (optional)

    Raises:
        ValueError: If value is not a valid positive integer within range
    """
    if not isinstance(value, int):
        raise ValueError("Value must be an integer")

    if value < min_value:
        raise ValueError(f"Value must be at least {min_value}")

    if max_value is not None and value > max_value:
        raise ValueError(f"Value must be at most {max_value}")


def validate_enum(value: str, allowed_values: list, case_sensitive: bool = True) -> None:
    """
    Validate value is in allowed list.

    Args:
        value: Value to validate
        allowed_values: List of allowed values
        case_sensitive: Whether comparison is case-sensitive

    Raises:
        ValueError: If value is not in allowed list
    """
    if not case_sensitive:
        value = value.lower()
        allowed_values = [v.lower() for v in allowed_values]

    if value not in allowed_values:
        raise ValueError(f"Value must be one of: {', '.join(allowed_values)}")


def sanitize_string(value: str, max_length=None) -> str:
    """
    Sanitize user input string.

    Args:
        value: String to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized string
    """
    # Strip whitespace
    value = value.strip()

    # Truncate if needed
    if max_length and len(value) > max_length:
        value = value[:max_length]

    # Remove control characters
    value = "".join(char for char in value if ord(char) >= 32 or char in "\n\r\t")

    return value


def validate_password_strength(password: str) -> None:
    """
    Validate password meets security requirements.

    Requirements:
    - At least 8 characters long
    - Contains uppercase letter
    - Contains lowercase letter
    - Contains number
    - Contains special character

    Args:
        password: Password to validate

    Raises:
        ValueError: If password does not meet security requirements
    """
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")

    if not search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")

    if not search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter")

    if not search(r"\d", password):
        raise ValueError("Password must contain at least one number")

    if not search(r"[@$!%*?&]", password):
        raise ValueError("Password must contain at least one special character (@$!%*?&)")
