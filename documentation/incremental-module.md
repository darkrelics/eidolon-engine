# Incremental Game Module

## Overview

The Incremental Game Module is a server-authoritative idle RPG subsystem within the Eidolon Engine ecosystem. It provides players with an automated, story-driven progression experience that serves as both an introduction to the game world and a complementary gameplay mode to the main MUD experience.

## Purpose

The incremental module serves three primary purposes:

1. **Gateway Experience**: Introduces new players to the Eidolon Engine universe through guided story content
2. **Idle Progression**: Offers time-based gameplay for players who want to progress without active engagement
3. **Character Development**: Provides an alternative path for character advancement through story completion

## Architecture Overview

The module follows a serverless architecture pattern:

- **Backend**: AWS Lambda functions handle all game logic and state transitions
- **Frontend**: Flutter web application provides the user interface
- **Storage**: DynamoDB stores character state and story progress
- **Content**: Story definitions stored in S3, loaded dynamically
- **Authentication**: Shared AWS Cognito identity with the main MUD

## Key Components

### 1. Story System
- JSON-based story definitions with Twine compatibility
- Three story types: one-time, daily, and repeatable
- Prerequisite checking for gated content
- Branching narratives with player decisions

### 2. Segment Processing
- Time-gated progression through story segments
- Server-calculated outcomes based on character stats
- Automatic reward distribution upon completion
- EventBridge-driven polling for segment completion

### 3. Character Integration
- Shared character records with the MUD system
- GameMode field prevents concurrent MUD/Incremental play
- Skills and attributes affect story outcomes
- Items and resources earned transfer to MUD inventory

### 4. Content Pipeline
- Authors write stories in JSON format following defined schemas
- GitHub Actions validate and publish to S3
- Hot-reloading of story content without deployments
- Version control for story iterations

## Technology Stack

- **Runtime**: Python 3.12 Lambda functions
- **Database**: DynamoDB with single-table design patterns
- **Frontend**: Flutter targeting web (mobile planned)
- **Infrastructure**: AWS CDK for deployment
- **Monitoring**: CloudWatch metrics and logging

## Related Documentation

- [Requirements](incremental-requirements.md) - Product requirements and user stories
- [Design](incremental-design.md) - Technical architecture and implementation details
- [MUD Workflow](incremental-mud-workflow.md) - Integration patterns with the MUD system