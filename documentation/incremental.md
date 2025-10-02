# Incremental Game System

## Overview

The Incremental Game Module is an idle RPG subsystem within the Eidolon Engine that provides timer-based story progression. Players experience narrative-driven gameplay through automated mechanics while maintaining full character compatibility with the main MUD.

## System Status

The incremental game system is fully deployed to production. For deployment details and metrics, see the [Implementation Guide](incremental-implementation.md#production-deployment-status).

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

Canonical segment definitions live in [Incremental Requirements](incremental-requirements.md#24-segment-types); the system supports decision and mechanical segments.

### Character Integration

- **Shared Character Data**: Same character plays both MUD and Incremental
- **Mode Exclusivity**: GameMode field prevents concurrent play (see [Character Mode Workflow](incremental-mud-workflow.md))
- **Persistent State**: Wounds, inventory, skills, and location carry between modes
- **Unified Progression**: Experience gained in either mode contributes to growth

## Technical Overview

The incremental game is built on the serverless architecture described in [Deployment Guide](deployment.md#system-architecture), using AWS Lambda functions, DynamoDB tables, and event-driven processing via SQS and EventBridge.

- **Architecture**: See [Technical Design](incremental-design.md) for detailed architecture
- **API**: See [API Documentation](incremental-api.md) for endpoints and Lambda functions
- **Implementation**: See [Implementation Guide](incremental-implementation.md) for code patterns and deployment

## Documentation

- [Requirements](incremental-requirements.md) - Functional and non-functional requirements
- [Technical Design](incremental-design.md) - System architecture and design decisions
- [API Documentation](incremental-api.md) - REST endpoints and Lambda functions
- [Story System](incremental-story.md) - State machines and processing logic
- [MUD Integration](incremental-mud-workflow.md) - Character mode transition workflows
- [Implementation Guide](incremental-implementation.md) - Code examples and deployment procedures
- [Database Schema](schema.md) - Shared data structures

## Getting Started

### For Players

Players can access the Incremental game through the portal deployed at `https://{client_host}.{domain}`. After character creation, they choose their initial game mode and can switch between modes when not actively playing. The GameMode field ensures characters can only be active in one mode at a time.

### For Developers

**Deployment**: Follow the commands in [Deployment Guide](deployment.md#quick-start) and select the incremental or hybrid mode when prompted.

**Key Environment Variables** (set in Lambda Stack):

- `SEGMENT_QUEUE_URL`: SQS queue for mechanical processing
- `STORY_ADVANCEMENT_QUEUE_URL`: SQS queue for story advancement
- `SSM_POLLER_STATE_PARAMETER`: SSM parameter for polling control
- `SEGMENT_BATCH_SIZE`: Processing batch size (default: 10)

### Production Metrics

For detailed metrics and performance characteristics, see the [Implementation Guide](incremental-implementation.md#production-deployment-status).
