# Deployment Modes

## Overview

The Eidolon Engine supports three deployment modes, each tailored for different use cases while sharing core backend infrastructure. The deployment system automatically adjusts the stack deployment order and frontend selection based on the chosen mode, providing optimal resource allocation for each scenario.

## Mode Comparison Table

| Aspect                 | MUD Mode             | Incremental Mode              | Hybrid Mode (Default)         |
| ---------------------- | -------------------- | ----------------------------- | ----------------------------- |
| **Frontend Deployed**  | Portal (portal.yml)  | Incremental (incremental.yml) | Incremental (incremental.yml) |
| **Stack Count**        | 9 stacks             | 8 stacks                      | 10 stacks                     |
| **Excluded Stacks**    | Story Stack          | S3, CloudWatch Stacks         | None (all stacks)             |
| **Lambda Functions**   | 17 deployed          | 17 deployed                   | 17 deployed                   |
| **DynamoDB Tables**    | 14 tables            | 14 tables                     | 14 tables                     |
| **Story Processing**   | Not available        | SQS, EventBridge, SSM         | SQS, EventBridge, SSM         |
| **Scripts Support**    | Lua scripts in S3    | Not available                 | Lua scripts in S3             |
| **CloudWatch Logging** | Full logging         | Basic Lambda logs only        | Full logging                  |
| **Use Case**           | Traditional MUD only | Story-driven incremental      | Full feature set              |

## Stack Deployment Order

Refer to the canonical sequence in [Deployment Guide](deployment.md#stack-deployment-order); this document focuses on how each mode changes the selection of stacks rather than repeating the step-by-step list.

## Deployment Process

### Initial Deployment

Start with the commands in [Deployment Guide](deployment.md#quick-start), then select a mode when prompted:

- **1**: MUD Mode - Traditional Multi-User Dungeon
- **2**: Incremental Mode - Story-driven incremental RPG
- **3**: Hybrid Mode - Full feature set (default)

### Mode Selection Impact

The selected mode determines:

1. **Stack deployment order** - Which stacks are deployed and in what sequence
2. **Frontend buildspec** - portal.yml for MUD, incremental.yml for others
3. **Resource allocation** - Whether to create S3 scripts bucket, CloudWatch logs, Story infrastructure
4. **Portal content** - What gets deployed to CloudFront

## Frontend Applications

### Portal (MUD Mode)

- **Source**: `/portal`
- **Buildspec**: `buildspec/portal.yml`
- **Deployment**: Automated via CodeBuild after Client Stack
- **Features**: Character management, authentication, account settings
- **API Integration**: Uses API Gateway at `api.{domain}`

### Incremental (Incremental/Hybrid Modes)

- **Source**: `/incremental`
- **Buildspec**: `buildspec/incremental.yml`
- **Deployment**: Automated via CodeBuild after Client Stack
- **Features**: Story progression, segment processing, character advancement
- **API Integration**: Uses API Gateway at `api.{domain}`

## Backend Infrastructure (Shared by All Modes)

For the definitive Lambda inventory, see [Lambda Functions](lambda-functions.md); for database definitions, see [Database Schema](schema.md). Each deployment mode selects from the same building blocks, enabling consistent APIs regardless of frontend.

### Mode-Specific Infrastructure

Refer to [Deployment System Design](deployment-design.md) for stack-by-stack details, including which components (Story, S3, CloudWatch) are toggled per mode.

## Choosing a Deployment Mode

### Choose MUD Mode when:

- You only want the traditional MUD experience
- You need Lua scripting support for game logic
- You want comprehensive CloudWatch logging
- You don't need story-driven incremental features

### Choose Incremental Mode when:

- You only want story-driven incremental gameplay
- You need SQS/EventBridge for async processing
- You don't need Lua scripts or detailed logging
- You want the leanest infrastructure footprint

### Choose Hybrid Mode when:

- You want the complete feature set
- You need both MUD and incremental capabilities
- You want maximum flexibility for future expansion
- You can support the full infrastructure footprint

## Technical Implementation Details

### CDK Context Configuration

The deployment mode is passed to all CDK stacks via context:

```python
context_args = ["-c", f"deployment_mode={params.deployment_mode}"]
```

Stacks use this to make mode-aware decisions:

- **CodeBuild Stack**: Selects appropriate buildspec file
- **Client Stack**: Configures portal build for selected mode
- **Story Stack**: Only deployed for Incremental/Hybrid modes

### Post-Deployment Operations

Regardless of mode, the system performs:

1. **Lambda Updates**: Functions updated from S3 artifacts
2. **Layer Management**: Old layer versions cleaned up
3. **Trigger Configuration**: Cognito triggers set for imported pools
4. **Portal Build**: Automatic CodeBuild execution with mode-specific buildspec
5. **CloudFront Invalidation**: Cache cleared after deployment

### Fixed Logical IDs

All resources use fixed logical IDs to prevent recreation:

- Prevents resource deletion on stack updates
- Maintains data persistence across deployments
- Ensures consistent resource references

### Production Deployment Status

All three modes have been successfully deployed and tested:

- **Module Size**: 94% of modules under 300 lines
- **Deployment Time**: Full deployment in under 15 minutes
- **Stack Success**: All 9 stacks operational in production
- **Lessons Applied**: 140 documented lessons incorporated
