# Python Style Guide for Eidolon Engine

This document defines the Python coding standards for the Eidolon Engine project. The style is based on Google's Python Style Guide with specific modifications for our codebase.

## General Principles

- **Single Responsibility**: Every function, class, and module must have exactly one responsibility and one reason to change
- **Simplicity**: Simple, readable code is preferred over clever solutions
- **Consistency**: Follow existing patterns in the codebase
- **Explicit over Implicit**: Make intentions clear in the code

## Import Style

### Use Explicit Imports

Always use explicit imports with `from ... import ...` syntax:

```python
# Good
from eidolon.dynamo import TableName, dynamo
from eidolon.logger import get_logger
from botocore.exceptions import ClientError

# Bad
import eidolon.dynamo
import logging
```

### Import Organization

Organize imports in three groups, separated by blank lines:

1. Standard library imports
2. Third-party library imports
3. Local application imports

```python
import json
import uuid
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import get_logger
from eidolon.validation import validate_uuid
```

### Never Use Typing Import

Do not use the `typing` module. Use Python's native type hints instead:

```python
# Good
def get_character(character_id: str) -> dict:
    pass

def find_items(item_ids: list) -> list:
    pass

# Bad
from typing import List, Dict
def get_character(character_id: str) -> Dict[str, Any]:
    pass
```

## Type Hints

### Use Native Python Types

Always use Python's built-in types for type hints:

```python
# Good
def process_data(items: list, config: dict) -> dict:
    pass

def get_names() -> list:
    pass

# Bad - avoid Union types
def process_data(items: list | None) -> dict:  # Don't use Union
    pass
```

### Avoid Union Types

Instead of Union types, use separate functions or handle None cases explicitly:

```python
# Good
def get_character(character_id: str) -> dict:
    """Returns character dict. Raises ValueError if not found."""
    character = dynamo.get_item(...)
    if not character:
        raise ValueError(f"Character {character_id} not found")
    return character

# Bad
def get_character(character_id: str) -> dict | None:
    return dynamo.get_item(...)
```

### Return Empty Collections Instead of None

When a function's return type is `list` or `dict`, return an empty collection rather than None:

```python
# Good
def get_items(character_id: str) -> list:
    """Returns list of items. Empty list if no items found."""
    items = dynamo.query(...)
    return items or []

def get_character_data(character_id: str) -> dict:
    """Returns character data. Empty dict if not found."""
    data = dynamo.get_item(...)
    return data or {}

# Bad
def get_items(character_id: str) -> list:
    items = dynamo.query(...)
    if not items:
        return None  # Wrong! Return [] instead
    return items
```

This eliminates the need for Union types and makes the code more predictable.

## Return Values

### Return Intermediate Values

Functions should return values to intermediate variables rather than returning the results of other function calls directly. This improves debugging, readability, and makes it easier to add error handling or logging:

```python
# Good - return intermediate values
def get_character_data(character_id: str) -> dict:
    """Get complete character data including inventory."""
    character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
    if not character:
        raise ValueError(f"Character {character_id} not found")

    inventory = get_character_inventory(character_id)
    character["Inventory"] = inventory

    return character

def process_combat(attacker_id: str, defender_id: str) -> dict:
    """Process combat between two characters."""
    attacker = get_character(attacker_id)
    defender = get_character(defender_id)

    damage = calculate_damage(attacker, defender)
    updated_defender = apply_damage(defender, damage)

    return {
        "damage": damage,
        "defender": updated_defender
    }

# Bad - directly returning function results
def get_character_data(character_id: str) -> dict:
    """Get complete character data including inventory."""
    return {
        **dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id}),
        "Inventory": get_character_inventory(character_id)
    }

def process_combat(attacker_id: str, defender_id: str) -> dict:
    """Process combat between two characters."""
    return {
        "damage": calculate_damage(get_character(attacker_id), get_character(defender_id)),
        "defender": apply_damage(get_character(defender_id), damage)  # damage not defined!
    }
```

Benefits of using intermediate values:

- **Debugging**: Can inspect intermediate values with breakpoints
- **Logging**: Can log important intermediate results
- **Error Handling**: Can validate intermediate results before proceeding
- **Readability**: Each step is clear and self-documenting
- **Maintainability**: Easy to add new logic between steps

### Prefer Dicts for Complex Returns

Use dictionaries for functions that need to return multiple values or status information:

```python
# Good
def create_character(name: str) -> dict:
    """
    Returns:
        Dict with:
            - success: bool
            - character_id: str (if success)
            - error: str (if failed)
    """
    try:
        character_id = generate_id()
        # ... create character ...
        return {
            "success": True,
            "character_id": character_id
        }
    except Exception as err:
        return {
            "success": False,
            "error": str(err)
        }

# Less preferred
def create_character(name: str) -> tuple:
    return character_id, error_message
```

## Error Handling

### Raise Errors Instead of Returning Them

For functions in the eidolon library, raise exceptions rather than returning error values:

```python
# Good - in eidolon library
def get_character(character_id: str) -> dict:
    """
    Get character by ID.

    Raises:
        ValueError: If character not found
        RuntimeError: If database error occurs
    """
    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
        if not character:
            raise ValueError(f"Character {character_id} not found")
        return character
    except ClientError as err:
        raise RuntimeError(f"Database error: {str(err)}")

# Good - in Lambda handler
def lambda_handler(event: dict, context: object) -> dict:
    try:
        character = get_character(character_id)
        return create_response(200, character)
    except ValueError as err:
        return error_response(str(err), 404)
    except RuntimeError as err:
        logger.error("Database error", exc_info=True)
        return error_response("Internal server error", 500)
```

### Use Narrow Try Blocks

Keep try blocks as small as possible, catching only the specific operations that might fail:

```python
# Good
character_id = event.get("characterId")
if not character_id:
    return error_response("Missing characterId", 400)

try:
    character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
except ClientError as err:
    logger.error("Failed to get character", extra={"error": str(err)})
    return error_response("Database error", 500)

if not character:
    return error_response("Character not found", 404)

# Bad - try block too broad
try:
    character_id = event.get("characterId")
    if not character_id:
        return error_response("Missing characterId", 400)

    character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
    if not character:
        return error_response("Character not found", 404)

    # ... more code ...
except Exception as err:
    return error_response("Error", 500)
```

### Exception Variable Naming

All exceptions must use the variable name `err` and it should be explicitly used in error messages and logging:

```python
# Good - always use 'err' as the exception variable
try:
    result = dynamo.get_item(...)
except ClientError as err:
    logger.error("Database operation failed", extra={"error": str(err)})
    raise RuntimeError(f"Failed to get item: {str(err)}")

# Bad - using other variable names
try:
    result = dynamo.get_item(...)
except ClientError as e:  # Don't use 'e'
    raise RuntimeError(f"Failed: {e}")
except Exception as ex:  # Don't use 'ex'
    logger.error(f"Error: {ex}")
```

### Avoid Nested Try/Except Blocks

Do not nest try/except blocks. Instead, use separate functions or sequential try blocks:

```python
# Bad - nested try/except
try:
    data = get_data()
    try:
        result = process_data(data)
    except ValueError as err:
        logger.error("Processing failed", extra={"error": str(err)})
except ClientError as err:
    logger.error("Database failed", extra={"error": str(err)})

# Good - sequential try blocks
try:
    data = get_data()
except ClientError as err:
    logger.error("Database failed", extra={"error": str(err)})
    raise RuntimeError(f"Failed to get data: {str(err)}")

try:
    result = process_data(data)
except ValueError as err:
    logger.error("Processing failed", extra={"error": str(err)})
    raise RuntimeError(f"Failed to process: {str(err)}")

# Good - separate functions
def get_and_process_data() -> dict:
    data = get_data_with_error_handling()
    return process_data_with_error_handling(data)
```

### One Exception Type Per Except Block

Each except block should handle only one specific exception type. This makes error handling explicit and prevents accidentally catching unintended exceptions:

```python
# Good - each except handles one specific exception
try:
    with open(filename, 'r') as f:
        data = json.load(f)
        process_data(data)
except FileNotFoundError as err:
    logger.error("File not found", extra={"filename": filename, "error": str(err)})
    raise ValueError(f"Configuration file {filename} not found")
except json.JSONDecodeError as err:
    logger.error("Invalid JSON", extra={"filename": filename, "error": str(err)})
    raise ValueError(f"Configuration file {filename} contains invalid JSON")
except KeyError as err:
    logger.error("Missing required key", extra={"key": str(err), "filename": filename})
    raise ValueError(f"Configuration missing required key: {err}")

# Bad - grouping multiple exceptions
try:
    with open(filename, 'r') as f:
        data = json.load(f)
        process_data(data)
except (FileNotFoundError, json.JSONDecodeError, KeyError) as err:
    # Can't handle each error appropriately
    logger.error("Error processing file", extra={"error": str(err)})
    raise ValueError("Failed to process configuration")

# Bad - catching base Exception
try:
    process_data(data)
except Exception as err:
    # Too broad - might catch system errors
    logger.error("Something went wrong", extra={"error": str(err)})
```

This approach ensures:

- Each error type gets appropriate handling
- Error messages are specific and helpful
- Unexpected exceptions aren't silently caught
- Debugging is easier with clear error paths

## Function Documentation

### Google Style Docstrings

Use Google-style docstrings for all functions:

```python
def calculate_damage(attacker: dict, defender: dict, weapon: dict) -> dict:
    """
    Calculate combat damage between attacker and defender.

    Uses the MUD combat system rules to determine damage dealt,
    considering attributes, skills, and weapon properties.

    Args:
        attacker: Character dict with combat stats
        defender: Character dict with defense stats
        weapon: Weapon item dict with damage properties

    Returns:
        Dict containing:
            - damage: int - Amount of damage dealt
            - damage_type: str - Type of damage (bashing/lethal/aggravated)
            - critical: bool - Whether this was a critical hit

    Raises:
        ValueError: If required stats are missing
        RuntimeError: If calculation fails
    """
```

## Lambda Function Architecture

### Lambda Handlers Must Never Raise Exceptions

The `lambda_handler` function is the entry point for AWS Lambda and must **NEVER** raise exceptions. All exceptions must be caught and converted to proper HTTP responses. This ensures:

1. **API Gateway Integration**: Unhandled exceptions result in generic 500 errors with no useful error messages
2. **CloudWatch Logging**: Proper error logging with context before returning the response
3. **Client Experience**: Consistent error response format that clients can parse
4. **Monitoring**: Clear metrics on error types and frequencies

```python
# CRITICAL: lambda_handler must ALWAYS return a valid HTTP response
def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda entry point - handles AWS-specific concerns only.

    IMPORTANT: This function must NEVER raise exceptions. All errors must be
    caught and converted to HTTP responses.
    """
    try:
        # All code that might raise exceptions goes here
        player_id = extract_player_id(event)
        body = parse_json_body(event)
        result = business_logic_function(player_id, body)
        return create_response(200, result)
    except ValueError as err:
        # Handle known business logic errors
        logger.error("Validation error", extra={"error": str(err)})
        return error_response(str(err), 400)
    except Exception as err:
        # Catch ALL other exceptions to prevent Lambda errors
        logger.error("Unexpected error", extra={"error": str(err)}, exc_info=True)
        return error_response("Internal server error", 500)
```

### Separation of Concerns

Lambda functions must follow this pattern:

```python
def lambda_handler(event: dict, context: object) -> dict:
    """Lambda entry point - handles AWS-specific concerns only."""
    try:
        # 1. Log invocation
        logger.info("Lambda invocation", extra={...})

        # 2. Handle CORS preflight
        if event.get("httpMethod") == "OPTIONS":
            return cors_handler.handle_preflight(event)

        # 3. Extract and validate authentication
        player_id = extract_player_id(event)

        # 4. Parse request
        body = parse_json_body(event)

        # 5. Call business logic
        result = business_logic_function(player_id, body.get("param"))

        # 6. Return formatted response
        if result["success"]:
            return create_response(200, result["data"])
        else:
            return error_response(result["error"], result["status_code"])
    except ValueError as err:
        logger.error("Request validation failed", extra={"error": str(err)})
        return error_response(str(err), 400)
    except Exception as err:
        logger.error("Lambda handler error", extra={"error": str(err)}, exc_info=True)
        return error_response("Internal server error", 500)

def business_logic_function(player_id: str, param: str) -> dict:
    """Pure business logic - no AWS dependencies."""
    try:
        # Validate inputs
        if not param:
            return {"success": False, "error": "Missing param", "status_code": 400}

        # Call eidolon library functions
        data = some_eidolon_function(param)

        return {"success": True, "data": data}
    except ValueError as err:
        return {"success": False, "error": str(err), "status_code": 400}
```

## Naming Conventions

### Variables and Functions

Use snake_case for all variables and functions:

```python
# Good
character_name = "Thorin"
def get_character_by_name(name: str) -> dict:
    pass

# Bad
characterName = "Thorin"
def getCharacterByName(name: str) -> dict:
    pass
```

### Constants

Use UPPER_SNAKE_CASE for constants:

```python
MAX_CHARACTERS_PER_PLAYER = 10
DEFAULT_HEALTH = 100
TABLE_NAME_PREFIX = "eidolon-"
```

### Classes

Use CamelCase for classes:

```python
class CharacterManager:
    pass

class CombatSystem:
    pass
```

### JSON Field Names

Use PascalCase for all JSON field names to maintain consistency with DynamoDB field names:

```python
# Good - PascalCase for JSON fields
response = {
    "CharacterID": character_id,
    "CharacterName": character_name,
    "AvailableStories": story_list,
    "Attributes": {"Strength": 4, "Agility": 2}
}

# Bad - don't use camelCase or snake_case
response = {
    "characterId": character_id,  # Wrong
    "character_name": character_name,  # Wrong
}
```

## Code Organization

### Module Length

Modules should be kept concise and focused. Keep modules under 300 lines to maintain readability and encourage proper separation of concerns.

### Private Methods and Functions

Do not use private methods or functions (those starting with underscore) in Python. Python's privacy model is based on convention rather than enforcement, making private methods pointless. Instead, use clear documentation to indicate internal interfaces.

```python
# Bad - don't use private methods
class Character:
    def _calculate_damage(self):  # Don't do this
        pass

# Good - use regular methods with clear documentation
class Character:
    def calculate_damage(self):
        """Internal method for damage calculation."""
        pass
```

### Methods vs Functions

Only create methods if they are tightly coupled to the class. If a function doesn't need access to instance state, make it a module-level function instead.

```python
# Good - function doesn't need instance state
def calculate_combat_damage(attacker_stats: dict, defender_stats: dict) -> int:
    """Calculate damage between two combatants."""
    pass

class Character:
    def take_damage(self, amount: int) -> None:
        """Apply damage to this character. Tightly coupled to instance."""
        self.health -= amount

# Bad - method that doesn't use instance state
class Character:
    def calculate_combat_damage(self, attacker_stats: dict, defender_stats: dict) -> int:
        """This doesn't use self, should be a function."""
        pass
```

### Single Responsibility Principle (SRP)

The Single Responsibility Principle is **mandatory** for all code. Each function, class, or module must have exactly one responsibility and one reason to change. This is the most important design principle in our codebase.

```python
# Good - each function has one job
def validate_character_name(name: str) -> bool:
    """Validate character name format."""
    pass

def check_name_availability(name: str) -> bool:
    """Check if name is available in database."""
    pass

def create_character_record(character_data: dict) -> str:
    """Create character in database."""
    pass

# Bad - function does too much (validates AND saves)
def create_and_validate_character(name: str, player_id: str) -> dict:
    """Validates, checks availability, creates character, sends email..."""
    pass
```

#### SRP Litmus Test

If you need "and" to describe what a function does, it's doing too much:

- ❌ "This function validates AND saves the character"
- ❌ "This class manages authentication AND user profiles"
- ❌ "This module handles database operations AND business logic"

#### Common SRP Violations to Avoid

1. **Mixed Concerns in Functions**:

```python
# Bad - mixes validation, database operation, and notification
def process_character(character_data: dict) -> dict:
    # Validates data
    if not character_data.get("name"):
        raise ValueError("Missing name")

    # Saves to database
    dynamo.put_item(TableName.CHARACTERS, character_data)

    # Sends notification
    send_email(character_data["email"], "Character created")

    return {"success": True}

# Good - separate responsibilities
def validate_character_data(character_data: dict) -> None:
    """Validate character data. Raises ValueError if invalid."""
    if not character_data.get("name"):
        raise ValueError("Missing name")

def save_character(character_data: dict) -> None:
    """Save character to database."""
    dynamo.put_item(TableName.CHARACTERS, character_data)

def notify_character_creation(email: str) -> None:
    """Send character creation notification."""
    send_email(email, "Character created")
```

2. **Lambda Handlers with Business Logic**:

```python
# Bad - Lambda handler contains business logic
def lambda_handler(event: dict, context: object) -> dict:
    character_id = event["characterId"]

    # Business logic should not be in handler
    character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
    if character["Level"] < 10:
        character["Level"] += 1
        dynamo.put_item(TableName.CHARACTERS, character)

    return create_response(200, character)

# Good - Lambda handler only orchestrates
def lambda_handler(event: dict, context: object) -> dict:
    try:
        character_id = event["characterId"]
        character = level_up_character(character_id)
        return create_response(200, character)
    except ValueError as err:
        return error_response(str(err), 400)

def level_up_character(character_id: str) -> dict:
    """Business logic in separate function."""
    character = get_character(character_id)
    if character["Level"] < 10:
        character["Level"] += 1
        save_character(character)
    return character
```

3. **Classes with Multiple Responsibilities**:

```python
# Bad - class handles too many concerns
class Character:
    def __init__(self, character_id: str):
        self.character_id = character_id
        self.data = self.load_from_database()

    def load_from_database(self) -> dict:
        # Database concern mixed with business logic
        return dynamo.get_item(...)

    def validate_name(self) -> bool:
        # Validation mixed with data access
        pass

    def send_notification(self) -> None:
        # Notification concern mixed with character logic
        pass

# Good - separate concerns into focused components
class CharacterRepository:
    """Handles character data persistence."""
    def get_character(self, character_id: str) -> dict:
        pass

    def save_character(self, character: dict) -> None:
        pass

class CharacterValidator:
    """Handles character validation rules."""
    def validate_name(self, name: str) -> bool:
        pass

class CharacterNotifier:
    """Handles character-related notifications."""
    def send_level_up_notification(self, character: dict) -> None:
        pass
```

#### Benefits of SRP

1. **Easier Testing**: Each component can be tested in isolation
2. **Better Reusability**: Single-purpose functions can be reused in different contexts
3. **Simpler Maintenance**: Changes to one responsibility don't affect others
4. **Clearer Code**: Each component has a clear, understandable purpose
5. **Reduced Bugs**: Changes are localized to specific responsibilities

## Logging

### Structured Logging

Always use structured logging with the extra parameter:

```python
# Good
logger.info(
    "Character created",
    extra={
        "character_id": character_id,
        "character_name": name,
        "player_id": player_id
    }
)

logger.error(
    "Failed to create character",
    extra={"error": str(err), "character_name": name},
    exc_info=True  # Include traceback for errors
)

# Bad
logger.info(f"Character {character_id} created for player {player_id}")
```

## Dictionary Operations

### Use .get() Instead of Direct Lookups

Always use the `.get()` method for dictionary lookups instead of direct `[]` access. This prevents KeyError exceptions and makes the code more robust:

```python
# Good - using .get() with defaults
character_name = character_data.get("Name", "Unknown")
health = character_data.get("Health", 100)
skills = character_data.get("Skills", {})

# Good - checking if key exists
character_id = event.get("characterId")
if not character_id:
    return error_response("Missing characterId", 400)

# Good - chaining .get() for nested structures
damage = combat_data.get("results", {}).get("damage", 0)

# Bad - direct lookup can raise KeyError
character_name = character_data["Name"]  # KeyError if "Name" missing
health = character_data["Health"]

# Bad - even in try blocks, prefer .get()
try:
    character_id = event["characterId"]
except KeyError:
    return error_response("Missing characterId", 400)
```

## Database Operations

### Use Eidolon Library Functions

All database operations should go through the eidolon library:

```python
# Good - in eidolon library
def get_character(character_id: str) -> dict:
    character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
    if not character:
        raise ValueError(f"Character {character_id} not found")
    return character

# Bad - in Lambda function
def lambda_handler(event: dict, context: object) -> dict:
    # Don't put database calls directly in Lambda handlers
    character = dynamo.get_item(...)  # Wrong!
```

## Comments

### Explain Why, Not What

Comments should explain the reasoning behind code, not describe what it does:

```python
# Good - explains why
# Use exponential backoff to avoid overwhelming the API during retries
retry_delay = min(300, (2 ** attempt) * 10)

# Bad - describes what (obvious from code)
# Set retry_delay to 2 to the power of attempt times 10
retry_delay = (2 ** attempt) * 10
```

### No TODO Comments

Do not add TODO, FIXME, or similar comments. Use GitHub issues for tracking work.

```python
# Bad
# TODO: Add validation for character level
# FIXME: This breaks when name contains Unicode

# Good
# Create a GitHub issue instead
```

## File Organization

### Module Structure

Each module should have:

1. Docstring describing the module
2. Imports (organized as specified above)
3. Constants
4. Classes (if any)
5. Functions

```python
"""
Character management utilities for Lambda functions.

Provides functions for character creation, validation, and management.
"""

import uuid
from datetime import datetime

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import get_logger

# Constants
MAX_NAME_LENGTH = 30
RESERVED_NAMES = ["admin", "system", "gm"]

# Module-level logger
logger = get_logger(__name__)

# Classes
class CharacterValidator:
    pass

# Functions
def create_character(name: str) -> dict:
    pass
```

## Testing

### Test Function Naming

Test functions should clearly describe what they test:

```python
# Good
def test_create_character_with_valid_name_succeeds():
    pass

def test_create_character_with_duplicate_name_raises_error():
    pass

# Bad
def test_create():
    pass

def test_error_case():
    pass
```

## Final Notes

- When in doubt, follow existing patterns in the codebase
- Prioritize readability over cleverness
- Keep functions small and focused
- Use meaningful variable names
- Ensure all code follows PEP 8 where not overridden by this guide
