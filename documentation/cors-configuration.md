# CORS Configuration Guide for Eidolon Engine

This guide explains how Cross-Origin Resource Sharing (CORS) is configured for the Eidolon Engine's API Gateway and Lambda functions.

## Overview

CORS configuration is handled at two levels in the deployment system:

1. **API Gateway**: Handles preflight OPTIONS requests with wildcard origins
2. **Lambda Functions**: Validate actual request origins via environment variables

## How CORS Currently Works

### 1. API Gateway Configuration

The API Gateway is configured with permissive CORS settings to handle preflight requests:

```python
# In api_stack.py
default_cors_preflight_options=apigateway.CorsOptions(
    allow_origins=["*"],  # Wildcard for preflight
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Amz-Date", "X-Api-Key", "X-Amz-Security-Token"],
    allow_credentials=True,
)
```

**Important**: The wildcard origin (`*`) is only for preflight OPTIONS requests. Actual origin validation happens in Lambda functions.

### 2. Lambda Function Configuration

Each Lambda function receives CORS configuration via environment variables:

```python
# Environment variables set in lambda_stack.py
"ALLOWED_ORIGINS": f"https://{client_host}.{domain}",
"CORS_ALLOW_CREDENTIALS": "true",
"CORS_ALLOW_HEADERS": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
"CORS_ALLOW_METHODS": "GET,POST,PUT,DELETE,OPTIONS",
"CORS_MAX_AGE": "86400",
```

### 3. Origin Validation Pattern

The actual origin validation happens in Lambda functions, not at the API Gateway level. This allows for:

- Dynamic origin configuration without redeploying API Gateway
- Different origins for different Lambda functions if needed
- Proper credential support with specific origins

### 4. Domain-Based Configuration

During deployment, CORS origins are configured based on your domain settings:

```bash
# During deployment, you'll be prompted for:
Domain (e.g., darkrelics.net): yourdomain.com
Client Host (e.g., portal): portal

# This results in ALLOWED_ORIGINS being set to:
# https://portal.yourdomain.com
```

## Technical Implementation

### CDK Stack Integration

1. **Lambda Stack**: Sets CORS environment variables on all API Lambda functions
2. **API Stack**: Configures API Gateway with CORS preflight options
3. **Client Stack**: Deploys the portal to the configured client host domain

### Environment Variable Structure

All API Lambda functions receive these CORS-related environment variables:

- `ALLOWED_ORIGINS`: The FQDN of the client (e.g., `https://portal.darkrelics.net`)
- `CORS_ALLOW_CREDENTIALS`: Set to `"true"` for authenticated requests
- `CORS_ALLOW_HEADERS`: Comma-separated list of allowed headers
- `CORS_ALLOW_METHODS`: Comma-separated list of allowed HTTP methods
- `CORS_MAX_AGE`: Preflight cache duration in seconds (86400 = 24 hours)

### Lambda Handler Pattern

Lambda functions should implement CORS handling like this:

```python
import os
from eidolon import cors

def lambda_handler(event, context):
    # Get origin from request
    origin = event.get('headers', {}).get('origin', '')

    # Validate origin
    allowed_origins = os.environ.get('ALLOWED_ORIGINS', '').split(',')
    if origin not in allowed_origins:
        return {
            'statusCode': 403,
            'body': json.dumps({'error': 'Origin not allowed'})
        }

    # Process request...

    # Return with CORS headers
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': origin,
            'Access-Control-Allow-Credentials': 'true'
        },
        'body': json.dumps(response_data)
    }
```

## Security Considerations

### Current Implementation Gaps

1. **Wildcard in API Gateway**: The API Gateway uses `*` for preflight, which is less secure than explicit origins
2. **Single Origin**: Only supports one client origin (portal.domain.com), not multiple environments
3. **No Development Support**: Localhost origins aren't automatically added

### Recommended Improvements

1. Replace wildcard with explicit origins in API Gateway
2. Support multiple origins (dev, staging, prod)
3. Add localhost origins for development
4. Implement origin validation at API Gateway level

## Deployment

CORS configuration is automatically applied during deployment:

```bash
cd deployment && python3 deploy.py
```

The deployment will prompt for domain configuration:

- Domain name (e.g., darkrelics.net)
- Client host subdomain (e.g., portal)

These values are used to construct the ALLOWED_ORIGINS for Lambda functions.

## Troubleshooting

### CORS Errors in Browser Console

1. Verify Lambda environment variables:

   ```bash
   aws lambda get-function-configuration --function-name api-character-list | jq '.Environment.Variables | .ALLOWED_ORIGINS'
   ```

2. Check API Gateway CORS configuration:

   ```bash
   aws apigateway get-rest-api --rest-api-id YOUR_API_ID | jq '.defaultCorsPreflightOptions'
   ```

3. Common issues and solutions:
   - **Origin not allowed**: The request origin doesn't match ALLOWED_ORIGINS in Lambda
   - **Credentials not supported**: Ensure CORS_ALLOW_CREDENTIALS is "true"
   - **Preflight failing**: Check API Gateway has OPTIONS method configured
   - **CloudFront blocking**: Ensure CloudFront forwards the Origin header

### Testing CORS

Test CORS configuration with curl:

```bash
# Test preflight request
curl -X OPTIONS https://mud-api.yourdomain.com/characters \
  -H "Origin: https://portal.yourdomain.com" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: Authorization" -v

# Test actual request
curl https://mud-api.yourdomain.com/characters \
  -H "Origin: https://portal.yourdomain.com" \
  -H "Authorization: Bearer YOUR_TOKEN" -v
```

## Best Practices

1. **Domain-Based Origins**: Use the client's FQDN for production CORS
2. **Use HTTPS**: Always use HTTPS origins in production
3. **Validate in Lambda**: Perform actual origin validation in Lambda functions
4. **Credentials with Specific Origins**: When using credentials, specify exact origins
5. **Environment Variables**: Use environment variables for dynamic configuration

## Key Lessons from Deployment

Based on production deployment experience:

1. **Custom Domain Required**: The system requires a custom domain for proper CORS configuration - this is collected during deployment to avoid circular dependencies

2. **FQDN Assembly**: The client FQDN (e.g., `https://portal.darkrelics.net`) is assembled at the deployment module level and passed as a complete value to stacks

3. **Two-Layer CORS**: API Gateway handles preflight with wildcards, Lambda functions validate actual origins - this provides flexibility without compromising security

4. **Environment Variables Over Hard-Coding**: All CORS settings are passed via environment variables, allowing changes without code modifications

## Adding Multiple Origins Support

Currently, the system only supports a single origin. To add multiple origins:

1. Modify the Lambda stack to accept multiple client hosts
2. Update ALLOWED_ORIGINS to be a comma-separated list
3. Modify Lambda functions to split and validate against multiple origins

Example enhancement:

```python
# In lambda_stack.py
allowed_origins = [
    f"https://{client_host}.{domain}",
    "http://localhost:3000",  # Development
    "http://localhost:8080",  # Alternative dev port
]
env_vars["ALLOWED_ORIGINS"] = ",".join(allowed_origins)
```

## Deployment Mode Considerations

The deployment system supports three modes that affect CORS:

- **MUD Mode**: Traditional gameplay - client at `portal.domain.com`
- **Incremental Mode**: Story-driven gameplay - client at `portal.domain.com`
- **Hybrid Mode**: Both features - client at `portal.domain.com`

All modes currently use the same client host configuration for CORS.
