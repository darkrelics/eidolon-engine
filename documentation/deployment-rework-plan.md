# Deployment System Rework Plan

## Overview

Complete replacement of the existing monolithic deployment system with a clean, modular architecture focused on simplicity and maintainability.

## Status: 7 of 9 Phases Complete - All Core Infrastructure Operational

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

## CDK Context Standardization [COMPLETE]

### Implementation Summary

Successfully standardized all CDK app files to use context pattern instead of argparse:
- **Removed argparse**: Eliminated boilerplate argument parsing from all app files
- **Unified pattern**: All stacks now use `app.node.try_get_context()` for parameters
- **Simplified deployment modules**: All use `run_cdk_deploy()` with context arguments
- **Complex data support**: DynamoDB tables passed as JSON through context

### Changes Applied

#### App Files Updated
- app_dynamodb.py - Removed argparse, uses context
- app_codebuild.py - Removed argparse, uses context  
- app_s3.py - Removed argparse, uses context
- app_cloudwatch.py - Removed argparse, uses context
- app_lambda.py - Removed argparse, uses context with JSON parsing
- app_player.py - Already used context (no change)
- app_story.py - Already used context (no change)

#### Deployment Modules Updated
- All modules now pass context using `-c` flags
- Proper format: `["-c", "key=value"]` as separate list items
- Complex data (DynamoDB tables) serialized as JSON

## Deployment Mode System [COMPLETE]

### Implementation Summary

Successfully implemented deployment mode system to support three distinct deployment configurations:
- **MUD Mode**: Traditional Multi-User Dungeon without story features
- **Incremental Mode**: Story-driven gameplay without S3/CloudWatch
- **Hybrid Mode**: Full feature set (default)

### Implementation Details

#### Created `deploy_mode.py` Module
- Deployment mode validation and normalization
- Stack order determination based on mode
- Portal buildspec selection (portal.yml for MUD, incremental.yml for others)
- Human-readable stack descriptions for display

#### Updated Core Components
- **Config class**: Added deployment_mode field with persistence to config.yml
- **DeploymentParams**: Added deployment_mode field
- **deploy.py**: 
  - Dynamic stack deployment based on mode
  - Mode-aware user input collection
  - Mode-specific deployment summaries

#### Deployment Flow Changes
- Mode selection integrated into parameter collection
- Conditional S3 scripts bucket collection (skipped for Incremental mode)
- Dynamic stack ordering replaces hardcoded deployment sequence
- Stack deployment map allows easy addition of future stacks

## Phase 7: Story Stack [COMPLETE]

### Phase 7 Summary

Successfully deployed Story Stack with complete EventBridge and SQS integration:
- Fixed CDK context passing for Lambda ARNs
- Implemented proper Lambda import with execution roles for SQS permissions
- Created EventBridge rule with Lambda targets
- Configured SQS triggers for segment processing
- All resources deploy and validate successfully

### Phase 7 Status

#### Completed Tasks

- Created StoryStack with SSM parameter, SQS queues, and EventBridge rule
- Implemented IAM managed policy for story operations
- Fixed context passing using separate `-c` flags for each parameter
- Used `Function.from_function_attributes()` for proper Lambda imports
- Created EventBridge rule (starts disabled) for polling
- Configured SQS triggers for ops-segment-process and ops-story-advance
- Updated Lambda environment variables with queue URLs
- Full production deployment successful

#### Validated Resources

- SSM Parameter: `/eidolon/story/config`
- SQS Queue: `eidolon-processing-queue`
- SQS Queue: `eidolon-advancement-queue`
- EventBridge Rule: `eidolon-story-poller` (DISABLED)
- IAM Policy: `eidolon-story-policy`
- Lambda environment variables updated

## Phase 2: CodeBuild Stack [COMPLETE]

## Phase 3: S3 Stack [COMPLETE]

## Phase 4: CloudWatch Stack [COMPLETE]

## Phase 5: Lambda Stack [COMPLETE]

## Phase 6: Player Stack [COMPLETE]

### Phase 6 Summary

Successfully implemented Cognito User Pool for player authentication with the following architecture:
- Cognito User Pool with email sign-in and password requirements
- User Pool Client for web applications (no secret)
- PostConfirmation trigger connected to cognito-player-new Lambda
- Reply email configuration for notifications
- No hosted UI domain (clients handle authentication)

### Phase 6 Status

#### Completed Tasks

- Created PlayerStack with Cognito User Pool and Client
- Implemented PostConfirmation trigger integration with existing Lambda
- Created player.py deployment module with Lambda ARN retrieval
- Created app_player.py for stack isolation
- Added reply email parameter collection to main deployment flow
- Fixed consistency issues across all deployment modules
- Validated User Pool and Client creation
- Updated config.yml with Cognito IDs

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
- Fixed buildspec YAML syntax errors (artifacts: type: NO_ARTIFACTS)
- Successfully tested complete Lambda stack deployment

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
60. **Resource Preservation Pattern**: Check for existing critical resources (S3, DynamoDB, Cognito, CloudFront, ACM) and import them to preserve data and avoid recreation
61. **Consolidated Resource Checks**: Use stack_utilities.py module for all boto3 existence checks to maintain consistency
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
81. **Buildspec YAML Syntax**: Use `artifacts: type: NO_ARTIFACTS` not `artifacts: files: Type: NO_ARTIFACTS`
82. **No Hosted UI Domain**: Skip Cognito hosted UI when clients provide authentication interfaces
83. **Trigger Integration Pattern**: Import existing Lambda ARNs for Cognito triggers rather than creating new ones
84. **User Input Centralization**: Collect all user inputs in deploy.py's collect_deployment_params()
85. **Reply Email Required**: Cognito requires reply-to email even with default email service
86. **Lambda ARN Graceful Handling**: Warn but continue if trigger Lambda not found
87. **Consistency Over Convenience**: Follow established patterns even if less convenient
88. **CDK Synthesis vs Runtime**: Resource existence checks during CDK synthesis don't have AWS access - always create resources
89. **Stack Parameter Consistency**: All stacks should use same parameter pattern (explicit parameters, not kwargs extraction)
90. **Output Method Standardization**: All stacks should use _add_outputs() method for consistent output organization
91. **Context Over Arguments**: Use CDK context (-c flags) for passing parameters to app files instead of command-line arguments
92. **Resource Import Limitations**: Importing existing resources during CDK synthesis is unreliable - prefer creating resources
93. **Existence Checks for Import Logic**: _exists() methods in stacks determine whether to import or create resources
94. **Lambda Layer Dependencies**: Layer must be successfully built before Lambda stack deployment
95. **Buildspec Artifact Handling**: When manually uploading to S3, omit artifacts section or use minimal configuration
96. **EventBridge Rule Dependencies**: Rule creation requires Lambda ARN to be available at synthesis time
97. **CDK State File Exclusion**: .cdk-state.json should be gitignored as it contains deployment-specific state
98. **Resource Checks During Construction**: Use boto3 during stack construction to check for existing resources that must be preserved
99. **Import or Create Pattern**: Check existence, import if found, create with RETAIN policy if not found
100. **Construct ARNs When Needed**: Use account ID and region to build expected ARNs rather than empty string defaults
101. **State Over Query**: Use deployment state to pass values between stacks rather than querying AWS
102. **Post-Deployment Validation**: Additional validation checks belong in deployment modules after stack deployment
103. **Parameter Object Consistency**: Pass complete params object to deployment functions for access to all values
104. **Deployment Mode Flexibility**: Support multiple deployment configurations through mode selection
105. **Dynamic Stack Ordering**: Use mode-based stack ordering instead of hardcoded sequences
106. **Module Separation**: Keep deployment logic in separate modules to prevent main script bloat
107. **Configuration Priority**: config.yml → cdk.json → defaults for consistent parameter resolution
108. **Conditional Input Collection**: Skip unnecessary inputs based on deployment mode
109. **Stack Function Mapping**: Use dictionary mapping for dynamic function dispatch
110. **Mode Validation**: Always validate and normalize user input for deployment modes
111. **CDK Context Standardization**: Use CDK context (`-c` flags) instead of argparse for all app files
112. **Context Flag Format**: Each `-c` and `key=value` must be separate list items for subprocess
113. **Lambda Import with Role**: Use `from_function_attributes()` with role ARN for proper permissions
114. **Imported Pool Limitations**: Cannot use `add_trigger()` on imported Cognito User Pools
115. **Dynamic Phase Numbering**: Calculate phase numbers based on deployment mode order
116. **JSON for Complex Context**: Pass complex data structures as JSON strings through context
117. **Silent Fallback**: Skip operations that can't be performed on imported resources without warnings
118. **ACM and CloudFront Preservation**: Always check for existing ACM certificates and CloudFront distributions to avoid recreation and DNS disruption
119. **Stack Separation by Responsibility**: Separate API Gateway from Client/Portal infrastructure for independent deployment and single responsibility
120. **API URL Passing**: Pass API URL from API stack outputs to Client stack via CDK context for proper dependency chain
121. **Default Bucket Naming**: Generate S3 bucket names from domain and subdomain (e.g., portal-darkrelics-net) when not explicitly provided
122. **Required Domain Parameters**: Make domain and hosted_zone_id required parameters to avoid circular dependencies and ensure proper DNS configuration
123. **Stack Descriptions**: Always provide descriptive stack descriptions in super().__init__() for CloudFormation visibility
124. **Verification Output Timing**: Pass deployment outputs directly to verification functions rather than reading from state that hasn't been updated yet
125. **Bucket Name Consistency**: Ensure verification uses the same bucket name that was actually deployed (from outputs or configuration)
126. **Post-Deployment Bucket Policy**: Update S3 bucket policy after stack deployment to ensure CloudFront has access, especially for imported buckets
127. **Automated Portal Deployment**: Execute CodeBuild project automatically after infrastructure setup to provide complete end-to-end deployment
128. **Fixed Logical IDs Required**: Always use fixed logical IDs for persistent resources (certificates, distributions, buckets) to prevent recreation on updates
129. **No Runtime Checks in Synthesis**: Resource existence checks during CDK synthesis don't work - they always return false without AWS credentials
130. **Import Pattern Belongs in Deployment Layer**: Resource import decisions must be made in deployment modules with AWS access, then passed via CDK context

## Current System Issues

1. **Monolithic Structure**: Single 1800+ line class handling all deployment logic
2. **Poor Separation of Concerns**: Business logic, infrastructure, and UI mixed together
3. **Code Duplication**: AWS client creation and configuration management scattered
4. **Complex Dependencies**: Circular dependencies and tightly coupled components
5. **Inconsistent Error Handling**: Silent failures and no clear recovery mechanism

## Deployment Modes

The system supports three deployment modes, each tailored for different use cases:

### MUD Mode (Multi-User Dungeon)
**Purpose:** Traditional MUD deployment without story-driven features
**Stack Order:** 
1. CodeBuild
2. DynamoDB
3. Lambda
4. Player
5. S3
6. CloudWatch
7. Client

**Excluded:** Story Stack
**Portal Build:** Uses `/buildspec/portal.yml`

### Incremental Mode
**Purpose:** Story-driven gameplay with incremental narrative features
**Stack Order:**
1. CodeBuild
2. DynamoDB
3. Lambda
4. Player
5. Story
6. Client

**Excluded:** S3 Stack, CloudWatch Stack
**Portal Build:** Uses `/buildspec/incremental.yml`

### Hybrid Mode (Default)
**Purpose:** Full feature set combining MUD and story-driven elements
**Stack Order:**
1. CodeBuild
2. DynamoDB
3. Lambda
4. Player
5. Story
6. S3
7. CloudWatch
8. Client

**Included:** All stacks
**Portal Build:** Uses `/buildspec/incremental.yml`

## New Architecture

### Design Principles

- **Simplicity First**: No clever abstractions or over-engineering
- **Sequential Execution**: Deploy one resource at a time, no parallelism
- **Clear Separation**: Infrastructure details in CDK state, operational config in config.yml
- **Module Size Limit**: Each module under 300 lines per CLAUDE.md standards
- **No Legacy Support**: Complete replacement, no migration paths needed

### Stack Organization

The deployment order varies based on the selected deployment mode:

#### Hybrid Mode (Default) - All Features
```
1. CodeBuild Stack    → Build infrastructure, artifacts bucket, and Lambda builds [COMPLETE]
2. DynamoDB Stack     → Tables and access policies [COMPLETE]
3. Lambda Stack       → Lambda layer, IAM role/policies, 16 Lambda functions [COMPLETE]
4. Player Stack       → Cognito User Pool and PostConfirmation trigger [COMPLETE]
5. Story Stack        → SSM parameter, SQS, EventBridge, additional Lambda permissions [READY FOR TESTING]
6. S3 Stack           → Scripts bucket [COMPLETE]
7. CloudWatch Stack   → Logging and metrics [COMPLETE]
8. API Stack          → API Gateway, custom domain, ACM certificate, Route53 record [DEPLOYED]
9. Client Stack       → S3 bucket, CloudFront, CodeBuild project, ACM certificate, Route53 record [DEPLOYED WITH WARNINGS]
10. [Portal Build]    → Frontend deployment with incremental.yml [NOT STARTED]
```

#### MUD Mode - Traditional Multi-User Dungeon
```
1. CodeBuild Stack    → Build infrastructure, artifacts bucket, and Lambda builds [COMPLETE]
2. DynamoDB Stack     → Tables and access policies [COMPLETE]
3. Lambda Stack       → Lambda layer, IAM role/policies, 16 Lambda functions [COMPLETE]
4. Player Stack       → Cognito User Pool and PostConfirmation trigger [COMPLETE]
5. S3 Stack           → Scripts bucket [COMPLETE]
6. CloudWatch Stack   → Logging and metrics [COMPLETE]
7. API Stack          → API Gateway, custom domain, ACM certificate, Route53 record [DEPLOYED]
8. Client Stack       → S3 bucket, CloudFront, CodeBuild project, ACM certificate, Route53 record [DEPLOYED WITH WARNINGS]
9. [Portal Build]     → Frontend deployment with portal.yml [NOT STARTED]
```
Note: Story Stack is excluded in MUD mode

#### Incremental Mode - Story-Driven Focus
```
1. CodeBuild Stack    → Build infrastructure, artifacts bucket, and Lambda builds [COMPLETE]
2. DynamoDB Stack     → Tables and access policies [COMPLETE]
3. Lambda Stack       → Lambda layer, IAM role/policies, 16 Lambda functions [COMPLETE]
4. Player Stack       → Cognito User Pool and PostConfirmation trigger [COMPLETE]
5. Story Stack        → SSM parameter, SQS, EventBridge, additional Lambda permissions [READY FOR TESTING]
6. API Stack          → API Gateway, custom domain, ACM certificate, Route53 record [DEPLOYED]
7. Client Stack       → S3 bucket, CloudFront, CodeBuild project, ACM certificate, Route53 record [DEPLOYED WITH WARNINGS]
8. [Portal Build]     → Frontend deployment with incremental.yml [NOT STARTED]
```
Note: S3 and CloudWatch Stacks are excluded in Incremental mode

## Project Status Summary

### Completed Phases (9 of 10) - API and Client Stacks Deployed
- **Phase 1**: DynamoDB Stack - DEPLOYED
- **Phase 2**: CodeBuild Stack - DEPLOYED
- **Phase 3**: S3 Stack - DEPLOYED
- **Phase 4**: CloudWatch Stack - DEPLOYED
- **Phase 5**: Lambda Stack - DEPLOYED
- **Phase 6**: Player Stack - DEPLOYED
- **Phase 7**: Story Stack - DEPLOYED

### System Enhancements
- **Deployment Mode System** - IMPLEMENTED
- **CDK Context Standardization** - COMPLETED
- **Story Stack Remediation** - COMPLETED
- **Dynamic Phase Numbering** - IMPLEMENTED

### Remaining Work (2 of 9)
- **Phase 8**: Client Stack - NOT STARTED  
- **Phase 9**: Portal Build - NOT STARTED

### Architecture Achievements
- Replaced 1800+ line monolithic class with modular architecture
- All modules under 300 lines as per standards
- Clean separation of concerns
- Dynamic deployment based on mode
- Standardized CDK context pattern across all stacks
- Production tested and operational for all 7 completed phases

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

### 7. Story Stack [READY FOR TESTING]

**Resources:**

- SSM Parameter for story configuration
- SQS Queues:
  - processing-queue
  - advancement-queue
- EventBridge rule for polling schedule (disabled by default)
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

**Remediation Applied:**
- Removed all resource existence checks that fail during CDK synthesis
- Resources now always create (CDK handles create vs update)
- Lambda ARNs constructed from account_id and region to ensure EventBridge rule creation
- All boto3 checks moved to post-deployment validation only

### 8. Client Stack [Phase 8 - COMPLETED]

**Resources:**

- Portal S3 bucket
- CloudFront distribution
- Route53 alias (required - custom domain)
- ACM certificate (required - custom domain)
- API Gateway with Lambda integrations (using Lambda ARNs from Lambda Stack)
- API Gateway custom domain (required)
- Portal CodeBuild project

**Deployment Mode Variations:**
- **MUD Mode:** Deployed as final stack (after CloudWatch)
- **Incremental Mode:** Deployed as final stack (after Story)
- **Hybrid Mode:** Deployed as final stack (after CloudWatch)
- All modes include full Client Stack resources

**Required User Input:**
- Custom domain name (same as Lambda Stack)
- Route53 Hosted Zone ID
- Deployment mode selection (MUD/Incremental/Hybrid)

**Config.yml Output:**

- S3.PortalBucket
- CloudFront.DistributionId
- CloudFront.DomainName
- API.GatewayUrl

### 9. Portal Build Execution [Phase 9 - NOT STARTED]

**Actions:**

- Execute portal build using mode-specific buildspec
- CloudFront invalidation (automatic)
- Final validation

**Buildspec Selection:**
- **MUD Mode:** Uses `/buildspec/portal.yml`
- **Incremental Mode:** Uses `/buildspec/incremental.yml`
- **Hybrid Mode:** Uses `/buildspec/incremental.yml`

**Build Configuration Differences:**
- `portal.yml`: Traditional MUD interface without story elements
- `incremental.yml`: Enhanced interface with story progression features

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

## Critical Lessons Learned

### Resource Recreation Issue (Fixed)

**Problem:** Resources were being deleted and recreated on every deployment despite using import-or-create pattern.

**Root Cause:** CDK synthesis happens before deployment and has no AWS access. The check functions always returned False during synthesis, causing CDK to generate CloudFormation templates with new logical IDs each time.

**Solution:** Use fixed logical IDs for all resources and rely on CDK/CloudFormation to handle create vs update:

```python
# OLD (BROKEN):
if check_s3_bucket_exists(bucket_name, region):
    return s3.Bucket.from_bucket_name(scope, construct_id, bucket_name)
return s3.Bucket(scope, construct_id, ...)  # Creates new logical ID each time

# NEW (WORKING):
return s3.Bucket(
    scope,
    "FixedLogicalId",  # Same ID every deployment
    bucket_name=bucket_name,
    removal_policy=RemovalPolicy.RETAIN,
    ...
)
```

**Key Insight:** CDK synthesis is deterministic - same inputs should produce same outputs. Dynamic checks during synthesis break this principle.
