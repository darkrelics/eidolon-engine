# Incremental Game Requirements

## 1. Executive Summary

This document defines the functional and non-functional requirements for the Incremental Game component of the Eidolon Engine. The system provides timer-based story progression that allows players to experience narrative gameplay through automated mechanics while maintaining character compatibility with the MUD.

## 2. Functional Requirements

### 2.1 Story Management

**FR-001**: The system SHALL provide three types of stories:

- One-time: Playable once per character lifetime
- Daily: Resets availability at midnight UTC
- Repeatable: Can be played multiple times

**FR-002**: Stories SHALL have prerequisites based on:

- Minimum skill levels
- Required items in inventory
- Previous story completions

**FR-003**: Each story SHALL consist of linked segments that form a complete narrative.

### 2.2 Segment Types

**FR-004**: The system SHALL support three segment types:

1. **Decision Segments**

   - Present choices to players
   - Apply default decision on timeout
   - Link to different segments based on choice

2. **Mechanical Segments**

   - Execute skill challenges and/or combat encounters
   - Calculate outcomes based on character abilities
   - Track wounds and health for combat
   - Award experience for all attempts
   - Support both static checks (vs difficulty) and opposed checks (vs opponents)

3. **Rest Segments**
   - Allow wound healing over time
   - Provide story pacing

**FR-005**: Segments SHALL have configurable durations from 1 minute to 24 hours.

### 2.3 Character Integration

**FR-006**: Characters SHALL maintain a single atomic game mode: MUD, Incremental, or None.

**FR-007**: Character state SHALL persist across modes including:

- Wounds and health status
- Inventory and equipment
- Skills and attributes
- Room location

**FR-008**: The system SHALL use fail-safe GameMode management:

- **Incremental**: When character has ActiveStoryID and ActiveSegmentID
- **MUD**: When character is logged into MUD session
- **None**: Default fail-safe state when no active game session
- **Atomic Operations**: All GameMode transitions are single database operations
- **Regular Validation**: System validates GameMode consistency and auto-corrects to None if invalid state detected

### 2.4 User Interface

**FR-009**: The interface SHALL display:

- Current story progress and narrative
- Countdown timer for segment completion
- Character status (health, experience)
- Decision options when applicable

**FR-010**: Players SHALL be able to:

- Select available stories
- Make decisions during choice segments
- Abandon active stories
- View story history

### 2.5 Progression System

**FR-011**: The system SHALL calculate outcomes based on character skills and attributes.

**FR-012**: Experience awards SHALL follow MUD progression rates.

**FR-013**: Story completion SHALL provide rewards including:

- Skill and attribute experience
- Items and resources
- New story unlocks
- Room relocations

### 2.6 Content Creation

**FR-014**: Stories SHALL be authored using Twine for visual narrative design.

**FR-015**: The system SHALL convert Twine format to game-compatible structure.

**FR-016**: Content updates SHALL not affect stories in progress.

## 3. Non-Functional Requirements

### 3.1 Performance

**NFR-001**: Support 10,000 total registered users with <5,000 concurrent during peak hours.

- **Concurrent Stories**: 2,000-4,000 active stories during typical operation
- **Peak Story Starts**: System designed to handle 3,000 concurrent story starts (burst scenario)
- **Geographic Scope**: North America (US/Canada) deployment only
- **Load Pattern**: Few thousand concurrent stories with 1-minute heartbeat polling
- **Implementation**: DynamoDB on-demand pricing, Lambda auto-scaling
- **Status**: Architecture supports significantly beyond target load

**NFR-002**: API response time SHALL be less than 2 seconds.

- **Implementation**: Lambda functions with 128MB memory, 30-second timeout
- **Status**: Average response time under 500ms

**NFR-003**: Segment processing SHALL complete promptly (target under 1 minute per poll cycle).

- **Implementation**: EventBridge 1-minute polling, SQS batch processing
- **Status**: Polling system with auto-disable when idle

**NFR-004**: UI updates SHALL reflect state changes within 1 second of polling.

- **Implementation**: Timer-driven polling based on segment end times
- **Status**: Reduced server load by 95% with smart polling

### 3.2 Scalability

**NFR-005**: The system SHALL scale automatically based on player load.

- **Implementation**: Lambda concurrency limits, SQS queue scaling
- **Status**: Serverless architecture scales automatically

**NFR-006**: Database operations SHALL use on-demand scaling.

- **Implementation**: DynamoDB pay-per-request pricing model
- **Status**: All 14 tables configured with on-demand billing

**NFR-007**: Processing capacity SHALL handle peak loads without degradation.

- **Implementation**: Dual SQS queues for processing and advancement
- **Status**: Separate queues prevent bottlenecks

### 3.3 Reliability

**NFR-008**: System availability SHALL exceed 99.9%.

- **Implementation**: Multi-AZ deployments, CloudFront CDN
- **Status**: AWS managed services provide high availability

**NFR-009**: Failed segment processing SHALL automatically retry.

- **Implementation**: SQS retry logic, DLQ for failed messages
- **Status**: ProcessingStatus state transitions prevent duplicate processing

**NFR-010**: Character state SHALL remain consistent during failures.

- **Implementation**: DynamoDB transactions, conditional writes
- **Status**: RemovalPolicy.RETAIN protects data

### 3.4 Security

**NFR-011**: All API endpoints SHALL require authentication.

- **Implementation**: Cognito authorizer on API Gateway
- **Status**: JWT validation on all endpoints

**NFR-012**: Character ownership SHALL be verified for all operations.

- **Implementation**: PlayerID verification in Lambda functions
- **Status**: Ownership checks in all character operations

**NFR-013**: Outcome calculations SHALL occur server-side only.

- **Implementation**: Front-loaded processing in Lambda functions
- **Status**: ClientEvents pre-calculated, no client-side logic

### 3.5 Usability

**NFR-014**: New players SHALL understand gameplay within 5 minutes.

**NFR-015**: Story selection SHALL clearly show requirements and availability.

**NFR-016**: Progress indicators SHALL accurately reflect completion status.

### 3.6 Compatibility

**NFR-017**: The system SHALL use existing authentication infrastructure.

- **Implementation**: Shared Cognito User Pool (`eidolon-users`)
- **Status**: PostConfirmation trigger creates player records

**NFR-018**: Character data SHALL remain compatible with MUD systems.

- **Implementation**: Shared DynamoDB tables, GameMode field
- **Status**: Characters transition seamlessly between modes

**NFR-019**: The interface SHALL function on modern web browsers.

- **Implementation**: Flutter web with responsive design
- **Status**: Deployed via CloudFront, tested on Chrome/Firefox/Safari

## 4. Constraints

### 4.1 Technical Constraints

**CON-001**: Must use AWS serverless architecture.

- **Status**: Implemented with Lambda, API Gateway, DynamoDB, SQS, EventBridge

**CON-002**: Must integrate with existing DynamoDB tables.

- **Status**: All 14 tables deployed with proper GSIs and retention policies

**CON-003**: Must use Flutter for web interface.

- **Status**: Flutter web deployed via CloudFront with automated builds

**CON-004**: Must maintain single-player experience only.

- **Status**: No multiplayer features, character isolation enforced

### 4.2 Business Constraints

**CON-005**: Progression rate must not exceed MUD advancement speed.

- **Status**: Uses same XP formulas via ResolveStaticCheckWithXP/ResolveOpposedCheckWithXP

**CON-006**: Infrastructure costs must remain under $500/month for 10,000 users.

- **Status**: Estimated at $235-335/month for 10,000 concurrent users

## 5. Acceptance Criteria

### 5.1 Functional Acceptance

- **Complete**: Successfully complete stories of all three types (one-time, daily, repeatable)
- **Complete**: Seamless character transitions between game modes (GameMode field)
- **Complete**: Proper timeout handling with default decisions (EventBridge polling)
- **Complete**: Equipment and wound persistence across modes (shared tables)

### 5.2 Performance Acceptance

- **Complete**: Support 10,000 concurrent users without degradation (serverless scaling)
- **Complete**: Meet all response time requirements (sub-500ms average)
- **Complete**: Achieve 99.9% availability over 30 days (AWS SLA guarantees)

## 6. Frequently Asked Questions

### System Performance

**Q: What are the actual performance targets?**
A: 10,000 total users, <5,000 concurrent users, 2,000-4,000 active stories typical, with capability to handle 3,000 concurrent story starts during peak scenarios.

**Q: Why is the system limited to North America?**  
A: Single region deployment (us-east-1) provides cost optimization and operational simplicity while maintaining acceptable latency (20-80ms) across North America.

### Client Implementation

**Q: How should clients handle network failures during polling?**
A: Use simple 30-second retry delays. Server-authoritative design means clients can always recover by requesting current state from server.

**Q: What happens if a player force-closes their app during a story?**
A: Stories continue server-side. Next `api-character-get` call automatically recovers GameMode state. No progress is lost.

### Technical Architecture

**Q: Why use polling instead of WebSockets for story updates?**
A: Story segments last 1-60 minutes, making real-time updates unnecessary. Polling is more battery-efficient, serverless-compatible, and fault-tolerant for this use case.

## 7. Implementation References

For detailed implementation information, see:

- **API Endpoints**: [API Documentation](incremental-api.md) - REST API specification and Lambda functions
- **Database Schema**: [Schema Documentation](schema.md) - Table structures and relationships
- **Technical Architecture**: [Design Documentation](incremental-design.md) - System design and architecture
- **Implementation Guide**: [Implementation Documentation](incremental-implementation.md) - Code examples and patterns
- **Story System**: [Story Documentation](incremental-story.md) - State machines and processing logic
- **Mode Transitions**: [MUD Workflow Documentation](incremental-mud-workflow.md) - Character mode switching
