# Deployment System Rework Plan

## Overview

Complete replacement of the existing monolithic deployment system with a clean, modular architecture focused on simplicity and maintainability.

## Status: Phase 1 COMPLETE - DynamoDB Stack Deployed and Battle-Tested

### Phase 1 Completed Work

- Core infrastructure modules (config.py, state.py, dynamodb_tables.py)
- DynamoDB CDK stack with 14 tables and IAM policy
- Deployment orchestrator (deploy.py) with proper error handling and validation
- CDK application entry point (app.py)
- Documentation updates
- Path handling fixes for cross-platform compatibility
- Account ID caching to prevent redundant API calls
- Flexible policy validation for future expansion
- Refactored deploy.py with clean separation of concerns
- DeploymentParams dataclass for parameter management
- CDK bootstrap verification
- Table status validation with retry logic
- Config template auto-copy functionality
- Enhanced error output capturing both stdout and stderr
- **Table import support** - Import existing tables from CDK context or AWS
- **Schema validation** - Validate existing tables match expected schema
- **CfnDeletionPolicy.RETAIN** - Prevent accidental data loss during stack updates
- **Safe dictionary access** - Replaced all square bracket access with .get() method
- **Region validation** - Validates and sanitizes region input (us-east-1, us-east-2, us-west-2)
- **Explicit parameter passing** - Region flows through arguments, not environment variables
- **Python3 compatibility** - Fixed cdk.json and deploy.py to use python3
- **Repeatable deployment** - Removed redeploy prompt for seamless updates
- **Production tested** - Successfully deployed and redeployed in production environment

## Phase 2: CodeBuild Stack (IN PROGRESS)

### Phase 2 Status

#### Open Tasks

- Create stacks/codebuild_stack.py with CodeBuildStack class
- Implement S3 bucket import/create logic with RETAIN policy
- Implement CodeBuild projects for lambda-layer and lambda-functions
- Add IAM roles and policies for CodeBuild projects
- Update app.py to instantiate CodeBuildStack
- Add deploy_codebuild_stack function in deploy.py
- Add validation functions for S3 bucket and CodeBuild projects
- Update main() to handle CodeBuild stack deployment
- Test CodeBuild stack deployment

#### Completed Tasks

- Extended DeploymentParams dataclass with CodeBuild parameters and defaults
- Modified collect_deployment_params to handle CodeBuild inputs following priority flow
- Updated Config class to handle S3 ArtifactsBucket field
- Implemented cdk.json context persistence for CodeBuild parameters
- Fixed all dictionary access to use .get() method

### Phase 2 Lessons Learned Violations & Corrections

During initial Phase 2 implementation, the following lessons from Phase 1 were violated and then corrected:

**Violated Lesson #1 - No Over-Engineering**

- Initially tried to create separate CodeBuildParams dataclass
- Corrected: Extended existing DeploymentParams dataclass

**Violated Lesson #15 - User Input Collection**

- Initially tried to create separate collect_codebuild_params function
- Corrected: Extended existing collect_deployment_params function

**Violated Lesson #3 - Python Style Compliance**

- Added unnecessary comments in dataclass
- Corrected: Removed comments per project style guide

**Violated Lesson #23 - Safe Dictionary Access**

- Initial implementation would have used square bracket access
- Corrected: All dictionary access uses .get() method

### Objectives

Create build infrastructure for Lambda functions with S3 bucket for artifacts and CodeBuild projects for automated builds from GitHub. The stack will import existing resources where found and apply appropriate retention policies.

### CodeBuild Stack Design

#### Parameter Collection Flow

The deployment will follow a strict priority order for parameter values:

1. **Defaults** - Hardcoded fallback values in the code
2. **cdk.json** - Persistent context values from previous runs
3. **config.yml** - System operational configuration
4. **User prompts** - Override all other sources

After validation, user inputs will be written back to cdk.json for persistence across deployments.

#### Required Parameters

- **S3 Bucket Name** - For Lambda artifacts storage
- **GitHub Owner** - Repository owner/organization
- **GitHub Repository** - Repository name
- **GitHub Branch** - Branch to build from
- **Region** - AWS region (flows from main deployment)

#### Core Components

**S3 Bucket for Lambda Artifacts**

The stack will manage an S3 bucket to store Lambda deployment packages and layer artifacts. If the bucket exists, it will be imported. The bucket will have RemovalPolicy.RETAIN to prevent data loss. The buildspec files expect an environment variable S3_BUCKET which CodeBuild will populate.

**Lambda Layer CodeBuild Project**

A CodeBuild project named "eidolon-lambda-layer-build" will build Python dependencies into a Lambda layer using buildspec/lambda-layer.yml. The project will use Python 3.12 runtime and output lambda-layer.zip to the S3 bucket. If the project exists, it will be imported. RemovalPolicy.DESTROY applies since projects can be recreated.

**Lambda Functions CodeBuild Project**

A CodeBuild project named "eidolon-lambda-functions-build" will package individual Lambda functions using buildspec/lambda-functions.yml. It generates a bloom filter for character names and packages each Lambda function with its dependencies. The project outputs multiple zip files to the S3 bucket.

**IAM Roles and Policies**

Each CodeBuild project will have its own IAM role with permissions to:

- Write to the S3 artifacts bucket
- Create CloudWatch Logs
- Read from the public GitHub repository

#### Resource Import Pattern

The stack will check for existing resources using boto3 before creation:

- S3: head_bucket to check existence
- CodeBuild: batch_get_projects to check for existing projects
- IAM roles: Will be created per project, not imported

#### Configuration Updates

After successful deployment:

- **cdk.json** - Store github_owner, github_repo, github_branch, s3_bucket
- **config.yml** - Update S3 section with ArtifactsBucket (or appropriate key per the plan)
- **.cdk-state.json** - Store project ARNs, role ARNs, bucket ARN

#### Validation

Post-deployment checks will verify:

- S3 bucket is accessible
- CodeBuild projects exist with correct source configuration
- IAM roles have required permissions
- Environment variables are properly configured

### Lessons Learned

1. **No Over-Engineering**: Avoided unnecessary abstractions (no factories, no complex class hierarchies)
2. **Script vs Library**: This is a one-time run script, not a library - no need for **init** imports or complex module structures
3. **Python Style Compliance**: No private methods (no underscore prefixes), functions over methods when not tightly coupled to classes
4. **Clear Separation**: Config.yml for operational data only, .cdk-state.json for infrastructure details
5. **Simple Naming**: Fixed table names without prefixes, single IAM policy with clear name
6. **Professional Output**: Use [OK], [MISSING] instead of emoji characters
7. **Proper Module Naming**: Use specific names (dynamodb_tables.py) instead of generic (constants.py)
8. **Path Handling**: Use pathlib.Path consistently for POSIX-style cross-platform compatibility
9. **Caching**: Use @functools.cache decorator for AWS account ID to avoid redundant API calls
10. **Flexible Validation**: Design validation functions to handle lists/multiple resources for easy expansion
11. **CDK v2 GSI Handling**: CDK automatically manages attribute definitions for GSI keys - no manual definition needed
12. **Import Organization**: Run scripts from their directory rather than manipulating sys.path
13. **Main Function Clarity**: Main should only orchestrate, not implement - separate functions for verify, input, deploy, validate, and update
14. **Parameter Management**: Use dataclasses for deployment parameters (region, account_id)
15. **User Input Collection**: Dedicated function for collecting user input with defaults
16. **Race Condition Handling**: Check table status, not just existence - retry if CREATING
17. **No Dynamic Imports**: All imports at module level for clarity
18. **Config Templates**: Auto-copy config.template.yml to config.yml if missing
19. **CDK Subprocess Reality**: CDK requires subprocess invocation - accepted as necessary
20. **Table Import Support**: Check CDK context and AWS for existing tables before creating new ones
21. **Schema Validation**: Validate partition and sort keys match expected configuration
22. **Data Retention**: Always use RemovalPolicy.RETAIN and CfnDeletionPolicy.RETAIN for DynamoDB
23. **Safe Dictionary Access**: Use .get() method instead of square brackets to prevent KeyError
24. **Nested Dictionary Access**: Chain .get() calls with default empty dict for intermediate levels
25. **Explicit Parameter Passing**: Pass region as explicit argument through the call chain (deploy.py → app.py → Stack → boto3)
26. **No Environment Manipulation**: Never rely on CDK setting environment variables - use argparse for explicit parameters
27. **CDK Tokens vs Strings**: self.region in CDK Stack returns a token, not a string - pass actual values as parameters
28. **Python3 Compatibility**: Always use python3 in scripts and cdk.json, not python
29. **Repeatable Deployments**: Design for frequent re-runs without user prompts for CI/CD compatibility
30. **No Sensitive Data in Docs**: Never include account numbers or other sensitive data in documentation

## Current System Issues

1. **Monolithic Structure**: Single 1800+ line class handling all deployment logic
2. **Poor Separation of Concerns**: Business logic, infrastructure, and UI mixed together
3. **Code Duplication**: AWS client creation and configuration management scattered
4. **Complex Dependencies**: Circular dependencies and tightly coupled components
5. **Inconsistent Error Handling**: Silent failures and no clear recovery mechanism

## New Architecture

### Design Principles

- **Simplicity First**: No clever abstractions or over-engineering
- **Sequential Execution**: Deploy one resource at a time, no parallelism
- **Clear Separation**: Infrastructure details in CDK state, operational config in config.yml
- **Module Size Limit**: Each module under 300 lines per CLAUDE.md standards
- **No Legacy Support**: Complete replacement, no migration paths needed

### Stack Organization

```
1. DynamoDB Stack     → Tables and access policies
2. CodeBuild Stack    → Build infrastructure and artifacts bucket
3. S3 Stack          → Scripts bucket
4. CloudWatch Stack  → Logging and metrics
5. [Build Phase]     → Execute Lambda builds
6. Player Stack      → Cognito and auth Lambdas
7. Character Stack   → Character management Lambdas
8. Story Stack       → Story processing, SQS, EventBridge
9. Client Stack      → Portal, CloudFront, API Gateway
10. [Portal Build]   → Final frontend deployment
```

## Detailed Stack Resources

### 1. DynamoDB Stack

**Resources:**

- 14 tables: players, characters, rooms, exits, items, prototypes, archetypes, motd, story, segments, active_segments, opponents, story_history, segment_history
- Single IAM managed policy for DynamoDB read/write access
- Global Secondary Indexes on characters, active_segments tables

**Features:**

- Import existing tables from CDK context or AWS
- Schema validation before import
- Automatic creation if tables don't exist
- Data retention with RemovalPolicy.RETAIN and CfnDeletionPolicy.RETAIN

**Config.yml Output:**

- Table name mappings only

### 2. CodeBuild Stack

**Resources:**

- Lambda artifacts S3 bucket
- Lambda Layer CodeBuild project
- Lambda Functions CodeBuild project
- IAM role and policies

**Config.yml Output:**

- None (infrastructure only)

### 3. S3 Stack

**Resources:**

- Scripts S3 bucket for Lua scripts

**Config.yml Output:**

- S3.ScriptsBucket

### 4. CloudWatch Stack

**Resources:**

- Log groups for Lambda and application
- Metrics namespace
- IAM managed policies for CloudWatch access

**Config.yml Output:**

- CloudWatch.LogGroup
- CloudWatch.MetricsNamespace

### 5. Build Execution Phase

**Actions:**

- Execute Lambda Layer build
- Execute Lambda Functions build
- Validate artifacts in S3

### 6. Player Stack

**Resources:**

- Cognito User Pool
- Cognito User Pool Client
- IAM role with attached policies
- Lambda functions:
  - `cognito-player-new` (PostConfirmation trigger)
  - `cognito-player-delete` (PreUserDeletion trigger)
- Cognito triggers configuration

**Config.yml Output:**

- Cognito.UserPoolId
- Cognito.ClientId

### 7. Character Stack

**Resources:**

- IAM role with attached policies
- Lambda functions:
  - `api-archetype-list`
  - `api-character-add`
  - `api-character-delete`
  - `api-character-get`
  - `api-character-list`

**Config.yml Output:**

- None

### 8. Story Stack

**Resources:**

- SSM Parameter for story configuration
- SQS Queues:
  - processing-queue
  - advancement-queue
- SQS access policy
- EventBridge rule for polling
- IAM role with attached policies
- Lambda functions:
  - `api-segment-decision`
  - `api-segment-history`
  - `api-segment-outcome`
  - `api-segment-rest`
  - `api-segment-status`
  - `api-story-abandon`
  - `api-story-start`
  - `ops-segment-poller`
  - `ops-segment-processor`
  - `ops-story-advance`

**Config.yml Output:**

- SSM.StoryParameter

### 9. Client Stack

**Resources:**

- Portal S3 bucket
- CloudFront distribution
- Route53 alias (if custom domain)
- ACM certificate (if custom domain)
- API Gateway with Lambda integrations
- API Gateway custom domain (if configured)
- Portal CodeBuild project

**Config.yml Output:**

- S3.PortalBucket
- CloudFront.DistributionId
- CloudFront.DomainName
- API.GatewayUrl

### 10. Portal Build Execution

**Actions:**

- Execute portal build
- CloudFront invalidation (automatic)
- Final validation

## Data Management

### Config.yml (Operational Information Only)

```yaml
# Only contains information needed for running the system
DynamoDB:
  Tables:
    Players: actual-table-name
    Characters: actual-table-name

S3:
  ScriptsBucket: bucket-name
  PortalBucket: bucket-name

CloudWatch:
  LogGroup: /aws/eidolon
  MetricsNamespace: Eidolon

Cognito:
  UserPoolId: us-east-1_xxxxx
  ClientId: xxxxxxxxxxxxx

CloudFront:
  DistributionId: EXXXXXXXXX
  DomainName: dxxxxx.cloudfront.net

API:
  GatewayUrl: https://xxxxx.execute-api.region.amazonaws.com/prod

SSM:
  StoryParameter: /eidolon/story/config

Game:
  Name: eidolon-engine
  ContactEmail: admin@example.com
```

### CDK State File (Infrastructure Details)

```json
{
  "stacks": {
    "stackName": {
      "deployed": true,
      "timestamp": "ISO-8601",
      "resources": {}
    }
  },
  "infrastructure": {
    "roles": {},
    "policies": {},
    "lambdaArns": {},
    "queueUrls": {},
    "eventBridgeRules": {},
    "codeBuildProjects": {}
  },
  "artifacts": {
    "bucketName": "",
    "builds": {}
  }
}
```

## Remaining Issues to Address

### Resolved Issues

1. ~~CDK Bootstrap Check~~ ✓ Implemented
2. ~~Error Output~~ ✓ Capturing both stdout and stderr
3. ~~State File Safety~~ - Not implementing
4. ~~Table Status Validation~~ ✓ Retry logic implemented
5. ~~Region Validation~~ ✓ Validates and sanitizes region input (us-east-1, us-east-2, us-west-2)
6. ~~Config Path Validation~~ ✓ Auto-creates from template

### Additional Considerations

- **Subprocess Dependency**: CDK requires subprocess invocation - Accepted as necessary
- **Hardcoded Table List**: Table names duplicated between dynamodb_tables.py and validate_tables()
- **Limited Retry Logic**: Only one 10-second retry for CREATING tables

## Implementation Phases

### Phase 1: Foundation Setup

**Objective:** Create core infrastructure and data models

**Deliverables:**

- `deployment/core/config.py` - Configuration dataclass (operational data only)
- `deployment/core/state.py` - CDK state tracking dataclass
- `deployment/core/aws_client.py` - Centralized boto3 client factory
- `deployment/core/validators.py` - Resource validation functions
- `deployment/core/constants.py` - Stack names and conventions

**Special Instructions:**

- Config class should only handle operational data
- State class tracks all infrastructure details
- AWS client factory should handle profile and region consistently
- Validators use boto3 for post-deployment verification

### Phase 2: Stack Implementation

**Objective:** Create CDK stack definitions

**Directory Structure:**

```
deployment/stacks/
├── base_stack.py         # Common stack functionality
├── dynamodb_stack.py     # Tables and policies
├── codebuild_stack.py    # Build projects
├── s3_stack.py          # Scripts bucket
├── cloudwatch_stack.py   # Logging
├── player_stack.py       # Cognito and triggers
├── character_stack.py    # Character Lambdas
├── story_stack.py        # Story processing
└── client_stack.py       # Frontend and API
```

**Special Instructions:**

- Each stack must be under 300 lines
- Use CDK L2 constructs where available
- Player stack must configure Cognito triggers
- Story stack includes EventBridge and SQS
- Client stack includes API Gateway

### Phase 3: Orchestration Layer

**Objective:** Implement sequential deployment logic

**Deliverables:**

- `deployment/orchestrator.py` - Main deployment orchestration
- `deployment/build_executor.py` - CodeBuild execution
- `deployment/stack_deployer.py` - CDK deployment wrapper

**Special Instructions:**

- Strictly sequential execution
- Save CDK state after each successful operation
- Update config.yml only with operational data
- Stop immediately on any failure
- Support resume from last successful step

### Phase 4: CLI and Entry Point

**Objective:** Create user interface

**Deliverables:**

- `deployment/deploy.py` - Main entry point
- `deployment/cli/prompts.py` - User interaction (isolated)

**Special Instructions:**

- Load order: defaults → CDK state → config.yml → user prompts
- Minimal user decisions required
- Clear progress indication
- Simple error messages with recovery instructions

## Validation Strategy

### Post-Stack Validation (boto3)

After each stack deployment:

1. Verify resources exist
2. Check resource configuration
3. Validate IAM policies attached
4. Test basic connectivity

### Build Artifact Validation

After build execution:

1. Verify lambda-layer.zip exists
2. Verify all 17 Lambda function zips exist (2 Player, 5 Character, 10 Story)
3. Check file sizes are reasonable

### Final System Validation

After complete deployment:

1. Test Cognito authentication
2. Verify API Gateway endpoints
3. Check CloudFront distribution
4. Validate portal accessibility

## Implementation Guidelines

### Code Standards

- Maximum 300 lines per module
- Maximum 50 lines per function
- No complex abstractions
- Clear variable names
- Explicit error handling

### Error Handling

- Fail fast on errors
- Clear error messages
- State preserved for resume
- No silent failures

### User Experience

- Appropriate prompts for required configuration
- Clear progress indication
- Simple success/failure messages
- Resume capability on failure

## Success Criteria

1. **Simplicity**: Code is straightforward and obvious
2. **Reliability**: Deployment either succeeds completely or fails clearly
3. **Maintainability**: Each module has single responsibility
4. **Resumability**: Can continue from failure point
5. **Validation**: Each step verified before proceeding

## Special Considerations

### No Testing Framework

- This is new development, not migration
- Limited input variability
- Code will either work or fail clearly
- No unit tests required

### Sequential Execution

- No parallel operations
- One resource at a time
- Clear, predictable order
- Easy to debug

### Configuration Management

- CDK state for infrastructure
- Config.yml for operational data only
- Clear separation of concerns

### In-Place Updates

- CDK handles create vs update
- Support for incremental changes
- No need for rollback logic

## Notes

- This is a complete replacement, not a migration
- No backwards compatibility needed
- Focus on simplicity over cleverness
- User should understand what's happening
- Each step should be obvious and verifiable
