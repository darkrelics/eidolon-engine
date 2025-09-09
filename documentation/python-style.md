# Python Style Guide for Eidolon Engine

This document defines the Python coding standards for the Eidolon Engine project. The style is based on Google's Python Style Guide with specific modifications for our codebase.

## Production Implementation Status

These style guidelines have been validated through production deployment:

- **Module Size Compliance**: 94% of modules under 300 lines, 100% under 1000 lines
- **16 Lambda Functions**: All following separation of concerns pattern
- **Fixed Logical IDs**: Implemented throughout for resource stability
- **140 Lessons Applied**: Style patterns refined through deployment experience

## General Principles

- **Single Responsibility**: Every function, class, and module must have exactly one responsibility and one reason to change
- **Simplicity**: Simple, readable code is preferred over clever solutions
- **Consistency**: Follow existing patterns in the codebase
- **Explicit over Implicit**: Make intentions clear in the code
- **Python3 Compatibility**: Always use `python3` command, not `python`

### Casing Policy

- Use PascalCase keys across the codebase: persistence, in-memory dicts, and API responses.
- Capitalize well-known abbreviations in keys: `SegmentID`, `OpponentID`, `SkillXP`, `HTTPStatusCode`.
- Do not write case-conversion helpers or case-tolerant reads; fix producers to emit correct keys.

Example:

```
{
  "ChallengeResults": [
    {
      "Attribute": "Melee",
      "Skill": "Parry",
      "Difficulty": 7,
      "Attempts": [{"EffectiveScore": 9, "Difficulty": 7, "Sigma": 0.8, "Success": true}],
      "BestSigma": 0.8,
      "Passed": true
    }
  ],
  "XPUpdates": {"SkillXP": {"Melee": 0.5}, "AttributeXP": {"Agility": 0.05}},
  "CombatState": {"Rounds": 3, "PlayerWounds": [], "OpponentWounds": [], "CombatLog": [], "Victor": "player", "OpponentDefeated": true, "OpponentID": "..."}
}
```

## Import Style

### Use Explicit Imports

Always use explicit imports with `from ... import ...` syntax:

```python
# Good
from eidolon.dynamo import TableName, dynamo
from eidolon.logger logger
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
from pydantic import BaseModel, Field, field_validator

from eidolon.dynamo import TableName, dynamo
from eidolon.logger logger
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

# Good - for dynamic data, use bare dict/list
class MyModel(BaseModel):
    metadata: dict = Field(default_factory=dict)  # Accepts any dict structure
    items: list = Field(default_factory=list)      # Accepts any list content

# Good - be specific when you know the types
class Character(BaseModel):
    inventory: dict[str, int] = Field(default_factory=dict)  # Item counts
    skills: list[str] = Field(default_factory=list)          # Skill names

# Bad
from typing import List, Dict, Any
def get_character(character_id: str) -> Dict[str, Any]:
    pass
```

When data structure is dynamic or unknown, use bare `dict` or `list` without type parameters. This is more practical and honest than attempting to use non-existent type hints.

## Type Hints

### Use Native Python Types

Always use Python's built-in types for type hints. With Python 3.12+, use the pipe operator for optional types:

```python
# Good
def process_data(items: list, config: dict) -> dict:
    pass

def get_names() -> list[str]:
    pass

# Good - for optional values (Python 3.12+)
def get_value(key: str) -> str | None:
    """Returns value or None if not found."""
    return data.get(key)
```

### Union Types in Pydantic Models

Pydantic models are an exception to the "avoid Union types" rule. For Pydantic field definitions, use the pipe operator for optional fields:

```python
# Good - Pydantic models use | None for optional fields
from pydantic import BaseModel, Field

class Character(BaseModel):
    name: str = Field(..., description="Character name")
    level: int = Field(1, ge=1, le=100)
    title: str | None = Field(default=None, description="Optional title")
    last_played: datetime | None = Field(default=None)

# Bad - Pydantic v2 requires proper optional typing
class Character(BaseModel):
    title: str = Field(default=None)  # Wrong! Will cause validation errors
```

### Avoid Union Types in Functions

For regular functions (not Pydantic models), prefer raising exceptions over returning optional values:

```python
# Good - raise exception instead of returning None
def get_character(character_id: str) -> dict:
    """Returns character dict. Raises ValueError if not found."""
    character = dynamo.get_item(...)
    if not character:
        raise ValueError(f"Character {character_id} not found")
    return character

# Less preferred - returning optional
def find_character(character_id: str) -> dict | None:
    """Returns character dict or None if not found."""
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

### EAFP Principle (Easier to Ask for Forgiveness than Permission)

Python follows the EAFP principle rather than LBYL (Look Before You Leap). Always use try/except blocks instead of checking conditions beforehand:

```python
# Good - EAFP style (Pythonic)
try:
    data = load_json(filename)
    process_data(data)
except FileNotFoundError:
    logger.warning(f"File not found: {filename}")
except json.JSONDecodeError as err:
    logger.error(f"Invalid JSON in {filename}: {err}")

# Bad - LBYL style (not Pythonic)
if os.path.exists(filename):
    data = load_json(filename)
    process_data(data)
else:
    logger.warning(f"File not found: {filename}")
```

More examples:

```python
# Good - try to use the dictionary key
try:
    value = config["important_setting"]
    process_setting(value)
except KeyError:
    logger.warning("Using default setting")
    value = DEFAULT_SETTING

# Bad - check if key exists first
if "important_setting" in config:
    value = config["important_setting"]
    process_setting(value)
else:
    logger.warning("Using default setting")
    value = DEFAULT_SETTING

# Good - try the operation
try:
    result = int(user_input)
except ValueError:
    logger.error("Invalid number format")
    return error_response("Please enter a valid number", 400)

# Bad - check if it's numeric first
if user_input.isdigit():
    result = int(user_input)
else:
    logger.error("Invalid number format")
    return error_response("Please enter a valid number", 400)
```

The EAFP principle makes code:

- More Pythonic and idiomatic
- Often faster (no redundant checks)
- More readable (focus on the happy path)
- More robust (handles edge cases better)

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
        raise RuntimeError(f"Database error: {err}")

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
    logger.error("Failed to get character")
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
    logger.error("Database operation failed")
    raise RuntimeError(f"Failed to get item: {err}")

# Bad - using other variable names
try:
    result = dynamo.get_item(...)
except ClientError as e:  # Don't use 'e'
    raise RuntimeError(f"Failed: {e}")
except Exception as ex:  # Don't use 'ex'
    logger.error(f"Error: {ex}")
```

### Exception Chaining with 'from err'

When re-raising exceptions, always use the `from err` syntax to preserve the exception chain. This maintains the full traceback for debugging while allowing you to provide more context-specific error messages:

```python
# Good - using 'from err' to chain exceptions
def get_character(character_id: str) -> dict:
    """Get character from database."""
    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
        if not character:
            raise ValueError(f"Character {character_id} not found")
        return character
    except ClientError as err:
        logger.error("Database query failed")
        raise RuntimeError(f"Failed to retrieve character {character_id}") from err

# Good - preserving exception chain across multiple layers
def process_character_action(character_id: str, action: str) -> dict:
    """Process an action for a character."""
    try:
        character = get_character(character_id)
        return apply_action(character, action)
    except RuntimeError as err:
        # Re-raise with additional context, preserving the chain
        raise RuntimeError(f"Cannot process action '{action}' for character") from err
    except ValueError as err:
        # Convert to more specific error type while preserving chain
        raise ValueError(f"Invalid character for action '{action}'") from err

# Bad - not using 'from err', loses original exception context
def get_character(character_id: str) -> dict:
    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
        return character
    except ClientError as err:
        # Wrong - loses the original ClientError traceback
        raise RuntimeError(f"Failed to retrieve character {character_id}")

# Bad - silently catching and re-raising different exception
def process_data(data: dict) -> dict:
    try:
        return transform_data(data)
    except KeyError:
        # Wrong - original KeyError context is lost
        raise ValueError("Missing required field")
```

### Exception Handling Responsibility

The function that raises an exception is NOT responsible for handling it. Exception handling is the responsibility of the calling function. This promotes clean separation of concerns:

```python
# Good - library function raises, caller handles
# In eidolon/character.py (library)
def update_character_health(character_id: str, damage: int) -> dict:
    """
    Apply damage to character.

    Raises:
        ValueError: If character not found or damage invalid
        RuntimeError: If database operation fails
    """
    if damage < 0:
        raise ValueError(f"Damage cannot be negative: {damage}")

    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
        if not character:
            raise ValueError(f"Character {character_id} not found")

        character["Health"] -= damage
        dynamo.put_item(TableName.CHARACTERS, character)
        return character
    except ClientError as err:
        raise RuntimeError(f"Failed to update character health") from err

# In Lambda handler (caller)
def lambda_handler(event: dict, context: object) -> dict:
    """Lambda handler is responsible for handling exceptions."""
    try:
        character_id = event.get("characterId")
        damage = event.get("damage", 0)

        # Call library function - it will raise if there's an error
        updated_character = update_character_health(character_id, damage)
        return create_response(200, updated_character)

    except ValueError as err:
        # Caller handles the ValueError appropriately
        logger.warning("Invalid request")
        return error_response(str(err), 400)
    except RuntimeError as err:
        # Caller handles the RuntimeError appropriately
        logger.error("Database error", exc_info=True)
        return error_response("Internal server error", 500)

# Bad - function tries to handle its own exceptions
def update_character_health(character_id: str, damage: int) -> dict:
    """Wrong - function shouldn't handle its own exceptions."""
    try:
        if damage < 0:
            # Wrong - returning error instead of raising
            return {"success": False, "error": "Invalid damage"}

        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
        character["Health"] -= damage
        dynamo.put_item(TableName.CHARACTERS, character)
        return {"success": True, "character": character}
    except Exception as err:
        # Wrong - catching and converting to return value
        return {"success": False, "error": str(err)}
```

Benefits of proper exception chaining and handling:

- **Full Tracebacks**: The `from err` syntax preserves the complete exception chain
- **Better Debugging**: Can trace errors through multiple layers of the application
- **Clear Responsibilities**: Functions focus on their core logic, not error handling
- **Flexible Error Handling**: Callers can handle errors appropriately for their context
- **Proper Logging**: Each layer can add relevant context to error messages

### Avoid Nested Try/Except Blocks

Do not nest try/except blocks. Instead, use separate functions or sequential try blocks:

```python
# Bad - nested try/except
try:
    data = get_data()
    try:
        result = process_data(data)
    except ValueError as err:
        logger.error("Processing failed")
except ClientError as err:
    logger.error("Database failed")

# Good - sequential try blocks
try:
    data = get_data()
except ClientError as err:
    logger.error("Database failed")
    raise RuntimeError(f"Failed to get data: {err}")

try:
    result = process_data(data)
except ValueError as err:
    logger.error("Processing failed")
    raise RuntimeError(f"Failed to process: {err}")

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
    logger.error("File not found")
    raise ValueError(f"Configuration file {filename} not found")
except json.JSONDecodeError as err:
    logger.error("Invalid JSON")
    raise ValueError(f"Configuration file {filename} contains invalid JSON")
except KeyError as err:
    logger.error("Missing required key")
    raise ValueError(f"Configuration missing required key: {err}")

# Bad - grouping multiple exceptions
try:
    with open(filename, 'r') as f:
        data = json.load(f)
        process_data(data)
except (FileNotFoundError, json.JSONDecodeError, KeyError) as err:
    # Can't handle each error appropriately
    logger.error("Error processing file")
    raise ValueError("Failed to process configuration")

# Bad - catching base Exception
try:
    process_data(data)
except Exception as err:
    # Too broad - might catch system errors
    logger.error("Something went wrong")
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

#### Production Lambda Configuration

All 16 production Lambda functions follow these standards:

- **Runtime**: Python 3.12
- **Memory**: 128MB (standardized across all functions)
- **Timeout**: 30 seconds
- **Handler Naming**: Must match Python module names (use underscores, not hyphens)
- **Fixed Logical IDs**: Each function has a permanent logical ID to prevent recreation

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
        body: dict = event.get("body", {})
        result = business_logic_function(player_id, body)
        return create_response(200, result)
    except ValueError as err:
        # Handle known business logic errors
        logger.error("Validation error")
        return error_response(str(err), 400)
    except Exception as err:
        # Catch ALL other exceptions to prevent Lambda errors
        logger.error("Unexpected error", exc_info=True)
        return error_response("Internal server error", 500)
```

### Separation of Concerns

Lambda functions must follow this pattern:

```python
def lambda_handler(event: dict, context: object) -> dict:
    """Lambda entry point - handles AWS-specific concerns only."""
    try:
        # 1. Log invocation
        logger.info("Lambda invocation")

        # 2. Handle CORS preflight
        if event.get("httpMethod") == "OPTIONS":
            return cors_handler.handle_preflight(event)

        # 3. Extract and validate authentication
        player_id = extract_player_id(event)

        # 4. Parse request
        body: dict = event.get("body", {})

        # 5. Call business logic
        result = business_logic_function(player_id, body.get("param"))

        # 6. Return formatted response
        if result["success"]:
            return create_response(200, result["data"])
        else:
            return error_response(result["error"], result["status_code"])
    except ValueError as err:
        logger.error("Request validation failed")
        return error_response(str(err), 400)
    except Exception as err:
        logger.error("Lambda handler error", exc_info=True)
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

## Pydantic Model Guidelines

### Pydantic v2 Configuration

When creating Pydantic models, use Pydantic v2 syntax and features:

```python
from pydantic import BaseModel, ConfigDict, Field

# Good - Pydantic v2 configuration
class MyModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,  # Accept multiple field name formats
        validate_assignment=True,
        extra="forbid",  # or "allow" for extensibility
    )

# Bad - Pydantic v1 style (deprecated)
class MyModel(BaseModel):
    class Config:
        validate_assignment = True
```

### Field Definitions with Proper Typing

Always use proper type hints with the pipe operator for optional fields:

```python
# Good - explicit optional typing
class Character(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    level: int = Field(1, ge=1, le=100)
    description: str | None = Field(default=None)
    attributes: dict[str, float] = Field(default_factory=dict)
    skills: list[str] = Field(default_factory=list)

# Bad - missing optional type annotation
class Character(BaseModel):
    description: str = Field(default=None)  # Will cause validation errors!
    attributes: dict = Field(default_factory=dict)  # Missing type parameters
```

### PascalCase Field Aliases

For API compatibility with DynamoDB, use PascalCase aliases:

```python
from pydantic.alias_generators import to_pascal

class BaseEidolonModel(BaseModel):
    """Base model with PascalCase serialization."""
    model_config = ConfigDict(
        alias_generator=to_pascal,  # Auto-generate PascalCase aliases
        populate_by_name=True,  # Accept both formats on input
    )

class Character(BaseEidolonModel):
    character_id: UUID = Field(..., alias="CharacterID")
    character_name: str = Field(..., alias="CharacterName")
```

### Avoid json_encoders (Deprecated in v2)

Use field serializers instead of the deprecated json_encoders:

```python
# Good - Pydantic v2 field serializer
from pydantic import field_serializer

class MyModel(BaseModel):
    @field_serializer("special_field")
    def serialize_special(self, value):
        return str(value)

# Bad - deprecated in v2
class MyModel(BaseModel):
    model_config = ConfigDict(
        json_encoders={UUID: str}  # Deprecated!
    )
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

Modules must be kept concise and focused according to production standards:

- **Ideal**: Under 300 lines (target for all new modules)
- **Maximum**: 1000 lines (absolute limit for complex modules)
- **Enforcement**: When a module exceeds 300 lines, immediately refactor into focused sub-modules
- **Production Status**: 94% compliance with 300-line target

This constraint has been validated through the deployment system rework, where a 1800+ line monolithic class was successfully refactored into modular components.

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

- [BAD] "This function validates AND saves the character"
- [BAD] "This class manages authentication AND user profiles"
- [BAD] "This module handles database operations AND business logic"

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

### Consistent Log Levels in Exception Blocks

Within a single exception block, use only one log level. Don't mix info/warning/error levels in the same except clause. This ensures consistent severity reporting and makes log analysis more effective:

```python
# Bad - mixing log levels in one exception block
try:
    character = get_character(character_id)
    apply_damage(character, damage)
except ValueError as err:
    logger.info("Starting error handling")  # Wrong - unnecessary info log
    logger.error("Failed to apply damage")
    return error_response(str(err), 400)

# Bad - info log followed by error in same block
try:
    result = process_combat(attacker, defender)
except RuntimeError as err:
    logger.info("Combat processing failed")
    logger.error("Combat error")  # Redundant
    raise

# Good - single appropriate log level per exception block
try:
    character = get_character(character_id)
    apply_damage(character, damage)
except ValueError as err:
    logger.warning("Invalid damage request", "character_id": character_id})
    return error_response(str(err), 400)
except RuntimeError as err:
    logger.error("Failed to apply damage", exc_info=True)
    return error_response("Internal server error", 500)

# Good - info logs outside exception handling
logger.info("Processing combat", "defender": defender_id})
try:
    result = process_combat(attacker, defender)
    logger.info("Combat completed")
except RuntimeError as err:
    logger.error("Combat processing failed", exc_info=True)
    raise
```

Choose the appropriate log level based on the exception's severity:

- `logger.warning`: For expected errors that are handled gracefully (e.g., validation failures)
- `logger.error`: For unexpected errors or system failures
- `logger.info`: For normal flow logging, placed outside exception blocks
- `logger.debug`: For detailed debugging information, also outside exception blocks

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

### No Shebang Lines

Python files should NOT include shebang lines (script headers). These are unnecessary for our deployment environment and add clutter:

```python
# Bad - don't include shebang lines
#!/usr/bin/env python3
#!/usr/bin/python

# Good - start directly with module docstring or imports
"""
Module docstring goes here.
"""
```

### Module Structure

Each module should have:

1. Docstring describing the module (no shebang line)
2. Imports (organized as specified above)
3. Constants
4. Classes (if any)
5. Functions
6. Maximum 50 lines per function (keep functions focused)

#### Import Organization Pattern

Group imports by category as validated in production:

```python
# Standard library imports
import json
import uuid
from datetime import datetime

# Third-party library imports
from botocore.exceptions import ClientError
from pydantic import BaseModel

# Local application imports
from eidolon.dynamo import dynamo
from eidolon.logger import logger
```

```python
"""
Character management utilities for Lambda functions.

Provides functions for character creation, validation, and management.
"""

import uuid
from datetime import datetime

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.logger logger

# Constants
MAX_NAME_LENGTH = 30
RESERVED_NAMES = ["admin", "system", "gm"]

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

## CDK-Specific Guidelines

### No AWS Access During Synthesis

CDK synthesis phase must not make AWS API calls. All resource checks should happen in deployment layer:

```python
# Bad - AWS calls during CDK synthesis fail
class MyStack(Stack):
    def __init__(self):
        if check_resource_exists():  # This always returns False during synthesis
            Resource.from_name(...)

# Good - Use fixed logical IDs and let CDK handle
class MyStack(Stack):
    def __init__(self):
        Resource(self, "FixedLogicalId", ...)
```

### Fixed Logical IDs

Always use fixed logical IDs for resources to prevent recreation on updates:

```python
# Production pattern from Lambda Stack
logical_id_map = {
    "api-character-list": "ApiCharacterListFunction",
    "cognito-player-new": "CognitoPlayerNewFunction",
    # ... etc
}
```

## Deployment Module Patterns

### Script vs Library Distinction

Deployment scripts are one-time run scripts, not libraries:

- No need for `__init__.py` imports
- No complex module structures
- Direct execution with `python3` command
- Focus on procedural flow

### Parameter Passing

Be explicit with parameter passing:

- Region flows through arguments, not environment variables
- Pass complete values to stacks (e.g., full FQDN for CORS)
- Avoid Python keywords in module names (e.g., use `lambda_functions.py` not `lambda.py`)

## Final Notes

- When in doubt, follow existing patterns in the codebase
- Prioritize readability over cleverness
- Keep functions small and focused (max 50 lines)
- Use meaningful variable names
- Ensure all code follows PEP 8 where not overridden by this guide
- These guidelines have been validated through production deployment of 9 CDK stacks
