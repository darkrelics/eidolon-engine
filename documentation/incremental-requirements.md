# Incremental Game Requirements

## 1. Executive Summary

This document defines the functional and non-functional requirements for the Incremental Game component of the Eidolon Engine. The system must provide timer-based story progression that allows players to experience narrative gameplay through automated mechanics while maintaining character compatibility with the MUD.

## 2. Functional Requirements

### 2.1 Story Management

**FR-001**: The system SHALL provide three types of stories:

- One-time: Playable once per character lifetime
- Daily: Resets availability at midnight UTC
- Repeatable: No cooldown restrictions

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

**FR-006**: Characters SHALL maintain a single game mode at a time (MUD, Incremental, or None).

**FR-007**: Character state SHALL persist across modes including:

- Wounds and health status
- Inventory and equipment
- Skills and attributes
- Room location

**FR-008**: The system SHALL prevent concurrent access to both game modes.

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

**NFR-001**: Support 10,000 concurrent incremental players.

**NFR-002**: API response time SHALL be less than 2 seconds.

**NFR-003**: Segment processing SHALL complete promptly (target under 1 minute per poll cycle).

**NFR-004**: UI updates SHALL reflect state changes within 1 second of polling.

### 3.2 Scalability

**NFR-005**: The system SHALL scale automatically based on player load.

**NFR-006**: Database operations SHALL use on-demand scaling.

**NFR-007**: Processing capacity SHALL handle peak loads without degradation.

### 3.3 Reliability

**NFR-008**: System availability SHALL exceed 99.9%.

**NFR-009**: Failed segment processing SHALL automatically retry.

**NFR-010**: Character state SHALL remain consistent during failures.

### 3.4 Security

**NFR-011**: All API endpoints SHALL require authentication.

**NFR-012**: Character ownership SHALL be verified for all operations.

**NFR-013**: Outcome calculations SHALL occur server-side only.

### 3.5 Usability

**NFR-014**: New players SHALL understand gameplay within 5 minutes.

**NFR-015**: Story selection SHALL clearly show requirements and availability.

**NFR-016**: Progress indicators SHALL accurately reflect completion status.

### 3.6 Compatibility

**NFR-017**: The system SHALL use existing authentication infrastructure.

**NFR-018**: Character data SHALL remain compatible with MUD systems.

**NFR-019**: The interface SHALL function on modern web browsers.

## 4. Constraints

### 4.1 Technical Constraints

**CON-001**: Must use AWS serverless architecture.

**CON-002**: Must integrate with existing DynamoDB tables.

**CON-003**: Must use Flutter for web interface.

**CON-004**: Must maintain single-player experience only.

### 4.2 Business Constraints

**CON-005**: Progression rate must not exceed MUD advancement speed.

**CON-006**: Infrastructure costs must remain under $500/month for 10,000 users.

## 5. Acceptance Criteria

### 5.1 Functional Acceptance

- Successfully complete stories of all three types
- Seamless character transitions between game modes
- Proper timeout handling with default decisions
- Equipment and wound persistence across modes

### 5.2 Performance Acceptance

- Support 10,000 concurrent users without degradation
- Meet all response time requirements
- Achieve 99.9% availability over 30 days
