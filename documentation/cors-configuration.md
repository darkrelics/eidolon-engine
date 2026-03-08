# CORS Configuration Guide for Eidolon Engine

This guide explains how Cross-Origin Resource Sharing (CORS) is configured for the Eidolon Engine's API Gateway and Lambda functions.

## Table of Contents

- [Overview](#overview)
- [Current Implementation](#current-implementation)
  - [API Gateway Configuration](#1-api-gateway-configuration)
  - [Lambda Function Configuration](#2-lambda-function-configuration)
  - [Centralized CORS Handler](#3-centralized-cors-handler)
  - [Lambda Handler Decorator](#4-lambda-handler-decorator)
  - [Response Helper Integration](#5-response-helper-integration)
- [Deployment Configuration](#deployment-configuration)
- [Security Implementation](#security-implementation)
- [Lambda Function Integration](#lambda-function-integration)
- [Troubleshooting](#troubleshooting)
- [Development Configuration](#development-configuration)
- [Code Reference](#code-reference)
- [Best Practices](#best-practices)
- [Architecture Notes](#architecture-notes)
- [Migration Notes](#migration-notes)
- [Related Documentation](#related-documentation)

## Overview

CORS configuration is handled at two levels:

1. **API Gateway**: Handles preflight OPTIONS requests with explicit origin
2. **Lambda Functions**: Add CORS headers to all responses via `@authenticated_handler` decorator

All CORS logic is centralized in `eidolon/cors.py` with automatic header injection via `eidolon/lambda_handler.py`.

## Current Implementation

### 1. API Gateway Configuration

The API Gateway is configured with explicit CORS settings based on deployment configuration:

```python
# In deployment/stacks/api_stack.py
default_cors_preflight_options=apigateway.CorsOptions(
    allow_origins=[client_origin],  # Explicit origin from deployment config
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Amz-Date", "X-Api-Key", "X-Amz-Security-Token"],
    allow_credentials=True,
)
```

Where `client_origin` is constructed during deployment as `https://{client_host}.{domain}`.

### 2. Lambda Function Configuration

Each Lambda function receives CORS configuration via environment variables:

```python
# Set in deployment/stacks/character_stack.py, player_stack.py, story_stack.py
"ALLOWED_ORIGINS": cors_origin,  # e.g., "https://portal.darkrelics.net"
"CORS_ALLOW_CREDENTIALS": "true",
"CORS_ALLOW_HEADERS": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
"CORS_ALLOW_METHODS": "GET,POST,PUT,DELETE,OPTIONS",
"CORS_MAX_AGE": "86400",
```

### 3. Centralized CORS Handler

All CORS logic is centralized in `eidolon/cors.py`:

**File:** `eidolon/cors.py`

**Key Features:**

- Single global instance: `cors_handler`
- Reads configuration from environment variables
- Supports multiple origins via comma-separated ALLOWED_ORIGINS
- Handles preflight OPTIONS requests
- Adds CORS headers to all responses automatically

**Fallback Logic:**

1. If "_" in ALLOWED_ORIGINS: Always return "_" without credentials
2. If ALLOWED_ORIGINS empty: Return "\*" without credentials (permissive degradation)
3. If origin in allowed list: Return origin with credentials if enabled
4. If single origin configured: Return that origin with credentials (fallback for mismatched origin)
5. If multiple origins configured and origin not in list: Return None (block request)

### 4. Lambda Handler Decorator

All API Lambda functions use the `@authenticated_handler` decorator from `eidolon/lambda_handler.py`, which encapsulates CORS handling, authentication, and error formatting:

```python
from eidolon.lambda_handler import authenticated_handler

@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    # Business logic here - no CORS or auth boilerplate needed
    result = do_something(player_id)

    return {"status_code": 200, "body": result}
```

**What the decorator handles:**

1. Request logging via `log_lambda_statistics()`
2. CORS preflight requests via `cors_handler.handle_preflight()`
3. Authentication extraction from JWT via `extract_player_id()`
4. Error handling with proper status codes
5. Response formatting with CORS headers via `lambda_response()`

**Key Points:**

- No manual CORS handling needed in Lambda functions
- No manual origin validation or header construction
- Decorator extracts `player_id` from Cognito JWT and passes to handler
- Return simple dict with `status_code` and `body` keys
- Errors raised as `ValueError` (4xx) or `RuntimeError` (500) are handled automatically

### 5. Response Helper Integration

The `eidolon/responses.py` module automatically adds CORS headers:

```python
def lambda_response(status_code: int, body: dict, event: dict) -> dict:
    # Creates response then adds CORS headers
    return cors_handler.add_cors_headers(create_response(status_code, body), event)

def lambda_error(event: dict, err: Exception) -> dict:
    # Error responses also get CORS headers
    return cors_handler.add_cors_headers(error_response("Internal server error", 500), event)
```

**All responses** from Lambda functions include proper CORS headers automatically.

## Deployment Configuration

### Domain-Based Configuration

During deployment:

```bash
cd deployment && python deploy.py
```

You will be prompted for:

- Domain (e.g., `darkrelics.net`)
- Client Host (e.g., `portal`)

This constructs:

- **API Gateway origin:** `https://portal.darkrelics.net`
- **Lambda ALLOWED_ORIGINS:** `https://portal.darkrelics.net`

### Multiple Origins Support

The system supports multiple origins via comma-separated list:

**In deployment stack:**

```python
# Example: Support production and localhost
allowed_origins = [
    f"https://{client_host}.{domain}",
    "http://localhost:3000",
    "http://localhost:8080",
]
env_vars["ALLOWED_ORIGINS"] = ",".join(allowed_origins)
```

**cors_handler automatically:**

- Splits on comma
- Validates request origin against list
- Returns matching origin in Access-Control-Allow-Origin header

## Security Implementation

### Origin Validation

The cors_handler implements strict origin validation:

**From eidolon/cors.py:**

```python
def is_origin_allowed(self, origin: str) -> bool:
    return bool(origin and origin in self.allowed_origins)
```

**Origin resolution logic:**

- Checks if origin is in allowed list
- Falls back to single origin if only one configured
- Blocks requests if multiple origins configured and origin not in list
- Logs warnings for blocked origins

### Credentials Handling

When `CORS_ALLOW_CREDENTIALS="true"`:

- Access-Control-Allow-Credentials header added
- Origin must be explicit (not wildcard)
- Required for authenticated requests with JWT tokens

**Note:** Wildcard origin ("_") cannot be used with credentials. If "_" is in ALLOWED_ORIGINS, credentials are automatically disabled.

### Preflight Caching

Preflight responses are cached for 24 hours (86400 seconds) as configured in CORS_MAX_AGE environment variable.

## Lambda Function Integration

All 19 API Lambda functions use the `@authenticated_handler` decorator:

**Character Functions:**

- api-character-add
- api-character-delete
- api-character-get
- api-character-list

**Archetype Functions:**

- api-archetype-list

**Item Functions:**

- api-item-brief
- api-item-consolidate
- api-item-consume
- api-item-discard
- api-item-prototype
- api-item-split

**Store Functions:**

- api-store-list
- api-store-purchase

**Segment Functions:**

- api-segment-decision
- api-segment-history
- api-segment-status

**Story Functions:**

- api-story-abandon
- api-story-history
- api-story-start

**Pattern Consistency:** 100% of API functions use `@authenticated_handler` decorator.

## Troubleshooting

### CORS Errors in Browser Console

**1. Verify Lambda Environment Variables**

```bash
aws lambda get-function-configuration \
  --function-name api-character-list \
  --query 'Environment.Variables.ALLOWED_ORIGINS' \
  --output text
```

Expected output: `https://portal.yourdomain.com`

**2. Test Preflight Request**

```bash
curl -X OPTIONS https://api.yourdomain.com/character/list \
  -H "Origin: https://portal.yourdomain.com" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: Authorization" \
  -v
```

Expected response:

- Status: 200
- Access-Control-Allow-Origin: https://portal.yourdomain.com
- Access-Control-Allow-Credentials: true

**3. Test Actual Request**

```bash
curl https://api.yourdomain.com/character/list \
  -H "Origin: https://portal.yourdomain.com" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -v
```

Expected response headers:

- Access-Control-Allow-Origin: https://portal.yourdomain.com
- Access-Control-Allow-Credentials: true

### Common Issues

**"Origin not in allowed list" Warning in Logs:**

- Request origin doesn't match ALLOWED_ORIGINS environment variable
- Check Lambda environment variables
- Verify request is from correct domain

**"No CORS headers in response":**

- Lambda function not using `@authenticated_handler` decorator
- Verify function imports from `eidolon.lambda_handler`
- Verify function returns dict with `status_code` and `body` keys

**"Credentials not supported with wildcard":**

- ALLOWED_ORIGINS contains "\*"
- Change to explicit origin for credential support

**CloudFront Blocking CORS:**

- Ensure CloudFront distribution forwards Origin header
- Check cache behavior settings

## Development Configuration

### Adding Localhost for Development

Update deployment stack to include localhost:

```python
# In deployment/stacks/character_stack.py (and others)
allowed_origins = [
    cors_origin,  # Production: https://portal.domain.com
    "http://localhost:3000",  # Flutter dev server
    "http://localhost:8080",  # Alternative port
]
env_vars["ALLOWED_ORIGINS"] = ",".join(allowed_origins)
```

Then redeploy the Character, Player, and Story stacks.

### Testing Locally

Run Flutter with chrome web-security disabled:

```bash
cd incremental
flutter run -d chrome --web-browser-flag="--disable-web-security"
```

Or configure ALLOWED_ORIGINS to include localhost as shown above.

## Code Reference

**CORS Implementation Files:**

- `eidolon/cors.py` - CorsHandler class with all CORS logic
- `eidolon/lambda_handler.py` - `@authenticated_handler` decorator integrating CORS
- `eidolon/responses.py` - `lambda_response()` and `lambda_error()` helpers
- `deployment/stacks/api_stack.py` - API Gateway CORS configuration
- `deployment/stacks/character_stack.py` - Lambda environment variables (ALLOWED_ORIGINS, etc.)
- `deployment/stacks/player_stack.py` - Lambda environment variables
- `deployment/stacks/story_stack.py` - Lambda environment variables

**All Lambda Functions:** Use `@authenticated_handler` decorator (19 API functions verified).

## Best Practices

1. **Use @authenticated_handler Decorator:** Never manually handle CORS in Lambda functions
2. **Environment Variables:** Configure origins via ALLOWED_ORIGINS, never hardcode
3. **Explicit Origins with Credentials:** Always use specific origins when credentials needed
4. **Comma-Separated List:** Support multiple origins by separating with commas
5. **HTTPS in Production:** Always use HTTPS origins for production deployments
6. **Simple Return Values:** Return dict with `status_code` and `body` from handlers

## Architecture Notes

**Why Two-Layer CORS:**

- API Gateway handles high-volume preflight requests efficiently
- Lambda functions validate actual request origins with business logic
- Environment variables allow dynamic configuration without API Gateway redeployment
- Single origin configuration (cors_handler) ensures consistency

**Security Model:**

- API Gateway preflight uses explicit origin from deployment config
- Lambda functions validate against ALLOWED_ORIGINS environment variable
- Credentials only allowed with explicit origins (never wildcard)
- Misconfiguration defaults to permissive mode (prevents service disruption)

## Migration Notes

If updating from previous implementation:

1. Replace manual CORS handling with `@authenticated_handler` decorator
2. Import from `eidolon.lambda_handler` instead of `eidolon.cors`
3. Change handler signature to include `player_id` parameter
4. Return simple dict with `status_code` and `body` keys
5. Remove any manual CORS header construction
6. Remove any manual origin validation logic

**Example migration:**

```python
# Before (manual pattern)
from eidolon.cors import cors_handler
from eidolon.responses import lambda_response

def lambda_handler(event: dict, context: object) -> dict:
    preflight = cors_handler.handle_preflight(event)
    if preflight:
        return preflight
    # ... auth extraction ...
    return lambda_response(200, data, event)

# After (decorator pattern)
from eidolon.lambda_handler import authenticated_handler

@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    # ... business logic only ...
    return {"status_code": 200, "body": data}
```

**Current Status:** All 19 API functions use `@authenticated_handler` decorator.

## Related Documentation

- [Architecture](architecture.md) - System architecture overview
- [Lambda Functions](lambda-functions.md) - Lambda function reference
- [Incremental API](incremental-api.md) - API endpoint documentation
- [Deployment](deployment.md) - Deployment configuration and procedures
- [Eidolon Library](eidolon-library.md) - Shared library documentation
