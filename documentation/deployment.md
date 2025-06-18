# Deployment Guide for Eidolon Engine

This guide explains how to deploy and manage Eidolon Engine infrastructure using the CDK-based incremental deployment system.

## Overview

The deployment system provides:
- **Incremental deployments** - Deploy or update only what's needed
- **Automatic resource detection** - Discovers and uses existing AWS resources
- **Zero-downtime updates** - Works with existing infrastructure
- **Infrastructure as Code** - All resources defined in CDK (Python)
- **Drift detection** - Validates existing resources against expected state

## Deployment Scenarios

### 1. Greenfield Deployment (New Environment)

For deploying to a fresh AWS account with no existing infrastructure:

```bash
cd deployment
python deploy.py --region us-east-1
```

The system will:
1. Prompt for required parameters (game name, email, GitHub details)
2. Create all necessary AWS resources
3. Save configuration to `server/config.yml`
4. Deploy Lua scripts to S3

### 2. Existing Infrastructure Deployment

For environments with existing resources (S3 buckets, DynamoDB tables, etc.):

```bash
# First, analyze what exists
python deploy.py --region us-east-1 --analyze-only

# Then deploy, adopting existing resources
python deploy.py --region us-east-1
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
python incremental_deploy.py --region us-east-1
```

The system will:
1. Compare current state with desired state
2. Apply only necessary changes
3. Show drift report if manual changes were made

## Command Line Options

```bash
python deploy.py [OPTIONS]

Options:
  --region REGION        AWS region (default: us-east-1)
  --profile PROFILE      AWS profile to use
  --auto-approve         Skip confirmation prompts
  --skip-scripts         Skip Lua script deployment
  --analyze-only         Only analyze infrastructure, don't deploy
```

## Configuration

### Initial Parameters

During first deployment, you'll be prompted for:
- **Game Name**: Unique identifier for your game (e.g., `my-mud`)
- **Contact Email**: Administrator email for notifications
- **GitHub Owner**: GitHub username or organization
- **GitHub Repository**: Repository name containing the code
- **GitHub Branch**: Branch to deploy from (default: `main`)

### Configuration File

The system creates and maintains `server/config.yml`:

```yaml
Game:
  name: my-mud
  PortalS3Bucket: my-mud-portal-123456789012  # Auto-detected or created
  ScriptsS3Bucket: my-mud-scripts-123456789012  # Auto-detected or created
  ScriptsS3Prefix: scripts

AWS:
  region: us-east-1
  contact_email: admin@example.com

Cognito:
  user_pool_id: us-east-1_xxxxxxxxx
  app_client_id: xxxxxxxxxxxxxxxxxxxx

DynamoDB:
  tables:
    players: my-mud-players
    characters: my-mud-characters
    rooms: my-mud-rooms
    # ... other tables

Logging:
  cloudwatch:
    log_group: /aws/eidolon/my-mud
    metrics_namespace: EidolonEngine/my-mud
```

## Resource Management

### S3 Buckets

The system handles S3 buckets intelligently:
- **Existing buckets**: Automatically detected and used
- **New buckets**: Created only if they don't exist
- **Naming**: `{game-name}-portal-{account-id}` and `{game-name}-scripts-{account-id}`

To use specific existing buckets, add to `config.yml` before deployment:
```yaml
Game:
  PortalS3Bucket: my-existing-portal-bucket
  ScriptsS3Bucket: my-existing-scripts-bucket
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

## Deployment Workflow

### 1. Pre-Deployment Analysis

Always analyze before deploying to understand what will happen:

```bash
python deploy.py --analyze-only
```

Output shows:
- Existing CloudFormation stacks
- Resources that can be adopted
- Resources that need creation
- Any configuration drift

### 2. Deploy

Review the deployment plan and proceed:

```bash
python incremental_deploy.py
```

### 3. Verify

After deployment:

```bash
# Check CDK stacks
cd cdk
cdk list

# Verify resources
aws s3 ls
aws dynamodb list-tables
aws logs describe-log-groups --log-group-name-prefix /aws/eidolon
```

### 4. Update Scripts

To deploy only Lua scripts:

```bash
python deploy_scripts.py
```

## Migrating from CloudFormation

If you have existing CloudFormation stacks (`eidolon-*`):

1. **The system will detect them automatically**
2. **DynamoDB and CloudWatch resources will be adopted**
3. **S3 buckets will be detected and used**
4. **Cognito and CodeBuild will coexist** (manual migration needed)

No need to delete CloudFormation stacks first - the system handles coexistence.

## Troubleshooting

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
1. Ensure table follows naming convention: `{game-name}-{table-type}`
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
3. **Use consistent naming**: Stick to the game name across all resources
4. **Regular drift checks**: Run analysis periodically
5. **Backup before major changes**: Export critical data

## Advanced Usage

### Custom Parameters

Override defaults via environment or config:

```bash
# Via environment
export CDK_DEFAULT_ACCOUNT=123456789012
export CDK_DEFAULT_REGION=eu-west-1

# Via context
cdk deploy -c game_name=special-mud
```

### Multi-Environment

Deploy multiple environments:

```bash
# Development
python deploy.py --region us-east-1

# Production (different region/account)
AWS_PROFILE=prod python deploy.py --region eu-west-1
```

### State Management

Deployment state is tracked in:
- `.deployment_state.json` - Local state file
- CloudFormation stack outputs - Resource identifiers
- `server/config.yml` - Runtime configuration

## Legacy Systems

The following systems are replaced by the CDK deployment:
- `deployment/deploy-old.py` - Legacy CloudFormation deployment script
- `cloudformation/*.yml` - CloudFormation templates (for reference only)
- Manual resource creation in AWS Console

Use `deploy.py` for all infrastructure management.