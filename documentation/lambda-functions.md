# Lambda Functions

This directory contains AWS Lambda functions that power the Eidolon Engine's unified backend infrastructure.

## Overview

All Lambda functions in this directory serve both the MUD Portal and Incremental game interfaces. The same backend infrastructure supports all deployment modes (MUD, Incremental, or Hybrid), with different frontend applications consuming these shared APIs.

## Production Deployment

The Lambda functions are deployed as part of the 9-stack CDK architecture:

- **16 Lambda Functions**: All operational with fixed logical IDs
- **Shared Execution Role**: `eidolon-lambda-execution-role`
- **Managed IAM Policy**: `eidolon-dynamodb-policy` with DescribeTable permission
- **Lambda Layer**: Shared `eidolon` library updated post-deployment
- **Fixed Logical IDs**: Preventing resource recreation on stack updates
- **Post-Deployment Updates**: Functions updated from S3 artifacts

## Current Implementation Status

All 16 Lambda functions are fully implemented and operational in production:

### Character Management (5 functions)

- `api-archetype-list` - List available archetypes
- `api-character-add` - Create new character with bloom filter validation
- `api-character-delete` - Delete character
- `api-character-get` - Get character details with inventory enrichment
- `api-character-list` - List player's characters

### Story Operations (7 functions)

- `api-story-start` - Begin new story
- `api-story-abandon` - Exit active story
- `api-segment-decision` - Submit player choice
- `api-segment-rest` - Initiate healing segment
- `api-segment-status` - Check segment readiness
- `api-segment-outcome` - Get segment results
- `api-segment-history` - Retrieve past segments

### Processing Functions (3 functions)

- `ops-segment-poller` - EventBridge-triggered polling
- `ops-segment-process` - SQS mechanical processing
- `ops-story-advance` - SQS story advancement

### Cognito Trigger (1 function)

- `cognito-player-new` - PostConfirmation trigger

The bloom filter for restricted character names is properly loaded and functional.

## Structure

### Function Organization by Stack

#### Lambda Stack Functions (All 16)

All functions are deployed via the Lambda Stack with:

- **Runtime**: Python 3.12
- **Memory**: 128MB
- **Timeout**: 30 seconds
- **Layer**: Shared `eidolon` library

#### Fixed Logical IDs

Each function has a fixed logical ID to prevent recreation:

```python
# From lambda_stack.py
logical_id_map = {
    "api-archetype-list": "ApiArchetypeListFunction",
    "api-character-add": "ApiCharacterAddFunction",
    "api-character-delete": "ApiCharacterDeleteFunction",
    "api-character-get": "ApiCharacterGetFunction",
    "api-character-list": "ApiCharacterListFunction",
    "api-segment-decision": "ApiSegmentDecisionFunction",
    "api-segment-history": "ApiSegmentHistoryFunction",
    "api-segment-outcome": "ApiSegmentOutcomeFunction",
    "api-segment-rest": "ApiSegmentRestFunction",
    "api-segment-status": "ApiSegmentStatusFunction",
    "api-story-abandon": "ApiStoryAbandonFunction",
    "api-story-start": "ApiStoryStartFunction",
    "cognito-player-new": "CognitoPlayerNewFunction",
    "ops-segment-poller": "OpsSegmentPollerFunction",
    "ops-segment-process": "OpsSegmentProcessFunction",
    "ops-story-advance": "OpsStoryAdvanceFunction"
}
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

All 14 tables with lowercase environment variable names:

- `players_table` - Players table
- `characters_table` - Characters table with GameMode field
- `archetypes_table` - Character archetypes
- `items_table` - Items table
- `rooms_table` - Rooms table
- `exits_table` - Room exits
- `prototypes_table` - Item prototypes
- `motd_table` - Messages of the day
- `story_table` - Story metadata
- `segments_table` - Story segment definitions
- `active_segments_table` - Active segment instances
- `story_history_table` - Story completion tracking
- `segment_history_table` - Segment completion history
- `opponents_table` - Combat opponent definitions

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
   - Creates 16 functions with fixed logical IDs
   - Sets environment variables from stack outputs
   - Attaches DynamoDB managed policy

3. **Post-Deployment Updates**:

   ```python
   # Automatic update from S3 artifacts
   lambda_client.update_function_code(
       FunctionName=function_name,
       S3Bucket=bucket_name,
       S3Key=f"{function_name}.zip"
   )
   ```

4. **Layer Version Management**:
   - New layer version published if changed
   - All functions updated to use new layer
   - Old layer versions automatically deleted

### Integration with Other Stacks

- **Player Stack** (#4): Configures Cognito trigger
- **Story Stack** (#5): Adds SQS/EventBridge permissions
- **API Stack** (#8): Creates API Gateway integrations

### Deployment Modes

- **MUD Mode**: All 16 functions deployed (Story Stack excluded)
- **Incremental Mode**: All 16 functions deployed with Story Stack
- **Hybrid Mode**: All 16 functions deployed with all stacks

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

        return lambda_response(200, {"Success": True}, event)

    except ValueError as err:
        # Handle expected business logic errors
        logger.error("Validation error")
        return lambda_response(400, {"Error": str(err)}, event)

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
   - Response adds: `{"InventoryDetails": {"RightHand": {"ItemID": "sword-uuid", "Name": "Iron Sword", ...}}}`

2. **Decimal to Float Conversion**: DynamoDB Decimal types are converted to standard floats
   - Applied to all numeric fields in the response

### JSON Field Naming Convention

All JSON responses use PascalCase for field names to maintain consistency with DynamoDB field names. Flexible casing is not supported.

- Database field: `CharacterName`
- API response: `CharacterName` (not transformed)
- This applies to all fields: `CharacterID`, `AvailableStories`, `Attributes`, etc.

These transformations ensure Flutter clients receive data in a consistent, usable format while maintaining the original database structure.
