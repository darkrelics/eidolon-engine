# Incremental Game System

## Overview

The Incremental Game Module is an idle RPG subsystem within the Eidolon Engine that provides timer-based story progression. Players experience narrative-driven gameplay through automated mechanics while maintaining full character compatibility with the main MUD.

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

- **Serverless Architecture**: AWS Lambda functions handle all game logic
- **Flutter Web Client**: Responsive interface for story progression
- **Shared Infrastructure**: Uses existing DynamoDB tables, Cognito auth, and API Gateway
- **Event-Driven Processing**: 1-minute polling system with SQS reliability
- **Cost Efficient**: ~$235-335/month for 10,000 concurrent users

## Documentation

- [Requirements](incremental-requirements.md) - Functional and non-functional requirements
- [Technical Design](incremental-design.md) - Architecture and implementation details
- [MUD Integration](incremental-mud-workflow.md) - Character transition workflows
- [Database Schema](schema.md) - Shared data structures

## Getting Started

Players can access the Incremental game through the same portal as the MUD. After character creation, they choose their initial game mode and can switch between modes when not actively playing.
