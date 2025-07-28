# Eidolon Engine Incremental Game Requirements Document

## 1. Executive Summary

This document outlines the functional and design requirements for the Incremental Game component of the Eidolon Engine. The Incremental Game mode provides a timer-based story progression system that allows players to experience narrative-driven gameplay through automated mechanics while maintaining character progression compatibility with the MUD component.

## 2. System Overview

### 2.1 Purpose

The Incremental Game component provides an alternative gameplay mode to the traditional MUD experience, allowing players to:

- Progress through story-driven content with timed segments
- Make meaningful decisions that affect narrative outcomes
- Maintain character progression across both Incremental and MUD modes
- Experience automated gameplay mechanics based on character attributes

### 2.2 Key Features

- Story-based progression with decision and narrative segments
- Timer-based gameplay (1 minute to 24 hours per segment)
- Character state persistence across game modes
- Equipment management interface
- Support for 10,000 concurrent users
- Three story types: one-time, daily, and repeatable
- Progression rate limited to match MUD gameplay speed

## 3. Functional Requirements

### 3.1 User Interface Requirements

#### 3.1.1 Story Display Screen

- **Primary Display Area**: Shows current story text with optional accompanying image
- **Story Progress Indicator**: Visual representation of current position within the story
- **Timer Display**: Shows remaining time until next segment becomes available
- **Character Status Bar**: Displays key character stats (Health, Experience, Current Equipment)

#### 3.1.2 Decision Interface

For decision segments, the interface must display:

- **Decision Text**: Clear description of the current choice
- **Option Buttons**: Selectable options for the player's decision
- **Time Limit Indicator**: If applicable, show countdown for decision timeout
- **Option Tooltips**: Display potential consequences or skill checks when hovering
- **Default Decision**: System calculates optimal choice based on character/world state for timeout scenarios

#### 3.1.3 Narrative Result Display

After each narrative segment completion:

- **Outcome Text**: Display one of five possible outcomes:
  - Death narrative
  - Failure narrative
  - Minimal success narrative
  - Normal success narrative
  - Exceptional success narrative
- **Rewards Summary**: Show changes to character sheet including:
  - Health changes
  - Experience gained
  - Equipment received
  - New room location

#### 3.1.4 Segment Completion Options

Present three action buttons:

- **Continue**: Proceed to next segment (if available)
- **Abandon Story**: Exit current story with confirmation dialog
- **Rest**: Pause story progression and restore character state

#### 3.1.5 Equipment Management Screen

- **Character Inventory Display**: Grid view of all possessed items
- **Equipment Slots**: Visual representation of equipped items by slot type
- **Item Details Panel**: Show item statistics and effects when selected
- **Shop Interface**: Purchase trivial items using character resources
- **Drag-and-Drop**: Allow equipment changes through intuitive UI interactions
- **Access Points**: Available from main menu, during rest periods, and outside of active stories

#### 3.1.6 Story Selection Screen

- **Available Stories List**: Display only stories meeting character prerequisites
- **Story Details**: Preview including:
  - Estimated completion time
  - Difficulty indicator
  - Potential rewards
- **Participation Status**: Show cooldowns for daily stories
- **Filter Options**: Sort by type, difficulty, or estimated time

### 3.2 Game Flow Requirements

#### 3.2.1 Story Participation Flow

1. System validates prerequisites and availability
2. Player selects story from available list
3. Character state transitions to Incremental mode via GameMode field
4. Story participation record created in ActiveSegments table
5. First segment (typically decision) is presented
6. Player makes decision, timeout triggers default decision based on character/world state
7. Narrative segment processes based on decision and character stats
8. Outcome is determined and displayed
9. Character sheet updates are applied
10. Player chooses to continue, abandon, or rest
11. Process repeats until story completion or abandonment

#### 3.2.2 Segment Processing Requirements

- **Minimum Segment Duration**: 1 minute
- **Maximum Segment Duration**: 24 hours
- **Processing Resolution**: 1 second (aligned with MUD ticker)
- **Processing Time Limit**: Lambda functions complete within 30 seconds
- **Auto-Progress**: Segments advance automatically after timer expiration
- **Offline Progression**: Calculate results for segments completed while offline
- **Default Decisions**: System determines optimal choice when player doesn't respond

### 3.3 Character State Management

#### 3.3.1 Mode Transition Requirements

- **Lock Mechanism**: GameMode field prevents simultaneous mode access
- **MUD Block**: Characters with GameMode="Incremental" cannot login to MUD
- **Incremental Block**: Characters with GameMode="MUD" cannot start incremental stories
- **Incremental to MUD**: Character must not have active story segments
- **MUD to Incremental**: Character must be logged out of MUD
- **Timeout Protection**: Automatic mode release after extended inactivity

#### 3.3.2 Story Participation Tracking

- **ActiveSegments Table**: Tracks active story participation per character
- **Current Segment**: Stored in ActiveSegments record
- **Completion History**: Maintained in Character table (CompletedStories field)
- **Daily Reset**: Clear daily story participation at server reset time
- **Cooldown Management**: Enforce story-specific cooldown periods
- **Available Stories**: Maintain list in character record

### 3.4 Story Types and Availability

#### 3.4.1 One-Time Stories

- Available once per character lifetime
- Cannot be re-entered after completion or abandonment
- Typically provide unique rewards or unlock content

#### 3.4.2 Daily Stories

- Reset availability at server midnight (UTC)
- Track last participation timestamp
- Provide consistent daily progression opportunities

#### 3.4.3 Repeatable Stories

- No cooldown restrictions
- May have diminishing rewards on repetition
- Used for farming or practice scenarios

### 3.5 Content Creation

#### 3.5.1 Story Authoring

- Stories authored using Twine's visual editor for branching narratives
- Twine to Incremental conversion tool transforms Twine format to game format
- Converted stories stored in DynamoDB Story and Segments tables
- Administrative tools for managing and updating story content

#### 3.5.2 Content Validation

- Schema validation ensures story structure integrity
- Prerequisite checking validates story requirements
- Combat balance verification for opponent statistics
- Reward rate validation to maintain progression balance

### 3.6 Integration Requirements

#### 3.6.1 MUD Compatibility

- Character attributes remain consistent across modes
- Equipment functions identically in both modes
- Room locations persist between mode switches
- Skills and abilities apply using same mechanics
- Shared DynamoDB tables for all character data

#### 3.6.2 Story Unlock Mechanisms

- Stories provided by character archetype on creation
- Stories unlocked through Incremental participation
- Stories unlocked through MUD participation
- Stories unlocked through external activity (TBD)
- Prerequisites based on skills or attributes
- Item or quest requirements
- Room-based story discovery

## 4. Design Requirements

### 4.1 Frontend Architecture (Flutter)

#### 4.1.1 Application Integration

The incremental game will be integrated into the existing portal structure:

```
portal/
├── lib/
│   ├── screens/
│   │   ├── incremental/
│   │   │   ├── story_selection_screen.dart
│   │   │   ├── story_display_screen.dart
│   │   │   ├── equipment_management_screen.dart
│   │   │   └── character_status_screen.dart
│   ├── services/
│   │   └── api_service.dart  # Extended with incremental endpoints
│   ├── models/
│   │   └── story.dart        # New story data models
│   └── providers/
│       └── incremental_state.dart  # New state management
```

#### 4.1.2 State Management Requirements

- **Global State**: Character data, active story, timer states
- **Local State**: UI interactions, form inputs
- **Persistence**: Cache story progress locally for offline viewing
- **Synchronization**: Polling-based updates from backend

#### 4.1.3 API Communication Layer

- **REST API Integration**: Reuse existing API Gateway endpoints
- **Polling Strategy**: Smart polling based on segment completion times
- **Authentication**: Existing Cognito token management
- **Error Handling**: Use standardized eidolon response patterns
- **Request Queue**: Buffer actions during poor connectivity

### 4.2 Backend Architecture

#### 4.2.1 Lambda Functions

New Lambda functions following existing patterns:

**api_get_stories**

- Retrieve available stories for character
- Filter based on prerequisites and cooldowns
- Return formatted story list

**api_start_story**

- Validate character can start story
- Use DynamoDB transaction to atomically:
  - Set GameMode to "Incremental"
  - Update AvailableStories and ActiveStoryID
  - Create ActiveSegments record
  - Create initial History entry
- Handle transaction conflicts gracefully
- Return first segment

**api_submit_decision**

- Record player decision
- Schedule next segment processing
- Return acknowledgment

**api_get_current_story**

- Retrieve current active story and segment state
- Calculate time remaining
- Return story metadata and segment data
- Include segment-specific fields (options for decisions, results for narratives, combat state)

**api_complete_segment**

- Process segment outcome
- Consider transaction approach based on frequency:
  - For story completion: Use transaction for atomic cleanup
  - For segment advancement: May use standard operations with idempotency
- Apply character updates (health, XP, inventory)
- Write History record
- Delete current segment
- Create next segment (if continuing)
- Advance to next segment or complete story

**api_abandon_story**

- Use DynamoDB transaction for atomic cleanup:
  - Clear active story and segments
  - Reset GameMode to "None"
  - Update AbandonedStories list
  - Create History abandonment record
- Apply abandonment penalties if any

#### 4.2.2 Database Schema (DynamoDB)

**Story Table**

```
{
  StoryID: String (HASH),
  Title: String,
  Description: String,
  NarrativeText: String,
  StoryType: String,  // one-time|daily|repeatable
  EstimatedDuration: Number,
  Prerequisites: Map,
  FirstSegmentID: String,
  CreatedAt: String,
  Version: Number
}
```

**Segments Table**

```
{
  StoryID: String (HASH),
  SegmentID: String (RANGE),
  SegmentType: String,  // decision|narrative|combat
  ShortStatus: String,
  SegmentDuration: Number,
  DecisionText: String,  // For decision segments
  DecisionOptions: Map,  // For decision segments
  NextSegmentID: String,  // For narrative/combat segments
  DefaultDecision: String,  // For decision segments
  Challenges: List,  // For narrative segments
  Combat: Map,  // For combat segments
  Results: Map  // For narrative/combat segments
}
```

**ActiveSegments Table**

```
{
  ActiveSegmentID: String (HASH),
  CharacterID: String,
  StoryID: String,
  SegmentID: String,
  StartTime: Number,
  EndTime: Number (GSI - EndTimeIndex),
  Decision: String,  // For decision segments
  ChallengeResults: List,  // For narrative segments
  CombatState: Map,  // For combat segments
  Outcome: String  // Final outcome
}
```

**Global Secondary Index:**

- **EndTimeIndex**: EndTime - For finding segments ready to process

_Note: Segments are deleted after processing. All segments in this table are implicitly active._

**Character Table (Extended Fields)**

```
{
  CharacterID: String (HASH),
  CharacterName: String (GSI - CharacterNameIndex),
  GameMode: String,  // MUD|Incremental|None
  AvailableStories: List[String],
  AbandonedStories: List[String],
  CompletedStories: List[String],
  ActiveStoryID: String,  // Current active story
  ActiveSegmentID: String,  // Current active segment
  // All other existing fields...
}
```

**Global Secondary Index:**

- **CharacterNameIndex**: CharacterName - For ensuring unique character names

**History Table**

```
{
  CharacterID: String (HASH),
  StoryID: String (RANGE),
  StoryTitle: String,        // Title of the story for display
  StartedAt: String,         // ISO timestamp when story began
  FinishedAt: String,        // ISO timestamp when story ended
  StoryType: String,         // one-time|daily|repeatable
  SegmentHistory: List[      // Detailed record of each segment
    {
      SegmentID: String,
      SegmentType: String,   // decision|narrative|combat
      Comment: String,       // Brief description of what happened
      Decision: String,      // For decision segments - player's choice text
      Outcome: String,       // For narrative/combat segments
      ResultText: String,    // Narrative text shown to player
      ChallengeResults: List,// For narrative segments
      FinalCombatState: Map, // For combat segments
      CompletedAt: String
    }
  ],
  FinalOutcome: String,      // death|failure|minimal|normal|exceptional
  TotalDuration: Number,     // Seconds from start to finish
  Rewards: Map,              // Aggregated rewards from story
  AbandonedCount: Number     // Times story was abandoned before completion
}
```

**Opponents Table**

```
{
  OpponentID: String (HASH),
  Name: String,
  Description: String,
  CombatRating: Number,     // Combined attack skill
  DefenseRating: Number,    // Combined defense skill
  DamageRating: Number,     // Combined damage potential
  Toughness: Number,        // Endurance for damage resistance
  ArmorRating: Number,      // Armor protection value
  Health: Number,           // Maximum health levels
  WeaponType: String,       // bashing|lethal|aggravated
  WeaponDamage: Number,     // Bonus damage from weapon
  LootTable: List[          // Items dropped on defeat
    {
      itemId: String,
      chance: Number
    }
  ],
  Tags: List[String],       // For filtering and searching
  CreatedAt: String         // ISO timestamp
}
```

### 4.3 Game Mechanics Integration

#### 4.3.1 Skill Check System

- Implement summarized skill checks for narrative segments
- Use same probability calculations as MUD combat
- Apply modifiers based on equipment and stats
- Support multiple simultaneous skill checks

#### 4.3.2 Combat Resolution

- Use full MUD combat mechanics including:
  - Two-stage resolution (hit check + damage check)
  - MUD wound system with time-based healing
  - Weapon and armor effects
  - Environmental modifiers
- Track opponent health levels dynamically
- Combat ends when:
  - Character reaches 0 health (death)
  - Opponent reaches 0 health (victory)
  - Maximum rounds reached (failure)
- Apply wounds that persist across segments
- Determine outcomes based on:
  - Death: Character reduced to 0 health
  - Failure: Max rounds reached without defeating opponent
  - Minimal: Victory with significant wounds
  - Normal: Victory with minor wounds
  - Exceptional: Victory without wounds

#### 4.3.3 Experience and Progression

- Award experience based on segment difficulty
- Scale rewards with character attributes and skills
- Apply same progression curves as MUD
- Track skill improvements from story actions
- **Critical**: Ensure progression rate never exceeds MUD gameplay speed

### 4.4 Performance and Scalability

#### 4.4.1 Concurrent User Support

- **Incremental Mode**: 10,000 concurrent users
- **Response Time**: < 2 seconds for all user actions
- **Lambda Concurrency**: Use default AWS limits
- **Database Capacity**: Pay-per-request (auto-scaling)

#### 4.4.2 Caching Strategy

- **Story Definitions**: Cache in Lambda memory
- **Character State**: Brief caching during active segments
- **Story Content**: Stored in DynamoDB Story and Segments tables

#### 4.4.3 Timing Service Architecture

- **EventBridge Rule**: Single rule triggers polling Lambda every 10 seconds
- **Lambda Processing**: Query EndTimeIndex GSI for completed segments
- **Batch Processing**: Process all ready segments in single invocation
- **Dynamic Scaling**: Enable/disable polling based on active story count
- **Failure Handling**: Retry logic with exponential backoff

### 4.5 Persistent Effects and Consequences

#### 4.5.1 Cross-Mode Persistence

All character modifications persist between game modes:

- **Wounds and Healing**:
  - Combat damage creates wounds using MUD damage system
  - Wounds heal based on real-time (bashing: 15min, lethal: 6hr, aggravated: 7d)
  - Character entering either mode retains all active wounds
  - Death in either mode requires appropriate resurrection

- **Inventory Persistence**:
  - Items gained from story segments appear in MUD inventory
  - Equipment worn affects combat calculations in both modes
  - Item destruction or loss persists across modes
  - Cursed items maintain their effects

- **Location Updates**:
  - Story effects can change character room location
  - Character appears in new room when returning to MUD
  - Death may transport to death realm (room 0 or configured)

- **Character Development**:
  - Experience gains apply to unified progression system
  - Skill improvements permanent across modes
  - Attribute modifications persist
  - Status effects (if implemented) carry over

#### 4.5.2 Implementation Requirements

- All character updates use existing DynamoDB patterns
- Wound application uses shared damage.go logic (when Lambda implementation exists)
- Item management uses existing inventory system
- Room changes update RoomID field directly

### 4.6 Security Requirements

#### 4.6.1 Authentication and Authorization

- AWS Cognito integration (existing)
- JWT token validation on all API calls
- Character ownership verification via PlayerID

#### 4.6.2 Anti-Cheat Measures

- Server-side validation of all game actions
- Timestamp verification for segment progression
- Rate limiting on API endpoints (existing)
- Outcome validation within defined parameters

### 4.7 Monitoring and Analytics

#### 4.7.1 Operational Metrics

- Lambda execution duration and errors
- API Gateway response times
- DynamoDB consumed capacity
- EventBridge rule execution

#### 4.7.2 Game Analytics

- Story completion rates
- Popular decision paths
- Average session duration
- Mode transition patterns
- Equipment usage statistics

#### 4.6.3 Audit Trail

- CloudWatch Logs for all progression events
- Structured logging using eidolon logger
- Standard retention policies

## 5. Technical Constraints

### 5.1 Platform Requirements

- Flutter 3.32+ for web application
- AWS Lambda with Python 3.12+ runtime
- DynamoDB with existing table structure
- API Gateway REST APIs (existing)
- EventBridge for timing (replaces Fargate)
- CloudWatch for logging and monitoring

### 5.2 Integration Constraints

- Maintain compatibility with existing MUD character system
- Use existing shared tables (no separate incremental tables)
- Preserve all game mechanics calculations
- Support future addition of new story types
- Single-player experience only
- Progression rate limited to MUD speed

## 6. Data Management

### 6.1 Character Data Integrity

- **GUIDANCE**: Use DynamoDB transactions for critical multi-table operations where atomicity is required
- Consider capacity costs (2x standard operations) when designing transaction boundaries
- GameMode field ensures mode exclusivity
- CloudWatch audit trail for progression events
- Standard backup and recovery procedures

#### 6.1.1 Transaction Design Patterns

Operations that benefit from DynamoDB transactions:

1. **Story Start** (Recommended Transaction):
   - Update Character table (GameMode, ActiveStoryID, AvailableStories)
   - Create ActiveSegments record
   - Create initial History entry
   - **Rationale**: Prevents orphaned segments if character update fails

2. **Story Completion/Abandonment** (Recommended Transaction):
   - Update Character table (GameMode to "None", story lists)
   - Create final History entry
   - Delete ActiveSegment(s)
   - **Rationale**: Ensures clean state transitions

3. **Character Creation with Items** (Optional Transaction):
   - Create Character record
   - Update Player's character list
   - Create initial Item records
   - **Rationale**: May use eventual consistency if items can be recreated

4. **Segment Processing** (Consider Non-Transactional):
   - Character updates (health, XP, location)
   - History recording
   - **Rationale**: High frequency operation; consider idempotent design instead

5. **Combat Rewards** (Mixed Approach):
   - Character health/wounds updates (standard operation)
   - Item creation and inventory updates (transaction if critical)
   - **Rationale**: Balance consistency needs with performance

#### 6.1.2 Transaction Alternatives

For high-frequency operations, consider:
- Idempotent operations with unique request IDs
- Conditional updates with version numbers
- Event sourcing with eventual consistency
- Compensating transactions for rollback

### 6.2 Timing Service Management

- Single EventBridge rule for all segment polling
- Automatic cleanup of completed segments (deletion from ActiveSegments)
- Lambda functions query GSI for time-based processing
- CloudWatch monitoring of timing accuracy
- Dynamic enable/disable based on active story presence

## 7. Acceptance Criteria

### 7.1 Functional Acceptance

- Successfully complete all three story types
- Seamless character transition between modes
- Equipment changes persist across modes
- Proper timeout handling with default decisions
- Mode exclusivity enforced via GameMode field

### 7.2 Performance Acceptance

- Support 10,000 concurrent incremental users
- Lambda execution under 30 seconds
- Page load time under 3 seconds
- 99.9% API availability
- Character progression rate ≤ MUD progression rate

### 7.3 User Experience Acceptance

- Intuitive story navigation
- Clear outcome communication
- Responsive design across devices
- Accessible to screen readers

## 8. Implementation Priorities

### 8.1 Phase 1: Core Story System

- Story definition table and Lambda functions
- Basic story flow (start, decision, complete)
- GameMode enforcement
- Simple timer implementation

### 8.2 Phase 2: Flutter Integration

- Story selection and display screens
- API service extensions
- Basic polling implementation
- Error handling integration

### 8.3 Phase 3: Advanced Features

- Equipment management
- Daily/repeatable stories
- Story unlocking mechanisms
- Performance optimization

## 9. Simplified Architecture Benefits

### 9.1 Reduced Complexity

- Reuse existing Lambda patterns
- Shared tables eliminate data synchronization
- Standard error handling via eidolon package

### 9.2 Cost Optimization

- Serverless pricing model
- No always-on container costs
- Efficient use of existing infrastructure
- Pay-per-use scaling

### 9.3 Maintenance Benefits

- Consistent patterns across all Lambda functions
- Single deployment pipeline
- Unified monitoring and logging
- Simplified debugging
