# Lambda Functions

This directory contains AWS Lambda functions that power the Eidolon Engine's unified backend infrastructure.

## Overview

All Lambda functions in this directory serve both the MUD Portal and Incremental game interfaces. The same backend infrastructure supports all deployment modes (MUD, Incremental, or Hybrid), with different frontend applications consuming these shared APIs.

## Current Implementation Status

All Lambda functions are fully implemented and working:

- User login and account creation (via Cognito) ✓
- Account validation ✓
- Account deletion with complete data cleanup ✓
- Listing characters ✓
- Character creation with name validation ✓
- Character retrieval with active segments ✓
- Character deletion ✓
- Archetype listing ✓

The bloom filter for restricted character names is properly loaded and functional.

## Structure

### Cognito Triggers

- `cognito_new_player.py` - Post-confirmation trigger to create player records
- `cognito_delete_player.py` - Pre-deletion trigger to clean up player data

### Character Management API (Shared)

These functions handle character operations for both Portal and Incremental interfaces:

#### Implemented Functions:

- `api_list_characters.py` - List all characters for a player
- `api_add_character.py` - Create new character with bloom filter name validation
- `api_get_character.py` - Get character details including active story segments
- `api_delete_character.py` - Delete a character by ID
- `api_get_archetypes.py` - Get available character archetypes

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
from eidolon.cors import apply_cors
from eidolon.dynamo import DynamoOperations
from eidolon.logger import get_logger
from eidolon.requests import get_query_parameter, parse_json_body
from eidolon.responses import success_response, error_response
```

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

- `DEFAULT_HEALTH` - Default health points for new characters (default: 100)
- `DEFAULT_ESSENCE` - Default essence points for new characters (default: 100)
- `MAX_CHARACTERS_PER_PLAYER` - Maximum characters allowed per player (default: 10)

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
  - Use `parse_json_body()` from `eidolon.requests`

- **Path Parameters**: **NEVER** use for IDs - always use query parameters instead
  - ❌ Wrong: `/characters/123`
  - ✅ Correct: `/characters?characterId=123`

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
from lambda.api_list_characters import lambda_handler
from eidolon.cors import apply_cors

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

## Best Practices

1. **Error Handling**: Always catch and log exceptions appropriately
2. **Input Validation**: Validate all inputs from API Gateway
3. **CORS**: Use the shared `apply_cors` function for consistent CORS handling
4. **Logging**: Use the standard Python logger for CloudWatch integration
5. **Environment Variables**: Use environment variables for configuration
6. **IAM Permissions**: Follow least privilege principle
7. **Response Format**: Return consistent API Gateway response format:
   ```python
   return {
       "statusCode": 200,
       "headers": {"Content-Type": "application/json"},
       "body": json.dumps({"key": "value"})
   }
   ```
