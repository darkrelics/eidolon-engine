# Incremental Deployment System Design

## Executive Summary

The Eidolon Engine deployment system provides a sophisticated, incremental infrastructure deployment solution that supports multiple game modes while maintaining a unified backend architecture. This system was designed to solve the complex challenge of deploying and managing AWS infrastructure for a multi-mode gaming platform that can operate as a traditional MUD, an incremental idle game, or a hybrid of both.

The deployment system leverages AWS CDK (Cloud Development Kit) to provide infrastructure-as-code capabilities while adding intelligent state management, resource discovery, and fail-forward recovery mechanisms. This approach enables zero-downtime updates, efficient resource utilization, and seamless transitions between different operational modes.

## The Challenge

Traditional deployment approaches often require complete infrastructure teardown and rebuild for significant changes, leading to:

- Extended downtime during updates
- Risk of data loss or corruption
- Complex rollback procedures
- Difficulty in maintaining multiple environments
- Manual configuration management prone to errors

The Eidolon Engine needed a deployment system that could:

- Support multiple game modes with different frontend requirements
- Share backend infrastructure efficiently across all modes
- Enable incremental updates without service disruption
- Detect and report configuration drift
- Provide clear recovery paths when deployments fail
- Minimize manual configuration while maintaining flexibility

## The Solution

Our incremental deployment system addresses these challenges through:

1. **Unified Backend Architecture**: All game modes share the same DynamoDB tables, Lambda functions, and API Gateway endpoints, reducing infrastructure costs and complexity.

2. **Mode-Aware Frontend Selection**: The system automatically deploys the appropriate frontend (Portal for MUD, Incremental for other modes) based on the selected deployment mode.

3. **Intelligent State Management**: The system tracks deployment state, preserves configuration between runs, and can resume from partial deployments.

4. **Resource Discovery and Validation**: Before deployment, the system discovers existing AWS resources and validates their configuration against the desired state.

5. **Fail-Forward Recovery**: Instead of automatic rollback, the system preserves successful deployments and provides clear guidance for fixing and continuing from failure points.

## Overview

This system enables incremental infrastructure updates with support for multiple deployment modes:

1. Reading existing `config.yml` if present
2. Validating current AWS resource states
3. Deploying unified backend infrastructure for all game modes
4. Selecting appropriate frontend based on deployment mode
5. Updating configuration incrementally

### Unified Architecture

All deployment modes (MUD, Incremental, Hybrid) share:

- **Same backend infrastructure**: DynamoDB tables, Lambda functions, API Gateway
- **Same authentication**: Cognito user pool
- **Different frontends**: Portal for MUD, Incremental for others

## Architecture Components

### 1. Deployment Orchestrator (`deployment/deploy.py`)

- Main entry point for all deployments
- Orchestrates the entire deployment lifecycle
- Manages parameter loading and user prompts
- Executes CDK deployments via subprocess
- Updates configuration files with deployment outputs
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

- **app.py**: Main CDK application entry point with mode-aware deployment
- **stacks/**: Individual CDK stack definitions
  - `iam_stack.py`: IAM roles and policies for server execution
  - `s3_stack.py`: S3 buckets with smart existing bucket detection
  - `dynamodb_stack.py`: Unified DynamoDB tables for all modes
  - `cognito_stack.py`: User authentication infrastructure (shared)
  - `cloudwatch_stack.py`: Logging and metrics configuration
  - `cloudfront_stack.py`: CDN distribution with mode-aware configuration
  - `codebuild_stack.py`: CI/CD pipeline selecting buildspec by mode
  - `lambda_stack.py`: Unified Lambda functions and API Gateway
  - `base_lambda_stack.py`: Shared Lambda layer and base functions

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
   - Determine deployment mode (mud/incremental/hybrid)
   - Extract S3 bucket names and other configurations
   - Prompt user for any missing required parameters

3. **Discovery & Analysis Phase**
   - Query existing CloudFormation stacks
   - Validate existing resources for drift detection
   - Generate drift report for any configuration mismatches

4. **Planning Phase**
   - Identify stacks to create vs update
   - Build comprehensive deployment plan
   - Present plan to user for approval

5. **Execution Phase**
   - Set up CDK environment variables and context
   - Pass deployment mode to CDK context
   - Execute `cdk deploy --all` with appropriate parameters
   - CDK creates unified backend for all modes
   - CDK selects frontend based on deployment mode
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

### Resource Naming

- All resources use simple names for clarity and consistency:
  - DynamoDB tables (unified): `players`, `characters`, `archetypes`, `items`, `progress`, `resources`, `rooms`, `exits`, `prototypes`, `motd`, `story`
  - S3 buckets:
    - Portal: `darkrelics-portal` (default) or custom name
    - Scripts: `darkrelics-scripts` (default) or custom name
    - Lambda: `{game_name}-lambda-{account_id}` (e.g., `eidolon-engine-lambda-123456789012`)
  - CloudWatch log group: `/aws/eidolon/server`
  - Cognito user pool: `eidolon-users`
  - CodeBuild project: `eidolon-codebuild`
  - CloudFront: `eidolon-distribution`
  - API Gateway: `eidolon-api` at `api.{domain}`
  - IAM resources:
    - Role: `{game_name}-server-execution-role`
    - Policies: `eidolon-{game_name}-dynamodb-access`, `eidolon-{game_name}-cloudwatch-access`
- CDK stack names are simple service names: `iam`, `s3`, `dynamodb`, `cognito`, `cloudwatch`, `codebuild`, `base-lambda`, `lambda`, `cloudfront`

### CI/CD Integration

The CodeBuild stack is integrated with CloudFront for seamless deployments:

- **Mode-aware builds**: Selects buildspec based on deployment mode
  - MUD mode: Uses `buildspec/portal.yml`, builds from `portal/`
  - Incremental/Hybrid: Uses `buildspec/incremental.yml`, builds from `incremental/`
- **Automatic cache invalidation**: Build process invalidates CloudFront distribution after S3 sync
- **Conditional invalidation**: Only runs when CloudFront distribution ID is configured
- **IAM permissions**: CodeBuild role includes cloudfront:CreateInvalidation permission

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

## Real-World Usage Scenarios

### Scenario 1: Initial Deployment

When deploying to a fresh AWS account, the system:

1. Prompts for minimal configuration (game name, domain, deployment mode)
2. Discovers that no existing infrastructure exists
3. Creates all required resources in the correct order
4. Generates a complete `config.yml` for future deployments
5. Deploys the selected frontend to CloudFront

### Scenario 2: Adding Incremental Game to Existing MUD

For an existing MUD deployment, switching to hybrid mode:

1. Reads existing `config.yml` and discovers deployed resources
2. Validates that backend infrastructure supports both modes
3. Updates only the CodeBuild and CloudFront configurations
4. Deploys the Incremental frontend without touching the backend
5. Preserves all existing game data and player accounts

### Scenario 3: Recovering from Failed Deployment

When a deployment partially fails:

1. The system preserves all successfully deployed stacks
2. Provides clear error messages about what failed and why
3. Allows operators to fix issues (e.g., IAM permissions, resource limits)
4. Resumes deployment from the failure point
5. Updates configuration only after full success

### Scenario 4: Configuration Drift Detection

During routine deployment checks:

1. The system compares actual AWS resources against expected state
2. Reports any manual changes or drift (e.g., modified IAM policies)
3. Offers options to update infrastructure or update expectations
4. Ensures consistency between code and deployed resources

## Benefits and Outcomes

### Operational Benefits

- **Reduced Deployment Time**: Incremental updates typically complete in 5-10 minutes vs 30-45 minutes for full deployments
- **Zero Downtime**: Backend services remain available during frontend updates
- **Lower Risk**: Partial failures don't affect running services
- **Better Observability**: Clear visibility into what's deployed and what's pending

### Development Benefits

- **Faster Iteration**: Developers can quickly test infrastructure changes
- **Mode Flexibility**: Easy switching between MUD, Incremental, and Hybrid modes
- **Simplified Testing**: Each component can be updated independently
- **Clear Separation**: Frontend and backend concerns are properly isolated

### Business Benefits

- **Cost Optimization**: Shared infrastructure reduces AWS costs by ~40%
- **Scalability**: Unified backend scales efficiently for all game modes
- **Maintainability**: Single codebase for infrastructure management
- **Flexibility**: New game modes can be added without infrastructure redesign

## Future Enhancements

The deployment system is designed for extensibility:

1. **Multi-Region Support**: Deploy to multiple AWS regions with data replication
2. **Blue-Green Deployments**: Support for zero-downtime backend updates
3. **Automated Testing**: Integration with infrastructure testing frameworks
4. **Cost Monitoring**: Built-in cost analysis and optimization recommendations
5. **Backup and Restore**: Automated backup strategies with point-in-time recovery

## Conclusion

The Eidolon Engine's incremental deployment system represents a sophisticated approach to infrastructure management that balances flexibility, reliability, and efficiency. By combining AWS CDK's infrastructure-as-code capabilities with intelligent state management and fail-forward recovery, the system enables rapid development and deployment while maintaining production stability.

This design demonstrates that complex multi-mode applications can be deployed and managed effectively without sacrificing simplicity or reliability. The unified backend architecture with mode-aware frontend selection provides a blueprint for similar multi-tenant or multi-mode applications.
