# Lambda Functions

This directory contains AWS Lambda functions that power the Eidolon Engine's unified backend infrastructure.

## Overview

All Lambda functions in this directory serve both the MUD Portal and Incremental game interfaces. The same backend infrastructure supports all deployment modes (MUD, Incremental, or Hybrid), with different frontend applications consuming these shared APIs.

## Current Implementation Status

All Lambda functions are fully implemented and working:

- User login and account creation (via Cognito)
- Account validation
- Account deletion with complete data cleanup
- Listing characters
- Character creation with name validation
- Character retrieval with active segments
- Character deletion
- Archetype listing

The bloom filter for restricted character names is properly loaded and functional.

## Structure

### Cognito Triggers

- `cognito_new_player.py` - Post-confirmation trigger to create player records
- `cognito_delete_player.py` - Pre-deletion trigger to clean up player data

### Character Management API (Shared)

These functions handle character operations for both Portal and Incremental interfaces:

#### Implemented Functions:

- `api_character_list.py` - List all characters for a player
- `api_character_add.py` - Create new character with bloom filter name validation
- `api_get_character.py` - Get character details including active story segments (enriches inventory with item details)
- `api_character_delete.py` - Delete a character by ID
- `api_archetypes_get.py` - Get available character archetypes

#### Not Yet Implemented:

- Character state saving/updating functionality
- Story progression APIs
- Segment management APIs (start, update, complete segments)

### Future Additions

Additional Lambda functions will be added for Incremental-specific features:

- Story progression tracking
- Segment management
- Plot state handling
- Active segment timers

## Shared Modules

Lambda functions import shared modules from the `eidolon/` directory:

```python
from eidolon.cors import cors_handler
from eidolon.dynamo import dynamo
from eidolon.logger logger
from eidolon.requests import get_query_parameter, get_required_field
from eidolon.responses import create_response, error_response
from eidolon.utilities import lambda_response, log_lambda_invocation, handle_preflight, lambda_error
from eidolon.player import extract_player_id, validate_player
from eidolon.validation import validate_uuid
```

### Key Modules:

- **eidolon.utilities**: Provides high-level convenience functions that wrap common patterns
- **eidolon.cors**: Provides the `cors_handler` object for CORS management
- **eidolon.responses**: Low-level response building functions
- **eidolon.player**: Player authentication and validation functions
- **eidolon.dynamo**: Database operations wrapper

These modules are automatically included in the deployment package during the build process.

## Environment Variables

Each Lambda function may use the following environment variables:

### Database Tables

All tables are shared between MUD and Incremental game modes:

- `PLAYERS_TABLE` - Players table (unified authentication)
- `CHARACTERS_TABLE` - Characters table (with GameMode field preventing concurrent use)
- `ARCHETYPES_TABLE` - Character archetypes
- `ITEMS_TABLE` - Items table
- `ROOMS_TABLE` - Rooms table
- `EXITS_TABLE` - Room exits
- `PROTOTYPES_TABLE` - Item prototypes
- `MOTD_TABLE` - Messages of the day

Tables being added for Incremental features:

- `STORY_TABLE` - Story metadata (table name: story)
- `ACTIVE_SEGMENTS_TABLE` - Active story segments (table not yet created in DynamoDB stack)
- `CHARACTER_HISTORY_TABLE` - Story completion tracking (table not yet created in DynamoDB stack)

Note: The `ACTIVE_SEGMENTS_TABLE` and `CHARACTER_HISTORY_TABLE` are referenced in existing Lambda functions but the corresponding tables need to be added to the DynamoDB stack configuration.

### Character Configuration

- `DEFAULT_HEALTH` - Default health points for new characters (default: 10)
- `DEFAULT_ESSENCE` - Default essence points for new characters (default: 3)
- `MAX_CHARACTERS_PER_PLAYER` - Maximum characters allowed per player (default: 1)

### CORS Configuration

- `ALLOWED_ORIGINS` - Comma-separated list of allowed CORS origins

## API Design Standards

### Parameter Passing

All Lambda functions must follow these parameter standards:

- **Query Parameters**: Use for resource-specific operations (GET, DELETE)
  - Example: `/characters?characterId=123`
  - Use `get_query_parameter()` from `eidolon.requests`
- **Request Body**: Use for data submission (POST, PUT, PATCH)
  - Example: `POST /characters` with JSON body `{"characterName": "Hero", "archetype": "Warrior"}`

- **Path Parameters**: **NEVER** use for IDs - always use query parameters instead
  - Wrong: `/characters/123`
  - Correct: `/characters?characterId=123`

### Consistency Requirements

- All Lambda functions that accept character IDs must use query parameters
- Frontend implementations must match backend parameter expectations
- Always use the standard utility functions from `eidolon.requests`

## Deployment

Lambda functions are packaged and deployed through AWS CodeBuild:

1. **Build Process** (`buildspec/lambda-functions.yml`):
   - Each function is packaged as a separate zip file
   - Shared `eidolon` modules are included if imported
   - Zip files are uploaded to S3

2. **Dependencies** (`buildspec/lambda-layer.yml`):
   - Common dependencies are packaged as a Lambda layer
   - Requirements from `requirements/lambda-requirements.txt`

3. **CDK Deployment**:
   - Functions are deployed via CDK stacks
   - Environment variables are set by CDK
   - IAM roles are managed by CDK

## Local Testing

To test Lambda functions locally:

```python
# Add to the top of your test script
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Now you can import Lambda functions and shared modules
from lambda.api_character_list import lambda_handler
from eidolon.utilities import lambda_response

# Create test event
event = {
    "httpMethod": "GET",
    "headers": {"origin": "https://darkrelics.net"},
    "requestContext": {
        "authorizer": {
            "claims": {"sub": "test-user-id"}
        }
    }
}

# Call handler
response = lambda_handler(event, {})
```

## Adding New Lambda Functions

1. Create the function file in this directory
2. Import any needed shared modules from `eidolon/`
3. Add the function to the appropriate CDK stack
4. The build process will automatically package it

## Lambda Function Architecture Pattern

Each Lambda function must have a Lambda handler which handles the event, calls a function with the business logic, then handles the response. The business logic function will call functions from the `./eidolon` library to perform their tasks. None of the database or I/O code should be present in the Lambda function beyond the event feed to the handler and the response back to the API.

### Required Structure

```python
def lambda_handler(event: dict, context: object) -> dict:
    """Lambda entry point - handles AWS-specific concerns."""
    # 1. Log invocation
    log_lambda_statistics(context, event)

    # 2. Handle CORS preflight
    if preflight_response:
        return preflight_response

    # 3. Extract and validate authentication
    try:
        player_id = extract_player_id(event)
    except ValueError as err:
        logger.error("Authentication failed")
        return lambda_response(401, {"error": "Unauthorized"}, event)
    except Exception as err:
        return lambda_error(event, err)

    # 4. Validate player exists
    try:
        if not validate_player(player_id):
            logger.error("Player not found in database")
            return lambda_response(401, {"error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error("Failed to validate player")
        return lambda_response(500, {"error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)

    # 5. Parse request parameters
    # 6. Call business logic function
    # 7. Return response
    try:
        result = business_logic_function(param1, param2)
        return lambda_response(200, result, event)
    except ValueError as err:
        logger.warning("Business logic error")
        return lambda_response(400, {"error": str(err)}, event)
    except RuntimeError as err:
        logger.error("Database error")
        return lambda_response(500, {"error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)

def business_logic_function(param1: str, param2: str) -> dict:
    """Pure business logic - testable and AWS-agnostic."""
    # 1. Validate business rules
    # 2. Call eidolon library functions for DB operations
    # 3. Orchestrate multiple operations as needed
    # 4. Return success/error dictionary with data
```

### Benefits of This Pattern

- **Separation of Concerns**: AWS-specific code stays in the handler, business logic remains pure
- **Testability**: Business logic can be unit tested without mocking AWS services
- **Consistency**: All database operations go through the eidolon library
- **Maintainability**: Clear boundaries between infrastructure and business code
- **Reusability**: Business logic functions can be called from different contexts

## Best Practices

1. **Error Handling**: Always catch and log exceptions appropriately
2. **Lambda Handler Exception Rule**: The `lambda_handler` function must **NEVER** raise exceptions - all errors must be caught and converted to HTTP responses
3. **Input Validation**: Validate all inputs from API Gateway
4. **CORS**: Use the `cors_handler` object from `eidolon.cors` for consistent CORS handling
5. **Logging**: Use the `log_lambda_invocation` utility for consistent logging
6. **Environment Variables**: Use environment variables for configuration
7. **IAM Permissions**: Follow least privilege principle
8. **Response Format**: Use `lambda_response` for consistent responses:

   ```python
   # Preferred pattern using utilities
   return lambda_response(200, {"key": "value"}, event)

   # This handles CORS headers and response formatting automatically
   ```

9. **Architecture Pattern**: Follow the handler/business logic separation pattern described above
10. **Utility Functions**: Prefer high-level utility functions from `eidolon.utilities`:
    - `log_lambda_statistics()` - For logging invocations
    - `lambda_response()` - For building responses with CORS
    - `lambda_error()` - For consistent error handling

### Critical: Lambda Handler Exception Handling

The `lambda_handler` function is the interface between AWS Lambda and your code. It must **ALWAYS** return a valid HTTP response and **NEVER** allow exceptions to escape. Here's why this is critical:

```python
def lambda_handler(event: dict, context: object) -> dict:
    """
    AWS Lambda entry point.

    CRITICAL: This function must NEVER raise exceptions. All exceptions must be
    caught and converted to appropriate HTTP responses.
    """
    try:
        # All Lambda logic goes inside this try block
        logger.info("Lambda invoked")

        # Your code here...

        return lambda_response(200, {"success": True}, event)

    except ValueError as err:
        # Handle expected business logic errors
        logger.error("Validation error")
        return lambda_response(400, {"error": str(err)}, event)

    except Exception as err:
        # CRITICAL: Catch ALL exceptions to prevent Lambda failures
        # Use lambda_error for consistent error handling
        return lambda_error(event, err)
```

**Why This Matters:**

- **API Gateway**: Unhandled exceptions cause API Gateway to return generic 500 errors with no useful information
- **Debugging**: Without proper error handling, debugging production issues becomes nearly impossible
- **Monitoring**: CloudWatch alarms and metrics depend on proper error logging
- **User Experience**: Clients need consistent, parseable error responses

## Data Transformations

Some Lambda functions apply transformations to data before returning responses:

### Character Data Transformations

The `api_get_character.py` function applies several transformations for client compatibility:

1. **Inventory Enrichment**: Raw inventory UUIDs are enriched with item details
   - Database: `{"RightHand": "sword-uuid"}`
   - Response adds: `{"InventoryDetails": {"RightHand": {"itemId": "sword-uuid", "name": "Iron Sword", ...}}}`

2. **Decimal to Float Conversion**: DynamoDB Decimal types are converted to standard floats
   - Applied to all numeric fields in the response

### JSON Field Naming Convention

All JSON responses use PascalCase for field names to maintain consistency with DynamoDB field names. Flexible casing is not supported.

- Database field: `CharacterName`
- API response: `CharacterName` (not transformed)
- This applies to all fields: `CharacterID`, `AvailableStories`, `Attributes`, etc.

These transformations ensure Flutter clients receive data in a consistent, usable format while maintaining the original database structure.
