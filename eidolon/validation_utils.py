"""
Validation utilities for Lambda functions.

Provides common validation functions for user input.
"""

import re


# Character name validation constants
NAME_PATTERN = re.compile(r"^[a-zA-Z'-]+$")
MIN_NAME_LENGTH = 4
MAX_NAME_LENGTH = 20


def validate_character_name(name: str) -> tuple[bool, str | None]:
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
        
    Returns:
        Tuple of (is_valid, error_message)
        - If valid: (True, None)
        - If invalid: (False, error_message)
    """
    if not name:
        return False, "Name cannot be empty"
    
    if len(name) < MIN_NAME_LENGTH:
        return False, f"Name must be at least {MIN_NAME_LENGTH} characters"
    
    if len(name) > MAX_NAME_LENGTH:
        return False, f"Name must be {MAX_NAME_LENGTH} characters or fewer"
    
    if not NAME_PATTERN.match(name):
        return False, "Name must contain only letters, hyphens, and apostrophes"
    
    # Check for special characters at start/end
    if name[0] in "-'" or name[-1] in "-'":
        return False, "Name cannot start or end with special characters"
    
    # Check for consecutive special characters
    for i in range(len(name) - 1):
        if name[i] in "-'" and name[i + 1] in "-'":
            return False, "Name cannot have consecutive special characters"
    
    # Check for excessive repetition
    for i in range(len(name) - 2):
        if name[i] == name[i + 1] == name[i + 2]:
            return False, "Name cannot have more than 2 consecutive identical characters"
    
    # Check letter ratio for short names with special chars
    if len(name) <= 3 and any(c in "-'" for c in name):
        return False, "Short names cannot contain special characters"
    
    # Ensure reasonable letter-to-special-character ratio
    letter_count = sum(1 for c in name if c.isalpha())
    if letter_count / len(name) < 0.5:
        return False, "Name must be primarily letters"
    
    return True, None


def validate_email(email: str) -> bool:
    """
    Validate email format.
    
    Args:
        email: Email address to validate
        
    Returns:
        True if valid email format, False otherwise
    """
    pattern = re.compile(r'^[\w\.-]+@([\w-]+\.)+[\w-]{2,4}$')
    return bool(pattern.match(email))


def validate_uuid(uuid_str: str) -> bool:
    """
    Validate UUID format.
    
    Args:
        uuid_str: UUID string to validate
        
    Returns:
        True if valid UUID format, False otherwise
    """
    pattern = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE
    )
    return bool(pattern.match(uuid_str))


def validate_positive_integer(value: any, min_value: int = 1, max_value: int | None = None) -> tuple[bool, str | None]:
    """
    Validate positive integer within range.
    
    Args:
        value: Value to validate
        min_value: Minimum allowed value (default: 1)
        max_value: Maximum allowed value (optional)
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(value, int):
        return False, "Value must be an integer"
    
    if value < min_value:
        return False, f"Value must be at least {min_value}"
    
    if max_value is not None and value > max_value:
        return False, f"Value must be at most {max_value}"
    
    return True, None


def validate_enum(value: str, allowed_values: list[str], case_sensitive: bool = True) -> tuple[bool, str | None]:
    """
    Validate value is in allowed list.
    
    Args:
        value: Value to validate
        allowed_values: List of allowed values
        case_sensitive: Whether comparison is case-sensitive
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not case_sensitive:
        value = value.lower()
        allowed_values = [v.lower() for v in allowed_values]
    
    if value not in allowed_values:
        return False, f"Value must be one of: {', '.join(allowed_values)}"
    
    return True, None


def sanitize_string(value: str, max_length: int | None = None) -> str:
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
    value = ''.join(char for char in value if ord(char) >= 32 or char in '\n\r\t')
    
    return value


def validate_password_strength(password: str) -> tuple[bool, str | None]:
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
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    
    if not re.search(r'[@$!%*?&]', password):
        return False, "Password must contain at least one special character (@$!%*?&)"
    
    return True, None