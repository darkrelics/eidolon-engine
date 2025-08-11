# Deployment System Rework Plan

## Overview

Complete replacement of the existing monolithic deployment system with a clean, modular architecture focused on simplicity and maintainability.

## Status: DynamoDB Stack Complete (Phase 1)

### Completed Work
- Core infrastructure modules (config.py, state.py, dynamodb_tables.py)
- DynamoDB CDK stack with 14 tables and IAM policy
- Deployment orchestrator (deploy.py)
- CDK application entry point (app.py)
- Documentation updates

### Lessons Learned
1. **No Over-Engineering**: Avoided unnecessary abstractions (no factories, no complex class hierarchies)
2. **Script vs Library**: This is a one-time run script, not a library - no need for __init__ imports or complex module structures
3. **Python Style Compliance**: No private methods (no underscore prefixes), functions over methods when not tightly coupled to classes
4. **Clear Separation**: Config.yml for operational data only, .cdk-state.json for infrastructure details
5. **Simple Naming**: Fixed table names without prefixes, single IAM policy with clear name
6. **Professional Output**: Use [OK], [MISSING] instead of emoji characters
7. **Proper Module Naming**: Use specific names (dynamodb_tables.py) instead of generic (constants.py)

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
- 11 tables: players, characters, rooms, exits, items, prototypes, archetypes, motd, story, segments, active_segments
- Single IAM managed policy for DynamoDB read/write access

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