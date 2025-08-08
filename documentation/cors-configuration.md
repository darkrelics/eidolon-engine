# CORS Configuration Guide for Eidolon Engine

This guide explains how Cross-Origin Resource Sharing (CORS) is configured for the Eidolon Engine's MUD Portal and Incremental game applications.

## Overview

CORS configuration is derived from CloudFront distributions and domain settings in the deployment configuration. The system automatically configures CORS based on your CloudFront setup.

## How CORS Currently Works

### 1. Automatic Configuration

CORS origins are automatically derived from your CloudFront and domain configuration:

```yaml
# In config.yml
Domain: yourdomain.com
CloudFrontDistributions:
  MUDPortal: dxxxxxxxxxxxxx.cloudfront.net
  IncrementalGame: dyyyyyyyyyy.cloudfront.net
```

The CDK deployment automatically allows CORS from:

- Your configured domain (with https://, https://www., http://, http://www.)
- CloudFront distribution URLs
- Common localhost ports for development (3000, 8080, 8000)

### 2. Additional Origins Configuration

If you need to add additional origins beyond the automatic configuration, set `allowed_cors_origins` in your config.yml:

```yaml
CORS:
allowed_cors_origins:
    - https://additional.domain.com
```

### 3. Manual Override (Not Currently Implemented)

The `configure_cors.py` script exists but its output is not currently used by the CDK deployment. It writes to these fields which are ignored:

```yaml
# These fields are written by configure_cors.py but NOT USED
CORS:
  MUDOrigins: # Not read by CDK
  IncrementalOrigins: # Not read by CDK
```

## Technical Implementation

1. **CDK Integration**: The CDK app derives CORS origins from CloudFront distributions and domain configuration
2. **Environment Variables**: Origins are passed to Lambda functions via the `ALLOWED_ORIGINS` environment variable (a comma-separated list). When an explicit list is configured, API Gateway preflight enables `Access-Control-Allow-Credentials`.
3. **Lambda Handler**: The `eidolon/cors.py` module validates request origins against the allowed list
4. **API Gateway**: Configured to handle preflight OPTIONS requests

## Security Features

- **Origin Validation**: Only explicitly allowed origins can make requests
- **Credentials Support**: When origins are configured, credentials are allowed
- **No Wildcards**: Production deployments should never use wildcard (`*`) origins
- **Preflight Handling**: Proper OPTIONS request handling for complex requests

## Deployment

CORS configuration is automatically applied when you deploy:

```bash
# Deploy all stacks
cdk deploy --all

# Or deploy specific stacks
cdk deploy base-lambda mud-lambda incremental-lambda
```

Note: Changes to CloudFront distributions or domain configuration in `config.yml` will update CORS origins on the next deployment.

## Troubleshooting

### CORS Errors in Browser Console

1. Check your CloudFront and domain configuration:

   ```bash
   cat config.yml | grep -E "Domain|CloudFrontDistributions" -A 3
   ```

2. Verify Lambda environment variables:

   ```bash
  aws lambda get-function-configuration --function-name api-character-list | grep ALLOWED_ORIGINS
   ```

3. Check CloudFront is forwarding the Origin header

4. Verify the actual origins being used:
   - Your domain should appear with https://, https://www., http://, and http://www. prefixes
   - CloudFront distributions should be included
   - Localhost origins (for development) should be present

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

## Adding Custom CORS Origins

To add custom CORS origins beyond the automatic CloudFront/domain configuration:

1. Add them to the `allowed_cors_origins` field in `config.yml`:

   ```yaml
   CORS:
  allowed_cors_origins:
       - https://custom.domain.com
       - https://another.domain.com
   ```

2. Deploy the changes:
   ```bash
   cdk deploy --all
   ```

Note: The `configure_cors.py` script exists but its output (`CORS.MUDOrigins` and `CORS.IncrementalOrigins`) is not currently read by the CDK deployment.

## Environment-Specific Configuration

You can maintain different configurations for different environments by using different config files:

```bash
# Development config with different domain/CloudFront
cp config.yml config.dev.yml
# Edit config.dev.yml to set development domain and CloudFront distributions

# Production config
cp config.yml config.prod.yml
# Edit config.prod.yml to set production domain and CloudFront distributions

# Deploy with specific config
cdk deploy --all -c config_file=config.prod.yml
```

## Future Enhancement

The `configure_cors.py` script and per-application CORS configuration (`CORS.MUDOrigins` and `CORS.IncrementalOrigins`) represent a planned enhancement that would allow more granular CORS control. To enable this functionality, the CDK deployment code would need to be updated to read from these configuration fields.
