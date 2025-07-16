# Deployment Guide for Eidolon Engine

This guide explains how to deploy and manage Eidolon Engine infrastructure using the CDK-based incremental deployment system.

## Prerequisites

- Python 3.11 or later (use `python3` command)
- AWS CLI configured with appropriate credentials
- AWS CDK CLI installed: `npm install -g aws-cdk`
- Required Python packages: `pip3 install -r requirements/scripts-requirements.txt`
- AWS CDK Bootstrap: The target AWS account must be bootstrapped for CDK. Run `cdk bootstrap aws://ACCOUNT-ID/REGION` if not already done

## Overview

The deployment system provides:

- **Incremental deployments** - Deploy or update only what's needed
- **Automatic resource detection** - Discovers and uses existing AWS resources
- **Zero-downtime updates** - Works with existing infrastructure
- **Infrastructure as Code** - All resources defined in CDK (Python)
- **Drift detection** - Validates existing resources against expected state
- **Multiple deployment modes** - Support for MUD, Incremental, and Hybrid game modes

### Deployment Modes

The Eidolon Engine supports three deployment modes, all sharing the same backend infrastructure but using different frontend applications:

- **MUD Mode**: Traditional Multi-User Dungeon with Portal frontend
- **Incremental Mode**: Idle/incremental game with Incremental frontend
- **Hybrid Mode** (default): Supports both game types with Incremental frontend

All modes share:

- Same DynamoDB tables (Players, Characters, Archetypes, Items, Story)
- Same Lambda functions and API Gateway
- Same Cognito user pool for authentication
- Unified backend infrastructure

## Deployment Scenarios

### 1. Greenfield Deployment (New Environment)

For deploying to a fresh AWS account with no existing infrastructure:

```bash
cd deployment
python3 deploy.py --region us-east-1
```

The system will:

1. Prompt for required parameters (game name, email, GitHub details)
2. Create all necessary AWS resources
3. Save configuration to `config.yml`
4. Deploy Lua scripts to S3

### 2. Existing Infrastructure Deployment

For environments with existing resources (S3 buckets, DynamoDB tables, etc.):

```bash
# First, analyze what exists
python3 deploy.py --region us-east-1 --analyze-only

# Then deploy, adopting existing resources
python3 deploy.py --region us-east-1
```

The system will:

1. Detect existing CloudFormation stacks
2. Find existing S3 buckets, DynamoDB tables, and other resources
3. Import compatible resources (DynamoDB, CloudWatch, S3)
4. Create new resources only where needed
5. Update configuration with all resource identifiers

### 3. Update Existing Deployment

To update an existing CDK deployment:

```bash
python3 deploy.py --region us-east-1
```

The system will:

1. Compare current state with desired state
2. Apply only necessary changes
3. Show drift report if manual changes were made

## Command Line Options

```bash
python3 deploy.py [OPTIONS]

Options:
  --region REGION        AWS region (default: us-east-1)
  --profile PROFILE      AWS profile to use
  --auto-approve         Skip confirmation prompts
  --skip-scripts         Skip Lua script deployment
  --analyze-only         Only analyze infrastructure, don't deploy
  --deploy-mud           Deploy in MUD mode (Portal frontend)
  --deploy-incremental   Deploy in Incremental mode
  --deploy-both          Deploy in Hybrid mode (default)
  --non-interactive      Run without interactive prompts
  --branch               Select specific GitHub branch
```

## Configuration

### Initial Parameters

During first deployment, you'll be prompted for:

- **Game Name**: Unique identifier for your game (default: `eidolon-engine`)
- **Contact Email**: Administrator email for notifications
- **GitHub Owner**: GitHub username or organization
- **GitHub Repository**: Repository name containing the code
- **GitHub Branch**: Branch to deploy from (default: `main`)

### Configuration File

The system creates and maintains `config.yml`:

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
CORS:
  AllowedOrigins: [] # Populated automatically based on deployment mode
  # For MUD mode: adds portal domain
  # For Incremental/Hybrid: adds incremental domain
  # Custom domains can be added manually after deployment

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

## Resource Naming Convention

All AWS resources use simple, unprefixed names for clarity:

| Resource Type           | Naming Pattern                | Example                                                  |
| ----------------------- | ----------------------------- | -------------------------------------------------------- |
| DynamoDB Tables         | `eidolon-{table_type}`        | `eidolon-players`, `eidolon-characters`, `eidolon-rooms` |
| S3 Buckets              | `eidolon-{type}`              | `eidolon-portal`                                         |
| CloudWatch Log Group    | `/aws/eidolon/server`         | `/aws/eidolon/server`                                    |
| Cognito User Pool       | `users`                       | `users`                                                  |
| CodeBuild Project       | `eidolon-portal-build`        | `eidolon-portal-build`                                   |
| CloudFront Distribution | `eidolon-portal-distribution` | `eidolon-portal-distribution`                            |
| IAM Policies            | `{service}-access`            | `dynamodb-access`                                        |
| CDK Stack Names         | `{service}`                   | `cognito`, `dynamodb`, `s3`, `lambda`, `cloudfront`      |
| API Gateway             | Single unified API            | `api.{domain}`                                           |

Legacy CloudFormation stacks with `eidolon-` prefix are still supported for backward compatibility.

## Resource Management

### S3 Buckets

The system handles S3 buckets intelligently:

- **Existing buckets**: Automatically detected and used
- **New buckets**: Created only if they don't exist
- **Naming**: `eidolon-portal` and `eidolon-scripts`

To use specific existing buckets, add to `config.yml` before deployment:

```yaml
Game:
  PortalS3Bucket: eidolon-portal
  ScriptsS3Bucket: eidolon-scripts
```

### DynamoDB Tables

Tables are created with:

- **Billing**: Pay-per-request (on-demand)
- **Backup**: Point-in-time recovery enabled
- **Retention**: Tables retained on stack deletion

Existing tables are automatically imported if they match the naming pattern.

### CloudWatch Logs

Log groups are created with configurable retention (default: 365 days).
Existing log groups are imported and settings preserved.

### CloudFront Distribution

The system manages CloudFront for portal distribution:

- **Existing distributions**: Can be imported by ID
- **New distributions**: Created with optimized caching
- **Security**: Uses Origin Access Identity for S3 access
- **HTTPS**: Enforces secure connections

To use an existing CloudFront distribution, add to `config.yml` before deployment:

```yaml
CloudFront:
  distribution_id: E1234567890ABC
```

## Deployment Workflow

The deployment process follows a specific order of operations to ensure infrastructure is created correctly:

### Prerequisites Check

Before running the deployment, ensure:

- AWS CDK is bootstrapped: `cdk bootstrap aws://ACCOUNT-ID/REGION`
- Required permissions are in place
- Dependencies are installed

### Order of Operations

1. **Check AWS Account Access** - Verify credentials and permissions
2. **Check for config.yml** - Look for existing configuration
3. **Validate Resources** - If config exists, validate all resources and update config with current state
4. **Deploy Infrastructure** - Create/update AWS resources in phases (requires CDK bootstrap)
5. **Build Artifacts** - Execute CodeBuild to create Lambda packages and frontend
6. **Update Functions** - Deploy Lambda functions with new code
7. **Finalize Configuration** - Write final config.yml with all resource IDs

### 1. Standard Deployment

Run the deployment wizard:

```bash
python3 deployment/deploy.py
```

This will:

- Check AWS access and display account information
- Validate existing resources if config.yml exists
- Deploy infrastructure in the correct order
- Execute builds automatically
- Update config.yml throughout the process

### 2. Validate Existing Infrastructure

To check if configured resources exist:

```bash
python3 deployment/deploy.py --validate
```

This validates all resources in config.yml against AWS and reports:

- Missing resources
- Configuration drift
- Access issues

### 3. Analyze Without Deploying

To see what would be deployed:

```bash
python3 deployment/deploy.py --analyze-only
```

### 4. Non-Interactive Deployment

For CI/CD pipelines:

```bash
python3 deployment/deploy.py --non-interactive --auto-approve
```

### 5. Update Scripts Only

To deploy only Lua scripts:

```bash
python3 deployment/deploy_scripts.py
```

## CI/CD Pipeline

### Frontend Deployment

The CodeBuild project automatically builds and deploys the appropriate Flutter web application based on the deployment mode:

#### MUD Mode

- Builds from `portal/` directory
- Uses `buildspec/portal.yml`
- Deploys Portal Flutter application

#### Incremental/Hybrid Modes

- Builds from `incremental/` directory
- Uses `buildspec/incremental.yml`
- Deploys Incremental Flutter application

The build process:

1. **Builds the Flutter web application**
2. **Syncs files to the S3 portal bucket**
3. **Invalidates CloudFront cache** (if configured)

### CloudFront Cache Invalidation

When CloudFront is configured, the build process automatically:

- Creates an invalidation for all paths (`/*`)
- Ensures users immediately see updated content
- No manual cache clearing required

The invalidation only runs if a CloudFront distribution ID is available, making the process backward compatible with S3-only deployments.

### Manual Portal Deployment

If you need to trigger a portal build manually:

```bash
# Using AWS CLI
aws codebuild start-build --project-name eidolon-portal-build

# Or through AWS Console
# Navigate to CodeBuild → eidolon-portal-build → Start build
```

## Migration Guide

### From Separated Backend Deployment

If migrating from the previous deployment with separate MUD and Incremental backends:

1. **Backend is now unified** - All modes share the same tables and APIs
2. **Table names are simplified** - No more `mud-` or `incremental-` prefixes
3. **Single API Gateway** - One API serves all game modes at `api.{domain}`
4. **Choose deployment mode** - Based on which frontend you need

The deployment system will automatically handle resource migration.

### From CloudFormation

If you have existing CloudFormation stacks (`eidolon-*`):

1. **The system will detect them automatically**
2. **DynamoDB and CloudWatch resources will be adopted**
3. **S3 buckets will be detected and used**
4. **Cognito and CodeBuild will coexist** (manual migration needed)

No need to delete CloudFormation stacks first - the system handles coexistence.

## Phased Deployment Details

The deployment process is divided into six phases to ensure proper dependency resolution:

### Phase 1: Foundation

- **IAM roles and policies** - Created first with no dependencies
- **S3 buckets** - Portal, scripts, and Lambda deployment buckets
- **DynamoDB tables** - All game data tables

### Phase 2: Authentication & Monitoring

- **Cognito User Pool** - User authentication
- **CloudWatch Log Groups** - Application logging

### Phase 3: Build Infrastructure

- **CodeBuild Projects** - For Lambda and frontend builds
- Projects are configured without GitHub webhooks
- Manual or deployment-triggered builds only

### Phase 4: Build Execution

- **Lambda Layer Build** - Dependencies package
- **Lambda Functions Build** - Individual function packages
- **Frontend Build** - Portal or Incremental application
- Builds run sequentially for Lambda, parallel for frontend
- CloudFront invalidation happens automatically if distribution exists

### Phase 5: Application Layer

- **Base Lambda Layer** - Shared dependencies
- **Lambda Functions** - API handlers
- **API Gateway** - RESTful API with custom domain
- **Cognito Triggers** - Post-confirmation Lambda

### Phase 6: Distribution

- **CloudFront** - CDN for frontend application

Each phase only proceeds if the previous phase succeeded. Failed deployments can be resumed from where they left off.

## Deployment Recovery (Fail-Forward Approach)

The deployment system uses a fail-forward strategy. When a deployment fails:

### Understanding Deployment Failures

1. **Partial Success**: Some stacks may have deployed successfully before the failure
2. **CDK Behavior**: Failed stacks are automatically rolled back by CDK
3. **State Preservation**: Successfully deployed stacks remain active

### Recovery Steps

#### 1. Assess the Failure

```bash
# Check which stacks were deployed
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE

# Review the failure details
cdk list
```

#### 2. Fix the Issue

Common fixes:

- **Permission errors**: Update IAM policies
- **Resource conflicts**: Rename resources or import existing ones
- **Limit exceeded**: Request AWS quota increases
- **Invalid parameters**: Correct configuration values

#### 3. Resume Deployment

```bash
# Re-run deployment (only failed stacks will be attempted)
python3 deploy.py --region us-east-1

# The system will:
# - Skip already deployed stacks
# - Attempt only the failed stacks
# - Update configuration with new outputs
```

#### 4. Alternative: Clean Slate

If you prefer to start over:

```bash
# List all stacks
cdk list

# Destroy specific stacks
cdk destroy <stack-name>

# Or destroy all stacks (careful!)
cdk destroy --all
```

### Fail-Forward Benefits

- **No data loss**: Successful deployments are preserved
- **Faster recovery**: Fix only what's broken
- **Learning opportunity**: Investigate failures in place
- **Incremental progress**: Build infrastructure step by step

## Troubleshooting

### CDK Bootstrap Issues

If you encounter errors like "SSM parameter /cdk-bootstrap/hnb659fds/version not found" or "Role arn:aws:iam::ACCOUNT:role/cdk-hnb659fds-deploy-role-ACCOUNT-REGION is invalid":

1. **Bootstrap the CDK environment**:

   ```bash
   cdk bootstrap aws://ACCOUNT-ID/REGION
   # Example: cdk bootstrap aws://542230992937/us-east-1
   ```

2. **If bootstrap fails due to existing resources**:
   - Check for existing CDK resources: `aws s3 ls | grep cdk-hnb659fds`
   - Delete failed bootstrap stack: `aws cloudformation delete-stack --stack-name CDKToolkit`
   - Wait for deletion: `aws cloudformation wait stack-delete-complete --stack-name CDKToolkit`
   - Retry bootstrap

3. **Common bootstrap errors**:
   - "Policy already exists": Delete conflicting IAM policies first
   - "Bucket already exists": The CDK assets bucket exists from a previous bootstrap
   - "SSM parameter already exists": Delete the parameter with `aws ssm delete-parameter --name /cdk-bootstrap/hnb659fds/version`

### Configuration File Path

The deployment system expects `config.yml` to be in the project root directory (one level up from the `deployment/` directory). If you see "No configuration found" errors:

1. Ensure `config.yml` exists in the project root: `/path/to/eidolon-engine/config.yml`
2. Run deployment commands from the `deployment/` directory
3. The system will automatically look for `../config.yml`

### "Stack already exists"

If you see CDK stack conflicts:

```bash
# List existing stacks
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE

# If needed, delete conflicting CDK stack
cdk destroy STACK_NAME
```

### "Bucket already exists"

Add the bucket name to `config.yml` before deployment:

```yaml
Game:
  PortalS3Bucket: existing-bucket-name
```

### "Table already exists"

The system should auto-import existing tables. If not:

1. Ensure table follows naming convention: `eidolon-{table-type}` (e.g., `eidolon-players`, `eidolon-characters`)
2. Check table is in the same region
3. Verify AWS credentials have access

### Resource Drift

If drift is detected:

1. Review the drift report
2. Decide whether to:
   - Accept drift (update CDK to match reality)
   - Fix drift (revert manual changes)
   - Ignore drift (if non-critical)

## Best Practices

1. **Always analyze first**: Use `--analyze-only` before deploying
2. **Keep config.yml in version control**: Track infrastructure changes
3. **Use consistent naming**: Resources use simple, unprefixed names
4. **Regular drift checks**: Run analysis periodically
5. **Backup before major changes**: Export critical data

### Fail-Forward Best Practices

1. **Small incremental changes**: Deploy one feature at a time
2. **Test in development first**: Use separate environments
3. **Document dependencies**: Know which stacks depend on others
4. **Monitor partial deployments**: Check health of deployed stacks
5. **Plan recovery strategy**: Know how to fix common failures before they happen

## Advanced Usage

### Deployment Mode Selection

```bash
# Deploy in MUD mode (Portal frontend)
python3 deployment/deploy.py --deploy-mud

# Deploy in Incremental mode
python3 deployment/deploy.py --deploy-incremental

# Deploy in Hybrid mode (supports both game types)
python3 deployment/deploy.py --deploy-both

# Or set in config.yml
Deployment:
  Mode: hybrid  # Options: 'mud', 'incremental', or 'hybrid'
```

### Custom Parameters

Override defaults via environment or config:

```bash
# Via environment
export CDK_DEFAULT_ACCOUNT=123456789012
export CDK_DEFAULT_REGION=eu-west-1
export DEPLOYMENT_MODE=hybrid

# Via context
cdk deploy -c deployment_mode=hybrid -c game_name=eidolon-engine
```

### Multi-Environment

Deploy multiple environments:

```bash
# Development
python3 deploy.py --region us-east-1

# Production (different region/account)
AWS_PROFILE=prod python3 deploy.py --region eu-west-1
```

### State Management

Deployment state is tracked in:

- `.deployment_state.json` - Local state file
- CloudFormation stack outputs - Resource identifiers
- `config.yml` - Runtime configuration

## Legacy Systems

The following systems are replaced by the CDK deployment:

- `deployment/deploy-old.py` - Legacy CloudFormation deployment script
- `cloudformation/*.yml` - CloudFormation templates (for reference only)
- Manual resource creation in AWS Console

Use `deploy.py` for all infrastructure management.
