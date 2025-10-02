# Release 1 Report — State Management, Atomic Updates, and Content Model Foundation

**Date:** 2025-10-02
**Branch:** inc-24
**Status:** In Progress
**Previous Release:** R0 (inc-23 deployed to AWS)

---

## Executive Summary

Release 1 focuses on backend logic robustness: making state transitions foolproof and updates atomic, while laying groundwork for story content management. This tackles Priority Items (1) and (2) head-on, ensuring subsequent features build on a solid foundation.

**Ship Gate:** Robust progression logic with no state corruption or duplicate rewards.

**Current Status (2025-10-02):** Task 1 Phase 1 complete (6 hours). State machine module created with atomic GameMode and ProcessingStatus transitions. Documentation updated with state diagrams. Unit tests and integration testing remain.

---

## R1 Objectives

1. **Formalize State Machines** — Prevent illegal state transitions in Character, Story, and Segment entities (Issue #491)
2. **Atomic Outcome Application** — Guarantee all-or-nothing effects with idempotency (Issue #726)
3. **Story Data Manifest** — Establish story index and content loading pipeline (Issue #605)
4. **API Documentation Alignment** — Ensure API docs match implementation (Issue #729)

---

## R1 Task List

### Task 1: Formalize and Enforce State Machines [Issue #491]

**Goal:** Prevent illegal or inconsistent state transitions in the incremental game loop.

**Priority:** HIGH (Priority Item #1)
**Status:** 🔄 In Progress (Phase 1 Complete)

#### Subtasks

| Subtask | Status | Notes |
|---------|--------|-------|
| Define Character GameMode state machine | ✅ Complete | GameMode enum with validation |
| Implement Segment ProcessingStatus transitions | ✅ Complete | Atomic claim/mark functions |
| Implement Story Lifecycle state machine | ✅ Complete | StoryLifecycle enum defined |
| Create state transition helper functions | ✅ Complete | state_machines.py module |
| Write unit tests for all transitions | ⏳ Pending | Valid + invalid transitions |
| Create state diagrams in documentation | ✅ Complete | 3 Mermaid diagrams in architecture.md |

**Implementation Details:**

**Character GameMode:**
- Allowed states: `{None, Incremental, MUD}`
- No direct MUD ↔ Incremental switch
- Character can only start story if `GameMode == None`
- Upon completion/abandonment, `GameMode` returns to `None`
- Helper function: `set_game_mode(character, new_mode)` with validation

**Segment ProcessingStatus:**
- States: `pending → processing → processed`
- Use conditional writes (DynamoDB) to enforce transitions
- Atomic claim: only set to `processing` if currently `pending`
- Idempotent: attempts to set `processed` twice fail gracefully

**Story Lifecycle:**
- States: `Available → Active → Completed/Abandoned`
- `api-story-start`: Only if `ActiveStoryID` is null
- On completion: Clear `ActiveStoryID`, set `GameMode = None`
- On abandonment: Move to `AbandonedStories`, clear active state

**Acceptance Criteria:**
- [ ] All unit tests for state transitions pass
- [x] Concurrent story start requests: only one succeeds, other blocked (conditional writes implemented)
- [ ] During full story run, logs show correct state transitions (pending integration testing)
- [x] Documentation updated with state diagrams
- [ ] Issue #491 can be closed (pending unit tests)

**Files Created:**
- `eidolon/state_machines.py` - State machine module with enums and transition functions

**Files Modified:**
- `eidolon/segment_polling.py` - Delegates to state machine for claim operation
- `eidolon/story_active.py` - Uses state machine for GameMode transitions
- `eidolon/character_story.py` - Uses state machine for reset operation
- `lambda/api_story_start.py` - Cleaned up imports (uses state machine via story_active)
- `documentation/architecture.md` - Added 3 state machine diagrams (lines 274-424)

**Phase 1 Accomplishments:**
- ✅ Created `state_machines.py` with GameMode, ProcessingStatus, StoryLifecycle enums
- ✅ Implemented `set_character_game_mode()` with atomic DynamoDB conditional writes
- ✅ Implemented `claim_segment_for_processing()` for atomic pending → processing transition
- ✅ Implemented `mark_segment_processed()` with idempotency support
- ✅ Added state diagrams to architecture.md (Character GameMode, Segment ProcessingStatus, Story Lifecycle)
- ✅ Updated existing code to use new state machine functions
- ✅ All linter checks passed

**Remaining Work:**
- Unit tests for all state transitions
- Integration testing with full story run

---

### Task 2: Ensure Atomic Application of Story Outcomes [Issue #726]

**Goal:** Guarantee effects are applied all-or-nothing with no duplicate rewards on retries.

**Priority:** HIGH (Priority Item #1)
**Status:** ⏳ Not Started

#### Subtasks

| Subtask | Status | Notes |
|---------|--------|-------|
| Design effects application routine | ⏳ Pending | Consolidate all updates |
| Implement idempotency key mechanism | ⏳ Pending | Use ActiveSegmentID |
| Add Currency field to Character schema | ⏳ Pending | Integer gold field |
| Implement currency rewards in outcomes | ⏳ Pending | story_rewards.py |
| Evaluate DynamoDB transactions vs conditionals | ⏳ Pending | Cost/complexity tradeoff |
| Write duplicate processing tests | ⏳ Pending | Verify no double rewards |
| Document atomicity approach | ⏳ Pending | In architecture.md |

**Implementation Details:**

**Effects Plan Consolidation:**
- When outcome determined, compile all updates: `{table_name: [updates]}`
- Example: +50 XP, new item, health update, room change
- Execute atomically using DynamoDB conditional writes

**Idempotency:**
- Use `ActiveSegmentID` as idempotency key
- `ProcessingStatus` prevents duplicate processing
- Consider `Characters.LastProcessedSegmentID` field
- Log segment ID in history to detect replays

**Currency Implementation:**
- Add `Gold` (integer) field to Character table
- Update schema to include `rewards.resources.gold`
- Implement currency increment in outcome application
- Add bounds checking (prevent overflow/negative)

**Transaction Strategy:**
- Current approach: conditional writes with `ProcessingStatus` guard
- DynamoDB transactions optional (higher cost, stronger atomicity)
- Group related updates with conditional expressions
- Set `SegmentOutcomeApplied = segmentID` in character update

**Acceptance Criteria:**
- [ ] Story completion yields consistent DB results
- [ ] Double-invocation of ops-story-advance doesn't duplicate rewards
- [ ] Currency rewards properly granted for stories that specify them
- [ ] Test logs confirm no partial updates in failure scenarios
- [ ] Issue #726 tasks completed (currency system implemented)

**Files to Modify/Create:**
- `eidolon/segment_processing.py`
- `eidolon/effects.py` (new)
- `eidolon/story_rewards.py`
- `eidolon/items.py`
- `eidolon/character_story.py`
- `deployment/stacks/dynamodb_stack.py` (add Currency field)
- `documentation/incremental-design.md`

---

### Task 3: Establish Story Data Manifest and Content Pipeline [Issue #605]

**Goal:** Introduce Story Index Manifest for client discovery and basic content loading.

**Priority:** MEDIUM (Priority Item #2)
**Status:** ⏳ Not Started

#### Subtasks

| Subtask | Status | Notes |
|---------|--------|-------|
| Design story-index.json manifest format | ⏳ Pending | Metadata fields |
| Create manifest generation script | ⏳ Pending | Query Story table |
| Determine manifest storage location | ⏳ Pending | S3 + CloudFront |
| Add missing Story table fields | ⏳ Pending | Difficulty, duration, etc. |
| Validate referential integrity | ⏳ Pending | Check segment links |
| Document content loading procedure | ⏳ Pending | For internal use |

**Implementation Details:**

**Manifest Format:**
```json
{
  "stories": [
    {
      "StoryID": "uuid",
      "Title": "string",
      "Description": "string",
      "StoryType": "one-time|daily|repeatable",
      "Difficulty": "1-10",
      "EstimatedDuration": "minutes",
      "Prerequisites": {
        "MinSkills": {"skill": level},
        "MinAttributes": {"attr": level}
      },
      "HeroImageURL": "url",
      "Recommended Level": number
    }
  ]
}
```

**Generation Process:**
- Python script queries all Story entries from DynamoDB
- Combines with additional metadata
- Produces `story-index.json`
- Initially manual, automated in R5

**Deployment:**
- Upload to client S3 bucket
- Accessible via CloudFront
- CloudFront invalidation on updates
- Client fetches via HTTPS GET

**Story Table Extensions:**
- Add `Difficulty` (number 1-10)
- Add `EstimatedDuration` (minutes, computed or manual)
- Add `HeroImageURL` (optional)
- Add `Active` flag for enable/disable

**Validation:**
- Verify `FirstSegmentID` exists in Segments table
- Check all `NextSegmentID` references valid
- Log warnings for incomplete stories
- Mark inactive if content errors found

**Acceptance Criteria:**
- [ ] System supports >1 story concurrently
- [ ] Generated manifest contains correct info for each story
- [ ] Manifest accessible via S3 URL or API endpoint
- [ ] No orphaned references in manifest generation log
- [ ] Issue #605 partially addressed (automation in R5)

**Files to Create/Modify:**
- `scripts/generate_story_index.py` (new)
- `deployment/stacks/s3_stack.py` (manifest bucket)
- `documentation/story-manifest.md` (new)
- `documentation/incremental-design.md`

---

### Task 4: Align API Documentation with Implementation [Issue #729]

**Goal:** Ensure public API documentation matches current implementation exactly.

**Priority:** MEDIUM
**Status:** ⏳ Not Started

#### Subtasks

| Subtask | Status | Notes |
|---------|--------|-------|
| Audit Lambda handlers for I/O | ⏳ Pending | Document each endpoint |
| Document all API endpoints | ⏳ Pending | Request/response schemas |
| Document error responses | ⏳ Pending | HTTP codes + messages |
| Add cURL examples | ⏳ Pending | For each endpoint |
| Review API Gateway configuration | ⏳ Pending | Verify paths/integrations |

**API Endpoints to Document:**

**Story Management:**
- `POST /story/start` - Start a story
  - Payload: `{CharacterID, StoryID}`
  - Response: `{Success, Segment: {ActiveSegmentID, SegmentType, StartTime, EndTime, ...}}`
  - Errors: 400 (invalid ID), 409 (already in story), 403 (prerequisites not met)

- `POST /story/abandon` - Abandon active story
  - Payload: `{CharacterID}` or `{StoryID}`
  - Response: `{Success}`
  - Errors: 400 (no active story)

- `GET /story/status` - Get current segment status
  - Query: `?characterId=uuid`
  - Response: Active segment details or null
  - Errors: 401 (unauthorized)

- `GET /story/history` - Get completed stories
  - Query: `?characterId=uuid`
  - Response: Array of StoryHistory entries
  - Errors: 401 (unauthorized)

**Segment Operations:**
- `POST /segment/decision` - Make choice in decision segment
  - Payload: `{CharacterID, SegmentID, Decision}`
  - Response: `{Success}`
  - Errors: 400 (invalid choice), 409 (already decided)

- `GET /segment/history` - Get segment history
  - Query: `?characterId=uuid`
  - Response: Array of SegmentHistory entries
  - Errors: 401 (unauthorized)

**Documentation Format:**
```markdown
## POST /story/start

Start a new story for a character.

### Request

```json
{
  "CharacterID": "uuid-string",
  "StoryID": "uuid-string"
}
```

### Response (200 OK)

```json
{
  "Success": true,
  "Segment": {
    "ActiveSegmentID": "uuid-string",
    "SegmentType": "decision|mechanical",
    "StartTime": 1234567890,
    "EndTime": 1234567890,
    ...
  }
}
```

### Error Responses

- `400 Bad Request` - Invalid CharacterID or StoryID
- `403 Forbidden` - Prerequisites not met
- `409 Conflict` - Character already in a story

### Example

```bash
curl -X POST https://api.domain.com/story/start \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"CharacterID":"abc-123","StoryID":"story-456"}'
```
```

**Acceptance Criteria:**
- [ ] All incremental API endpoints documented
- [ ] Front-end developer can follow docs to interact with API
- [ ] Documentation reviewed by QA tester for clarity
- [ ] All error cases documented with expected codes/messages
- [ ] Issue #729 partially fulfilled (API reference complete)

**Files to Create/Modify:**
- `documentation/incremental-api.md` (update/create)
- `documentation/lambda-functions.md` (reference)

---

## R1 Exit Criteria

| Criterion | Target | Status | Notes |
|-----------|--------|--------|-------|
| State machines formalized | ✅ Pass | 🔄 In Progress | Phase 1 complete, unit tests pending |
| Atomic effects application | ✅ Pass | ⏳ Not Started | No duplicate rewards |
| Idempotency verified | ✅ Pass | ⏳ Not Started | Retry scenarios tested |
| Multi-story support | ✅ Pass | ⏳ Not Started | ≥2 stories in manifest |
| API documentation complete | ✅ Pass | ⏳ Not Started | All endpoints documented |
| Issue #491 closed | ✅ Pass | 🔄 In Progress | Implementation done, tests pending |
| Issue #726 closed | ✅ Pass | ⏳ Not Started | Currency + atomicity done |
| Issue #605 partial | ✅ Pass | ⏳ Not Started | Manifest generated |
| Issue #729 partial | ✅ Pass | ⏳ Not Started | API reference complete |

---

## Overall R1 Progress

### Progress Summary: 17% Complete

| Task | Progress | Notes |
|------|----------|-------|
| Task 1: State Machines | 60% | Phase 1 complete (implementation + diagrams) |
| Task 2: Atomic Updates | 0% | Not started |
| Task 3: Story Manifest | 0% | Not started |
| Task 4: API Documentation | 0% | Not started |
| **Overall** | **17%** | 1 of 4 tasks in progress |

**Note:** Combat system work on inc-24 is separate from formal R1 plan. Combat rework addresses specific issues but is not part of the R1 deliverables per the program plan.

---

## Timeline Recommendation

**Current Phase:**
- Task 1: State machine formalization in progress (Phase 1 complete)

**Next Steps:**
- Complete Task 1: Unit tests and integration testing
- Start Task 2: Atomic effects application
- Complete Task 2: Currency and idempotency
- Complete Task 3: Story manifest generation
- Complete Task 4: API documentation

---

## Dependencies

**Task 1 → Task 2:** State machines (especially ProcessingStatus) must be in place before implementing atomic effects.

**Task 2 → Task 3:** Atomic effects should be working before adding multiple stories to avoid compounding bugs.

**Task 3 → R1.1:** Story manifest needed for client story browsing UI.

**All Tasks → R2:** Observability from R0 will help monitor R1 changes.

---

## Risks & Mitigation

### Risk: Race Conditions in Distributed Environment

**Mitigation:**
- Use DynamoDB conditional updates with expected state values
- Test concurrent operations (two simultaneous story starts)
- Implement comprehensive logging of state transitions

### Risk: Partial Updates During Failures

**Mitigation:**
- Use idempotency keys (ActiveSegmentID)
- ProcessingStatus prevents duplicate processing
- Consider DynamoDB transactions for critical multi-table updates
- Test timeout scenarios by forcing Lambda delays

### Risk: State Machine Over-Constraining

**Mitigation:**
- Include recovery logic in ops-segment-poller
- Log all state transitions with context
- Design escape hatches for stuck states

### Risk: Caching Introduces Staleness

**Mitigation:**
- Story definitions don't change mid-run
- Cache invalidation on content deployment
- Document cache behavior for developers

---

## Testing Strategy

### Unit Tests
- State transition helpers with all valid/invalid combinations
- Outcome application logic with various difficulty results
- Currency bounds checking (overflow, negative)

### Integration Tests
- Full story playthrough: create character → start story → complete
- Concurrent story starts (verify only one succeeds)
- Duplicate segment processing (verify idempotency)

### Property-Based Tests
- Segment completion run twice yields same final state
- Random event sequences don't lead to inconsistent states

### Manual Tests
- Multiple stories in manifest
- Story start with/without prerequisites
- Character state after story completion/abandonment

---

## R1 to R1.1 Transition

Upon R1 completion, the backend will be:
- ✅ State-safe (no illegal transitions possible)
- ✅ Atomic (no duplicate rewards)
- ✅ Multi-story capable (manifest supports ≥2 stories)
- ✅ Well-documented (API reference complete)

**R1.1 will add:**
- Client story browsing UI
- Mode transition UI
- End-to-end user flow from character selection to story completion

---

## Issue Tracking

| Issue | Title | R1 Status |
|-------|-------|-----------|
| #491 | State machines | Task 1 - To Complete |
| #726 | Story effects integration | Task 2 - To Complete |
| #605 | Story index manifest | Task 3 - Partial (automation in R5) |
| #729 | Comprehensive documentation | Task 4 - Partial (API reference) |

---

## Notes

- Combat rework on inc-24 is **not** part of R1 formal plan
- R1 focuses on **backend robustness**, not gameplay features
- Currency system infrastructure built here, economy fleshed out in R6
- Story manifest generation manual for now, automated in R5
- Full documentation completion spans R1, R5, and R7
