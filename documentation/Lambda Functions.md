# Lambda Functions

This directory contains AWS Lambda functions that power the Eidolon Engine's unified backend infrastructure.

## Overview

All Lambda functions in this directory serve both the MUD Portal and Incremental game interfaces. The same backend infrastructure supports all deployment modes (MUD, Incremental, or Hybrid), with different frontend applications consuming these shared APIs.

## Current Implementation Status

The Incremental mode currently supports:

- User login and account creation (via Cognito)
- Account validation
- Account deletion (though the Lambda is inefficient)
- Listing characters
- Character creation UI (but backend Lambda has issues)

Known issues:

- Character creation Lambda expects an optional bloom filter file for restricted names (missing file is logged but doesn't break functionality)
- Character deletion Lambda implementation status unclear
- Account deletion Lambda works but needs optimization for efficiency

## Structure

### Cognito Triggers

- `cognito_new_player.py` - Post-confirmation trigger to create player records
- `cognito_delete_player.py` - Pre-deletion trigger to clean up player data

### Character Management API (Shared)

These functions handle character operations for both Portal and Incremental interfaces:

#### Working Functions:

- `api_list_characters.py` - List all characters for a player ✓

#### Functions with Issues:

- `api_add_character.py` - Create new character (works but expects optional bloom filter file for restricted names)
- `api_delete_character.py` - Delete a character (implementation status unclear)
- `cognito_delete_player.py` - Account deletion trigger (works but inefficient implementation)

#### Status Unknown:

- `api_get_character.py` - Get character details
- `api_get_archetypes.py` - Get available character archetypes

#### Not Yet Implemented:

- Character state saving functionality
- Story progression APIs
- Segment management APIs

### Future Additions

Additional Lambda functions will be added for Incremental-specific features:

- Story progression tracking
- Segment management
- Plot state handling
- Active segment timers

## Shared Modules

Lambda functions may import shared modules from the `eidolon/` directory:

```python
from eidolon.cors_handler import cors_handler
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

Future Incremental-specific tables:

- `STORY_TABLE` - Story metadata
- `ACTIVE_SEGMENTS_TABLE` - Active story segments
- `CHARACTER_HISTORY_TABLE` - Story completion tracking

### CORS Configuration

- `ALLOWED_ORIGINS` - Comma-separated list of allowed CORS origins

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
from eidolon.cors_handler import cors_handler

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
3. **CORS**: Use the shared `cors_handler` for consistent CORS handling
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
