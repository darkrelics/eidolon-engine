# Eidolon Engine Deployment Guide

This guide explains how to deploy the Eidolon Engine infrastructure using the modular CDK-based deployment system that replaced the monolithic 1800+ line deployment class.

## Prerequisites

- Python 3.12 or later (always use `python3` command)
- AWS CLI configured with appropriate credentials
- AWS CDK CLI installed: `npm install -g aws-cdk`
- Required Python packages: `pip3 install -r requirements/scripts-requirements.txt`
- AWS CDK Bootstrap: Run `cdk bootstrap aws://ACCOUNT-ID/REGION` if not already done
- Supported regions: us-east-1, us-east-2, us-west-2

## Quick Start

```bash
cd deployment
python3 deploy.py
```

The deployment will:

1. Check CDK bootstrap status
2. Collect deployment parameters (mode, domain, etc.)
3. Deploy 9 CDK stacks in sequence based on selected mode
4. Execute Lambda builds automatically
5. Update Lambda functions from S3 artifacts
6. Execute portal build via CodeBuild
7. Update config.yml with all resource identifiers

## System Architecture

- **9 CDK Stacks**: CodeBuild, DynamoDB, Lambda, Player, Story, S3, CloudWatch, API, Client
- **3 Deployment Modes**: MUD, Incremental, Hybrid (default)
- **16 Lambda Functions**: API handlers and operational functions
- **14 DynamoDB Tables**: All with RemovalPolicy.RETAIN
- **Fixed Logical IDs**: Preventing resource recreation on updates
- **Post-Deploy Updates**: Lambda functions automatically updated from S3

## Key Features

The deployment system provides:

- **Fixed Logical IDs**: Preventing resource recreation on stack updates
- **CDK Context Pattern**: All stacks use `-c` flags for parameters (no argparse)
- **AWS Access Isolation**: No AWS API calls during CDK synthesis
- **Automated End-to-End**: From infrastructure to portal deployment
- **Post-Deployment Operations**: Lambda updates, layer cleanup, trigger configuration
- **Production Tested**: All 9 phases deployed and operational

## Deployment Modes

### MUD Mode (8 Stacks)

- **Frontend**: Portal app via `buildspec/portal.yml`
- **Excludes**: Story Stack (no SQS/EventBridge)
- **Includes**: S3 Scripts, CloudWatch logging
- **Use Case**: Traditional MUD experience only

### Incremental Mode (7 Stacks)

- **Frontend**: Incremental app via `buildspec/incremental.yml`
- **Excludes**: S3 Scripts, CloudWatch Stack
- **Includes**: Story Stack (SQS/EventBridge)
- **Use Case**: Story-driven incremental gameplay

### Hybrid Mode - Default (9 Stacks)

- **Frontend**: Incremental app via `buildspec/incremental.yml`
- **Includes**: All stacks for complete functionality
- **Use Case**: Full feature set with both game modes

## Stack Deployment Order

### Phase-Based Deployment

Stacks deploy in a specific order based on dependencies:

1. **CodeBuild Stack**: Build infrastructure and artifacts bucket
2. **DynamoDB Stack**: 14 tables with managed IAM policy
3. **Lambda Stack**: Layer, 16 functions, shared execution role
4. **Player Stack**: Cognito User Pool with PostConfirmation trigger
5. **Story Stack** (Incremental/Hybrid only): SSM, SQS, EventBridge
6. **S3 Stack** (MUD/Hybrid only): Scripts bucket with Lua upload
7. **CloudWatch Stack** (MUD/Hybrid only): Logging infrastructure
8. **API Stack**: API Gateway with Lambda integrations
9. **Client Stack**: CloudFront, S3, automated portal build

## Deployment Process

### Initial Setup

```bash
cd deployment
python3 deploy.py
```

You'll be prompted for:

1. **Deployment Mode**: MUD, Incremental, or Hybrid (default)
2. **Domain Configuration**: Domain name and Route53 Hosted Zone ID
3. **GitHub Settings**: Owner, repository, branch (for CodeBuild)
4. **S3 Buckets**: Artifacts and scripts bucket names
5. **Reply Email**: For Cognito notifications

### Parameter Priority

The system loads parameters in this order:

1. Hardcoded defaults in code
2. Saved values from `cdk.json`
3. Existing `config.yml` values
4. User prompts (override all)

### CDK Context Configuration

All parameters are passed via CDK context:

```python
# Example from deployment modules
context_args = [
    "-c", f"region={params.region}",
    "-c", f"deployment_mode={params.deployment_mode}",
    "-c", f"domain={params.domain}",
    "-c", f"api_host={params.api_host}",
    "-c", f"client_host={params.client_host}"
]
```

Each stack has its own app file (`app_*.py`) to prevent output contamination.

## Post-Deployment Operations

### Automatic Lambda Updates

After CDK deployment, the system:

1. **Updates Lambda functions** from S3 artifacts
2. **Publishes new layer version** if changed
3. **Updates all functions** to use new layer
4. **Deletes old layer versions** to prevent accumulation
5. **Configures Cognito triggers** for imported User Pools

### Portal Build Automation

The Client Stack automatically:

1. **Starts CodeBuild project** after infrastructure
2. **Monitors build progress** with phase updates
3. **Syncs to S3** and invalidates CloudFront
4. **Displays portal URL** on completion

## Critical Implementation Details

### Fixed Logical IDs

All resources use fixed logical IDs to prevent recreation:

```python
# Example from Lambda Stack
def _get_function_logical_id(self, function_name: str) -> str:
    logical_id_map = {
        "api-character-list": "ApiCharacterListFunction",
        "cognito-player-new": "CognitoPlayerNewFunction",
        # ... etc
    }
    return logical_id_map.get(function_name, ...)
```

### No AWS Access During Synthesis

Resource checks happen in deployment layer, not CDK:

```python
# WRONG - Fails during synthesis
if check_s3_bucket_exists(bucket_name):
    s3.Bucket.from_bucket_name(...)

# RIGHT - Use fixed IDs, let CDK handle
s3.Bucket(self, "FixedLogicalId", bucket_name=...)
```

### Configuration Files

#### config.yml (Operational Data)

Contains runtime configuration:

```yaml
Game:
  name: eidolon-engine
  PortalS3Bucket: eidolon-portal # Auto-detected or created
  ScriptsS3Bucket: eidolon-scripts # Auto-detected or created
  ScriptsS3Prefix: scripts
  PortalUrl: https://d1234567890.cloudfront.net # Portal URL via CloudFront

# Deployment mode configuration
Deployment:
  Mode: hybrid # Options: 'mud', 'incremental', or 'hybrid'

AWS:
  region: us-east-1
  contact_email: contact@darkrelics.net

# API configuration (unified for all modes)
API:
  Domain: darkrelics.net
  HostedZoneId: Z1234567890ABC
  Subdomain: api # api.darkrelics.net

# CORS configuration for API Gateway
allowed_cors_origins: [] # Optional list; when empty, API preflight defaults to "*" without credentials
  # When set, API Gateway preflight uses this explicit list and allows credentials
  # ALLOWED_ORIGINS env var is passed to Lambdas as a comma-separated string

CloudFront:
  distribution_id: E1234567890ABC
  domain_name: d1234567890.cloudfront.net
  portal_url: https://d1234567890.cloudfront.net

Cognito:
  user_pool_id: us-east-1_xxxxxxxxx
  app_client_id: xxxxxxxxxxxxxxxxxxxx

# Unified DynamoDB tables (same for all deployment modes)
DynamoDB:
  Tables:
    Players: players
    Characters: characters
    Archetypes: archetypes
    Items: items
    Story: story # For incremental game story data
    Rooms: rooms
    Exits: exits
    Prototypes: prototypes
    Motd: motd

Logging:
  cloudwatch:
    log_group: /aws/eidolon/server
    metrics_namespace: eidolon/metrics
```

#### cdk.json (CDK Context)

Stores deployment parameters:

```json
{
  "context": {
    "region": "us-east-1",
    "deployment_mode": "hybrid",
    "domain": "darkrelics.net",
    "hosted_zone_id": "Z1234567890ABC",
    "github_owner": "robinje",
    "github_repo": "eidolon-engine",
    "github_branch": "develop",
    "s3_bucket": "eidolon-engine-lambda-542230992937"
  }
}
```

#### .cdk-state.json (Infrastructure State)

Tracks deployed resources and outputs (gitignored).

## Resource Naming

- **DynamoDB Tables** (14): `players`, `characters`, `rooms`, `exits`, `items`, `prototypes`, `archetypes`, `motd`, `story`, `segments`, `active_segments`, `story_history`, `segment_history`, `opponents`
- **Lambda Functions** (16): `api-*` and `ops-*` prefixed names
- **S3 Buckets**: `eidolon-engine-lambda-{account}`, `eidolon-scripts-{account}`, portal bucket
- **Cognito Pool**: `eidolon-users`
- **CloudWatch**: `/eidolon/server` log group
- **CDK Stack IDs**: Simple lowercase (`dynamodb`, `lambda`, `player`, etc.)
- **IAM**: Shared `eidolon-lambda-execution-role` with managed policies

## Lambda Infrastructure

### Shared Execution Role

All Lambda functions use a single execution role with:

- DynamoDB access via managed policy
- CloudWatch Logs permissions
- Additional policies attached by dependent stacks

### Environment Variables

```python
# Set in lambda_stack.py
"LOG_LEVEL": "INFO",  # Validated in eidolon/environment.py
"ALLOWED_ORIGINS": f"https://{client_host}.{domain}",
"CORS_ALLOW_CREDENTIALS": "true",
# DynamoDB table names from stack outputs
# Function-specific configs (SEGMENT_BATCH_SIZE, etc.)
```

### Post-Deployment Updates

Lambda functions are updated from S3 after CDK deployment:

```python
# Automatic update ensures latest code
lambda_client.update_function_code(
    FunctionName=function_name,
    S3Bucket=bucket_name,
    S3Key=f"{function_name}.zip"
)
```

## Known Issues and Solutions

### API Domain Configuration

The Flutter app expects domain without protocol:

```python
# Fixed in client_stack.py
"API_DOMAIN": codebuild.BuildEnvironmentVariable(
    value=f"{self.api_host}.{self.domain}"  # Not self.api_url
)
```

### DynamoDB Permissions

Must include `DescribeTable` action:

```python
# Fixed in dynamodb_stack.py
actions=[
    "dynamodb:DescribeTable",  # Required for table access
    "dynamodb:GetItem",
    "dynamodb:PutItem",
    # ... other actions
]
```

### Cognito Trigger Permissions

For imported User Pools, permissions set post-deployment:

```python
# In player.py - always check and add permissions
if current_trigger == lambda_arn:
    # Still need to check Lambda permissions
    # Don't return early
```

## Production Metrics

### Deployment Statistics

- **Total Stacks**: 9 independent CDK stacks
- **Lambda Functions**: 16 with shared execution role
- **DynamoDB Tables**: 14 with RemovalPolicy.RETAIN
- **Module Size**: 94% under 300 lines, 100% under 1000 lines
- **Deployment Time**: Full deployment in under 15 minutes
- **Lessons Learned**: 140 documented and applied

## Buildspec Selection by Mode

### Portal Build (MUD Mode)

Using `buildspec/portal.yml`:

```yaml
# Builds from portal/ directory
# Deploys traditional MUD interface
# No story/incremental features
```

### Incremental Build (Incremental/Hybrid)

Using `buildspec/incremental.yml`:

```yaml
# Builds from incremental/ directory
# Includes story progression features
# Timer-based gameplay interface
```

### Automatic Execution

CodeBuild runs automatically after Client Stack:

1. **Build starts** immediately after infrastructure
2. **Real-time monitoring** with phase updates
3. **S3 sync** to portal bucket
4. **CloudFront invalidation** clears cache
5. **Portal URL** displayed on completion

## Module Organization

### Deployment Modules (`deployment/`)

- **deploy.py**: Main orchestrator (parameter collection, stack ordering)
- **utilities.py**: CDK deployment wrapper, validation helpers
- **dynamodb.py**: DynamoDB stack deployment and validation
- **codebuild.py**: Build infrastructure with automatic execution
- **lambda_functions.py**: Lambda deployment with S3 updates
- **player.py**: Cognito deployment with trigger configuration
- **story.py**: SQS/EventBridge deployment (mode-aware)
- **api.py**: API Gateway deployment
- **client.py**: CloudFront and portal build automation

### CDK App Files (`deployment/app_*.py`)

Each stack has its own app file:

- Prevents output contamination
- Uses CDK context for parameters
- No argparse, uses `try_get_context()`

## Stack Dependencies

### Direct Dependencies

```
CodeBuild → (provides artifacts for) → Lambda
DynamoDB → (policy attached to) → Lambda
Lambda → (functions used by) → Player, Story, API
Player → (authorizer for) → API
API → (URL passed to) → Client
```

### Mode-Specific Dependencies

**MUD Mode**:

- S3 Scripts → Server can read Lua scripts
- CloudWatch → Server writes logs

**Incremental/Hybrid**:

- Story → SQS triggers Lambda functions
- Story → EventBridge invokes poller

### Post-Deployment Operations

1. **Lambda Updates**: Force update from S3 artifacts
2. **Layer Cleanup**: Delete old versions
3. **Cognito Triggers**: Configure for imported pools
4. **S3 Policies**: Update for CloudFront access
5. **Portal Build**: Execute CodeBuild project

## Troubleshooting

### CDK Bootstrap Required

```bash
cdk bootstrap aws://ACCOUNT-ID/REGION
```

If you see "SSM parameter /cdk-bootstrap/hnb659fds/version not found":

- The account needs CDK bootstrap
- Bootstrap creates required roles and buckets
- Only needed once per account/region

### Resource Already Exists

With fixed logical IDs, CDK handles existing resources:

- Resources are updated, not recreated
- Data is preserved across deployments
- Use RemovalPolicy.RETAIN for safety

### Lambda Permission Issues

For Cognito triggers on imported pools:

```bash
# Manually add if needed
aws lambda add-permission \
  --function-name cognito-player-new \
  --statement-id CognitoInvokePermission \
  --action lambda:InvokeFunction \
  --principal cognito-idp.amazonaws.com \
  --source-arn arn:aws:cognito-idp:REGION:ACCOUNT:userpool/POOL_ID
```

### API URL Double HTTPS Issue

If you see `https://https://api.domain.com`:

```python
# Problem: API_DOMAIN set to full URL
# Solution: Pass domain only
"API_DOMAIN": f"{api_host}.{domain}"  # Not api_url
```

### LOG_LEVEL Validation

The system now validates LOG_LEVEL:

```python
# Accepts: "20", "INFO", "DEBUG", etc.
# Returns: Always a string name for logging module
LOG_LEVEL = _validate_log_level(os.environ.get("LOG_LEVEL", "INFO"))
```

### Layer Version Accumulation

Old layer versions are automatically deleted:

```python
# Keeps only current version
lambda_client.delete_layer_version(
    LayerName=layer_name,
    VersionNumber=old_version
)
```

## Best Practices

### Architecture Guidelines

1. **Module Size**: Keep modules under 300 lines (1000 max)
2. **Fixed Logical IDs**: Prevent resource recreation
3. **CDK Context**: Use for all parameter passing
4. **Stack Isolation**: Separate app file per stack
5. **Post-Deploy Updates**: Always update Lambdas from S3

### Deployment Guidelines

1. **CDK Bootstrap First**: Required for each account/region
2. **Collect Input Upfront**: All prompts before execution
3. **Single Confirmation**: One approval for entire deployment
4. **Mode Selection**: Choose appropriate deployment mode
5. **Validate After Deploy**: Check resources with boto3

### Operational Guidelines

1. **Region Validation**: Only us-east-1, us-east-2, us-west-2
2. **RemovalPolicy.RETAIN**: For all stateful resources
3. **Managed Policies**: No inline policies
4. **Pattern Consistency**: Same patterns across all stacks

## Summary

The Eidolon Engine deployment system represents a complete transformation from a monolithic 1800+ line class to a clean, modular architecture with:

- **9 Independent CDK Stacks**: Each with focused responsibility
- **3 Deployment Modes**: MUD, Incremental, and Hybrid
- **Automated End-to-End**: Infrastructure to portal deployment
- **Production Tested**: All components operational
- **140 Lessons Applied**: Best practices throughout

The system demonstrates that complex infrastructure can be managed effectively with proper modularization, fixed logical IDs, and clear separation between CDK synthesis and AWS operations.

## CDK Development Notes

### Critical CDK Synthesis Limitations

Based on extensive production deployment experience, these patterns must be followed:

#### CDK Synthesis Constraints

- **No AWS Access During Synthesis**: CDK synthesis happens without AWS credentials. Any boto3 calls in CDK stack classes will fail. The deployment system uses boto3 in top-level deployment scripts for resource verification before CDK synthesis
- **Fixed Logical IDs Required**: Use fixed IDs like `"PortalBucket"` not dynamic ones to prevent resource recreation
- **CDK Tokens vs Strings**: `self.region` returns a token, not a string. Pass actual region values as parameters
- **No Runtime Imports**: All imports must be at module level. No dynamic imports or module injection

#### Resource Management Patterns

```python
# CORRECT: Fixed logical ID with RETAIN policy
bucket = s3.Bucket(
    self,
    "ArtifactsBucket",  # Fixed ID - won't change between deployments
    bucket_name=bucket_name,
    removal_policy=RemovalPolicy.RETAIN,
    auto_delete_objects=False,
)

# WRONG: Dynamic ID causes recreation
bucket = s3.Bucket(
    self,
    f"Bucket-{timestamp}",  # Changes every deployment!
    bucket_name=bucket_name,
)
```

#### Import Pattern for Existing Resources

```python
# In deployment module (has AWS access)
def deploy_stack(params):
    from stacks.stack_utilities import check_s3_bucket_exists
    bucket_exists = check_s3_bucket_exists(params.bucket, params.region)

    context_args = [
        "-c", f"bucket_exists={'true' if bucket_exists else 'false'}",
    ]
    return run_cdk_deploy("stack", params.region, app_command, context_args)

# In CDK stack
def __init__(self, scope, id, bucket_exists: bool = False, **kwargs):
    if bucket_exists:
        bucket = s3.Bucket.from_bucket_name(self, "Bucket", bucket_name)
    else:
        bucket = s3.Bucket(self, "Bucket", bucket_name=bucket_name,
                          removal_policy=RemovalPolicy.RETAIN)
```

#### Lambda Layer Version Management

```python
# Post-deployment cleanup of old layer versions
def update_lambda_layer(layer_name: str, s3_key: str):
    # Publish new version
    new_version = lambda_client.publish_layer_version(...)

    # Update all functions to use new version
    for function in functions:
        lambda_client.update_function_configuration(
            FunctionName=function,
            Layers=[new_version['LayerVersionArn']]
        )

    # Delete old version
    lambda_client.delete_layer_version(
        LayerName=layer_name,
        VersionNumber=old_version
    )
```

#### Common Pitfalls to Avoid

1. **Square Bracket Dictionary Access**: Use `.get()` method for safe access
2. **Environment Variable Manipulation**: Pass region explicitly, don't rely on CDK environment
3. **Inline IAM Policies**: Always use managed policies
4. **Dynamic Resource Naming**: Causes resource recreation on every deployment
5. **Resource Checks in CDK**: Will always fail during synthesis
