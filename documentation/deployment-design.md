# Incremental Deployment System Design

## Overview

This system enables incremental infrastructure updates by:

1. Reading existing `config.yml` if present
2. Validating current AWS resource states
3. Deploying only changed or missing resources
4. Updating configuration incrementally

## Architecture Components

### 1. Deployment Orchestrator (`deployment/deploy.py`)

- Main entry point for all deployments
- Orchestrates the entire deployment lifecycle
- Manages parameter loading and user prompts
- Executes CDK deployments via subprocess
- Updates configuration files with deployment outputs
- Handles CloudFormation to CDK migration
- Implements fail-forward approach for error recovery

### 2. State Manager (`deployment/state_manager.py`)

- Reads and writes infrastructure state to local cache
- Tracks deployed resources and their configurations
- Persists deployment parameters between runs
- Records deployment history and events

### 3. Resource Validator (`deployment/resource_validator.py`)

- Validates individual AWS resources (DynamoDB, CloudWatch, CodeBuild, etc.)
- Checks resource configurations against desired state
- Detects configuration drift
- Provides factory pattern for extensible resource validation

### 4. CDK Application (`deployment/cdk/`)

- **app.py**: Main CDK application entry point
- **stacks/**: Individual CDK stack definitions
  - `s3_stack.py`: S3 buckets with smart existing bucket detection
  - `dynamodb_stack.py`: DynamoDB tables with import capabilities
  - `cognito_stack.py`: User authentication infrastructure
  - `cloudwatch_stack.py`: Logging and metrics configuration
  - `cloudfront_stack.py`: CDN distribution for portal with import support
  - `codebuild_stack.py`: CI/CD pipeline for portal deployment

### 5. Configuration Manager (within `state_manager.py`)

- Reads and updates `config.yml`
- Manages configuration sections (Game, AWS, Cognito, DynamoDB, etc.)
- Ensures configuration consistency with deployed resources

### 6. Script Deployment (`deployment/deploy_scripts.py`)

- Standalone utility for Lua script deployment to S3
- List and delete capabilities for deployed scripts
- Independent of main infrastructure deployment

## Deployment Flow

1. **Prerequisites Check**
   - Verify CDK is installed
   - Validate AWS credentials and access
   - Confirm AWS account and region

2. **Parameter Loading**
   - Load saved parameters from state manager
   - Read existing `config.yml` if present
   - Extract S3 bucket names and other configurations
   - Prompt user for any missing required parameters

3. **Discovery & Analysis Phase**
   - Query existing CloudFormation stacks (both CDK and legacy)
   - Map legacy CloudFormation resources to CDK expectations
   - Determine migration strategy (adopt, coexist, or greenfield)
   - Validate existing resources for drift detection
   - Generate drift report for any configuration mismatches

4. **Planning Phase**
   - Identify stacks to create vs update
   - Determine resource adoption requirements
   - Build comprehensive deployment plan
   - Present plan to user for approval

5. **Execution Phase**
   - Set up CDK environment variables and context
   - Pass adopted resource information to CDK
   - Execute `cdk deploy --all` with appropriate parameters
   - CDK handles dependency resolution automatically
   - Monitor deployment progress
   - On failure, stop and provide recovery guidance

6. **Configuration Update**
   - Query deployed stack outputs
   - Update `config.yml` with:
     - Cognito user pool and client IDs
     - DynamoDB table names
     - CloudWatch log groups
     - S3 bucket names
     - CloudFront distribution ID and portal URL
   - Save updated configuration

7. **Finalization**
   - Record deployment event in state manager
   - Save deployment state and parameters
   - Deploy Lua scripts to S3 (if applicable)
   - Report deployment summary

## Key Benefits

- No complete redeployment for minor changes
- Faster deployment times
- Fail-forward approach with clear recovery paths
- Configuration drift detection
- Minimal user input required
- Infrastructure as code with type safety
- Built-in CDK diff capabilities
- Automatic dependency resolution by CDK

## Implementation Notes

### Consolidated Architecture

The implementation consolidates functionality into fewer modules than originally designed:

- **Parameter management** is integrated directly into the deployment orchestrator
- **CDK management** is handled through subprocess calls and the CDK CLI
- **Dependency resolution** is delegated to CDK's native capabilities
- **Configuration management** is part of the state manager module

This consolidation follows the codebase principle of "simplicity of code is high priority" and reduces complexity while maintaining all required functionality.

### Migration Support

The system supports three deployment scenarios:

1. **Greenfield**: Complete new deployment with no existing resources
2. **Adoption**: Import existing resources (DynamoDB tables, S3 buckets) into CDK management
3. **Coexistence**: CDK stacks work alongside legacy CloudFormation stacks when adoption isn't possible

### Resource Naming

- All resources use simple, unprefixed names for clarity and consistency:
  - DynamoDB tables: `eidolon-players`, `eidolon-characters`, `eidolon-rooms`, `eidolon-exits`, `eidolon-items`, `eidolon-prototypes`, `eidolon-archetypes`, `eidolon-motd`
  - S3 buckets: `eidolon-portal`, `eidolon-scripts`
  - CloudWatch log group: `/aws/eidolon/server`
  - Cognito user pool: `eidolon-users`
  - CodeBuild project: `eidolon-portal-build`
  - CloudFront: `eidolon-portal-distribution`
  - IAM policies: `eidolon-dynamodb-access`, `eidolon-cloudwatch-access`
- Legacy CloudFormation stacks are still detected with `eidolon-` prefix for backward compatibility
- CDK stack names are simple service names: `cognito`, `dynamodb`, `cloudwatch`, `s3`, `cloudfront`, `codebuild`

### CI/CD Integration

The CodeBuild stack is integrated with CloudFront for seamless deployments:

- **Automatic cache invalidation**: Build process invalidates CloudFront distribution after S3 sync
- **Conditional invalidation**: Only runs when CloudFront distribution ID is configured
- **IAM permissions**: CodeBuild role includes cloudfront:CreateInvalidation permission
- **Backward compatibility**: Works with both CloudFront and S3-only deployments

This ensures zero-downtime deployments with immediate content updates for end users.

### Fail-Forward Approach

The deployment system uses a fail-forward strategy rather than automatic rollback:

1. **Partial Deployment Success**: If some stacks deploy successfully before a failure, they remain deployed
2. **Incremental Recovery**: Failed deployments can be fixed and re-run without affecting successful stacks
3. **State Preservation**: Deployment state tracks what succeeded for informed recovery decisions
4. **CDK Stack Rollback**: Individual stack failures are rolled back by CDK, preventing broken stacks
5. **Manual Intervention**: Requires human decision on whether to continue, fix, or destroy

This approach:

- **Preserves successful work**: Doesn't waste successfully deployed resources
- **Enables debugging**: Failed stacks can be investigated in place
- **Supports iteration**: Fix issues and redeploy only what failed
- **Reduces risk**: No cascading rollback failures
- **Maintains control**: Operators decide the recovery strategy
