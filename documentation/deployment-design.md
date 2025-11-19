# Eidolon Engine Deployment System Design

## Executive Summary

The Eidolon Engine deployment system provides a modular, CDK-based infrastructure deployment solution that supports multiple game modes while maintaining clean separation of concerns. Successfully replacing a monolithic 1800+ line deployment class, the new architecture features 10 independent CDK stacks, 3 deployment modes, and automated end-to-end deployment from infrastructure provisioning to portal deployment.

The system leverages AWS CDK v2 with a clear separation between CDK synthesis and deployment operations, ensuring that AWS API calls only occur during the deployment phase. This architecture enables reliable deployments, efficient resource management, and seamless transitions between different operational modes (MUD, Incremental, and Hybrid).

## The Challenge

The original deployment system suffered from:

- **Monolithic Structure**: Single 1800+ line class handling all deployment logic
- **Poor Separation of Concerns**: Business logic, infrastructure, and UI mixed together
- **Code Duplication**: AWS client creation and configuration management scattered
- **Complex Dependencies**: Circular dependencies and tightly coupled components
- **Inconsistent Error Handling**: Silent failures with no clear recovery mechanism
- **Resource Recreation**: Resources being deleted and recreated on every deployment

The Eidolon Engine needed a deployment system that could:

- Support multiple game modes with different frontend requirements
- Maintain clean separation between CDK synthesis and AWS operations
- Use fixed logical IDs to prevent resource recreation
- Provide post-deployment Lambda updates from S3 artifacts
- Enable automated portal builds after infrastructure deployment
- Enforce module size limits (300 lines ideal, 1000 maximum)

## The Solution

The new modular deployment system addresses these challenges through:

1. **Modular Architecture**: 10 independent CDK stacks with clean separation of concerns, 94% of modules under 300 lines.

2. **Fixed Logical IDs**: Preventing resource recreation by using consistent logical IDs across deployments.

3. **CDK Context Standardization**: All stacks use `app.node.try_get_context()` instead of argparse for parameter passing.

4. **Post-Deployment Updates**: Lambda functions and layers automatically updated from S3 artifacts after CDK deployment.

5. **Automated Portal Deployment**: CodeBuild project executes automatically after Client Stack deployment.

6. **AWS Access Isolation**: All AWS API calls moved from CDK synthesis to deployment layer, ensuring synthesis is deterministic.

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

### 2. Core Infrastructure (`deployment/core/`)

- **config.py**: Configuration dataclass for operational data persistence
- **state.py**: CDK state tracking for deployment management
- **dynamodb_tables.py**: Table configurations with schema definitions

### 3. Stack Utilities (`deployment/stacks/stack_utilities.py`)

- Consolidated resource existence checks using boto3
- S3 bucket, DynamoDB table, and Cognito User Pool validation
- ACM certificate and CloudFront distribution preservation
- Used during deployment layer, not CDK synthesis

### 4. CDK Applications (`deployment/app_*.py`)

Each stack has its own app file to prevent cross-contamination:

- **app_dynamodb.py**: DynamoDB tables with managed policy
- **app_codebuild.py**: Build projects and artifacts bucket
- **app_s3.py**: Scripts bucket with automatic upload
- **app_cloudwatch.py**: Log group and metrics namespace
- **app_lambda.py**: Layer, functions, and execution role
- **app_player.py**: Cognito User Pool with triggers
- **app_character.py**: Character-related Lambda functions (api-item-brief, api-item-prototype, api-item-consume)
- **app_story.py**: SSM, SQS, EventBridge integration
- **app_api.py**: API Gateway with Lambda integrations
- **app_client.py**: CloudFront, S3, and portal build

### 5. Deployment Modules

Modular deployment functions for each stack:

- **dynamodb.py**: Table deployment and validation
- **codebuild.py**: Build project deployment with automatic execution
- **s3.py**: Scripts bucket with Lua upload
- **cloudwatch.py**: Logging infrastructure
- **lambda_functions.py**: Lambda deployment with post-deploy updates
- **player.py**: Cognito setup with trigger configuration
- **character.py**: Character stack deployment
- **story.py**: Event-driven processing setup
- **api.py**: API Gateway deployment
- **client.py**: Portal infrastructure with automated build

## Deployment Flow

1. **Prerequisites Check**

   - Verify CDK bootstrap status
   - Validate AWS credentials and region
   - Auto-copy config.template.yml if needed

2. **Parameter Collection**

   - Priority: Defaults → cdk.json → config.yml → User prompts
   - Collect all user input upfront
   - Single deployment confirmation
   - Mode selection (MUD/Incremental/Hybrid)

3. **Stack Deployment Order (Mode-Dependent)**

   The detailed sequence for each mode is maintained in [Deployment Guide](deployment.md#stack-deployment-order).

4. **CDK Execution**

   - Pass parameters via CDK context (-c flags)
   - Each stack in separate app file
   - Fixed logical IDs for all resources
   - Post-deployment validation with boto3

5. **Post-Deployment Operations**

   - Lambda function updates from S3
   - Layer version management and cleanup
   - Cognito trigger configuration for imported pools
   - S3 bucket policy updates for CloudFront

6. **Automated Portal Build**
   - CodeBuild project execution
   - Real-time phase monitoring
   - S3 sync and CloudFront invalidation
   - Portal URL display on completion

## Key Achievements

- **Modular Architecture**: 94% of modules under 300 lines (vs 1800+ line monolith)
- **Fixed Logical IDs**: Preventing resource recreation on updates
- **CDK Best Practices**: No AWS access during synthesis phase
- **Automated Deployment**: End-to-end from infrastructure to portal
- **Post-Deploy Updates**: Ensuring Lambda functions use latest code
- **Layer Management**: Automatic cleanup of old Lambda layer versions
- **Production Tested**: All 9 phases deployed and operational
- **140 Lessons Learned**: Documented and applied throughout implementation

## Implementation Notes

### Consolidated Architecture

The implementation consolidates functionality into fewer modules than originally designed:

- **Parameter management** is integrated directly into the deployment orchestrator
- **CDK management** is handled through subprocess calls and the CDK CLI
- **Dependency resolution** is delegated to CDK's native capabilities
- **Configuration management** is part of the state manager module

This consolidation follows the codebase principle of "simplicity of code is high priority" and reduces complexity while maintaining all required functionality.

### Resource Naming

- **DynamoDB Tables**: See [Database Schema](schema.md) for canonical table names and fields
- **S3 Buckets**:
  - Artifacts: `eidolon-engine-lambda-{account_id}`
  - Scripts: `eidolon-scripts-{account_id}`
  - Portal: `portal.{domain}` or custom
- **Lambda Functions**: 18 total (17 deployed, 1 not deployed)
- **Cognito**: `eidolon-users` pool
- **CloudWatch**: `/eidolon/server` log group
- **API Gateway**: REST API at `api.{domain}`
- **CloudFront**: Distribution at `portal.{domain}`
- **IAM**: Shared execution role with managed policies
- **CDK Stack IDs**: Simple lowercase names (`dynamodb`, `lambda`, `player`, etc.)

### Critical Implementation Lessons

1. **CDK Synthesis vs Runtime**: Resource existence checks during synthesis don't have AWS access - use fixed logical IDs instead
2. **Post-Deployment Updates**: Lambda functions must be updated from S3 after CDK deployment to ensure latest code
3. **Context Over Arguments**: Use CDK context (-c flags) instead of argparse for all app files
4. **Stack Isolation**: Each CDK stack needs its own app file to prevent output contamination
5. **Lambda Permission Management**: Cognito trigger permissions must be managed post-deployment for imported User Pools
6. **API Domain Configuration**: Pass domain without protocol to Flutter builds to prevent double `https://`
7. **DynamoDB Permissions**: Include `DescribeTable` action for proper table access

### Deployment Modes

**MUD Mode**: Traditional Multi-User Dungeon — see [Deployment Modes](deployment-modes.md) for the full comparison; the legacy portal buildspec is the only frontend asset deployed.

**Incremental Mode**: Story-Driven Gameplay — see [Deployment Modes](deployment-modes.md); this mode excludes the Lua scripts and CloudWatch stacks.

**Hybrid Mode** (Default): Full Feature Set — see [Deployment Modes](deployment-modes.md); deploys all stacks with the incremental frontend.

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

## Production Deployment Results

### Architecture Improvements

- **Code Organization**: From 1800+ line monolith to modular architecture (94% modules under 300 lines)
- **Deployment Reliability**: Fixed logical IDs prevent resource recreation
- **CDK Compliance**: No AWS access during synthesis phase
- **Automation**: End-to-end deployment including portal build

### Operational Achievements

- **10 CDK Stacks**: All deployed and operational in production
- **3 Deployment Modes**: Successfully tested (MUD, Incremental, Hybrid)
- **140 Lessons Learned**: Documented and applied
- **Post-Deploy Updates**: Lambda functions automatically updated from S3
- **Layer Management**: Old versions automatically cleaned up

### Key Metrics

- **Module Size**: 94% under 300 lines, 100% under 1000 lines
- **Stack Count**: 10 independent CDK stacks
- **Lambda Functions**: 18 total (17 deployed, 1 not deployed)
- **DynamoDB Tables**: 14 tables with managed policy
- **Deployment Time**: Full deployment in under 15 minutes

## System Validation

### Post-Stack Validation

- Resource existence verification with boto3
- IAM policy attachment confirmation
- Lambda function and layer updates from S3
- Cognito trigger configuration for imported pools

### Build Artifact Validation

- Lambda layer zip existence and size
- All Lambda function zips present (17 deployed functions)
- Portal build output in S3
- CloudFront distribution accessibility

### Integration Points

- Cognito PostConfirmation → cognito-player-new Lambda
- SQS Queues → ops-segment-process and ops-story-advance
- EventBridge → ops-segment-poller (disabled by default)
- API Gateway → All API Lambda functions with Cognito authorizer

## Conclusion

The Eidolon Engine deployment system successfully demonstrates how a complex monolithic deployment system can be transformed into a clean, modular architecture. Through 140 documented lessons learned and strict adherence to CDK best practices, the system achieves reliable, automated deployments while maintaining code simplicity.

Key successes include the separation of CDK synthesis from AWS operations, use of fixed logical IDs to prevent resource recreation, and automated post-deployment updates ensuring Lambda functions always use the latest code. The system's production deployment validates that sophisticated multi-mode applications can be deployed efficiently without sacrificing maintainability or reliability.
