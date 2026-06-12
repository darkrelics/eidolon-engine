# Lambda Functions

This directory contains AWS Lambda functions that power the Eidolon Engine's unified backend infrastructure.

## Overview

All Lambda functions in this directory serve both the MUD Portal and Incremental game interfaces. The same backend infrastructure supports all deployment modes (MUD, Incremental, or Hybrid), with different frontend applications consuming these shared APIs.

## Production Deployment

The Lambda functions are deployed as part of the architecture described in [Deployment Guide](deployment.md#system-architecture). Highlights include fixed logical IDs, a shared execution role (`eidolon-lambda-execution-role`), the managed `eidolon-dynamodb-policy`, and post-deployment updates sourced from S3 artifacts.

## Current Implementation Status

18 Lambda functions deployed (19 total, cognito-player-delete not deployed). All functions fully implemented and operational in production.

**Deployment Distribution:**

- Character Stack: 7 functions
- Story Stack: 9 functions
- Player Stack: 1 function

### Character Management (8 functions - Character Stack)

- `api-archetype-list` - List available archetypes
- `api-character-add` - Create new character with bloom filter validation
- `api-character-delete` - Delete character
- `api-character-get` - Get character details with inventory enrichment
- `api-character-list` - List player's characters
- `api-item-brief` - Get lightweight item metadata (ItemID + PrototypeID)
- `api-item-prototype` - Get complete item prototype definition
- `api-item-consume` - Consume inventory item and apply effects

### Story Operations (9 functions - Story Stack)

**API Functions (6 total):**

- `api-story-start` - Begin new story
- `api-story-abandon` - Exit active story
- `api-story-history` - Get story history by instance IDs
- `api-segment-decision` - Submit player choice
- `api-segment-status` - Check segment readiness
- `api-segment-history` - Retrieve past segments

**Operational Functions (3 total):**

- `ops-segment-poller` - EventBridge-triggered polling (1 minute)
- `ops-segment-process` - SQS mechanical processing
- `ops-story-advance` - SQS story advancement

### Cognito Trigger (1 function - Player Stack)

- `cognito-player-new` - PostConfirmation trigger

### Not Deployed (1 function)

- `cognito-player-delete` - Code exists, not deployed (awaiting API implementation)

The bloom filter for restricted character names is properly loaded and functional.

## Structure

### Function Organization by Stack

#### Function Deployment

Functions are deployed via Character, Player, and Story stacks (not Lambda Stack).

**Lambda Stack provides:**

- Shared execution role
- Shared layer (eidolon dependencies)
- No functions deployed directly in Lambda Stack

**All functions use:**

- **Runtime**: Python 3.12
- **Memory**: 128MB
- **Timeout**: 30 seconds
- **Layer**: Shared `eidolon-dependencies` layer
- **Role**: Shared `eidolon-lambda-execution-role`

#### Fixed Logical IDs

Each function has a fixed logical ID to prevent recreation:

```python
# Logical IDs as defined in cf/eidolon-lambda-character.yml,
# cf/eidolon-lambda-cognito.yml, and cf/eidolon-lambda-story.yml
logical_id_map = {
    # Character Stack (8 functions)
    "api-archetype-list": "ApiArchetypeListFunction",
    "api-character-add": "ApiCharacterAddFunction",
    "api-character-delete": "ApiCharacterDeleteFunction",
    "api-character-get": "ApiCharacterGetFunction",
    "api-character-list": "ApiCharacterListFunction",
    "api-item-brief": "ApiItemBriefFunction",
    "api-item-prototype": "ApiItemPrototypeFunction",
    "api-item-consume": "ApiItemConsumeFunction",
    # Player Stack (1 function)
    "cognito-player-new": "CognitoPlayerNewFunction",
    # Story Stack (9 functions)
    "api-story-start": "ApiStoryStartFunction",
    "api-story-abandon": "ApiStoryAbandonFunction",
    "api-story-history": "ApiStoryHistoryFunction",
    "api-segment-decision": "ApiSegmentDecisionFunction",
    "api-segment-history": "ApiSegmentHistoryFunction",
    "api-segment-status": "ApiSegmentStatusFunction",
    "ops-segment-poller": "OpsSegmentPollerFunction",
    "ops-segment-process": "OpsSegmentProcessFunction",
    "ops-story-advance": "OpsStoryAdvanceFunction"
}
# Total: 18 deployed
```

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

All Lambda functions receive standardized environment variables from the Lambda Stack:

### Common Variables (All Functions)

```python
# From lambda_stack.py
"APPLICATION_NAME": "eidolon-engine"
"LOG_LEVEL": "INFO"  # Validated by eidolon/environment.py
"ALLOWED_ORIGINS": f"https://{client_host}.{domain}"
"CORS_ALLOW_CREDENTIALS": "true"
"CORS_ALLOW_HEADERS": "Content-Type,X-Amz-Date,Authorization,..."
"CORS_ALLOW_METHODS": "GET,POST,PUT,DELETE,OPTIONS"
"CORS_MAX_AGE": "86400"
```

### Database Tables (From DynamoDB Stack Outputs)

Environment variable names follow the table identifiers in [Database Schema](schema.md); each Lambda reads the lowercase `_table` variables emitted by the stack outputs.

### Function-Specific Variables

**Story Processing Functions**:

- `SEGMENT_QUEUE_URL` - SQS queue for mechanical segments
- `STORY_ADVANCEMENT_QUEUE_URL` - SQS queue for advancement
- `SSM_POLLER_STATE_PARAMETER` - SSM parameter for polling
- `SEGMENT_BATCH_SIZE` - Processing batch size (default: 10)

**Character Configuration**:

- `MAX_CHARACTERS_PER_PLAYER` - Maximum characters per player (default: 1)

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

Lambda functions are deployed through the modular CDK stack system:

### CDK Stack Deployment (Lambda Stack #3)

1. **CodeBuild Process** (Stack #1):
   - Builds Lambda layer from `requirements/lambda-requirements.txt`
   - Packages each function with `eidolon` modules
   - Uploads artifacts to S3 bucket

2. **Lambda Stack Deployment** (Stack #3):
   - Creates shared execution role
   - Deploys Lambda layer
   - No functions deployed in Lambda Stack itself

3. **Character, Player, Story Stacks** (Stacks #4, #5, #6):
   - Deploy 17 functions total with fixed logical IDs
   - Import shared role and layer from Lambda Stack
   - Set environment variables from stack outputs
   - Use shared DynamoDB managed policy

4. **Post-Deployment Updates** (Phase 11):

   ```python
   # Automatic update from S3 artifacts
   lambda_client.update_function_code(
       FunctionName=function_name,
       S3Bucket=bucket_name,
       S3Key=f"{function_name}.zip"
   )
   ```

5. **Layer Version Management**:
   - Reuses most recent published layer version
   - All functions updated to use latest layer
   - Old layer versions must be deleted manually (not automated)

### Integration with Other Stacks

- **Lambda Stack** (#3): Provides shared role and layer
- **Player Stack** (#4): Deploys cognito-player-new, configures Cognito trigger
- **Character Stack** (#5): Deploys 7 character/item API functions
- **Story Stack** (#6): Deploys 9 story/segment functions, adds SQS/EventBridge permissions
- **API Stack** (#9): Creates API Gateway integrations for all functions

### Deployment Modes

- **MUD Mode**: All 17 functions deployed (Story Stack excluded for MUD, but all functions still deployed)
- **Incremental Mode**: All 17 functions deployed with Story Stack
- **Hybrid Mode**: All 17 functions deployed with all stacks

**Note:** All deployment modes deploy the same Lambda functions. Mode selection affects which infrastructure stacks are deployed (SQS queues, EventBridge, S3 scripts), not which Lambda functions.

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

**Three-Layer Architecture**: Every Lambda function follows a strict three-layer pattern for separation of concerns, testability, and maintainability.

### Layer Responsibilities

1. **Lambda Handler Layer**: AWS-specific concerns (authentication, CORS, HTTP responses)
2. **Business Logic Layer**: Pure Python business logic (orchestration, validation, flow control)
3. **Eidolon Library Layer**: Database operations, AWS services, shared utilities

### Required Structure

```python
def lambda_handler(event: dict, context: object) -> dict:
    """
    Layer 1: Lambda Handler - AWS-specific concerns only.

    CRITICAL: This function must NEVER raise exceptions.
    All exceptions must be caught and converted to HTTP responses.
    """
    # 1. Log invocation
    log_lambda_statistics(context, event)

    # 2. Handle CORS preflight
    preflight_response = cors_handler.handle_preflight(event)
    if preflight_response:
        return preflight_response

    # 3. Extract and validate authentication
    try:
        player_id = extract_player_id(event)
    except ValueError as err:
        logger.warning(f"Authentication failed: {err}")
        return lambda_response(401, {"Error": "Unauthorized"}, event)
    except Exception as err:
        return lambda_error(event, err)

    # 4. Parse request parameters (query/body based on endpoint type)
    try:
        # Parse parameters appropriate to endpoint
        character_id = get_query_parameter(event, "CharacterID")  # GET/DELETE
        # OR
        body = parse_event_body(event)                           # POST
        character_id = body.get("CharacterID")

        if not character_id:
            return lambda_response(400, {"Error": "Missing CharacterID"}, event)

    except ValueError as err:
        return lambda_response(400, {"Error": str(err)}, event)
    except Exception as err:
        return lambda_error(event, err)

    # 5. Call business logic function
    try:
        result = business_logic_function(character_id, player_id)
        return lambda_response(200, result, event)
    except Exception as err:
        return lambda_error(event, err)

def business_logic_function(character_id: str, player_id: str) -> dict:
    """
    Layer 2: Business Logic - Pure Python, no AWS dependencies.

    This function orchestrates the business process by calling eidolon library
    functions. It handles business rule validation and flow control.

    Raises:
        ValueError: For 4xx client errors (validation, not found, forbidden)
        RuntimeError: For 5xx server errors (database failures, system issues)
    """
    # 1. Call eidolon library functions for data operations
    try:
        character = character_get(character_id, player_id)  # May raise ValueError/RuntimeError
    except ValueError:
        # Library handles not found, ownership validation - re-raise for handler
        raise
    except RuntimeError:
        # Library handles database errors - re-raise for handler
        raise

    # 2. Business logic validation and orchestration
    if character.get("GameMode") != "None":
        raise ValueError("Character is currently busy in another game mode")

    # 3. Execute business operations via eidolon library
    try:
        result = perform_character_operation(character)  # May raise ValueError/RuntimeError
        return {"Success": True, "Data": result}
    except ValueError:
        # Business rule violations - re-raise for proper HTTP status
        raise
    except RuntimeError:
        # System failures - re-raise for proper HTTP status
        raise

# Layer 3: Eidolon Library Functions (in /eidolon directory)
def character_get(character_id: str, player_id: str) -> dict:
    """
    Layer 3: Eidolon Library - Database operations and AWS services.

    Library functions either:
    1. Handle errors locally where appropriate (retries, fallbacks)
    2. Raise appropriate exceptions for business logic layer

    Raises:
        ValueError: Client errors - invalid IDs, not found, access denied
        RuntimeError: Server errors - database failures, AWS service issues
    """
    # Handle database operations, retries, error classification
    # Raise ValueError for 4xx conditions, RuntimeError for 5xx conditions
```

### Error Handling Flow

**Exception Propagation Pattern:**

1. **Eidolon Library**: Handles retries/fallbacks locally OR raises ValueError (4xx) / RuntimeError (5xx)
2. **Business Logic**: Re-raises library exceptions OR adds business validation exceptions
3. **Lambda Handler**: Catches ALL exceptions, converts to appropriate HTTP responses

**HTTP Status Code Mapping:**

- `ValueError` → 400/403/404/409 (client errors)
- `RuntimeError` → 500 (server errors)
- `Any other Exception` → 500 (unexpected errors)

**Detailed Status Code Usage:**

- **400 Bad Request**: Invalid parameters, malformed JSON, validation failures
- **401 Unauthorized**: Missing/invalid JWT token, authentication failures
- **403 Forbidden**: Valid auth but access denied (character not owned, story not available)
- **404 Not Found**: Resource doesn't exist (character, story, segment not found)
- **409 Conflict**: Resource state conflict (character busy, decision already made)
- **500 Internal Server Error**: Database failures, AWS service issues, unexpected errors

### GameMode Fail-Safe Pattern

**All Incremental Lambda functions MUST validate GameMode consistency:**

```python
def validate_incremental_gamemode(character: dict, character_id: str) -> None:
    """
    Validate and auto-correct GameMode for Incremental operations.

    GameMode States (Atomic):
    - Incremental: Has ActiveStoryID and ActiveSegmentID
    - MUD: Character logged into MUD session
    - None: Default fail-safe state

    Auto-correction: Set to None if inconsistent state detected.
    """
    game_mode = character.get("GameMode", "None")
    active_story_id = character.get("ActiveStoryID")
    active_segment_id = character.get("ActiveSegmentID")

    # Check for inconsistent state
    if game_mode == "Incremental" and (not active_story_id or not active_segment_id):
        logger.warning(f"GameMode=Incremental but missing story/segment IDs for {character_id}, correcting to None")

        # Auto-correct to fail-safe state
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET GameMode = :none REMOVE ActiveStoryID, ActiveSegmentID",
            ExpressionAttributeValues={":none": "None"}
        )
        raise ValueError("Character was in invalid GameMode, corrected to None")

    elif game_mode == "None" and active_story_id and active_segment_id:
        logger.warning(f"GameMode=None but has active story/segment for {character_id}, correcting to Incremental")

        # Auto-correct to proper state
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET GameMode = :incremental",
            ExpressionAttributeValues={":incremental": "Incremental"}
        )
        # Continue processing - state is now correct

    elif game_mode not in ["MUD", "Incremental", "None"]:
        logger.error(f"Invalid GameMode '{game_mode}' for {character_id}, correcting to None")

        # Auto-correct invalid states to fail-safe
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET GameMode = :none REMOVE ActiveStoryID, ActiveSegmentID",
            ExpressionAttributeValues={":none": "None"}
        )
        raise ValueError("Character was in invalid GameMode, corrected to None")

# Usage in all Incremental Lambda functions:
def business_logic_function(character_id: str, player_id: str) -> dict:
    character = character_get(character_id, player_id)

    # REQUIRED: Validate and auto-correct GameMode
    validate_incremental_gamemode(character, character_id)

    # Continue with business logic...
```

**Benefits:**

- **Data Integrity**: Prevents corruption by auto-correcting invalid states
- **Fail-Safe Design**: Always defaults to "None" when state is ambiguous
- **Atomic Operations**: Each correction is a single database update
- **Self-Healing**: System automatically recovers from inconsistent states
- **Audit Trail**: All corrections are logged for monitoring

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

### Critical Rule: Lambda Handler Exception Boundary

The `lambda_handler` function is the interface between AWS Lambda and your code. It must **ALWAYS** return a valid HTTP response and **NEVER** allow exceptions to escape.

**Why This Is Critical:**

- **API Gateway**: Unhandled exceptions cause generic 500 errors with no useful information
- **Debugging**: Without proper error handling, production debugging becomes nearly impossible
- **Monitoring**: CloudWatch alarms and metrics depend on proper error logging
- **User Experience**: Clients need consistent, parseable error responses

**Implementation Pattern:**

```python
def lambda_handler(event: dict, context: object) -> dict:
    """
    AWS Lambda entry point - Layer 1: Infrastructure concerns only.

    CRITICAL RULE: This function must NEVER raise exceptions.
    All exceptions must be caught and converted to HTTP responses.
    """
    try:
        # All Lambda logic goes inside this try block
        log_lambda_statistics(event, context)

        # Handle authentication, parsing, business logic call
        result = business_logic_function(params)
        return lambda_response(200, result, event)

    except Exception as err:
        # CRITICAL: Catch ALL exceptions to prevent Lambda failures
        return lambda_error(event, err)  # Handles logging and consistent error format
```

**Testing the Business Logic Layer:**

```python
# Unit test example - no AWS dependencies needed
def test_business_logic():
    # Mock eidolon library functions
    with patch('eidolon.character_data.character_get') as mock_get:
        mock_get.return_value = {"CharacterID": "test", "GameMode": "None"}

        result = business_logic_function("test-char", "test-player")
        assert result["Success"] is True
```

## Data Transformations

Some Lambda functions apply transformations to data before returning responses:

### Character Data Transformations

The `api_get_character.py` function applies several transformations for client compatibility:

1. **Inventory Enrichment**: Raw inventory UUIDs are enriched with item details
   - Database: `{"RightHand": "sword-uuid"}`
   - Response adds: `{"InventoryDetails": {"RightHand": {"ItemID": "sword-uuid", "Name": "Iron Sword", ...}}}`

2. **Decimal to Float Conversion**: DynamoDB Decimal types are converted to standard floats
   - Applied to all numeric fields in the response

### JSON Field Naming Convention

All JSON responses use PascalCase for field names to maintain consistency with DynamoDB field names. Flexible casing is not supported.

- Database field: `CharacterName`
- API response: `CharacterName` (not transformed)
- This applies to all fields: `CharacterID`, `AvailableStories`, `Attributes`, etc.

These transformations ensure Flutter clients receive data in a consistent, usable format while maintaining the original database structure.
