# Lambda Functions

This directory contains AWS Lambda functions for the Eidolon Engine API.

## Structure

Lambda functions are organized by their purpose:

### Cognito Triggers

- `cognito_new_player.py` - Post-confirmation trigger to create player records
- `cognito_delete_player.py` - Pre-deletion trigger to clean up player data

### MUD API Functions

- `api_list_characters.py` - List all MUD characters for a player
- `api_delete_character.py` - Delete a MUD character
- `api_get_archetypes.py` - Get available character archetypes
- `api_save_character.py` - Save character state

### Incremental Game API Functions

- `api_list_incremental_characters.py` - List incremental game characters
- `api_get_character.py` - Get incremental character details
- `api_add_character.py` - Create new incremental character

## Shared Modules

Lambda functions may import shared modules from the `eidolon/` directory:

```python
from eidolon.cors_handler import cors_handler
```

These modules are automatically included in the deployment package during the build process.

## Environment Variables

Each Lambda function may use the following environment variables:

### Database Tables

- `players_table` - Shared players DynamoDB table
- `characters_table` - Game-specific characters table
- `items_table` - MUD items table
- `ARCHETYPES_TABLE` - Archetypes table
- `CHARACTERS_TABLE` - Incremental characters table
- `ACTIVE_SEGMENTS_TABLE` - Active game segments table

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
