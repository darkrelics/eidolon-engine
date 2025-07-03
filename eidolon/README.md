# Eidolon Shared Python Modules

This directory contains shared Python modules used across multiple Lambda functions in the Eidolon Engine project.

## Structure

```
eidolon/
├── __init__.py          # Package initialization
├── cors_handler.py      # CORS handling for Lambda functions
└── README.md           # This file
```

## Modules

### cors_handler.py

Provides centralized CORS (Cross-Origin Resource Sharing) configuration and validation for API responses.

**Usage:**
```python
from eidolon.cors_handler import cors_handler

def lambda_handler(event, context):
    # Handle preflight requests
    if event.get('httpMethod') == 'OPTIONS':
        return cors_handler.handle_preflight(event)
    
    # Your lambda logic here...
    
    # Add CORS headers to response
    return cors_handler.add_cors_headers(response, event)
```

**Features:**
- Validates request origins against allowed list
- Handles preflight OPTIONS requests
- Configurable via environment variables
- Supports credentials when origins are validated

## Lambda Packaging

The shared modules are automatically included in Lambda deployment packages by the build process:

1. The `buildspec/lambda-functions.yml` file packages each Lambda function
2. If a Lambda function imports from `eidolon`, the entire module is included
3. The module is placed at the root of the Lambda package for proper imports

## Adding New Shared Modules

To add a new shared module:

1. Create the module file in the `eidolon/` directory
2. Import it in your Lambda functions: `from eidolon.module_name import ...`
3. The build process will automatically include it in the deployment package

## Environment Variables

Modules may use the following environment variables:

- `ALLOWED_ORIGINS`: Comma-separated list of allowed CORS origins
- `CORS_ALLOW_CREDENTIALS`: Whether to allow credentials (default: true)
- `CORS_ALLOWED_HEADERS`: Comma-separated list of allowed headers
- `CORS_ALLOWED_METHODS`: Comma-separated list of allowed HTTP methods
- `CORS_MAX_AGE`: Max age for preflight cache in seconds

## Testing

When testing Lambda functions locally that use shared modules:

```python
import sys
import os

# Add parent directory to path for local testing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eidolon.cors_handler import cors_handler
```

## Best Practices

1. Keep shared modules focused and single-purpose
2. Document all public functions and classes
3. Include type hints for better IDE support
4. Write unit tests for shared functionality
5. Avoid circular dependencies between modules