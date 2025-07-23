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
4. Story participation record created in story table
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
- **Transition Validation**: Verify character is not in combat or other locked states
- **Timeout Protection**: Automatic mode release after extended inactivity

#### 3.3.2 Story Participation Tracking

- **Story Table**: Tracks active/completed stories per character
- **Current Segment**: Stored in story participation record
- **Completion History**: Maintained in story table with timestamps
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

### 3.5 Integration Requirements

#### 3.5.1 MUD Compatibility

- Character attributes remain consistent across modes
- Equipment functions identically in both modes
- Room locations persist between mode switches
- Skills and abilities apply using same mechanics
- Shared DynamoDB tables for all character data

#### 3.5.2 Story Unlock Mechanisms

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
- Set GameMode to "Incremental"
- Initialize story participation record
- Return first segment

**api_submit_decision**

- Record player decision
- Schedule next segment processing
- Return acknowledgment

**api_get_segment**

- Retrieve current segment state
- Calculate time remaining
- Return segment data

**api_complete_segment**

- Process segment outcome
- Apply character updates
- Advance to next segment or complete story

**api_abandon_story**

- Clear active story
- Reset GameMode to "None"
- Apply abandonment penalties if any

#### 4.2.2 Database Schema (DynamoDB)

**Story Table (Existing, Extended)**

```
{
  PlayerID: String (PK),
  StoryID: String (SK),
  Status: String (active|completed|abandoned),
  CurrentSegment: String,
  SegmentStartTime: Number,
  NextCompletionTime: Number,
  Decisions: Map,
  Outcomes: List,
  StartTime: Number,
  CompletionTime: Number,
  TTL: Number  // For automatic cleanup
}
```

**Stories Definition Table (New)**

```
{
  StoryID: String (PK),
  StoryType: String (one-time|daily|repeatable),
  Title: String,
  Description: String,
  Prerequisites: Map,
  EstimatedDuration: Number,
  Segments: List[
    {
      SegmentID: String,
      Type: String (decision|narrative),
      Content: String,
      ImageUrl: String (optional),
      Duration: Number,
      Options: List (for decisions),
      DefaultDecisionLogic: String,
      Outcomes: Map (for narratives)
    }
  ]
}
```

**Character Table (Existing fields utilized)**

```
{
  CharacterID: String (PK),
  PlayerID: String,  // Existing attribute
  GameMode: String,  // Existing field (MUD|Incremental|None)
  AvailableStories: List[String],  // New field
  // All other existing MUD fields...
}
```

### 4.3 Game Mechanics Integration

#### 4.3.1 Skill Check System

- Implement summarized skill checks for narrative segments
- Use same probability calculations as MUD combat
- Apply modifiers based on equipment and stats
- Support multiple simultaneous skill checks

#### 4.3.2 Combat Resolution

- Abstract MUD combat into narrative outcomes
- Calculate damage/health changes over segment duration
- Apply same formulas but in bulk processing
- Maintain outcome log for review

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
- **Static Assets**: S3 with CloudFront distribution

#### 4.4.3 Timing Service Architecture

- **EventBridge Rules**: Schedule segment completions
- **Lambda Processing**: Handle completions at 1-second resolution
- **Batch Processing**: Group simultaneous completions
- **Failure Handling**: Retry logic with exponential backoff

### 4.5 Security Requirements

#### 4.5.1 Authentication and Authorization

- AWS Cognito integration (existing)
- JWT token validation on all API calls
- Character ownership verification via PlayerID

#### 4.5.2 Anti-Cheat Measures

- Server-side validation of all game actions
- Timestamp verification for segment progression
- Rate limiting on API endpoints (existing)
- Outcome validation within defined parameters

### 4.6 Monitoring and Analytics

#### 4.6.1 Operational Metrics

- Lambda execution duration and errors
- API Gateway response times
- DynamoDB consumed capacity
- EventBridge rule execution

#### 4.6.2 Game Analytics

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

- Use existing DynamoDB transaction patterns
- GameMode field ensures mode exclusivity
- CloudWatch audit trail for progression events
- Standard backup and recovery procedures

### 6.2 Timing Service Management

- EventBridge rules created per active segment
- Automatic cleanup of completed segments
- Lambda functions handle rule execution
- CloudWatch monitoring of timing accuracy

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

### 8.1 Phase 1: Core Story System (Weeks 1-3)

- Story definition table and Lambda functions
- Basic story flow (start, decision, complete)
- GameMode enforcement
- Simple timer implementation

### 8.2 Phase 2: Flutter Integration (Weeks 4-5)

- Story selection and display screens
- API service extensions
- Basic polling implementation
- Error handling integration

### 8.3 Phase 3: Advanced Features (Weeks 6-8)

- Equipment management
- Daily/repeatable stories
- Story unlocking mechanisms
- Performance optimization

## 9. Simplified Architecture Benefits

### 9.1 Reduced Complexity

- No Fargate container service needed
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
