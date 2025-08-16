# Lambda Function Rework and Alignment Assessment

## Overview

This document provides a comprehensive assessment of the 16 Lambda functions in the Eidolon Engine's incremental game system, evaluating their alignment with the documented design and identifying any necessary rework items.

## Key System Understanding

### Automatic Wound Healing

The `character_get` function in `eidolon/character_data.py` automatically handles time-based wound healing:

- Heals wounds when `HealedAt` timestamp has passed
- Updates character state from "unconscious" to "standing" when healed
- Persists healing changes to database
- Calculates current health as `MaxHealth - len(wounds)`
- Healing progress shown each time character is loaded

### Rest Segments

Rest segments serve two distinct purposes:

1. **During Stories**: Player-requested breaks that allow recovery time within the story flow
2. **Outside Stories**: REST capabilities available when no story is active (future implementation)

**Impact**: Rest segments are gameplay mechanics that leverage time as a resource, not just UI elements. The healing happens automatically via `character_get`, but rest segments provide strategic recovery opportunities.

## Lambda Function Checklist

### API Functions (12 Functions)

#### ✅ api-archetype-list

- [x] Returns player-available archetypes
- [x] Filters by `Player: true` flag
- [x] Caches at cold start
- [x] PascalCase response format
- **Status**: ALIGNED - No changes needed

#### ✅ api-character-add

- [x] Validates character name and limit
- [x] Creates from archetype template
- [x] Initializes starting items
- [x] Sets initial GameMode="None"
- **Status**: ALIGNED - No changes needed

#### ✅ api-character-delete

- [x] Validates character ownership
- [x] Removes from player's character list
- [x] Cleans up character data
- **Status**: ALIGNED - No changes needed

#### ✅ api-character-get

- [x] Validates character ownership
- [x] Enriches with inventory details
- [x] Includes active story/segment if present
- [x] Returns available stories when no active story
- **Status**: ALIGNED - No changes needed

#### ✅ api-character-list

- [x] Returns all characters for authenticated player
- [x] Includes dead status
- [x] No caching for fresh data
- **Status**: ALIGNED - No changes needed

#### ✅ api-story-start

- [x] Validates prerequisites and GameMode="None"
- [x] Creates active segment with pre-calculated outcomes
- [x] Atomically updates character state
- [x] Queues mechanical segments to processing queue
- [x] Enables polling infrastructure
- [x] Creates story history entry
- **Status**: ALIGNED - No changes needed

#### ✅ api-story-abandon

- [x] Validates character in Incremental mode
- [x] Immediately resets character GameMode
- [x] Adds to AbandonedStories list
- [x] Records in story history
- [x] Deletes active segment
- **Status**: ALIGNED - No changes needed

#### ✅ api-segment-decision

- [x] Records player choice in Decision field
- [x] Sets DecisionMadeAt timestamp
- [x] Validates segment ownership
- **Status**: ALIGNED - No changes needed

#### ✅ api-segment-outcome

- [x] Retrieves completed segment results
- [x] Falls back to segment_history if active segment deleted
- [x] Returns narrative and effects based on outcome
- [x] Includes next segment ID
- **Status**: ALIGNED - No changes needed

#### ✅ api-segment-status

- [x] Returns completion status and time remaining
- [x] Includes results if segment complete
- [x] Validates character ownership
- **Status**: ALIGNED - No changes needed

#### ✅ api-segment-history

- [x] Queries completed segments for active story
- [x] Returns enriched segment data
- [x] Sorts by start time (newest first)
- **Status**: ALIGNED - No changes needed

#### ✅ api-segment-rest

- [x] Creates rest segment for story break/recovery
- [x] Validates character state
- [x] Requires active story (correct - rest segment is story mechanic)
- [x] Requires active segment (correct - inserts rest into story flow)
- **Status**: ALIGNED - Correctly implements story-based rest mechanic

### Operational Functions (4 Functions)

#### ✅ ops-segment-poller (EventBridge triggered)

- [x] Queries EndTimeIndex for expired segments
- [x] Sends ALL completed segments to advancement queue
- [x] Handles stuck mechanical segments (>15 min)
- [x] Marks exhausted segments as "exceptional"
- [x] Auto-enables/disables polling based on active segments
- [x] Manages SSM parameter state
- **Status**: ALIGNED - No changes needed

#### ✅ ops-segment-process (SQS triggered)

- [x] Processes mechanical segments only
- [x] Validates message schema
- [x] Claims segment with RunningFlag
- [x] Uses MUD mechanics for calculations
- [x] Generates ClientEvents array
- [x] Invalid messages not retried
- [x] Returns batchItemFailures for SQS
- **Status**: ALIGNED - No changes needed

#### ✅ ops-story-advance (SQS triggered)

- [x] Claims segment with RunningFlag for idempotency
- [x] Processes simple segments if needed
- [x] Applies CharacterUpdates and combat rewards
- [x] Creates next segment or completes story
- [x] Records segment/story history
- [x] Handles death/unconscious outcomes
- [x] Deletes processed segments
- [x] Updates polling state when no segments remain
- **Status**: ALIGNED - No changes needed

#### ✅ cognito-player-new (Cognito PostConfirmation trigger)

- [x] Creates player record in DynamoDB
- [x] Initializes empty CharacterList
- [x] Sets proper timestamps
- **Status**: ALIGNED - No changes needed

## Message Passing and State Machines

### Message Flow ✅

```
EventBridge → Poller → SQS Queues → Processors
                ↓            ↓
         Processing Q   Advancement Q
                ↓            ↓
         ops-segment-   ops-story-
           process        advance
```

### Message Validation ✅

- **Processing Queue**: Requires ActiveSegmentID, CharacterID, StoryID, SegmentID, SegmentType
- **Advancement Queue**: Requires only ActiveSegmentID
- Invalid messages are dropped (not retried) to prevent poison messages

### Story State Machine ✅

```
Available → Active → Completed/Abandoned
```

- Atomic transitions with conditional checks
- GameMode field prevents concurrent play
- Proper cleanup on completion/abandonment

### Segment State Machine ✅

```
pending → processing → processed → completed → [deleted]
```

- RunningFlag prevents concurrent processing
- Idempotent operations via claim_segment_for_processing
- Automatic timeout handling for stuck segments

## Critical System Features

### Concurrency Control ✅

- **RunningFlag**: Prevents duplicate processing
- **Conditional Updates**: DynamoDB conditions prevent race conditions
- **Atomic Operations**: Story state changes are transactional

### Error Handling ✅

- **SQS Batch Failures**: Failed messages returned for retry
- **Invalid Messages**: Logged but not retried
- **Stuck Segments**: Auto-marked as "exceptional" after timeout
- **Graceful Degradation**: Players get best outcome on failures

### Front-loaded Processing ✅

- All outcomes calculated when segments start
- ClientEvents pre-generated
- CharacterUpdates determined upfront

## Rework Items

### 1. Documentation Updates

**Required Changes**:

- Update incremental-story.md to clarify wound healing is automatic via `character_get`
- Document that rest segments are strategic gameplay mechanics, not just UI timers
- Clarify that rest segments during stories allow recovery breaks as part of time management
- Note future REST capabilities will be available outside story context

**Priority**: MEDIUM - Important for developer understanding

## System Alignment Summary

### Overall Assessment: 100% Aligned

**Strengths**:

- Message passing correctly implemented
- State machines match documented design
- Proper error handling and idempotency
- Concurrency control well-implemented
- Front-loaded processing as designed
- Rest segments correctly require story context
- Time-based mechanics properly integrated

**Documentation Needs**:

- Clarification on automatic healing via `character_get`
- Rest segments as strategic gameplay elements

**No Issues With**:

- Story state transitions
- Segment processing flow
- Queue message routing
- Polling infrastructure
- History recording
- Character state management

## Validation Checklist for Lambda Functions

When evaluating Lambda functions, verify:

### 1. Infrastructure

- [ ] Uses shared execution role: `eidolon-lambda-execution-role`
- [ ] Has DynamoDB policy with DescribeTable permission
- [ ] Fixed logical ID preventing recreation
- [ ] Environment variables properly configured
- [ ] CORS handled via environment variables

### 2. Error Handling

- [ ] Returns appropriate HTTP status codes
- [ ] Includes descriptive error messages
- [ ] Handles preflight requests
- [ ] Validates JWT authentication
- [ ] Checks character ownership

### 3. Data Consistency

- [ ] Uses PascalCase for response fields
- [ ] Validates UUID formats
- [ ] Performs atomic operations where needed
- [ ] Handles missing/invalid data gracefully

### 4. Business Logic

- [ ] Follows documented state machines
- [ ] Implements front-loaded processing
- [ ] Maintains idempotency
- [ ] Prevents concurrent access issues

### 5. SQS Integration (if applicable)

- [ ] Validates message schema
- [ ] Returns batchItemFailures
- [ ] Drops invalid messages (no retry)
- [ ] Logs processing summary

### 6. Performance

- [ ] Caches where appropriate
- [ ] Minimizes DynamoDB calls
- [ ] Uses GSI efficiently
- [ ] Completes within timeout limits

## Conclusion

The Lambda functions are well-implemented and closely aligned with the documented design. The message passing and state machine operations are robust and production-ready. Only minor adjustments are needed, primarily around rest segment flexibility for future enhancements. The system correctly handles normal flow, error conditions, concurrent access, and edge cases.
