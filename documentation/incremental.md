# Incremental Game System

## Overview

The Incremental Game Module is an idle RPG subsystem within the Eidolon Engine that provides timer-based story progression. Players experience narrative-driven gameplay through automated mechanics while maintaining full character compatibility with the main MUD.

## Production Status

The incremental game system is **fully deployed to production** as part of the modular 9-stack CDK architecture:

- **Deployment Modes**: Available in Incremental (7 stacks) and Hybrid (9 stacks) modes
- **Infrastructure**: 16 Lambda functions, 14 DynamoDB tables, dual SQS queues
- **Automated Deployment**: End-to-end from infrastructure to portal in under 15 minutes
- **Fixed Logical IDs**: Preventing resource recreation on stack updates
- **Module Compliance**: 94% of modules under 300 lines, 100% under 1000 lines

## Purpose

The incremental module serves as:

- **New Player Gateway**: Story-driven introduction to the Eidolon Engine universe
- **Idle Progression**: Time-based gameplay for players wanting passive advancement
- **Alternative Gameplay**: Different experience from active MUD participation while using the same character

## Core Features

### Story System

- **Twine-Authored Content**: Visual narrative design with branching paths
- **Three Story Types**: One-time (unique rewards), daily (reset at midnight UTC), and repeatable
- **Prerequisite System**: Stories unlock based on skills and items
- **Timer-Based Progression**: Segments advance automatically (1 minute to 24 hours)

### Segment Types

1. **Decision**: Player choices with configurable timeouts
2. **Mechanical**: Skill challenges and/or combat using MUD mechanics
3. **Rest**: Healing periods where wounds recover

### Character Integration

- **Shared Character Data**: Same character plays both MUD and Incremental
- **Mode Exclusivity**: GameMode field prevents concurrent play
- **Persistent State**: Wounds, inventory, skills, and location carry between modes
- **Unified Progression**: Experience gained in either mode contributes to growth

## Technical Overview

### Architecture Components

- **Serverless Architecture**: 16 AWS Lambda functions with shared execution role
- **Flutter Web Client**: Deployed via CloudFront with automated builds
- **Shared Infrastructure**: 14 DynamoDB tables with RemovalPolicy.RETAIN
- **Event-Driven Processing**: EventBridge 1-minute polling with SQS queues
- **Cost Efficient**: ~$235-335/month for 10,000 concurrent users

### Infrastructure Stack (Incremental Mode)

1. **CodeBuild Stack**: Build infrastructure and Lambda artifacts
2. **DynamoDB Stack**: 14 tables with managed IAM policy
3. **Lambda Stack**: Layer and 16 functions with fixed logical IDs
4. **Player Stack**: Cognito User Pool with PostConfirmation trigger
5. **Story Stack**: SQS queues, EventBridge rule, SSM parameter
6. **API Stack**: API Gateway with Lambda integrations
7. **Client Stack**: CloudFront and automated portal build

### Key Lambda Functions

**Story Operations**:
- `api-story-start`: Begin new stories
- `api-story-abandon`: Exit active stories
- `api-segment-decision`: Submit player choices
- `api-segment-rest`: Initiate healing segments
- `api-segment-status`: Check segment readiness
- `api-segment-outcome`: Retrieve results
- `api-segment-history`: View past segments

**Processing Functions**:
- `ops-segment-poller`: EventBridge-triggered polling
- `ops-segment-process`: SQS mechanical processing
- `ops-story-advance`: SQS story advancement

### Story Infrastructure

**SQS Queues**:
- `eidolon-processing-queue`: Mechanical segment processing
- `eidolon-advancement-queue`: Story advancement

**EventBridge**:
- Rule: `eidolon-story-poller` (1-minute schedule)
- Auto-enabled when stories active, disabled when idle

**SSM Parameter**:
- `/eidolon/story/config`: Controls polling state

## Documentation

- [Requirements](incremental-requirements.md) - Functional and non-functional requirements with implementation status
- [Technical Design](incremental-design.md) - Architecture and implementation details with production metrics
- [API Documentation](incremental-api.md) - REST endpoints with Lambda function details
- [Story System](incremental-story.md) - State machines and processing flows
- [MUD Integration](incremental-mud-workflow.md) - Character transition workflows with infrastructure context
- [Implementation Guide](incremental-implementation.md) - Development and deployment procedures
- [Database Schema](schema.md) - Shared data structures with DynamoDB specifications

## Getting Started

### For Players

Players can access the Incremental game through the portal deployed at `https://{client_host}.{domain}`. After character creation, they choose their initial game mode and can switch between modes when not actively playing. The GameMode field ensures characters can only be active in one mode at a time.

### For Developers

**Deployment**:
```bash
cd deployment
python3 deploy.py
# Select "incremental" or "hybrid" mode when prompted
```

**Key Environment Variables** (set in Lambda Stack):
- `SEGMENT_QUEUE_URL`: SQS queue for mechanical processing
- `STORY_ADVANCEMENT_QUEUE_URL`: SQS queue for story advancement
- `SSM_POLLER_STATE_PARAMETER`: SSM parameter for polling control
- `SEGMENT_BATCH_SIZE`: Processing batch size (default: 10)

### Production Metrics

- **Deployment Time**: Full system deployment in under 15 minutes
- **Response Time**: API responses average under 500ms
- **Availability**: 99.9% uptime via AWS managed services
- **Scalability**: Supports 10,000+ concurrent users
- **Cost**: $235-335/month for 10,000 active users

### Implementation Patterns

- **Front-loaded Processing**: All outcomes calculated when segments start
- **Fixed Logical IDs**: Resources maintain identity across deployments
- **Post-Deployment Updates**: Lambda functions updated from S3 artifacts
- **No AWS Access During Synthesis**: CDK best practices compliance
- **Managed Policies**: Shared execution role with managed IAM policies
