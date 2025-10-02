# Release 1 Report — State Management, Atomic Updates, and Content Model Foundation

**Date:** 2025-10-02
**Branch:** inc-24
**Status:** In Progress
**Previous Release:** R0 (inc-23 deployed to AWS)

---

## Executive Summary

Release 1 focuses on backend logic robustness: making state transitions foolproof and updates atomic, while laying groundwork for story content management. This tackles Priority Items (1) and (2) head-on, ensuring subsequent features build on a solid foundation.

**Ship Gate:** Robust progression logic with no state corruption or duplicate rewards.

**Current Status (2025-10-02):** Task 1 Phases 1-2 complete. State machine module created with atomic transitions, integrated into existing codebase. Documentation updated with state diagrams. Phase 3 (testing) pending.

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
**Status:** 🔄 In Progress (Phases 1-2 Complete, Phase 3 Pending)

#### Subtasks

| Subtask | Status | Notes |
|---------|--------|-------|
| Define Character GameMode state machine | ✅ Complete | GameMode enum with validation |
| Implement Segment ProcessingStatus transitions | ✅ Complete | Atomic claim/mark functions |
| Implement Story Lifecycle state machine | ✅ Complete | StoryLifecycle enum defined |
| Create state transition helper functions | ✅ Complete | state_machines.py module |
| Integration testing for state transitions | ⏳ Pending | End-to-end story flow validation |
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
- [ ] Integration testing validates state transitions in full story run
- [x] Concurrent story start requests: only one succeeds, other blocked (conditional writes implemented)
- [ ] During full story run, logs show correct state transitions (pending integration testing)
- [x] Documentation updated with state diagrams
- [ ] Issue #491 can be closed (pending integration testing)

**Files Created:**
- `eidolon/state_machines.py` - State machine module with enums and transition functions

**Files Modified:**
- `eidolon/segment_polling.py` - Delegates to state machine for claim operation
- `eidolon/story_active.py` - Uses state machine for GameMode transitions
- `eidolon/character_story.py` - Uses state machine for reset operation
- `lambda/api_story_start.py` - Cleaned up imports (uses state machine via story_active)
- `documentation/architecture.md` - Added 3 state machine diagrams (lines 274-424)

**Phase 1 Accomplishments (Create State Machine Module):**
- ✅ Created `state_machines.py` with GameMode, ProcessingStatus, StoryLifecycle enums
- ✅ Implemented `set_character_game_mode()` with atomic DynamoDB conditional writes
- ✅ Implemented `claim_segment_for_processing()` for atomic pending → processing transition
- ✅ Implemented `mark_segment_processed()` with idempotency support
- ✅ Implemented `reset_segment_to_pending()` for stuck segment recovery
- ✅ Added state diagrams to architecture.md (Character GameMode, Segment ProcessingStatus, Story Lifecycle)

**Phase 2 Accomplishments (Integration):**
- ✅ Updated `segment_polling.py` to delegate to state machine for claim operation
- ✅ Updated `story_active.py` to use `set_character_game_mode()` for transitions
- ✅ Updated `character_story.py` to use state machine for reset operation
- ✅ Cleaned up imports in `api_story_start.py`
- ✅ Fixed Pylance type checking issues with type ignore comments
- ✅ All linter checks passed

**Phase 3 Remaining Work (Testing & Documentation):**
- ⏳ Integration testing with full story run
- ⏳ Manual verification of state transitions in production-like environment

**Note:** Per project policy (see documentation/unit-tests.md), this project does not implement unit tests. Integration testing and manual verification provide sufficient validation for well-designed code.

---

### Task 2: Ensure Atomic Application of Story Outcomes [Issue #726]

**Goal:** Guarantee effects are applied all-or-nothing with no duplicate rewards on retries.

**Priority:** HIGH (Priority Item #1)
**Status:** 🔄 Deferred (Currency aspects moved to R6)

**Note:** Currency system implementation deferred to R6 (Economy & Balance). Basic accounting/banking processes should all be created together. This task will be completed in two parts:
- **R1**: Idempotency and atomic effects application (non-currency)
- **R6**: Currency system with full economy implementation

#### Subtasks

| Subtask | Status | Notes |
|---------|--------|-------|
| Design effects application routine | ⏳ R1 | Consolidate all updates (XP, items, wounds) |
| Implement idempotency key mechanism | ⏳ R1 | Use ActiveSegmentID |
| Add Currency field to Character schema | 🔄 R6 | Deferred to Economy release |
| Implement currency rewards in outcomes | 🔄 R6 | Deferred to Economy release |
| Write duplicate processing tests | ⏳ R1 | Verify no double rewards |
| Document atomicity approach | ⏳ R1 | In architecture.md |

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

**Currency Implementation (Deferred to R6):**
- Add `Gold` (integer) field to Character table (Python int, no overflow risk)
- Update schema to include `rewards.resources.gold`
- Implement currency increment in outcome application
- Validate non-negative (prevent bugs from causing negative currency)
- **Rationale:** All economy/banking/currency features should be designed and implemented together in R6

**Atomicity Strategy:**
- Use DynamoDB conditional writes exclusively (transactions untenable due to cost/performance)
- `ProcessingStatus` field prevents duplicate processing at segment level
- Single-table updates with conditional expressions for Characters table
- Idempotency key: `LastProcessedSegmentID` in Character record
- Items use generated UUIDs - simple `put_item` (cheaper than conditional expression)
- Design to avoid multi-table atomicity requirements

**Design Principle:** Keep related data in the same table when atomicity is required. Character XP, wounds, and state live in Characters table for single atomic update. Items table uses UUID primary keys for natural idempotency without conditional writes.

**Acceptance Criteria (R1 Scope):**
- [ ] Story completion yields consistent DB results
- [ ] Double-invocation of ops-story-advance doesn't duplicate XP/item rewards
- [ ] Test logs confirm no partial updates in failure scenarios
- [ ] Idempotency mechanism prevents duplicate processing
- [ ] Issue #726 partially complete (atomicity done, currency deferred to R6)

**Deferred to R6:**
- [ ] Currency rewards properly granted for stories that specify them
- [ ] Full economy system with banking/trading processes

**Files to Modify/Create (R1 Scope):**
- `eidolon/segment_processing.py` - Effects consolidation
- `eidolon/effects.py` (new) - Atomic effects application
- `eidolon/story_rewards.py` - XP and item rewards
- `eidolon/items.py` - Item reward validation
- `eidolon/character_story.py` - Story outcome effects
- `documentation/incremental-design.md` - Atomicity documentation

**Deferred to R6:**
- `deployment/stacks/dynamodb_stack.py` - Currency field addition
- Currency reward logic in story_rewards.py

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
| State machines formalized | ✅ Pass | 🔄 In Progress | Phases 1-2 complete, integration testing pending |
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

### Progress Summary: 20% Complete

| Task | Progress | Notes |
|------|----------|-------|
| Task 1: State Machines | 80% | Phases 1-2 complete (implementation + integration) |
| Task 2: Atomic Updates | 0% | Not started |
| Task 3: Story Manifest | 0% | Not started |
| Task 4: API Documentation | 0% | Not started |
| **Overall** | **20%** | 1 of 4 tasks in progress |

**Note:** Combat system work on inc-24 is separate from formal R1 plan. Combat rework addresses specific issues but is not part of the R1 deliverables per the program plan.

---

## Timeline Recommendation

**Current Phase:**
- Task 1: State machine formalization in progress (Phase 1 complete)

**Next Steps:**
- Complete Task 1: Integration testing and manual verification
- Start Task 2: Atomic effects application
- Complete Task 2: Idempotency (currency deferred to R6)
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

**Note:** Per project policy (documentation/unit-tests.md), this project does NOT implement unit tests. Testing focuses on integration and manual verification of actual system behavior.

### Integration Tests
- Full story playthrough: create character → start story → complete
- Concurrent story starts (verify only one succeeds)
- Duplicate segment processing (verify idempotency)
- End-to-end state transitions in production-like environment

### Manual Tests
- Multiple stories in manifest
- Story start with/without prerequisites
- Character state after story completion/abandonment
- State transition verification through logs and database inspection
- Race condition scenarios (concurrent API calls)

### Observability & Validation
- Production monitoring for actual behavior patterns
- Log analysis for state transition verification
- DynamoDB conditional write failures indicate race conditions (expected behavior)
- Code review for correctness and design quality

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
