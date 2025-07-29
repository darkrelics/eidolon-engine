# Incremental Game System

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
- **Storage**: DynamoDB stores all game data including character state, story definitions, and progress
- **Authentication**: Shared AWS Cognito identity with the main MUD

## Key Components

### 1. Story System

- Stories composed using Twine for visual narrative design
- Story definitions stored in DynamoDB tables after conversion
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
- Wound system persists across both game modes

### 4. Content Management

- Authors create stories using Twine's visual editor
- Twine to Incremental conversion tool transforms stories for the game engine
- Story content stored in DynamoDB tables (Story and Segments)
- Administrative tools for managing published story content
- Version field in Story table enables content updates
- Direct database updates for immediate content availability

## Health and Damage System

The incremental module implements the same sophisticated wound tracking system as the MUD:

### Wound Mechanics

- **Damage creates wounds**: Each point of damage adds a wound map to the character's wounds list
- **Three damage types**:
  - Bashing: Heals in 15 minutes (bruises, stunning)
  - Lethal: Heals in 6 hours (cuts, serious injuries)
  - Aggravated: Heals in 7 days (grievous wounds)
- **Health calculation**: `Health = MaxHealth - len(wounds)`
- **Real-time healing**: Wounds heal automatically when their HealAt timestamp expires

### Combat Integration

Combat segments fully implement the MUD combat system:

- Opposed skill checks determine hit/miss
- Damage rolls calculate wounds inflicted
- Environmental modifiers affect combat (dim lighting, difficult terrain)
- Combat outcomes based on wounds sustained:
  - Death: Health reaches 0
  - Minimal: Victory with 3+ wounds
  - Normal: Victory with 1-2 wounds
  - Exceptional: Victory without wounds

### Persistent Consequences

- Wounds persist when switching between MUD and Incremental modes
- Character entering Incremental mode wounded starts at disadvantage
- Death in either mode affects the character across both systems
- Healing continues in real-time regardless of which mode is active

## Technology Stack

- **Runtime**: Python 3.12 Lambda functions
- **Database**: DynamoDB storing all game data and content
- **Frontend**: Flutter targeting web (mobile planned)
- **Infrastructure**: AWS CDK for deployment
- **Monitoring**: CloudWatch metrics and logging

## Related Documentation

- [Requirements](incremental-requirements.md) - Product requirements and user stories
- [Design](incremental-design.md) - Technical architecture and implementation details
- [MUD Workflow](incremental-mud-workflow.md) - Integration patterns with the MUD system
