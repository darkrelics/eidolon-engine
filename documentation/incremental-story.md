# Incremental Story and Segment State Machines

## Overview

The Eidolon Engine's incremental game mode features a story-driven progression system where characters navigate through interconnected segments that form complete narratives. Stories are composed of segments, which are time-based activities that advance automatically once initiated. This document describes the state machines that govern both stories and segments, as well as the Lambda functions that implement the state transitions.

### Core Concepts

- **Story**: A complete narrative arc available to characters based on their archetype and progress
- **Segment**: A single timed activity within a story (mechanical challenges, decisions, or rest periods)
- **Front-loaded Processing**: All outcomes are calculated when segments start, not when they end
- **Event-driven Advancement**: A polling system checks every minute for completed segments
- **Mode Exclusivity**: Characters can only be active in one game mode at a time (MUD or Incremental)

### Production Infrastructure

The story system is deployed as part of the 9-stack CDK architecture:

- **Story Stack**: Available in Incremental and Hybrid deployment modes
- **16 Lambda Functions**: Including 12 story-related functions
- **14 DynamoDB Tables**: 5 dedicated to story/segment data
- **SQS Queues**: Dual queues for processing and advancement
- **EventBridge**: 1-minute polling rule (auto-enabled when stories active)
- **Fixed Logical IDs**: Preventing resource recreation on updates

## Schema Elements

### Story Table

The Story table contains prototype definitions for all available stories:

- **StoryID** (HASH): UUID of the story
- **Title**: Display title of the story
- **StoryType**: one-time, daily, or repeatable
- **FirstSegmentID**: Starting segment UUID
- **Prerequisites**: Requirements to start (skills, items)
- **BaseXPMultiplier**: XP modifier (default 0.5, must be < 1.0)

### Segments Table

The Segments table contains prototype definitions for all story segments:

- **StoryID** (HASH): Parent story UUID
- **SegmentID** (RANGE): Segment UUID
- **SegmentType**: decision, mechanical, or rest
- **SegmentDuration**: Time in seconds for completion
- **DecisionOptions**: For decisions, maps choice ID to next segment ID
- **NextSegmentID**: For mechanical segments, the following segment
- **Challenges**: List of skill/attribute challenges
- **Combat**: Combat configuration if applicable

### ActiveSegments Table

The ActiveSegments table tracks currently running segment instances:

- **ActiveSegmentID** (HASH): Instance UUID
- **CharacterID** (GSI): Character UUID for querying
- **ProcessingStatus**: pending → processing → processed → completed
- **RunningFlag**: Claim flag to prevent concurrent processing
- **StartTime/EndTime**: Unix timestamps defining the segment window
- **ClientEvents**: Pre-calculated event sequence for display
- **CharacterUpdates**: Changes to apply on completion
- **Outcome**: death/failure/minimal/normal/exceptional

### StoryHistory Table

Records completed story attempts:

- **CharacterID** (HASH): Character UUID
- **StoryID** (RANGE): Story UUID
- **AttemptNumber** (RANGE): Increments per attempt
- **FinalOutcome**: Overall story result
- **XPEarned**: Total XP from all segments

### SegmentHistory Table

Archives completed segment instances:

- **CharacterID** (HASH): Character UUID
- **ActiveSegmentID** (RANGE): Instance UUID from ActiveSegments
- **All fields from ActiveSegments** are copied here
- **SkillXPAwarded/AttributeXPAwarded**: XP breakdown for analytics

## Story State Machine

### States

Stories exist in one of these states relative to a character:

1. **Available**: Listed in character's AvailableStories array
2. **Active**: Character has ActiveStoryID set
3. **Completed**: Listed in CompletedStories array
4. **Abandoned**: Listed in AbandonedStories array

### State Transitions

```
Available → Active
  Trigger: POST /stories/start
  Lambda: api-story-start
  Actions:
    - Create ActiveSegment record for first segment
    - Set character GameMode = "Incremental"
    - Set character ActiveStoryID and ActiveSegmentID
    - Queue mechanical segments for processing
    - Enable polling infrastructure
    - Create StoryHistory entry

Active → Completed
  Trigger: Final segment completes with non-terminal outcome
  Lambda: ops-story-advance
  Actions:
    - Apply final character updates and rewards
    - Move StoryID to CompletedStories
    - Clear ActiveStoryID and ActiveSegmentID
    - Set GameMode = "None"
    - Update StoryHistory with completion data
    - Delete ActiveSegment record

Active → Abandoned
  Trigger: POST /stories/abandon OR death/failure outcome
  Lambda: api-story-abandon OR ops-story-advance
  Actions:
    - Move StoryID to AbandonedStories
    - Clear ActiveStoryID and ActiveSegmentID
    - Set GameMode = "None"
    - Update StoryHistory as abandoned
    - Delete ActiveSegment record
```

### Story Lifecycle

1. **Initialization** (from prototype):
   - Story definitions loaded from Story table
   - Available stories determined by archetype and prerequisites
   - Added to character's AvailableStories list

2. **Activation**:
   - Player selects story via api-story-start
   - First segment copied from Segments table
   - ActiveSegment instance created with calculated outcomes
   - Character state atomically updated

3. **Progression**:
   - Segments advance one by one
   - Each segment completion triggers next segment creation
   - Story remains active until terminal outcome or completion

4. **Completion**:
   - Final segment processed by ops-story-advance
   - All rewards and effects applied
   - Story moved to history tables
   - Character returned to idle state

## Segment State Machine

### Processing Status States

Segments progress through these ProcessingStatus values:

1. **pending**: Initial state, awaiting processing
2. **processing**: Being processed by Lambda function
3. **processed**: Processing complete, awaiting timer expiry
4. **completed**: Timer expired, ready for advancement

### RunningFlag States

The RunningFlag provides concurrency control:

- **false**: Segment available for processing
- **true**: Segment claimed by a Lambda instance

### Complete State Transitions

```
Created → pending/false
  Trigger: Story start or previous segment advancement
  Lambda: api-story-start OR ops-story-advance
  Actions:
    - Create ActiveSegment record
    - Calculate all outcomes immediately
    - Generate ClientEvents array
    - Set timers (StartTime, EndTime)

pending/false → processing/true (Mechanical only)
  Trigger: ops-segment-poller finds segment ready
  Lambda: ops-segment-process (via SQS)
  Actions:
    - Claim segment with RunningFlag
    - Process challenges and combat
    - Apply XP and wounds immediately
    - Store results in segment

processing/true → processed/false
  Trigger: Processing completes
  Lambda: ops-segment-process
  Actions:
    - Update segment with results
    - Clear RunningFlag
    - Mark as processed

processed/false → completed/false
  Trigger: EndTime reached
  Lambda: ops-segment-poller
  Actions:
    - Send to advancement queue
    - No state change needed

completed/false → [deleted]
  Trigger: Story advancement
  Lambda: ops-story-advance
  Actions:
    - Apply CharacterUpdates
    - Create next segment or complete story
    - Copy to SegmentHistory
    - Delete from ActiveSegments
```

### Segment Types and Processing

#### Mechanical Segments

- Contain skill challenges and/or combat
- Processed by ops-segment-process via SQS
- XP and wounds applied during processing
- Outcomes: death/failure/minimal/normal/exceptional

#### Decision Segments

- Present choices to player
- No processing needed (outcome predetermined)
- Player submits via api-segment-decision
- Timeout uses DefaultDecision if specified

#### Rest Segments

Rest segments are special healing segments that allow characters to recover from wounds between story adventures. Unlike regular story segments, rest segments:

- Are initiated by the player via POST /segments/rest endpoint (handled by **api-segment-rest**)
- Provide healing over time based on wound severity
- Heal wounds based on type (bashing: 15min, lethal: 6hr, aggravated: 7d)
- Always have "normal" outcome with no decision points
- No special processing required - healing is automatic
- Can be initiated when character is not in an active story
- Create a temporary ActiveSegment that manages the healing process
- Character remains in "rest" mode until segment completion

### Segment Lifecycle

1. **Creation** (from prototype):
   - Segment definition loaded from Segments table
   - ActiveSegment instance created with UUID
   - All outcomes calculated immediately (front-loaded)
   - ClientEvents generated for entire duration

2. **Processing** (mechanical only):
   - Poller detects segment ready for processing
   - Queued to SQS for ops-segment-process
   - Challenges evaluated, combat simulated
   - XP and wounds applied to character

3. **Waiting**:
   - Segment timer runs (SegmentDuration)
   - Client displays events over time
   - No server processing during wait

4. **Advancement**:
   - Poller detects EndTime reached
   - Queued to SQS for ops-story-advance
   - Character updates applied
   - Next segment created or story completed

5. **Archival**:
   - All segment data copied to SegmentHistory
   - ActiveSegment record deleted
   - History preserved for analytics

## Lambda Function Machinery

### Production Configuration

All Lambda functions are deployed with:

- **Runtime**: Python 3.12
- **Memory**: 128MB
- **Timeout**: 30 seconds
- **Shared Execution Role**: `eidolon-lambda-execution-role`
- **DynamoDB Policy**: `eidolon-dynamodb-policy` with DescribeTable permission
- **Fixed Logical IDs**: Preventing recreation on stack updates
- **Post-Deployment Updates**: Functions updated from S3 artifacts

### API Layer Functions

**api-story-start** (Logical ID: `ApiStoryStartFunction`):

- Validates prerequisites and character state
- Creates first ActiveSegment with pre-calculated outcomes
- Updates character to active game mode (GameMode="Incremental")
- Queues mechanical segments to `eidolon-processing-queue`
- **Polling Management**: Sets SSM parameter to "run" AND enables EventBridge rule
- Environment: `SEGMENT_QUEUE_URL` for SQS integration

**api-segment-decision** (Logical ID: `ApiSegmentDecisionFunction`):

- Records player choice in Decision field
- Sets DecisionMadeAt timestamp
- Returns confirmation to client

**api-segment-outcome** (Logical ID: `ApiSegmentOutcomeFunction`):

- Retrieves completed segment results
- Returns narrative and effects
- Used by client after segment timer expires

**api-story-abandon** (Logical ID: `ApiStoryAbandonFunction`):

- Marks story as abandoned
- Clears character active state
- Records in StoryHistory

**api-segment-rest** (Logical ID: `ApiSegmentRestFunction`):

- Initiates healing rest for wounded characters
- Creates a special rest segment with calculated healing times
- Validates character is not in an active story
- Sets character GameMode to "Incremental" during rest
- Healing duration based on wound severity (bashing/lethal/aggravated)
- Automatically heals wounds when segment completes

### Processing Layer Functions

**ops-segment-poller** (Logical ID: `OpsSegmentPollerFunction`):

- **Trigger**: EventBridge rule `eidolon-segment-poller` (1-minute schedule)
- Reads SSM parameter `/eidolon/segment-poller-state` for "run"/"stop" state
- Queries for segments with EndTime <= now
- Sends ALL completed segments to `eidolon-advancement-queue`
- **Polling State Management**:
  - If parameter="run" and no segments found: Sets parameter to "stop"
  - If parameter="stop": Checks for active segments
    - If active segments exist: Sets parameter back to "run"
    - If no active segments: Disables EventBridge rule
- Environment: `SSM_POLLER_STATE_PARAMETER`, queue URLs

**ops-segment-process** (Logical ID: `OpsSegmentProcessFunction`):

- **Trigger**: SQS `eidolon-processing-queue`
- Claims segment with RunningFlag (prevents duplicates)
- Processes mechanical challenges and combat
- Applies XP and wounds immediately to character
- Updates segment with outcome and results
- **No polling management** - focused solely on segment processing
- Environment: `SEGMENT_BATCH_SIZE` for processing limits

**ops-story-advance** (Logical ID: `OpsStoryAdvanceFunction`):

- **Trigger**: SQS `eidolon-advancement-queue`
- Claims segment with RunningFlag for idempotency
- Processes simple segments (rest/decision) if not already processed
- Applies deferred CharacterUpdates (combat rewards, story effects)
- Creates next segment or completes story
- **Polling Management**: When story completes (next_segment_id is None):
  - Checks if any active segments remain
  - If none: Sets SSM parameter to "stop" (does NOT touch EventBridge)
- Resets GameMode="None" when story completes
- Writes to story_history and segment_history tables

### Queue Architecture

**Production Queue Configuration**:

**eidolon-processing-queue** (SQS Standard Queue):

- URL: `https://sqs.{region}.amazonaws.com/{account}/eidolon-processing-queue`
- Feeds ops-segment-process Lambda
- Handles mechanical segments only
- Message retention: 4 days
- Visibility timeout: 30 seconds
- Dead-letter queue after 3 retries

**eidolon-advancement-queue** (SQS Standard Queue):

- URL: `https://sqs.{region}.amazonaws.com/{account}/eidolon-advancement-queue`
- Feeds ops-story-advance Lambda
- Handles all segment types for completion
- Message retention: 4 days
- Visibility timeout: 30 seconds
- Dead-letter queue after 3 retries

### Polling Infrastructure

**SSM Parameter** (`/eidolon/segment-poller-state`):

- Stores polling state: "run" or "stop"
- Checked by poller each invocation
- **State Transitions**:
  - Set to "run" by: api-story-start, ops-segment-poller (when finding active segments)
  - Set to "stop" by: ops-story-advance (when completing last story), ops-segment-poller (when no segments to process)

**EventBridge Rule** (`eidolon-segment-poller`):

- Schedule: rate(1 minute)
- Target: ops-segment-poller Lambda
- State: DISABLED by default
- **Enable/Disable Authority**:
  - ONLY api-story-start can enable the rule
  - ONLY ops-segment-poller can disable the rule (when parameter="stop" and no active segments)
- Race condition window: <100ms between final check and disable (acceptable)

### Polling State Flow

The polling system follows this state machine:

```
1. INITIAL STATE: Parameter="stop", Rule=DISABLED
   └─> Player starts story (api-story-start)
       └─> Sets Parameter="run", Enables Rule → POLLING ACTIVE

2. POLLING ACTIVE: Parameter="run", Rule=ENABLED
   ├─> Poller finds no segments (ops-segment-poller)
   │   └─> Sets Parameter="stop" → POLLING STOPPED
   └─> Story completes with no other active segments (ops-story-advance)
       └─> Sets Parameter="stop" → POLLING STOPPED

3. POLLING STOPPED: Parameter="stop", Rule=ENABLED
   ├─> Poller finds active segments (ops-segment-poller)
   │   └─> Sets Parameter="run" → POLLING ACTIVE
   └─> Poller finds no active segments (ops-segment-poller)
       └─> Disables Rule → INITIAL STATE
```

**Key Design Principles**:
- Separation of concerns: SSM parameter controls polling behavior, EventBridge rule controls execution
- Single responsibility: Each Lambda has specific polling authority
- Graceful degradation: System continues even if polling management fails
- Cost optimization: Automatic shutdown when no stories active

## Error Recovery and Edge Cases

### Timeout Recovery

- Segments past EndTime marked "exceptional"
- Gives players best possible outcome
- Prevents indefinite waiting

### Stuck Segment Recovery

- Mechanical segments stuck >15 minutes get retried
- RunningFlag reset to allow reprocessing
- Maximum 3 retry attempts

### Concurrent Processing Prevention

- RunningFlag prevents duplicate processing
- Atomic DynamoDB operations ensure consistency
- SQS provides at-least-once delivery

### Failure Modes

**Processing Failure**:

- Segment remains in processing state
- Poller eventually marks as exceptional
- Player protected from system errors

**Queue Message Loss**:

- Poller re-queues unprocessed segments
- Idempotent processing prevents issues
- History tables provide audit trail

**Lambda Timeout**:

- RunningFlag remains set
- Poller detects stuck segment
- Automatic retry after 15 minutes

## Summary

The Eidolon Engine's incremental story system implements a robust state machine architecture that ensures reliable progression through narrative content. The front-loaded processing model calculates all outcomes when segments begin, allowing for predictable client experiences. The distributed Lambda architecture with SQS queuing provides scalability and fault tolerance, while the comprehensive history tracking enables analytics and debugging. The system prioritizes player experience by gracefully handling failures and providing automatic recovery mechanisms.
