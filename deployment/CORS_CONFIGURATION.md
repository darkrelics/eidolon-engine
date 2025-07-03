# CORS Configuration Guide for Eidolon Engine

This guide explains how to configure Cross-Origin Resource Sharing (CORS) for the Eidolon Engine's MUD Portal and Incremental game applications.

## Overview

CORS configuration is now parameterized through the deployment configuration, allowing you to specify allowed origins for each application without modifying code.

## Quick Start

### 1. Configure CORS Origins

Use the provided configuration script:

```bash
cd deployment

# Configure MUD Portal origins
python configure_cors.py --type mud --origins https://portal.yourdomain.com https://mud.yourdomain.com

# Configure Incremental game origins
python configure_cors.py --type incremental --origins https://incremental.yourdomain.com https://idle.yourdomain.com

# Configure both applications with same origins
python configure_cors.py --type both --origins https://yourdomain.com --cloudfront dxxxxxxxxxxxxx.cloudfront.net
```

### 2. Development Configuration

For local development, include localhost origins:

```bash
python configure_cors.py --type both --origins https://yourdomain.com --localhost
```

This adds common localhost ports (3000, 8080, 8000) for both http://localhost and http://127.0.0.1.

### 3. Manual Configuration

You can also edit `config.yml` directly:

```yaml
# CORS configuration for API origins
CORS:
  MUDOrigins:
    - https://mud.yourdomain.com
    - https://portal.yourdomain.com
    - https://dxxxxxxxxxxxxx.cloudfront.net
  IncrementalOrigins:
    - https://incremental.yourdomain.com
    - https://idle.yourdomain.com
    - https://dxxxxxxxxxxxxx.cloudfront.net
```

## How It Works

1. **CDK Integration**: The CDK app reads CORS configuration from `config.yml`
2. **Environment Variables**: Origins are passed to Lambda functions via `ALLOWED_ORIGINS` environment variable
3. **Lambda Handler**: The `cors_handler.py` module validates request origins against the allowed list
4. **API Gateway**: Configured to handle preflight OPTIONS requests

## Security Features

- **Origin Validation**: Only explicitly allowed origins can make requests
- **Credentials Support**: When origins are configured, credentials are allowed
- **No Wildcards**: Production deployments should never use wildcard (`*`) origins
- **Preflight Handling**: Proper OPTIONS request handling for complex requests

## Deployment

After configuring CORS origins:

```bash
# Deploy all stacks with new CORS configuration
cdk deploy --all

# Or deploy specific stacks
cdk deploy base-lambda mud-lambda incremental-lambda
```

## Troubleshooting

### CORS Errors in Browser Console

1. Check that the origin is in the allowed list:
   ```bash
   cat config.yml | grep -A 5 CORS
   ```

2. Verify Lambda environment variables:
   ```bash
   aws lambda get-function-configuration --function-name mud-list-characters | grep ALLOWED_ORIGINS
   ```

3. Check CloudFront is forwarding the Origin header

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

1. **Be Specific**: Only add origins that actually need access
2. **Use HTTPS**: Always use HTTPS origins in production
3. **No Wildcards**: Never use `*` for production APIs
4. **Separate Environments**: Use different origins for dev/staging/prod
5. **Regular Audits**: Review and remove unused origins periodically

## Migration from Hardcoded CORS

If you're migrating from hardcoded CORS headers:

1. Configure origins in `config.yml`
2. Deploy Lambda functions with updated code
3. Test thoroughly before removing old code
4. Monitor for any CORS-related errors

## Environment-Specific Configuration

You can maintain different configurations for different environments:

```bash
# Development
cp config.yml config.dev.yml
python configure_cors.py --config config.dev.yml --type both --localhost

# Production
cp config.yml config.prod.yml
python configure_cors.py --config config.prod.yml --type both --origins https://yourdomain.com

# Deploy with specific config
cdk deploy --all -c config_file=config.prod.yml
```