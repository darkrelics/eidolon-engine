# Eidolon Engine - Incremental Module

A server-authoritative incremental RPG module built with Lambda functions and DynamoDB, designed to introduce players to the Eidolon Engine world through story-driven progression.

## Overview

This incremental module serves as a gateway to the Eidolon Engine universe, providing players with an automated RPG experience driven by story segments. Players progress through time-gated narrative segments, with all game logic enforced server-side to prevent cheating and ensure consistent gameplay.

## Architecture

### Server-Authoritative Design

- **Time Authority**: Lambda functions control all timing - no client-side progression
- **Story Blobs**: JSON documents in DynamoDB define complete story content
- **State Management**: Character progression stored in DynamoDB with conditional writes
- **Content Delivery**: Stories loaded from DynamoDB (with future S3/CloudFront option)
- **Security**: All rewards and progression calculated server-side

### Technical Stack

- **Backend**: Go Lambda functions for game logic
- **Database**: DynamoDB for character sheets and story content
- **Client**: Flutter Web (mobile apps in future phases)
- **Monitoring**: CloudWatch metrics and EMF logging
- **Authentication**: AWS Cognito (shared with main game)

## Development Plan

### Phase 0 – Foundation (½ sprint)

**Goal**: Establish common development environment and contracts

- Repository structure: `/idle` with `lambda/`, `schemas/`, `stories/`, `client/idle`
- Development tooling: `make dev` for local DynamoDB and Lambda testing
- Story blob JSON Schema (draft 2020-12) defining segment structure
- CI pipeline for story validation and Lambda tests

**Deliverable**: Agreed contracts, one-command local stack, green CI

### Phase 1 – Core Loop MVP (1 sprint)

**Goal**: Make the game playable with server-side authority

- **StartSegment Lambda**: Validate character, set segment timer, return end time
- **ConcludeSegment Lambda**: Validate completion time, evaluate outcome, apply rewards
- **DynamoDB Tables**: StoryBlob (stories) and CharacterSheet (player state)
- **Minimal Client**: Flutter countdown timer and outcome display
- **Observability**: CloudWatch metrics for segments started/completed

**Deliverable**: Complete game loop with one hard-coded story

### Phase 2 – Content Pipeline (1 sprint)

**Goal**: Enable dynamic content without backend changes

- Git-to-S3 story publishing on merge
- Story index manifest for browsing
- Client dynamic story loading
- Revision handling for live updates
- Content validation hooks

**Deliverable**: Non-developers can publish stories; live updates work

### Phase 3 – Progression Features (2 sprints)

**Goal**: Add depth with prestige and branching

- Prestige system with multipliers
- Branching story paths (weighted random)
- Rest and abandon mechanics
- Extended analytics for game balance

**Deliverable**: Complete idle RPG loop with meaningful progression

### Phase 4 – Scale Hardening (as needed)

**Goal**: Production readiness

- Lambda provisioned concurrency
- CloudWatch Synthetics monitoring
- Cost controls and autoscaling
- Security review and WAF

**Deliverable**: SLA-ready module supporting 100k DAU

## Game Systems

### Story Structure

Stories are JSON documents containing:

- Metadata (title, minLevel, heroImageUrl)
- Ordered array of segments
- Each segment includes:
  - Display text and duration
  - Challenge definition (skill/attribute requirements)
  - Outcomes (critSuccess, success, neutral, fail, death)
  - Rewards and next segment references

### Character Progression

Based on the Eidolon Engine MUD mechanics:

#### Attributes

- **Physical**: Strength, Agility, Endurance
- **Mental**: Intelligence, Perception, Cunning
- **Social**: Charisma, Presence, Intrigue

#### Skills

- **Combat**: Melee, Archery, Brawling, Dodge, Parry
- **Stealth**: Stealth, Investigation, Tumbling, Climbing, Lockpicking
- **Magic**: Mythos, Arcane
- **Survival**: First Aid, Foraging, Appraise

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
- **Prestige System**: Reset for permanent multipliers

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
- `POST /prestige`: Reset character with multipliers
- `POST /abandon`: Cancel current segment with penalty

### Data Models

#### CharacterSheet

```json
{
  "playerId": "string",
  "attributes": {
    /* strength, agility, etc. */
  },
  "skills": {
    /* melee, stealth, etc. */
  },
  "inventory": {
    /* items and currencies */
  },
  "activeStory": {
    "storyId": "string",
    "segmentId": "string",
    "endsAt": "timestamp",
    "revision": "number"
  },
  "prestigeLevel": 0,
  "lockToken": "string"
}
```

#### StoryBlob

```json
{
  "storyId": "string",
  "title": "string",
  "minLevel": 1,
  "revision": 1,
  "segments": [
    {
      "id": "string",
      "text": "string",
      "duration": 300,
      "challenge": {
        "skill": "melee",
        "attribute": "strength",
        "difficulty": 5
      },
      "outcomes": {
        "critSuccess": { "xp": 1.0, "gold": 10, "next": "segment2" },
        "success": { "xp": 0.25, "gold": 5, "next": "segment2" },
        "neutral": { "xp": 0.125, "gold": 2, "next": "segment2" },
        "fail": { "xp": 0.125, "gold": 0, "next": "segment2" },
        "death": { "xp": 0, "gold": 0, "next": "respawn" }
      }
    }
  ]
}
```

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
