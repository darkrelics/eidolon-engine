# Deployment System Rework Plan

## Overview

Complete replacement of the existing monolithic deployment system with a clean, modular architecture focused on simplicity and maintainability.

## Status: Phase 5 COMPLETE - Lambda Stack Deployed

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

## Phase 2: CodeBuild Stack [COMPLETE]

## Phase 3: S3 Stack [COMPLETE]

## Phase 4: CloudWatch Stack [COMPLETE]

## Phase 5: Lambda Stack [COMPLETE]

### Phase 5 Summary

Successfully implemented Lambda infrastructure for all non-Cognito-triggered Lambda functions with the following architecture:
- Lambda layer deployed from CodeBuild artifacts (lambda-layer.zip)
- Shared IAM execution role with DynamoDB and CloudWatch Logs policies
- 16 Lambda functions deployed (all except cognito-player-delete)
- CORS configuration using client FQDN (client_host.domain)
- Environment variables for DynamoDB tables and CORS settings
- Handler configurations fixed to use underscores (matching Python module names)

### Phase 5 Status

#### Completed Tasks

- Created LambdaStack with layer deployment from S3 artifacts
- Implemented shared IAM execution role with proper permissions
- Created lambda_functions.py deployment module (renamed from lambda_deploy.py)
- Created app_lambda.py for stack isolation
- Deployed 16 Lambda functions in alphabetical order
- Fixed handler configurations (api_character_list.lambda_handler not api-character-list.lambda_handler)
- Added CORS configuration with client_host and client_domain parameters
- Integrated DynamoDB table names from previous stack outputs
- Fixed module naming conflict (lambda is a Python keyword)
- Ensured consistent parameter passing across modules
- Validated Lambda artifacts exist in S3 before deployment

### Phase 4 Summary

Successfully implemented CloudWatch infrastructure for logging and monitoring with the following architecture:
- Single log group `/eidolon/server` with 1-year retention and RETAIN policy
- Metrics namespace `eidolon/metrics` for custom application metrics
- Managed policy `eidolon-cloudwatch-policy` with permissions for log streams and metrics
- Import capability for existing log groups
- Simplified from original CloudFormation (removed Lambda/CodeBuild specific groups)

### Phase 4 Status

#### Completed Tasks

- Created CloudWatchStack with single server log group
- Implemented managed policy for CloudWatch access (logs and metrics)
- Created cloudwatch.py deployment module with validation
- Created app_cloudwatch.py for stack isolation
- Updated DeploymentParams to use existing region parameter
- Extended Config class with CloudWatch settings and defaults
- Updated deploy.py to include CloudWatch stack deployment
- Added CloudWatch to deployment summary and final status
- Fixed region parameter handling to match established patterns
- Fixed stack ID naming to match conventions
- Fixed IAM policy validation by removing import logic
- Aligned with other stacks' managed policy patterns

### Phase 4 Lessons Learned Violations & Corrections

During Phase 4 implementation, the following lessons were violated:

**Violated Lesson #43 - Pattern Reuse**

- Initially used different parameter names (`region` vs `region_name`) than established stacks
- Initially used different stack ID pattern (`eidolon-cloudwatch` vs `cloudwatch`)
- Initially tried to import existing IAM policies while other stacks always create them
- Corrected: Updated to match exact patterns from existing stacks

**Violated Lesson #27 - CDK Tokens vs Strings**

- Attempted to override CDK Stack's read-only `region` property
- Corrected: Used `region_name` parameter stored before super().__init__()

**Violated Lesson #31 - Managed Policies Only**

- Attempted to import existing managed policies using `from_managed_policy_arn()`
- This created references that CDK doesn't actually manage, causing validation failures
- Corrected: Always create managed policy definitions and let CDK handle create/update

**Root Cause Analysis**

The CloudWatch stack implementation failed to properly analyze existing patterns before implementation:
1. Did not check how other stacks handled region parameters
2. Did not verify stack ID naming conventions
3. Did not examine app file structure patterns thoroughly
4. Added unnecessary complexity with policy import logic not used elsewhere

### Phase 3 Summary

Successfully implemented S3 infrastructure for Lua scripts with the following architecture:
- S3 bucket with import capability and RETAIN policy
- Managed policy `eidolon-scripts-s3-policy` for read/write access
- Automatic upload of scripts from `/scripts_lua/*` to `<bucket>/scripts/*`
- Reused patterns from CodeBuild stack for consistency
- Refactored to separate app files per stack for clean isolation

### Phase 3 Status

#### Completed Tasks

- Updated DeploymentParams with scripts_bucket field
- Extended collect_deployment_params for scripts bucket input
- Created S3Stack with bucket import/create logic
- Implemented managed policy for S3 access (no role needed)
- Created s3.py module with deployment and validation functions
- Added automatic script upload using boto3
- Updated app.py for conditional S3Stack creation
- Updated main() to include S3 deployment
- Extended Config class to persist scripts bucket
- Refactored to separate app files (app_dynamodb.py, app_codebuild.py, app_s3.py) for stack isolation
- Removed deprecated app.py per no legacy code policy

### Phase 2 Summary (Including Phase 5 Integration)

Successfully implemented CodeBuild infrastructure for Lambda builds with the following architecture:
- Single shared IAM role with custom managed policies for least privilege
- S3 bucket with import capability and RETAIN policy for artifacts
- Two CodeBuild projects for lambda-layer and lambda-functions builds
- Modular deployment code split into focused modules under 300 lines each
- Comprehensive validation for all resources
- Unified user input flow with single deployment confirmation
- **Phase 5 Integration**: Automatic build execution after stack deployment
- Sequential build execution (layer then functions)
- Real-time build monitoring with phase updates
- Build artifact validation for all 17 Lambda functions

**Phase 2 & 5 Completed**: Successfully deployed and tested with integrated build execution

### Phase 2 Status

#### Completed Tasks

- Extended DeploymentParams dataclass with CodeBuild parameters and defaults
- Modified collect_deployment_params to handle CodeBuild inputs following priority flow
- Updated Config class to handle S3 ArtifactsBucket field
- Implemented cdk.json context persistence for CodeBuild parameters
- Fixed all dictionary access to use .get() method
- Created stacks/codebuild_stack.py with CodeBuildStack class
- Implemented S3 bucket import/create logic with RETAIN policy
- Implemented CodeBuild projects for lambda-layer and lambda-functions
- Created shared IAM role with custom managed policies for CloudWatch and S3 access
- Updated app.py to instantiate CodeBuildStack
- Added deploy_codebuild_stack function (now in codebuild.py)
- Added validation functions for S3 bucket and CodeBuild projects
- Updated main() to handle CodeBuild stack deployment
- Refactored deployment code into modular structure (deploy.py, utilities.py, dynamodb.py, codebuild.py)
- Unified user input collection with single deployment confirmation
- Removed per-stack deployment prompts for uninterrupted execution
- Tested CodeBuild stack deployment successfully

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

**Violated Lesson #31 - Managed Policies Only**

- Initially created two separate IAM roles with AWS managed policies
- Corrected: Created single shared role with custom managed policies following lessons 32-35

**Violated Lesson #2 - Script vs Library**

- deploy.py grew to over 700 lines with mixed responsibilities
- Corrected: Refactored into 4 focused modules under 300 lines each

**Violated User Experience Principle**

- Initially had deployment confirmations scattered throughout execution
- Corrected: Consolidated all user input first, then single confirmation before execution

**Violated Stack Isolation Principle**

- Initially had single app.py creating all stacks, causing output contamination
- Corrected: Separated into app_dynamodb.py, app_codebuild.py, app_s3.py for clean isolation

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

A CodeBuild project named "eidolon-lambda-layer" will build Python dependencies into a Lambda layer using buildspec/lambda-layer.yml. The project will use Python 3.12 runtime and output lambda-layer.zip to the S3 bucket. If the project exists, it will be imported. RemovalPolicy.DESTROY applies since projects can be recreated.

**Lambda Functions CodeBuild Project**

A CodeBuild project named "eidolon-lambda-functions" will package individual Lambda functions using buildspec/lambda-functions.yml. It generates a bloom filter for character names and packages each Lambda function with its dependencies. The project outputs multiple zip files to the S3 bucket.

**IAM Roles and Policies**

A single shared IAM role (`eidolon-lambda-codebuild-role`) will be used by both CodeBuild projects with two custom managed policies:

- `eidolon-codebuild-logs-policy`: CloudWatch Logs permissions for `/aws/codebuild/*`
- `eidolon-codebuild-s3-policy`: Read/write access to artifacts bucket at `/*`

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
31. **Managed Policies Only**: All IAM policies must be managed policies (AWS managed or custom managed) - no inline policies
32. **Shared IAM Roles**: When multiple resources need similar permissions, use a single shared role
33. **Custom Managed Policies**: Prefer custom managed policies with least privilege over AWS managed policies
34. **Resource Naming**: Use consistent naming pattern (eidolon-resource-type-purpose)
35. **Policy Resource Scoping**: Be specific with resource ARNs while maintaining flexibility for growth
36. **Module Size Enforcement**: When a module exceeds 300 lines, immediately refactor into focused sub-modules
37. **Import Organization**: Group imports by category (standard library, external packages, local modules)
38. **Function Parameter Types**: Use dataclasses for complex parameter sets, primitives for simple functions
39. **Conditional Stack Creation**: Use conditional logic in app.py to only create stacks when required parameters exist
40. **User Input Flow**: Collect all user input upfront, confirm once, then execute without interruption
41. **Deployment Confirmation**: Show comprehensive summary of all resources before asking for confirmation
42. **Stack Execution Order**: Execute infrastructure stacks before build stacks to ensure dependencies exist
43. **Pattern Reuse**: Copy successful patterns from previous stacks to maintain consistency
44. **Script Upload Integration**: Include data upload as part of stack deployment for complete provisioning
45. **Stack Isolation**: Each CDK stack should have its own app file to prevent cross-contamination of outputs
46. **No Legacy Code**: Remove deprecated files immediately - no backwards compatibility needed per project policy
47. **CloudWatch Simplification**: Single log group for server, not separate groups for Lambda/CodeBuild
48. **Default Values**: Provide sensible defaults for CloudWatch settings in Config class
49. **Pattern Analysis Before Implementation**: Always examine existing stack implementations for patterns before creating new stacks
50. **Stack ID Convention**: Use lowercase stack type names as stack IDs (e.g., "cloudwatch" not "eidolon-cloudwatch")
51. **Parameter Naming Consistency**: Use exact same parameter names across all stacks (e.g., region_name not region)
52. **App File Structure**: Follow established app file patterns including parse_known_args() and description parameter
53. **Phase Integration**: Build execution phases can be integrated into deployment phases for better cohesion
54. **Sequential Dependencies**: Enforce build order when artifacts depend on each other (layer before functions)
55. **Build Monitoring**: Provide real-time phase updates during long-running operations
56. **Error Context**: Include relevant logs (last 50 lines) when builds fail for immediate debugging
57. **Artifact Validation**: Always validate build outputs exist and have reasonable sizes
58. **Consistent Messaging**: Integrated operations should maintain parent phase context in output
59. **CDK Resource Management**: Always create resource definitions; let CDK handle create vs update logic
60. **Avoid Import Complexity**: Don't import existing AWS resources unless absolutely necessary - CDK handles updates
61. **Validation Compatibility**: Imported resources won't validate properly since CDK doesn't manage them
62. **Artifact Path Accuracy**: Verify exact S3 paths for artifacts (e.g., lambda-layer/lambda-layer.zip)
63. **Function Name Precision**: Use exact Lambda function names in validation (ops-segment-process not ops-segment-processor)
64. **Lambda Infrastructure First**: Deploy Lambda layer and functions before service integrations (Cognito, SQS, EventBridge)
65. **Trigger Separation**: Cognito-triggered Lambdas have different lifecycle - handle separately from API/operational Lambdas
66. **Shared IAM Role**: Single Lambda execution role with attached policies is simpler than per-function roles
67. **Policy Attachment Pattern**: Create base policies with stack, attach additional policies in dependent stacks
68. **Environment Variable Sources**: Lambda environment variables derived from previous stack outputs, not config.yml
69. **Dynamic CloudWatch Logs**: Lambda functions create their own log groups dynamically - no pre-creation needed
70. **Wide Initial Permissions**: Start with broad Lambda role permissions, refine pre-GA
71. **No Lambda Versioning**: Aliases and versions add complexity without value for this use case
72. **Custom Domain Required**: System requires custom domain for CORS - collect upfront to avoid circular dependencies
73. **Lambda Module Naming**: Avoid Python keywords in module names (e.g., lambda.py → lambda_functions.py)
74. **Handler Path Consistency**: Lambda handlers must match Python module names (underscores not hyphens)
75. **CORS FQDN Assembly**: Assemble client FQDN at deployment module level, pass complete value to stacks
76. **Parameter Object Pattern**: Pass complete params object to deployment modules for flexibility
77. **CDK Auto-Update**: CDK automatically updates existing resources - no manual update logic needed
78. **Player Stack Separation**: Cognito-triggered Lambdas require different lifecycle management
79. **Comment Out Not Delete**: Comment out incomplete implementations for future reference
80. **Default Values Matter**: Provide sensible defaults (portal, darkrelics.net) to streamline deployment

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
1. DynamoDB Stack     → Tables and access policies [COMPLETE]
2. CodeBuild Stack    → Build infrastructure, artifacts bucket, and Lambda builds [COMPLETE]
3. S3 Stack          → Scripts bucket [COMPLETE]
4. CloudWatch Stack  → Logging and metrics [COMPLETE]
5. Lambda Stack      → Lambda layer, IAM role/policies, 16 Lambda functions (excluding cognito-player-delete)
6. Player Stack      → Cognito User Pool, triggers, cognito-player-delete Lambda
7. Story Stack       → SSM parameter, SQS, EventBridge, additional Lambda permissions
8. Client Stack      → Portal, CloudFront, API Gateway
9. [Portal Build]    → Final frontend deployment
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

### 3. S3 Stack (COMPLETE)

**Resources:**

- Scripts S3 bucket for Lua scripts
- IAM managed policy for S3 read/write access
- Automatic script upload from /scripts_lua/* to bucket/scripts/*

**Config.yml Output:**

- S3.ScriptsBucket

### 4. CloudWatch Stack [COMPLETE]

**Resources:**

- Single log group `/eidolon/server` with 1-year retention
- Metrics namespace `eidolon/metrics`
- IAM managed policy `eidolon-cloudwatch-policy`

**Config.yml Output:**

- CloudWatch.LogGroup: /eidolon/server
- CloudWatch.MetricsNamespace: eidolon/metrics

### 5. Lambda Stack

**Resources:**

- Lambda Layer deployment from built artifact
- Shared IAM role for all Lambda functions
- IAM managed policies:
  - DynamoDB read/write access (attach existing policy from DynamoDB stack)
  - CloudWatch Logs write access (create/write to dynamic log groups)
- 16 Lambda functions (all except cognito-player-delete):
  - Player: `cognito-player-new`
  - Character: `api-archetype-list`, `api-character-add`, `api-character-delete`, `api-character-get`, `api-character-list`
  - Story: `api-segment-decision`, `api-segment-history`, `api-segment-outcome`, `api-segment-rest`, `api-segment-status`, `api-story-abandon`, `api-story-start`, `ops-segment-poller`, `ops-segment-process`, `ops-story-advance`

**Lambda Configuration:**
- Runtime: Python 3.12
- Memory: 128MB (all functions)
- Timeout: 30 seconds (all functions)
- Layer association for all functions
- Environment variables (from environment.py patterns):
  - DynamoDB table names from DynamoDB stack outputs
  - APPLICATION_NAME, LOG_LEVEL
  - ALLOWED_ORIGINS (from custom domain input collected upfront)
  - CORS settings (credentials, headers, methods, max age)
  - Function-specific configs (SEGMENT_BATCH_SIZE, etc.)

**Required User Input:**
- Custom domain name (for CORS configuration)

**Config.yml Output:**
- None (Lambda ARNs used directly by dependent stacks)

### 6. Player Stack

**Resources:**

- Cognito User Pool
- Cognito User Pool Client
- ~~Lambda function: `cognito-player-delete`~~ (No appropriate Cognito trigger - needs different approach)
- ~~IAM execution role for cognito-player-delete~~ (Not needed without the Lambda)
- Cognito triggers configuration:
  - PostConfirmation → cognito-player-new (from Lambda Stack)
- Lambda invoke permissions for Cognito service

**Note:** cognito-player-delete cannot be deployed as originally planned. A different process needs to be devised for player deletion.

**Config.yml Output:**

- Cognito.UserPoolId
- Cognito.ClientId

### 7. Story Stack

**Resources:**

- SSM Parameter for story configuration
- SQS Queues:
  - processing-queue
  - advancement-queue
- EventBridge rule for polling schedule
- IAM managed policy with:
  - SSM read access for story parameters
  - SQS send/receive/delete permissions
  - EventBridge permissions
- Attach policy to Lambda role from Lambda Stack
- Lambda permissions:
  - EventBridge invoke permission for ops-segment-poller
  - Update Lambda environment variables with SQS queue URLs

**Config.yml Output:**

- SSM.StoryParameter

### 8. Client Stack

**Resources:**

- Portal S3 bucket
- CloudFront distribution
- Route53 alias (required - custom domain)
- ACM certificate (required - custom domain)
- API Gateway with Lambda integrations (using Lambda ARNs from Lambda Stack)
- API Gateway custom domain (required)
- Portal CodeBuild project

**Required User Input:**
- Custom domain name (same as Lambda Stack)
- Route53 Hosted Zone ID

**Config.yml Output:**

- S3.PortalBucket
- CloudFront.DistributionId
- CloudFront.DomainName
- API.GatewayUrl

### 9. Portal Build Execution

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
