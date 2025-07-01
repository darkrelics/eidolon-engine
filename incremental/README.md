# Eidolon Engine - Incremental Module

A server-authoritative incremental RPG module built with Lambda functions and DynamoDB, designed to introduce players to the Eidolon Engine world through story-driven progression.

## Overview

This incremental module serves as a gateway to the Eidolon Engine universe, providing players with an automated RPG experience driven by story segments. Players progress through time-gated narrative segments, with all game logic enforced server-side to prevent cheating and ensure consistent gameplay.

## Architecture

### Server-Authoritative Design

- **Time Authority**: Lambda functions control all timing - no client-side progression
- **Story Content**: JSON documents stored in S3, referenced by DynamoDB
- **State Management**: Character progression stored in DynamoDB with conditional writes
- **Content Delivery**: Stories loaded from S3 via signed URLs
- **Security**: All rewards and progression calculated server-side
- **No Client Trust**: Flutter app only displays server-calculated results

### Technical Stack

- **Backend**: Python Lambda functions for game logic
- **Database**: DynamoDB for character state and story metadata
- **Storage**: S3 for story JSON content
- **Client**: Flutter Web (mobile apps in future phases)
- **Monitoring**: CloudWatch metrics and EMF logging
- **Authentication**: AWS Cognito (shared with main game)

## Development Plan

### Phase 0 – Foundation [COMPLETED]

**Goal**: Establish common development environment and contracts

- Repository structure: `/incremental` with `lambda/`, `schemas/`, `lib/`, `test/`
- Story schema JSON (story.schema.json) defining segment structure with Twine compatibility
- Flutter client foundation with authentication via AWS Cognito
- Character model based on server archetypes from `/data/test_archetypes.json`

**Deliverable**: Schema defined, Flutter models implemented, authentication working

### Phase 1 – Core Loop MVP

**Goal**: Make the game playable with server-side authority

- **Character Management** (#664): Create/retrieve character Lambda functions
- **StartSegment Lambda** (#660): Validate character, set segment timer, return end time
- **ConcludeSegment Lambda** (#661): Validate completion time, evaluate outcome, apply rewards
- **S3 Story Integration** (#645): Modify Lambdas to fetch stories from S3
- **Example Story** (#662): Tutorial story demonstrating all mechanics
- **DynamoDB Tables**:
  - IncrementalCharacters (player progression)
  - ActiveSegments (time-gated segments)
  - StoryRegistry (S3 object references) (#644)
  - StoryManifest (browsing metadata) (#644)
  - CharacterHistory (completion tracking)
- **S3 Story Storage** (#643): Configure bucket for story content
- **Cognito Identity Pool** (#646): Enable direct S3 access
- **Flutter Timer UI** (#663): Countdown timer and outcome display
- **Observability**: CloudWatch metrics for segments started/completed

**Deliverable**: Complete game loop with example story from S3

### Phase 2 – Content Pipeline

**Goal**: Enable dynamic content without backend changes

- **Twine Converter** (#640): Create twine2idle tool for Twee/HTML conversion
- **Git-to-S3 Pipeline**: GitHub Action for story publishing
- **Story Manifest Updates**: Auto-generate browsing index
- **Client Story Loading**: Dynamic story list from S3
- **Revision Handling**: Support hot-patching live stories
- **Content Validation**: JSON schema validation on commit
- **Author Documentation** (#619): Story writing handbook

**Deliverable**: Non-developers can publish stories; live updates work

### Phase 3 – Progression Features

**Goal**: Add depth with branching and rest mechanics

- **Branching Paths** (#610): Weighted random story branches
- **Rest & Abandon** (#611): Alternative segment outcomes
- **Extended Analytics**: Detailed metrics for balancing
- **Replay Prevention**: CharacterHistory tracking
- **Achievement System**: Story completion rewards
- **QA Test Suite** (#618): Automated progression testing

**Deliverable**: Complete idle RPG loop with meaningful progression

### Phase 4 – Scale Hardening

**Goal**: Production readiness

- Lambda provisioned concurrency
- CloudWatch Synthetics monitoring
- Cost controls and autoscaling
- Security review and WAF

**Deliverable**: SLA-ready module supporting 100k DAU

## Game Systems

### Story Structure

Stories are JSON documents stored in S3, following the story.schema.json specification:

- Metadata (name, author, tags, Twine export info)
- Passages array with Twine-compatible structure
- Each passage includes:
  - Narrative text and duration
  - Links to other passages
  - gameData with incremental mechanics:
    - Challenge definition (skill + attribute vs difficulty)
    - Requirements (resources, progress flags)
    - Outcomes (criticalSuccess, success, failure, criticalFailure)
    - Rewards and penalties

### Character Progression

Based on the Eidolon Engine MUD mechanics, using archetypes from `/data/test_archetypes.json`:

#### Attributes

- **Physical**: Strength, Agility, Endurance
- **Mental**: Intelligence, Perception, Cunning
- **Social**: Charisma, Presence, Intrigue

#### Skills

- **Combat**: Melee, Archery, Brawling, Dodge, Parry
- **Stealth**: Stealth, Investigation, Tumbling, Climbing, Lockpicking
- **Magic**: Mythos, Arcane
- **Survival**: FirstAid, Foraging, Appraise

#### Character Creation

- Players select from available archetypes (Wizard, Rogue, Warrior, etc.)
- Each archetype defines starting attributes, skills, health, and essence
- No level system - progression is purely through skill/attribute improvements

#### Experience System

Challenges in story segments use the MUD's XP mechanics:

- **Base XP**: 0.25 per action
- **Variance Modifier**: Based on challenge difficulty
  - Fighting stronger opponents = more XP (up to 4x)
  - Fighting weaker opponents = less XP (down to 0.25x)
  - Formula: (min_score/max_score)²
- **Failure Penalty**: 50% XP on failed actions
- **Skill Progression**: XP Required = 10 × 3.5^(current_score)
- **Attribute Growth**: Attributes gain 10% of skill XP

### Segment Resolution

1. **StartSegment**: Player begins a story segment

   - Lambda validates character can attempt it
   - Sets timer based on segment duration
   - Returns end timestamp to client

2. **ConcludeSegment**: Timer expires, player claims rewards
   - Lambda validates time has passed
   - Evaluates challenge (skill + attribute vs difficulty)
   - Determines outcome (critSuccess/success/neutral/fail/death)
   - Applies XP and rewards based on outcome
   - Advances to next segment or branch

### Incremental Adaptations

- **Automated Play**: No manual actions required during segments
- **Time Gates**: Real-world timers enforce pacing
- **Offline Progress**: Stories continue while away
- **Visual Progress**: Countdown timers and progress bars
- **Server Authority**: All progression calculations happen in Lambda functions
- **Story Focus**: Content drives engagement, not prestige mechanics

## Content Management

### Story Publishing Workflow

1. Authors write stories in JSON format
2. Validate against schema locally
3. Push to Git repository
4. GitHub Actions validates and publishes
5. Stories available immediately to players

### Story Design Guidelines

- Segments should be 30 seconds to 24 hours
- Include variety of challenge types
- Balance risk/reward for different outcomes
- Support both linear and branching narratives
- Test with game balance simulator

## API Endpoints

### Lambda Functions

- `POST /start-segment`: Begin a story segment
- `POST /conclude-segment`: Complete segment and claim rewards
- `POST /abandon`: Cancel current story run with penalty
- `POST /rest`: Rest instead of continuing story

### Data Models

Data models follow the story.schema.json specification and DynamoDB table structure defined in cloudformation/dynamo.yml

## Implementation Status

### Completed

- Story schema definition with Twine compatibility
- Flutter character models (display-only)
- Archetype loading system
- API service for Lambda calls
- DynamoDB table definitions
- Authentication integration

### Next Steps

- Implement StartSegment Lambda function
- Implement ConcludeSegment Lambda function
- Create example story content
- Build timer UI in Flutter
- Add story browsing interface

## Development Setup

### Prerequisites

- Go 1.21+
- Flutter 3.0+
- AWS CLI configured
- Docker for DynamoDB Local

### Local Development

```bash
# Start local environment
make dev

# Run Lambda tests
cd lambda && go test ./...

# Run Flutter client
cd client/idle && flutter run -d chrome
```

### Story Validation

```bash
# Validate a story file
make validate-story STORY=stories/tutorial.json

# Validate all stories
make validate-stories
```

## Testing Strategy

- **Unit Tests**: Lambda function logic
- **Integration Tests**: Full flow with DynamoDB Local
- **Load Tests**: Simulate 10k concurrent players
- **Story Tests**: Automated play-through of all paths
- **Client Tests**: Flutter widget and integration tests

## Monitoring

### Key Metrics

- `SegmentsStarted`: Count per story
- `SegmentsCompleted`: Success rate tracking
- `ConcludeLatency`: P50/P95/P99
- `PrestigeEvents`: Progression tracking
- `ActivePlayers`: Concurrent users
- `StoryCompletionRate`: Full story completion

### Dashboards

- Real-time player activity
- Story performance metrics
- Error rates and latency
- Cost per player metrics

## Success Criteria

### Technical

- All time enforcement in Lambda
- No client-side exploits possible
- > 99.9% availability under synthetics
- P95 cold start <120ms

### Operational

- P95 conclude latency <150ms
- Daily AWS cost <$15 at 100k DAU
- 3-minute content deployment

### Player Experience

- Zero client crashes
- Smooth progression curve
- Engaging story content
- Clear feedback on all actions

## Future Enhancements

- Mobile apps (iOS/Android)
- Character export to main game
- Seasonal story events
- Guild/social features
- Achievement system
- Leaderboards

## Contributing

See [Story Author Handbook](docs/story-author-handbook.md) for content creation guidelines.

For code contributions, ensure all tests pass and follow the style guide in CLAUDE.md.
