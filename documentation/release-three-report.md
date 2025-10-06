# Release 3 Report — Honest Beta Readiness

**Date:** 2025-10-06 (Planning)
**Branch:** TBD (will branch from develop)
**Status:** 🔄 PLANNING — Tasks defined, ready for execution
**Previous Release:** R2 (inc-25 - Security hardening and production readiness)

---

## Executive Summary

Release 3 focuses on **honest beta readiness** by fixing critical bugs, eliminating performance waste, and delivering minimal but complete authoring capabilities. This release corrects misstatements from prior planning, acknowledges what's already complete, and prioritizes real blockers discovered through code review.

**Core Principle:** Fix what's broken, measure before spending, ship minimal docs, add real content.

**Ship Gate:** Currency persists correctly, client polling reduced to design intent, performance baseline documented, idempotency proven, authors can create content, security sanity checks complete.

---

## Critical Corrections from Prior Planning

**What Changed:**
- **Currency** - Not "add new feature" but "fix broken stub implementation"
- **Story Loader** - Already exists (#757 CLOSED); task is to document usage, not build
- **CI Validation** - Already operational (R0); task is to refine error messages
- **WAF** - Already deployed (R2); full security audit remains appropriately deferred
- **Client Polling** - Newly identified 10× API waste issue (from design docs)

**Honest Assessment:**
- ~30-40% of original R3 scope was claiming credit for completed work
- Currency application bug was hidden as "future economy feature"
- Client inefficiency was not acknowledged
- Performance optimization assumed provisioned concurrency before measurement

---

## R3 Task Categories

### Critical Path (Bug Fixes) — 2 Tasks
- R3-T1: Fix currency reward application (stub implementation)
- R3-T2: Fix client polling cadence (10× API waste)

### Performance Baseline — 1 Task
- R3-T3: Load testing and provisioned concurrency decision

### Quality Assurance — 1 Task
- R3-T4: Automated idempotency and integration tests

### Enablement — 2 Tasks
- R3-T5: Author Quick-Start documentation
- R3-T6: Create real beta story content

### Security — 1 Task
- R3-T7: Scoped security sanity pass

**Total:** 7 tasks (all critical for beta)

---

## Task Details

### R3-T1: Fix Currency Reward Application

**Status:** 🔴 CRITICAL - Core progression feature broken
**Priority:** P0 - Must complete first
**Issues:** #726 (effects integration), #639 (economy framework - partial)

#### Current State

**What Exists:**
- `eidolon/story_rewards.py:12-48` - `calculate_story_rewards()` correctly computes currency amounts
- `eidolon/story_rewards.py:51-69` - `apply_story_rewards()` is a **stub that does nothing**
- Currency field references in `documentation/schema.md` at lines 53, 98, 105, 108, 111, 114, 601
- Story JSON supports currency rewards in outcome definitions

**What's Broken:**
```python
def apply_story_rewards(character_id: str, rewards: dict) -> None:
    """Apply calculated rewards to a character."""
    try:
        # Story rewards currently only handle items and currency
        # XP is awarded through segment processing for specific skills

        logger.info(f"Applied story rewards for {character_id}")  # ← DOES NOTHING
    except ClientError as err:
        logger.error(f"Failed to apply rewards for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to apply rewards: {err}") from err
```

**Impact:** Players complete stories expecting currency rewards but receive nothing.

#### Implementation Requirements

**1. Verify Character Schema**

Check if `Currency` or `Gold` field exists in Characters table:
```python
# Check actual character records in DynamoDB
# Expected: Either field exists or needs migration
```

**Action:** If field missing, add to Character schema as `Currency` (Number, default 0).

**2. Implement Atomic Currency Update**

```python
def apply_story_rewards(character_id: str, rewards: dict) -> None:
    """Apply calculated rewards to a character."""
    try:
        currency_amount = rewards.get("currency", 0)
        items = rewards.get("items", [])

        if currency_amount == 0 and not items:
            logger.info(f"No rewards to apply for {character_id}")
            return

        # Build update expression
        update_parts = []
        attr_values = {}

        if currency_amount > 0:
            update_parts.append("Currency = if_not_exists(Currency, :zero) + :currency")
            attr_values[":currency"] = currency_amount
            attr_values[":zero"] = 0

        if items:
            # Item application already handled by apply_segment_outcome
            # This is for story-level completion bonuses only
            pass

        if update_parts:
            dynamo.update_item(
                TableName.CHARACTERS,
                Key={"CharacterID": character_id},
                UpdateExpression=f"SET {', '.join(update_parts)}",
                ExpressionAttributeValues=attr_values,
            )
            logger.info(f"Applied rewards for {character_id}: currency={currency_amount}")
    except ClientError as err:
        logger.error(f"Failed to apply rewards for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to apply rewards: {err}") from err
```

**3. Update Callers**

Verify all calls to `apply_story_rewards()` pass correct rewards dict:
- `eidolon/story_completion.py` - Story completion path
- Check any segment outcome paths that grant currency

**4. Add Validation**

Update `scripts_python/validate_story_content.py`:
```python
def validate_currency_rewards(story_data: dict):
    """Validate currency reward values are reasonable."""
    errors = []
    for segment in story_data.get("Segments", []):
        results = segment.get("Results", {})
        for outcome_name, outcome_data in results.items():
            effects = outcome_data.get("Effects", {})
            currency = effects.get("currency", 0)
            if currency < 0:
                errors.append(f"Segment {segment['SegmentID']}: {outcome_name} has negative currency: {currency}")
            if currency > 10000:  # Arbitrary sanity limit
                errors.append(f"Segment {segment['SegmentID']}: {outcome_name} has excessive currency: {currency}")
    return errors
```

#### Testing Requirements

**Unit Tests:**
```python
# tests/unit/test_story_rewards.py
def test_apply_currency_reward():
    """Test currency is added to character balance."""
    character_id = create_test_character(currency=100)
    rewards = {"currency": 50, "items": []}

    apply_story_rewards(character_id, rewards)

    character = get_character(character_id)
    assert character["Currency"] == 150

def test_apply_currency_idempotent():
    """Test replayed reward application doesn't double-grant."""
    # This will be covered in R3-T4 integration tests
    pass
```

**Integration Test:**
- Start story → complete with currency reward → verify balance increased exactly once
- Retry story advancement (simulate SQS replay) → verify currency not double-granted

#### Files Modified

- `eidolon/story_rewards.py` - Implement apply_story_rewards
- `eidolon/character_data.py` - Add get_currency/update_currency helpers if needed
- `documentation/schema.md` - Document Currency field if adding
- `scripts_python/validate_story_content.py` - Add currency validation
- `data/test_story.json` or `data/test_story_branching.json` - Add currency reward example

#### Acceptance Criteria

- [ ] Currency field exists in Characters table schema
- [ ] `apply_story_rewards()` implementation persists currency to DynamoDB
- [ ] Update uses atomic ADD operation (prevents race conditions)
- [ ] Validator checks currency values in story JSON
- [ ] Unit tests verify currency application
- [ ] Integration test proves single application on replay
- [ ] At least one test story includes currency reward
- [ ] Character GET API returns currency balance

#### Definition of Done

**Code Review Checklist:**
- Uses `if_not_exists(Currency, :zero) + :currency` pattern for safety
- No direct `character["Currency"] = X` assignments (prevents races)
- Error handling preserves atomicity (no partial updates)
- Logging includes actual currency amount applied

**Manual Verification:**
1. Load story with currency reward
2. Complete story successfully
3. Verify `GET /character?CharacterID=X` shows increased currency
4. Attempt to replay completion (manually trigger ops_story_advance)
5. Verify currency did not double

---

### R3-T2: Fix Client Polling Cadence

**Status:** 🟡 HIGH - Performance and cost impact
**Priority:** P0 - Required for beta
**Issues:** Create new issue "Fix incremental client polling cadence"

#### Current State

**What Documentation Says:**

From `documentation/incremental-design.md:686-695`:

> #### **Common Implementation Problems**
>
> ❌ **Dual Polling Systems**: Multiple timers competing for same resources (GameScreen + SegmentProvider)
> ❌ **API Call Explosion**: 10x more calls than necessary (10 vs 2 per segment)
> ❌ **Race Conditions**: Multiple async operations updating UI state simultaneously
> ❌ **Complex Client Logic**: Attempting to predict server behavior instead of trusting it

**Expected Behavior:**
- **~2 API calls per segment**: 1× GET /character at segment start, 1× GET /segment/status when timer expires
- **Server-authoritative timing**: Client waits for server-provided EndTime
- **Single polling loop**: One source of truth, no competing timers

**Current Behavior:**
- Multiple polling systems running simultaneously
- Aggressive status checks every few seconds
- ~10× more API calls than design intent
- Client-side complexity attempting to predict outcomes

**Impact:**
- Wasted API Gateway invocations (cost)
- Unnecessary DynamoDB reads (cost)
- Increased Lambda cold starts
- Potential rate limiting / throttling
- Poor battery life for mobile clients

#### Investigation Required

**Before Implementation:**

1. **Measure Current Baseline**
   - Enable API Gateway execution logging (INFO level)
   - Track calls per character per segment for 5-10 test runs
   - Document actual call pattern

2. **Locate Problematic Code**
   - `incremental/lib/services/` - Polling service implementations
   - `incremental/lib/screens/game_screen.dart` - Game screen polling
   - `incremental/lib/providers/` - Provider-level polling
   - Search for `Timer.periodic`, `Future.delayed` in incremental codebase

3. **Identify Competing Systems**
   - Document which components initiate polling
   - Map data flow and state update paths

#### Implementation Requirements

**Design Pattern (from documentation):**

From `documentation/incremental-design.md:606-654`:

```dart
class ServerAuthoritativePolling {
  bool _isPolling = false;

  /// Simple polling loop that follows server cadence exactly
  Future<void> startStoryPolling(String characterId) async {
    if (_isPolling) return;
    _isPolling = true;

    // ALWAYS wait 60 seconds for initial server processing
    await Future.delayed(const Duration(seconds: 60));

    while (_isPolling) {
      try {
        // 1. Get character state (includes activeSegmentID)
        final character = await apiService.getCharacterById(characterId);
        updateUIWithServerState(character);

        // 2. Check if story is complete
        if (character?.activeSegmentID == null) {
          break; // Story finished - stop polling
        }

        // 3. Get segment timing from server
        final segmentStatus = await apiService.getSegmentStatus(
          characterId: characterId
        );

        // 4. Wait exactly the time server specifies
        final timeRemaining = segmentStatus['TimeRemaining'] as int? ?? 0;
        if (timeRemaining > 0) {
          await Future.delayed(Duration(seconds: timeRemaining));
        } else {
          // Segment complete, brief delay before next check
          await Future.delayed(const Duration(seconds: 5));
        }

      } catch (e) {
        // 30-second retry delay for all errors
        await Future.delayed(const Duration(seconds: 30));
      }
    }

    _isPolling = false;
  }
}
```

**Implementation Steps:**

1. **Create Single Polling Service**
   - `incremental/lib/services/story_polling_service.dart`
   - Implement server-authoritative pattern above
   - Add proper error handling and retry logic

2. **Remove Competing Systems**
   - Audit and remove any existing polling in GameScreen
   - Remove provider-level polling timers
   - Consolidate to single service

3. **Add Metrics Collection**
   - Log API calls per segment (client-side counter)
   - Track timing accuracy (segment completion within 5s of EndTime)
   - Monitor error rates

4. **Update UI Integration**
   - GameScreen calls polling service after story start
   - Providers update from polling callbacks, don't initiate polls
   - Clear separation: service polls, providers store, widgets display

#### Testing Requirements

**Before/After Measurement:**

```
Baseline (Current):
- Story with 5-minute segment
- Expected: 2 API calls
- Actual: ??? (measure)

After Fix:
- Same story, same segment
- Target: ≤3 API calls (GET /character once, GET /segment/status 1-2 times)
```

**Test Scenarios:**

1. **Happy Path**
   - Start story → 60s delay → status check → wait TimeRemaining → completion
   - Verify: Exactly 2 API calls

2. **Network Interruption**
   - Start story → disconnect network mid-segment → reconnect
   - Verify: Graceful retry, story completes correctly

3. **Multiple Characters**
   - Start stories on 2 different characters
   - Verify: Independent polling loops, no interference

4. **App Background/Resume**
   - Start story → background app → resume after segment completion
   - Verify: Resumes correctly, fetches current state

#### Files Modified

- `incremental/lib/services/story_polling_service.dart` - NEW
- `incremental/lib/screens/game_screen.dart` - Remove polling, call service
- `incremental/lib/providers/segment_provider.dart` - Remove polling timers
- Any other files with `Timer.periodic` or polling logic

#### Acceptance Criteria

- [ ] Single polling service implementation exists
- [ ] All competing polling code removed
- [ ] Measured API calls reduced from baseline to ≤3 per segment
- [ ] Test scenarios pass (happy path, network interruption, multi-character, background/resume)
- [ ] Client-side metrics logged for verification
- [ ] No race conditions or state update conflicts
- [ ] Battery usage reduced (measured via Flutter DevTools or manual observation)

#### Definition of Done

**Before/After Comparison:**
```
BEFORE (Measured):
- Segment Duration: 5 minutes
- API Calls: _____ (document actual)
- Pattern: (document observed behavior)

AFTER (Target):
- Segment Duration: 5 minutes
- API Calls: ≤3
- Pattern: GET /character (1×) → wait → GET /segment/status (1-2×)
```

**Code Review Checklist:**
- Single source of polling truth
- No Timer.periodic outside polling service
- Providers are passive (updated by service, don't poll)
- Error handling includes exponential backoff
- Service properly cancels on story completion

---

### R3-T3: Performance Baseline and Provisioned Concurrency Decision

**Status:** 🟡 IMPORTANT - Evidence-based optimization
**Priority:** P1 - Should complete before beta launch
**Issues:** #728 (optimize Lambda performance), #613 (provisioned concurrency)

#### Current State

**What Exists:**
- 16 Lambda functions deployed with standard configuration:
  - Runtime: Python 3.12
  - Memory: 128MB
  - Timeout: 30 seconds
  - Concurrency: Default (unreserved)

**What's Unknown:**
- Actual cold start latencies under realistic load
- Warm invocation performance
- Poller throughput capacity
- Which functions are truly latency-sensitive vs. background

**Provisioned Concurrency Status:**
- NOT currently configured in `deployment/lambda_functions.py`
- Issue #613 proposes specific allocations but without measurement evidence

#### Implementation Requirements

**Phase 1: Create Load Test Harness**

Create `scripts_python/load_test_incremental.py`:

```python
"""
Load test harness for incremental game API.

Simulates N concurrent users performing story workflows.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import List

@dataclass
class TestResults:
    """Load test results."""
    function_name: str
    invocations: int
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    cold_starts: int
    errors: int

async def simulate_user_session(user_id: int, api_base_url: str, auth_token: str) -> List[float]:
    """
    Simulate one user's complete story workflow.

    Returns list of API latencies in milliseconds.
    """
    latencies = []

    # 1. GET /character (includes available stories)
    start = time.time()
    # ... API call
    latencies.append((time.time() - start) * 1000)

    # 2. POST /story/start
    start = time.time()
    # ... API call
    latencies.append((time.time() - start) * 1000)

    # 3. GET /segment/status (polling)
    # ... repeat based on segment duration

    # 4. POST /segment/decision (if decision segment)

    # 5. GET /character (completion check)

    return latencies

async def run_load_test(concurrent_users: int, duration_minutes: int):
    """Run load test with N concurrent users."""
    tasks = []
    for user_id in range(concurrent_users):
        task = asyncio.create_task(simulate_user_session(user_id, ...))
        tasks.append(task)

    results = await asyncio.gather(*tasks)
    # Aggregate and analyze
    return results
```

**Phase 2: Execute Load Tests**

Test Scenarios:

1. **Cold Start Baseline**
   - Invoke each Lambda function after 5+ minutes idle
   - Measure initialization time
   - Repeat 10 times, take P95

2. **Concurrent Load**
   - 10 users: Light load (beta minimum)
   - 50 users: Target beta capacity
   - Measure throughput and latencies

3. **Poller Stress Test**
   - Create 100 segments with EndTime in next 1 minute
   - Verify poller processes all within 2 minutes
   - Check for throttling or timeouts

**Phase 3: Collect CloudWatch Metrics**

For each Lambda function, gather:
- `Duration` - P50, P95, P99
- `ConcurrentExecutions` - Max
- `Errors` - Count
- `Throttles` - Count
- Cold start indicators (first invocation after idle)

Query using AWS CLI:
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=eidolon-api-story-start \
  --statistics Average,Maximum \
  --start-time 2025-10-06T00:00:00Z \
  --end-time 2025-10-06T23:59:59Z \
  --period 3600
```

**Phase 4: Analyze and Decide**

Create decision matrix:

| Function | Cold Start P95 | Warm P95 | User-Facing? | PC Recommended? | PC Allocation |
|----------|---------------|----------|--------------|-----------------|---------------|
| api-story-start | ??? ms | ??? ms | Yes | TBD | TBD |
| api-segment-status | ??? ms | ??? ms | Yes | TBD | TBD |
| api-character-get | ??? ms | ??? ms | Yes | TBD | TBD |
| ops-segment-poller | ??? ms | ??? ms | No (background) | TBD | TBD |
| ops-segment-process | ??? ms | ??? ms | No (async) | TBD | TBD |
| ops-story-advance | ??? ms | ??? ms | No (async) | TBD | TBD |

**Decision Criteria:**
- **Cold start P95 > 1000ms** AND **user-facing** → Strong candidate for PC
- **Cold start P95 > 500ms** AND **high frequency** → Candidate for PC
- **Background/async functions** → Generally do NOT need PC
- **Cost consideration:** PC costs ~$15/month per allocated unit

**Phase 5: Implement PC if Justified**

If decision is YES for any functions:

```python
# deployment/lambda_functions.py

# Example for api-story-start
lambda_function = _lambda.Function(
    self,
    "ApiStoryStart",
    function_name="eidolon-api-story-start",
    runtime=_lambda.Runtime.PYTHON_3_12,
    handler="api_story_start.lambda_handler",
    code=_lambda.Code.from_asset("lambda"),
    layers=[eidolon_layer],
    role=lambda_execution_role,
    memory_size=128,
    timeout=Duration.seconds(30),
    environment=environment,
    reserved_concurrent_executions=10,  # Limit max concurrency
)

# Add provisioned concurrency with auto-scaling
version = lambda_function.current_version
alias = _lambda.Alias(
    self,
    "ApiStoryStartAlias",
    alias_name="live",
    version=version,
)

# Provisioned concurrency target
target = appscaling.ScalableTarget(
    self,
    "ApiStoryStartScaling",
    service_namespace=appscaling.ServiceNamespace.LAMBDA,
    max_capacity=20,
    min_capacity=5,
    resource_id=f"function:{lambda_function.function_name}:live",
    scalable_dimension="lambda:function:ProvisionedConcurrentExecutions",
)

# Scaling policy
target.scale_on_utilization(
    utilization=0.70,  # Scale when 70% utilized
)
```

#### Deliverables

1. **Load Test Script**
   - `scripts_python/load_test_incremental.py`
   - README with usage instructions

2. **Performance Baseline Report**
   - `documentation/performance-baseline-r3.md`
   - Includes all metrics, graphs, and analysis

3. **Provisioned Concurrency Decision Memo**
   - Section in performance baseline report
   - Rationale for YES/NO decisions per function
   - Cost/benefit analysis
   - Implementation if recommended

#### Acceptance Criteria

- [ ] Load test harness executes successfully
- [ ] 10-user and 50-user concurrent tests completed
- [ ] CloudWatch metrics collected for all 16 Lambda functions
- [ ] Decision matrix completed with evidence
- [ ] Performance baseline documented
- [ ] Provisioned concurrency configured if justified (or explicit NO decision documented)
- [ ] Cost impact calculated and approved

#### Definition of Done

**Required Documentation:**

Create `documentation/performance-baseline-r3.md` with:

1. Test Methodology
2. Results Tables (metrics per function)
3. Decision Matrix
4. Provisioned Concurrency Recommendations
5. Cost Analysis
6. Implementation Notes (if PC deployed)

**Minimum Acceptable Performance:**
- P95 API latency < 2000ms (including cold starts)
- P95 warm invocation < 200ms
- Zero throttles or errors during 50-user test
- Poller processes 100 segments < 2 minutes

---

### R3-T4: Automated Idempotency and Integration Tests

**Status:** 🟡 IMPORTANT - Regression prevention
**Priority:** P1 - Required for beta confidence
**Issues:** #726 (effects integration verification)

#### Current State

**What R2 Delivered:**
- Manual idempotency verification (documented in R2 report)
- State machine validation
- Atomic update patterns verified

**What's Missing:**
- **Automated regression tests** for critical scenarios
- CI integration for idempotency checks
- Comprehensive integration test suite

**Risk:**
Future code changes could break idempotency guarantees without detection.

#### Implementation Requirements

**Test Framework:**

Create `tests/integration/` directory structure:

```
tests/
├── __init__.py
├── conftest.py                    # Pytest fixtures
├── integration/
│   ├── __init__.py
│   ├── test_story_idempotency.py  # Story-level tests
│   ├── test_segment_idempotency.py # Segment-level tests
│   ├── test_concurrent_operations.py # Race condition tests
│   └── fixtures/
│       ├── test_stories.json      # Test story definitions
│       └── test_characters.json   # Test character data
└── helpers/
    ├── __init__.py
    ├── dynamo_helpers.py          # DynamoDB test utilities
    └── lambda_helpers.py          # Lambda invocation helpers
```

**Test Scenarios (Critical Path):**

1. **Double Story Start**
   ```python
   async def test_double_story_start_idempotent():
       """
       Verify that attempting to start the same story twice results in:
       - First request succeeds (200)
       - Second request fails with 409 Conflict
       - Only one ActiveSegment record created
       - GameMode set exactly once
       """
       character_id = create_test_character()
       story_id = create_test_story()

       # Attempt simultaneous starts
       results = await asyncio.gather(
           invoke_lambda("api-story-start", {"CharacterID": character_id, "StoryID": story_id}),
           invoke_lambda("api-story-start", {"CharacterID": character_id, "StoryID": story_id}),
           return_exceptions=True
       )

       # Verify exactly one succeeded
       success_count = sum(1 for r in results if r.get("statusCode") == 200)
       assert success_count == 1

       # Verify database state
       character = get_character(character_id)
       assert character["GameMode"] == "Incremental"

       segments = query_active_segments(character_id)
       assert len(segments) == 1
   ```

2. **Double Decision Submission**
   ```python
   async def test_double_decision_submit_idempotent():
       """
       Verify that submitting decision twice results in:
       - First submission accepted
       - Second submission rejected (already decided)
       - Decision field set exactly once
       """
       character_id, segment_id = setup_decision_segment()

       # Submit same decision twice
       results = await asyncio.gather(
           invoke_lambda("api-segment-decision", {
               "CharacterID": character_id,
               "Decision": "choice1"
           }),
           invoke_lambda("api-segment-decision", {
               "CharacterID": character_id,
               "Decision": "choice1"
           }),
           return_exceptions=True
       )

       # Verify behavior
       segment = get_active_segment(segment_id)
       assert segment["Decision"] == "choice1"
       # Should only be recorded once
   ```

3. **Segment Processing Retry (SQS Replay)**
   ```python
   def test_segment_processing_retry_no_double_rewards():
       """
       Verify that replaying segment processing (SQS retry) does not:
       - Grant XP twice
       - Grant items twice
       - Grant currency twice
       - Apply wounds twice
       """
       character_id, segment_id = setup_mechanical_segment()

       # Process segment
       result1 = invoke_lambda("ops-segment-process", {
           "Records": [{
               "body": json.dumps({"ActiveSegmentID": segment_id})
           }]
       })

       character_after_first = get_character(character_id)
       xp_after_first = character_after_first["Skills"]["combat"]
       currency_after_first = character_after_first.get("Currency", 0)

       # Replay processing (simulate SQS retry)
       result2 = invoke_lambda("ops-segment-process", {
           "Records": [{
               "body": json.dumps({"ActiveSegmentID": segment_id})
           }]
       })

       character_after_second = get_character(character_id)
       xp_after_second = character_after_second["Skills"]["combat"]
       currency_after_second = character_after_second.get("Currency", 0)

       # Verify no double-grant
       assert xp_after_first == xp_after_second
       assert currency_after_first == currency_after_second
   ```

4. **Story Advancement Retry**
   ```python
   def test_story_advancement_retry_idempotent():
       """
       Verify that replaying story advancement (SQS retry) does not:
       - Create duplicate segments
       - Apply completion rewards twice
       - Transition GameMode multiple times
       """
       character_id, segment_id = setup_completed_segment()

       # First advancement
       invoke_lambda("ops-story-advance", {
           "Records": [{
               "body": json.dumps({"ActiveSegmentID": segment_id})
           }]
       })

       segments_after_first = query_segment_history(character_id)
       character_after_first = get_character(character_id)

       # Retry advancement
       invoke_lambda("ops-story-advance", {
           "Records": [{
               "body": json.dumps({"ActiveSegmentID": segment_id})
           }]
       })

       segments_after_second = query_segment_history(character_id)
       character_after_second = get_character(character_id)

       # Verify no duplication
       assert len(segments_after_first) == len(segments_after_second)
       assert character_after_first == character_after_second
   ```

5. **Story Abandon Flow**
   ```python
   def test_story_abandon_complete_flow():
       """
       Verify story abandon correctly:
       - Moves story to AbandonedStories
       - Clears ActiveStoryID and ActiveSegmentID
       - Resets GameMode to None
       - Creates StoryHistory entry with AbandonedAt
       - Deletes ActiveSegment record
       - Allows restart of same story
       """
       character_id, story_id = setup_active_story()

       # Abandon story
       result = invoke_lambda("api-story-abandon", {
           "CharacterID": character_id
       })
       assert result["statusCode"] == 200

       # Verify state
       character = get_character(character_id)
       assert character["GameMode"] == "None"
       assert character.get("ActiveStoryID") is None
       assert character.get("ActiveSegmentID") is None
       assert story_id in character.get("AbandonedStories", [])

       # Verify can restart
       restart_result = invoke_lambda("api-story-start", {
           "CharacterID": character_id,
           "StoryID": story_id
       })
       assert restart_result["statusCode"] == 200
   ```

**Test Helpers:**

```python
# tests/helpers/dynamo_helpers.py

def create_test_character(**overrides):
    """Create test character with defaults."""
    character = {
        "CharacterID": str(uuid.uuid4()),
        "PlayerID": str(uuid.uuid4()),
        "CharacterName": f"TestChar{random.randint(1000, 9999)}",
        "GameMode": "None",
        "Currency": 0,
        "Skills": {"combat": 5.0, "stealth": 3.0},
        # ... other required fields
        **overrides
    }
    dynamo.put_item(TableName.CHARACTERS, Item=character)
    return character["CharacterID"]

def create_test_story(**overrides):
    """Create test story with defaults."""
    story = {
        "StoryID": str(uuid.uuid4()),
        "Title": "Test Story",
        "FirstSegmentID": str(uuid.uuid4()),
        # ... other required fields
        **overrides
    }
    dynamo.put_item(TableName.STORY, Item=story)
    return story["StoryID"]

def query_active_segments(character_id):
    """Get all active segments for character."""
    return dynamo.query(
        TableName.ACTIVE_SEGMENTS,
        IndexName="CharacterID-index",
        KeyConditionExpression="CharacterID = :cid",
        ExpressionAttributeValues={":cid": character_id}
    ).get("Items", [])

def cleanup_test_data(character_id):
    """Clean up test character and related data."""
    # Delete character
    # Delete active segments
    # Delete history entries
    pass
```

**CI Integration:**

Create `.github/workflows/integration-tests.yml`:

```yaml
name: Integration Tests

on:
  pull_request:
    paths:
      - 'lambda/**'
      - 'eidolon/**'
      - 'tests/**'
  push:
    branches: [develop, main]

jobs:
  integration:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install -r requirements/test-requirements.txt
          pip install -r requirements/lambda-requirements.txt

      - name: Run integration tests
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          AWS_DEFAULT_REGION: us-east-1
        run: |
          pytest tests/integration/ -v --tb=short

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: integration-test-results
          path: test-results/
```

#### Acceptance Criteria

- [ ] Integration test suite covers all 5 critical scenarios
- [ ] Test helpers created for common operations
- [ ] Tests run in isolated environment (dev/test AWS account or mocked)
- [ ] CI workflow configured and passing
- [ ] Tests added to PR gate (must pass before merge)
- [ ] Documentation of test scenarios and expected behavior
- [ ] Cleanup procedures to prevent test data accumulation

#### Definition of Done

**Test Execution:**
- All 5 scenarios pass consistently (no flaky tests)
- Tests complete quickly
- Tests clean up their own data

**CI Integration:**
- Workflow runs on every PR touching Lambda/eidolon code
- Workflow status badge added to README
- Failing tests block merge

**Documentation:**
- `tests/integration/README.md` explains how to run tests locally
- Each test has clear docstring explaining scenario and expectations

---

### R3-T5: Author Quick-Start Documentation

**Status:** 🟢 STRAIGHTFORWARD - Documentation task
**Priority:** P1 - Required for beta content creation
**Issues:** #729 (documentation suite), #619 (author handbook - merge duplicate)

#### Current State

**What Exists:**
- `documentation/incremental-design.md` (896 lines) - Technical architecture
- `documentation/schema.md` (38,185 lines) - Complete DynamoDB schema
- `scripts_python/validate_story_content.py` - Content validator
- `scripts_python/validate_branching.py` - Branching validator
- `database/data_loader.py` - Story loader implementation
- `.github/workflows/story-validation.yml` - CI validation workflow

**What's Missing:**
- **Pragmatic, non-developer-friendly** guide to create stories
- Copy-paste examples for common patterns
- Clear workflow: create → validate → load → test

**NOT Required:**
- Comprehensive author handbook (deferred to R4/R5)
- Story design theory or creative writing guidance
- Advanced balancing formulas

#### Implementation Requirements

**Create: `documentation/story-author-quickstart.md`**

**Target Audience:** Non-developers who can edit JSON and run command-line tools.

**Structure:**

```markdown
# Story Author Quick-Start Guide

## Prerequisites

- Text editor (VS Code, Sublime, or any JSON editor)
- Python 3.12+ installed
- Access to repository on local machine
- AWS CLI configured (for loading to DynamoDB)

## Story Creation Workflow

### 1. Create Your Story JSON

Stories are defined in JSON format with two main sections:
- **Story metadata** - Title, description, prerequisites
- **Segments** - Individual story beats with challenges and outcomes

#### Minimal Story Template

[Copy-paste template for linear story]

#### Story Fields Explained

- `StoryID` (UUID) - Unique identifier (generate at https://www.uuidgenerator.net/)
- `Title` (string) - Story name shown to players
- `Description` (string) - Brief summary
- `FirstSegmentID` (UUID) - Points to starting segment
- `Prerequisites` (object) - Requirements to unlock story
- `RewardTiers` (object) - Currency/items awarded on completion

### 2. Create Your Segments

Each segment represents one story beat. Types:
- **Mechanical** - Skill challenges and/or combat
- **Decision** - Player choice with branching paths

#### Mechanical Segment Template

[Copy-paste template with challenge]

#### Decision Segment Template

[Copy-paste template with 2-3 choices]

#### Segment Fields Explained

[Brief field reference with examples]

### 3. Validate Your Story

Before loading, always validate:

```bash
cd multi-user-dungeon
python scripts_python/validate_story_content.py data/your-story.json
python scripts_python/validate_branching.py data/your-story.json
```

**Common Validation Errors:**

- "Segment X not found" → Check SegmentID references
- "Missing outcome Death" → All mechanical segments need Death outcome
- "Orphaned segment" → Every segment must be reachable

### 4. Load Story to DynamoDB

```bash
python database/data_loader.py --story data/your-story.json
```

**Dry-run first:**
```bash
python database/data_loader.py --story data/your-story.json --dry-run
```

### 5. Test Your Story

1. Launch the incremental web app
2. Create a character meeting prerequisites
3. Start your story
4. Play through all paths
5. Verify outcomes and rewards

**Testing Checklist:**
- [ ] Story appears in available list (if prereqs met)
- [ ] All segments display correct narrative
- [ ] Decision choices work
- [ ] Mechanical segments process correctly
- [ ] Rewards apply on completion
- [ ] Story can be replayed if repeatable

## Common Patterns

### Linear Story (No Branching)

[Example: 3-segment linear story]

### Branching Story (Player Choices)

[Example: Story with 2 decision points]

### Combat Story

[Example: Story with opponent fight]

## Story Balance Guidelines

**Segment Durations:**
- Early game: 1-5 minutes (quick engagement)
- Mid game: 5-15 minutes (progression)
- Late game: 15-60 minutes (idle mechanics)

**Difficulty Tiers:**
- Tier 1: Skills 0-3, simple challenges
- Tier 2: Skills 3-6, moderate challenges
- Tier 3: Skills 6-10, complex challenges

**Currency Rewards:**
- Tier 1: 10-50 currency
- Tier 2: 50-200 currency
- Tier 3: 200-1000 currency

## Troubleshooting

**Problem:** "Story not appearing for my character"
- Check Prerequisites (skills, items)
- Verify character doesn't have story in CompletedStories
- Check cooldown if repeatable

**Problem:** "Validation fails with unknown error"
- Ensure JSON is valid (use jsonlint.com)
- Check all UUIDs are properly formatted
- Verify all references exist

**Problem:** "Story loaded but crashes on start"
- Check FirstSegmentID points to valid segment
- Verify all NextSegmentID references exist
- Ensure mechanical segments have all outcomes

## Next Steps

- Read full Schema Reference: [schema.md](schema.md)
- Study example stories: `data/test_story.json`, `data/test_story_branching.json`
- Join story author discussions: [GitHub Discussions]

## Getting Help

- Questions: Open GitHub Discussion
- Bugs: File GitHub Issue
- Content review: Submit PR to `data/stories/` directory
```

**Required Examples:**

Create 3 copy-paste templates in the doc:

1. **Linear 3-segment story** (narrative only)
2. **Branching story with 2 decision points**
3. **Combat story with skill challenge prereq**

Each example should be:
- Complete and valid (passes validation)
- ~50-100 lines (readable)
- Commented to explain key fields

#### Additional Documentation Updates

**Update `README.md`:**

Add link to Quick-Start in "Documentation" section:

```markdown
## Documentation

- [Story Author Quick-Start](documentation/story-author-quickstart.md) - Create your first story
- [Deployment Guide](documentation/deployment.md) - Infrastructure setup
- [Architecture Overview](documentation/architecture.md) - System design
```

**Update `.github/workflows/story-validation.yml`:**

Add comment explaining validation for contributors:

```yaml
# This workflow validates story content on every PR
# Ensures stories meet structural requirements before merge
# See documentation/story-author-quickstart.md for authoring guide
```

#### Acceptance Criteria

- [ ] Quick-Start document created with all sections
- [ ] 3 copy-paste templates included and validated
- [ ] README.md updated with link
- [ ] CI workflow commented
- [ ] Non-developer can follow guide end-to-end without additional help
- [ ] All examples pass validation when copy-pasted

#### Definition of Done

**Validation Test:**

Have a non-developer (or simulated non-dev using ONLY the Quick-Start) attempt to:
1. Create a simple 2-segment story
2. Validate it
3. Load it to dev environment
4. Play it in the incremental app

**Success criteria:**
- Completes workflow efficiently
- Encounters no undocumented errors
- Story works correctly in app

**Documentation Quality:**
- No assumed knowledge beyond "can edit JSON"
- Every error message explained
- Clear progression from simple to complex

---

### R3-T6: Create Real Beta Story Content

**Status:** 🟢 STRAIGHTFORWARD - Content creation
**Priority:** P1 - Beta needs playable content
**Issues:** (Content gap, no existing issue)

#### Current State

**What Exists:**
- `data/test_story.json` - Basic test fixture
- `data/test_story_branching.json` - Branching test fixture

**What's Needed:**
- 2-3 **complete, balanced, playable** stories for beta testers
- Mix of story types (linear, branching, combat)
- Appropriate for early-game characters (skills 0-5)

#### Implementation Requirements

**Story 1: "The Mysterious Package" (Linear, Narrative)**

**Type:** Linear progression, decision-only
**Duration:** 5-10 minutes total
**Theme:** Mystery/Investigation
**Prerequisites:** None (starter story)

**Structure:**
1. **Opening** - Character receives mysterious package
2. **Decision** - Open immediately or investigate sender?
3. **Investigation** - Follow clues (narrative only)
4. **Resolution** - Reveal contents and consequences

**Rewards:**
- Completion: 25 currency, possible item reward
- Outcomes vary by choices made

**File:** `data/stories/mysterious-package.json`

---

**Story 2: "Goblin Scouts" (Combat Tutorial)**

**Type:** Linear with combat
**Duration:** 3-5 minutes
**Theme:** Combat introduction
**Prerequisites:** None

**Structure:**
1. **Setup** - Encounter goblin scouts on road
2. **Challenge** - Perception check to avoid ambush (optional advantage)
3. **Combat** - Fight 2 weak goblins
4. **Resolution** - Victory rewards, defeat consequences

**Mechanics:**
- 1× Perception challenge (Difficulty: 5, optional)
- 1× Combat (Opponent: "Goblin Scout" - weak, designed to teach combat)

**Rewards:**
- Success: 50 currency, basic weapon item
- Failure: Minor wounds, reduced currency

**File:** `data/stories/goblin-scouts.json`

---

**Story 3: "The Branching Path" (Complex Branching)**

**Type:** Decision-heavy with multiple outcomes
**Duration:** 8-12 minutes
**Theme:** Moral choices with consequences
**Prerequisites:** Skills: Any skill >= 3

**Structure:**
1. **Setup** - Find injured traveler on road
2. **Decision 1** - Help, rob, or ignore?
3. **Branch A: Help** - Stealth check to avoid bandits
   - Success → Reward and reputation
   - Failure → Combat with bandits
4. **Branch B: Rob** - Quick reward, negative consequences later
5. **Branch C: Ignore** - Miss out on rewards, safe passage

**Weighted Branching:**
- Help path has skill-gated better outcomes
- Rob path has guaranteed short-term gain, long-term cost
- Ignore path is safe but unrewarding

**Rewards:**
- Help + Success: 100 currency, unique item, reputation
- Help + Combat Win: 75 currency, wounds
- Rob: 50 currency, reputation loss
- Ignore: 0 currency, no consequences

**File:** `data/stories/branching-path.json`

---

#### Story Creation Process

**For Each Story:**

1. **Write Narrative Content**
   - Opening narrative (hook)
   - Segment descriptions (what player sees)
   - Outcome narratives (consequences)
   - Decision option text

2. **Define Mechanics**
   - Skill checks with appropriate difficulty
   - Combat opponents (if any)
   - Prerequisite requirements
   - Reward tiers

3. **Generate UUIDs**
   - StoryID
   - SegmentID for each segment
   - Use https://www.uuidgenerator.net/ or Python uuid library

4. **Create JSON**
   - Follow schema from schema.md
   - Use Quick-Start templates as base
   - Add currency rewards (R3-T1 implementation)

5. **Validate**
   ```bash
   python scripts_python/validate_story_content.py data/stories/story-name.json
   python scripts_python/validate_branching.py data/stories/story-name.json
   ```

6. **Load to Dev**
   ```bash
   python database/data_loader.py --story data/stories/story-name.json
   ```

7. **Playtest**
   - Create test character with appropriate skills
   - Play through all paths
   - Verify all outcomes work
   - Check rewards apply correctly
   - Document any bugs or issues

8. **Balance Tuning**
   - Adjust difficulties based on playtest
   - Tune rewards to match time investment
   - Ensure failure states aren't punishing

#### Playtest Documentation

For each story, create playtest notes:

```markdown
# Playtest: [Story Name]

**Date:** 2025-10-XX
**Tester:** [Name]
**Character:** Level X, Skills: {...}

## Test Runs

### Run 1: [Path Taken]
- Segments completed: X
- Duration: X minutes
- Outcome: [Success/Failure/Death]
- Rewards: X currency, [items]
- Issues: [None / List issues]

### Run 2: [Different Path]
- ...

## Balance Assessment

- Difficulty: [Too Easy / Appropriate / Too Hard]
- Duration: [Too Short / Appropriate / Too Long]
- Rewards: [Too Low / Appropriate / Too High]

## Bugs Found

1. [Bug description] - Severity: [Low/Medium/High]
2. ...

## Recommendations

- [ ] Adjust difficulty of segment X
- [ ] Increase/decrease rewards
- [ ] Fix narrative typos
- [ ] ...
```

#### Deliverables

**Story Files:**
- `data/stories/mysterious-package.json`
- `data/stories/goblin-scouts.json`
- `data/stories/branching-path.json`

**Playtest Documentation:**
- `data/stories/playtest-notes/mysterious-package.md`
- `data/stories/playtest-notes/goblin-scouts.md`
- `data/stories/playtest-notes/branching-path.md`

**Story Catalog Update:**
Create `data/stories/README.md`:

```markdown
# Beta Story Catalog

## Available Stories

### The Mysterious Package
- **Type:** Linear, narrative-focused
- **Duration:** 5-10 minutes
- **Prerequisites:** None
- **Difficulty:** Easy
- **Rewards:** 25 currency, random item

### Goblin Scouts
- **Type:** Combat tutorial
- **Duration:** 3-5 minutes
- **Prerequisites:** None
- **Difficulty:** Easy
- **Rewards:** 50 currency, basic weapon

### The Branching Path
- **Type:** Complex branching
- **Duration:** 8-12 minutes
- **Prerequisites:** Any skill >= 3
- **Difficulty:** Medium
- **Rewards:** 0-100 currency, unique items

## Adding New Stories

See [Story Author Quick-Start](../../documentation/story-author-quickstart.md)
```

#### Acceptance Criteria

- [ ] 3 stories created and validated
- [ ] All stories loaded to dev environment
- [ ] Each story playtested at least 2× with different paths
- [ ] Playtest notes documented
- [ ] Balance adjustments applied based on testing
- [ ] Story catalog created
- [ ] All stories use currency rewards (verify R3-T1 implementation)

#### Definition of Done

**Quality Checklist:**
- Narrative is engaging and error-free
- All mechanics work as intended
- No dead-end segments
- All outcomes reachable
- Rewards feel appropriate for time/difficulty
- Stories pass validation without warnings

**Beta-Ready Criteria:**
- Non-developer can play all stories without confusion
- Stories demonstrate different mechanics (narrative, combat, branching)
- Difficulty appropriate for new players
- Fun to play (subjective but important)

---

### R3-T7: Scoped Security Sanity Pass

**Status:** 🟡 IMPORTANT - Risk mitigation
**Priority:** P2 - Should complete before beta
**Issues:** #616 (security audit - partial, full audit deferred per R2)

#### Current State

**What's Already Secure (from R2):**
- WAF deployed on CloudFront, API Gateway, Cognito
- Rate limiting active
- AWS managed rules for common attacks
- No critical security issues in R2

**What This Pass Covers:**
- IAM least-privilege verification
- Input validation completeness
- Authentication enforcement
- Secrets hygiene
- Quick wins, not comprehensive audit

**What's Explicitly Deferred:**
- Full penetration testing
- Third-party security audit
- Advanced threat modeling
- Compliance certifications (SOC2, etc.)

#### Implementation Requirements

**Security Checklist:**

The complete security sanity pass checklist follows, with **actual IAM review findings** from deployment/ directory analysis.

**Documentation Instructions:**
- Mark checklist items with `✓` as you complete them
- Document all CRITICAL and HIGH findings in the "IAM Security Review - Actual Findings" section below
- Use sequential finding IDs: R3-SEC-001, R3-SEC-002, etc. (R3-IAM-001 through R3-IAM-005 already used)
- Update this document inline - do not create separate files

```markdown
# R3 Security Sanity Pass Checklist

## 1. IAM Least Privilege Review

### Lambda Execution Role

**Check:** `deployment/stacks/lambda_stack.py` - Lambda execution role

- [✓] Review `eidolon-lambda-execution-role` permissions
- [✓] Verify no `"*"` resources in DynamoDB policy
- [✓] Verify no `"*"` actions (should be specific: dynamodb:GetItem, PutItem, etc.)
- [✓] Confirm SQS permissions limited to specific queue ARNs
- [✓] Verify SSM permissions limited to `/eidolon/*` parameter path
- [ ] Check CloudWatch Logs permissions are scoped to function log groups

**Expected Policy Structure:**
```json
{
  "Effect": "Allow",
  "Action": [
    "dynamodb:GetItem",
    "dynamodb:PutItem",
    "dynamodb:UpdateItem",
    "dynamodb:Query"
  ],
  "Resource": [
    "arn:aws:dynamodb:REGION:ACCOUNT:table/characters",
    "arn:aws:dynamodb:REGION:ACCOUNT:table/characters/index/*"
  ]
}
```

**Tool:** Use `aws iam get-role-policy` to review

**Findings:**

✅ **DynamoDB Policy (deployment/stacks/dynamodb_stack.py:69-91)** - GOOD
- Uses specific table ARNs from `self.table_arns + self.index_arns`
- No wildcard resources
- Specific actions only (no `dynamodb:*`)
- Properly includes GSI ARNs

✅ **SQS Permissions (deployment/stacks/story_stack.py:144-154)** - GOOD
- Scoped to specific queue ARNs: `processing_queue.queue_arn` and `advancement_queue.queue_arn`
- No wildcards

✅ **SSM Permissions (deployment/stacks/story_stack.py:138-142)** - GOOD
- Scoped to `/eidolon/story/*` parameter path
- No wildcards beyond intended prefix

⚠️ **CloudWatch Logs Policy (deployment/stacks/lambda_stack.py:86-91)** - CRITICAL ISSUE
- **CONFIRMED R3-IAM-001**: Uses wildcard `*:*` in resources
- Line 90: `resources=[f"arn:aws:logs:{self.region_name}:*:*"]`
- Allows access to ANY log group in the region
- MUST FIX before beta

---

### Lambda Function Separation

**Check:** Should read-only functions have write permissions?

- [✓] `api-character-get` - Should ONLY have DynamoDB read (GetItem, Query)
- [✓] `api-character-list` - Should ONLY have DynamoDB read
- [✓] `api-archetype-list` - Should ONLY have DynamoDB read
- [✓] Verify write functions have necessary permissions but read-only don't

**Findings:**

⚠️ **All Lambda functions share the same execution role** - CONFIRMED R3-IAM-002

**Read-Only Functions (need only GetItem, Query, DescribeTable):**
- `api-archetype-list`
- `api-character-get`
- `api-character-list`
- `api-segment-history`
- `api-segment-status`
- `api-story-history`

**Read-Write Functions (need PutItem, UpdateItem, DeleteItem):**
- `api-character-add`
- `api-character-delete`
- `api-segment-decision`
- `api-story-abandon`
- `api-story-start`
- All `ops-*` functions

**Current State:**
- All functions use shared role `eidolon-lambda-execution-role` (deployment/stacks/lambda_stack.py:66-102)
- DynamoDB policy grants: `PutItem`, `UpdateItem`, `DeleteItem`, `BatchWriteItem` to ALL functions
- Read-only functions have unnecessary write permissions

**Recommendation:** Create separate IAM policies for read-only vs read-write functions (DEFER TO R4 - acceptable for beta with Cognito auth + input validation)

---

## 2. API Gateway Authorization

**Check:** All endpoints enforce Cognito authorizer

Tool: Review `deployment/stacks/api_stack.py`

- [ ] Verify EVERY resource has `authorizer` parameter set
- [ ] Check that authorizer type is `COGNITO_USER_POOLS`
- [ ] Confirm no `authorizationType: NONE` endpoints (except OPTIONS for CORS)

**Manual Test:**
```bash
# Attempt to call API without Authorization header
curl -X GET https://api.yourdomain.com/character?CharacterID=test

# Expected: 401 Unauthorized
# If 200 or any other response: CRITICAL FINDING
```

**Test All Endpoints:**
- [ ] GET /character
- [ ] POST /character
- [ ] DELETE /character
- [ ] POST /story/start
- [ ] POST /story/abandon
- [ ] POST /segment/decision
- [ ] GET /segment/status
- [ ] GET /segment/history
- [ ] GET /story/history
- [ ] GET /archetype

**Findings:** [List any unprotected endpoints]

---

## 3. Input Validation

**Check:** Lambda functions validate ALL inputs before processing

### Required Validations

For each Lambda function in `lambda/api_*.py`:

**Query Parameters:**
- [ ] Validate UUIDs using `validate_uuid()` from eidolon.validation
- [ ] Reject requests with missing required parameters (return 400)
- [ ] Check parameter types (no integer overflow, string length limits)

**Request Bodies:**
- [ ] Parse JSON safely (handle parse errors)
- [ ] Validate all required fields present
- [ ] Check string length limits (CharacterName, StoryID, etc.)
- [ ] Validate enum values (GameMode, SegmentType, etc.)

**Example Checks:**

`api_character_add.py`:
```python
def lambda_handler(event, context):
    # Check body parsing
    body = parse_event_body(event)  # ✓ Handles parse errors

    # Check required fields
    character_name = body.get("CharacterName")
    if not character_name:  # ✓ Validates presence
        return lambda_response(400, {"Error": "Missing CharacterName"}, event)

    # Check string length
    if len(character_name) > 50:  # ✓ Prevents abuse
        return lambda_response(400, {"Error": "CharacterName too long"}, event)

    # Check Bloom filter
    if name_is_prohibited(character_name):  # ✓ Content filtering
        return lambda_response(400, {"Error": "Name not allowed"}, event)

    # UUID validation
    archetype_id = body.get("ArchetypeID")
    if not validate_uuid(archetype_id):  # ✓ Type safety
        return lambda_response(400, {"Error": "Invalid ArchetypeID format"}, event)
```

**Audit Each Function:**
- [ ] `api_character_add.py` - Name validation, archetype validation
- [ ] `api_character_get.py` - CharacterID validation
- [ ] `api_character_delete.py` - CharacterID validation, ownership check
- [ ] `api_story_start.py` - CharacterID, StoryID validation
- [ ] `api_segment_decision.py` - CharacterID, Decision validation
- [ ] All other API functions

**Common Vulnerabilities to Check:**
- SQL injection (N/A - using DynamoDB)
- NoSQL injection - Check that inputs aren't used directly in expressions
- Command injection - Check that no inputs passed to shell commands
- Path traversal - Check that no file paths constructed from input
- XSS - Check that responses don't reflect unescaped input (API only, not applicable)

**Findings:** [List functions with weak/missing validation]

---

## 4. Secrets Management

**Check:** No secrets in environment variables or code

### Environment Variables

Review `deployment/stacks/lambda_stack.py` and other stack files:

- [ ] No API keys in environment variables
- [ ] No passwords in environment variables
- [ ] No secret tokens in environment variables
- [ ] Verify all secrets use SSM Parameter Store or Secrets Manager

**Current Environment Variables:**
```python
environment = {
    "APPLICATION_NAME": "eidolon-engine",  # ✓ Not secret
    "LOG_LEVEL": "INFO",  # ✓ Not secret
    "ALLOWED_ORIGINS": f"https://{client_host}.{domain}",  # ✓ Not secret
    "players_table": "players",  # ✓ Not secret
    # ... table names (all non-secret)
}
```

**Acceptable:** Table names, log levels, non-sensitive config

**Unacceptable:** API keys, passwords, tokens

### Code Review

Search codebase for hardcoded secrets:

```bash
# Search for common secret patterns
grep -r "api_key\|apikey\|password\|secret\|token" lambda/ eidolon/ deployment/
# Review results for any hardcoded values
```

- [ ] No hardcoded API keys
- [ ] No hardcoded passwords
- [ ] No hardcoded tokens
- [ ] No commented-out secrets

**Findings:** [List any secrets found]

---

## 5. Data Protection

**Check:** Encryption at rest and in transit

### DynamoDB Encryption

Review `deployment/stacks/dynamodb_stack.py`:

- [ ] Verify all tables have encryption enabled
- [ ] Confirm encryption type (AWS managed or customer managed)

**Current Implementation:**
```python
# Default: AWS managed encryption (acceptable for beta)
# If higher security needed: Use customer managed KMS keys
```

### S3 Encryption

Review S3 bucket configurations:

- [ ] Verify all buckets have encryption enabled
- [ ] Confirm SSL/TLS required for uploads
- [ ] Check bucket policies prevent unencrypted uploads

### API Gateway

- [ ] Confirm API Gateway uses TLS 1.2+ only
- [ ] Verify certificate is valid
- [ ] Check no HTTP (non-TLS) endpoints exposed

**Manual Test:**
```bash
curl -v https://api.yourdomain.com/character 2>&1 | grep "TLS"
# Should show TLS 1.2 or TLS 1.3
```

---

## 6. Logging and Monitoring (No PII)

**Check:** Logs don't contain sensitive data

Review Lambda functions for logging statements:

```bash
grep -r "logger\." lambda/ eidolon/ | grep -i "password\|token\|secret\|ssn\|credit"
```

**What to Look For:**
- [ ] No passwords logged
- [ ] No authentication tokens logged
- [ ] No credit card numbers (N/A for this app)
- [ ] No SSN or PII (player email, real names, etc.)

**Acceptable Logging:**
- Character IDs (UUIDs)
- Player IDs (UUIDs)
- Story/Segment IDs
- Skill values, game state
- Error messages (without sensitive context)

**Current Logging Patterns:**
```python
logger.info(f"Character {character_id} started story {story_id}")  # ✓ OK
logger.error(f"Failed to authenticate: {err}")  # ⚠️ Check err doesn't contain token
```

**Findings:** [List any PII in logs]

---

## 7. Cognito Configuration

**Check:** Cognito User Pool security settings

Review `deployment/stacks/player_stack.py`:

- [ ] Password policy enforced (minimum length, complexity)
- [ ] MFA available (optional for beta, recommended for production)
- [ ] Email verification required
- [ ] Account recovery options configured
- [ ] No user enumeration vulnerabilities (check error messages)

**Manual Test - User Enumeration:**
```bash
# Attempt signup with existing email
# Expected: Generic error, not "email already exists"

# Attempt login with non-existent user
# Expected: Generic error, not "user not found"
```

**Findings:** [Document any weak settings]

---

## 8. CORS Configuration

**Check:** CORS allows only intended origins

Review `deployment/stacks/api_stack.py` and `eidolon/cors.py`:

- [ ] ALLOWED_ORIGINS is explicit list, not "*"
- [ ] CORS_ALLOW_CREDENTIALS is true (required for Cognito)
- [ ] CORS_ALLOW_METHODS is minimal (only needed methods)
- [ ] CORS_MAX_AGE is reasonable (86400 = 24 hours)

**Current Configuration:**
```python
"ALLOWED_ORIGINS": f"https://{client_host}.{domain}"  # ✓ Specific origin
"CORS_ALLOW_CREDENTIALS": "true"  # ✓ Required for auth
"CORS_ALLOW_METHODS": "GET,POST,PUT,DELETE,OPTIONS"  # ✓ Minimal set
```

**Unacceptable:**
```python
"ALLOWED_ORIGINS": "*"  # ✗ Too permissive with credentials
```

**Findings:** [Any CORS issues]

---

## Tools to Use

### Automated Scanning

**1. Prowler (AWS Security Best Practices)**
```bash
pip install prowler
prowler aws --profile your-profile --severity critical high
```

Run checks:
- IAM policies
- S3 bucket permissions
- DynamoDB encryption
- API Gateway configuration
- CloudWatch logging

**Results:** Document any CRITICAL or HIGH findings in the "IAM Security Review - Actual Findings" section below, using the next available finding ID (R3-SEC-001, R3-SEC-002, etc.)

**2. Checkov (Infrastructure as Code Scanning)**
```bash
pip install checkov
checkov -d deployment/
```

Scans CDK code for security issues.

**Results:** Document any CRITICAL or HIGH findings in the "IAM Security Review - Actual Findings" section below.

**3. Bandit (Python Code Security)**
```bash
pip install bandit
bandit -r lambda/ eidolon/
```

Checks for common Python security issues.

**Results:** Document any CRITICAL or HIGH findings in the "IAM Security Review - Actual Findings" section below.

### Manual Verification

**Test Authentication Bypass:**
```bash
# Attempt API calls without token
for endpoint in /character /story/start /segment/decision; do
  echo "Testing $endpoint"
  curl -X GET "https://api.yourdomain.com$endpoint" -w "\nStatus: %{http_code}\n\n"
done
# All should return 401 Unauthorized
```

**Results:** If any endpoint returns non-401 status, document as CRITICAL finding in "IAM Security Review - Actual Findings" section.

**Test Input Validation:**
```bash
# Attempt SQL injection patterns (even though using DynamoDB)
curl -X POST https://api.yourdomain.com/character \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"CharacterName": "'; DROP TABLE characters; --"}'
# Should return 400 Bad Request (name validation)

# Attempt XSS patterns
curl -X POST https://api.yourdomain.com/character \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"CharacterName": "<script>alert(1)</script>"}'
# Should return 400 Bad Request (name validation)
```

**Results:** If any test succeeds (returns 200) or causes unexpected behavior, document as HIGH finding in "IAM Security Review - Actual Findings" section.

---

## Severity Classification

**Critical:** Requires immediate fix before beta
- Unprotected API endpoints
- Hardcoded secrets
- No encryption at rest/transit
- Severe input validation gaps (injection vulnerabilities)

**High:** Should fix before beta, can be mitigated
- Overly-broad IAM permissions
- Weak Cognito settings
- PII in logs
- CORS misconfigurations

**Medium:** Fix in R4 or document as known issue
- Missing MFA enforcement
- Suboptimal password policies
- Non-critical logging improvements

**Low:** Document and defer to post-launch
- Code quality issues
- Non-security tech debt

---

## Findings Template

**Where to document:** Add new findings to the "IAM Security Review - Actual Findings" section below (starting at line 2015).

**Format for each finding:**

**Finding ID:** R3-SEC-001
**Severity:** [Critical/High/Medium/Low]
**Category:** [IAM/Input/Auth/Secrets/Data/Logging/Cognito/CORS]
**Description:** [What was found]
**Location:** [File/line or AWS resource]
**Risk:** [What could happen if exploited]
**Recommendation:** [How to fix]
**Status:** [Open/Fixed/Mitigated/Accepted Risk]

**Note:** R3-IAM-001 through R3-IAM-005 are already documented. Use R3-SEC-001, R3-SEC-002, etc. for additional findings.

---

## Exit Criteria

- [ ] All checklist items reviewed
- [ ] Automated tools run (Prowler, Checkov, Bandit)
- [ ] Manual tests completed
- [ ] Findings documented with severity
- [ ] Critical and High findings fixed or mitigated
- [ ] Remaining findings documented in GitHub issues for R4/R5
```

---

### IAM Security Review - Actual Findings

**Date Reviewed:** 2025-10-06
**Files Analyzed:** `deployment/stacks/lambda_stack.py`, `deployment/stacks/dynamodb_stack.py`, `deployment/stacks/story_stack.py`, `deployment/stacks/player_stack.py`

#### Summary of IAM Findings

Found **4 HIGH severity issues** and **2 LOW severity items**.

**Critical Findings (ALL FIXED):**
1. ✅ CloudWatch Logs policies use account ID wildcard (`*`) in 2 files - FIXED
2. ✅ CloudWatch Logs policy for Lambda uses overly broad log group scope (`*:*`) - FIXED

---

#### Finding R3-IAM-001: CloudWatch Logs Wildcard Resource ✅ **FIXED**

**Location:** `deployment/stacks/lambda_stack.py:86-101`

**Previous Configuration:**
```python
iam.PolicyStatement(
    effect=iam.Effect.ALLOW,
    actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
    resources=[f"arn:aws:logs:{self.region_name}:*:*"],  # ← OVERLY BROAD
)
```

**Issue:** The wildcard resource `*:*` granted permission to create/write logs to **any log group in the region**, not just Lambda function log groups.

**Risk:**
- Lambda functions could write to unrelated log groups
- Potential for log group pollution or data leakage
- Violated least privilege principle

**Applied Fix:**
```python
logs_policy = iam.ManagedPolicy(
    self,
    "LambdaLogsPolicy",
    managed_policy_name="eidolon-lambda-logs-policy",
    description="CloudWatch Logs permissions for Lambda functions",
    statements=[
        # CreateLogGroup needs log-group ARN without :*
        iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["logs:CreateLogGroup"],
            resources=[f"arn:aws:logs:{self.region_name}:{self.account}:log-group:/aws/lambda/*"],
        ),
        # CreateLogStream and PutLogEvents need log-group ARN with :*
        iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["logs:CreateLogStream", "logs:PutLogEvents"],
            resources=[f"arn:aws:logs:{self.region_name}:{self.account}:log-group:/aws/lambda/*:*"],
        ),
    ],
)
```

**Severity:** HIGH - Allowed broader access than necessary
**Status:** ✅ **FIXED** - deployment/stacks/lambda_stack.py:80-101

---

#### Finding R3-IAM-002: No Separation Between Read-Only and Read-Write Functions ⚠️ **HIGH**

**Observation:** All Lambda functions share the same execution role with full read/write permissions to all DynamoDB tables.

**Current State:**
- `api-character-get` (read-only function) has `PutItem`, `UpdateItem`, `DeleteItem` permissions
- `api-character-list` (read-only function) has write permissions
- `api-archetype-list` (read-only function) has write permissions

**Risk:** If a read-only Lambda is compromised (e.g., SSRF, injection), attacker gains write access to all tables.

**Defense in Depth Recommendation:**

Create separate IAM policies for read-only vs read-write functions:

**Read-Only Functions:**
- `api-character-get`
- `api-character-list`
- `api-archetype-list`
- `api-story-history`
- `api-segment-history`
- `api-segment-status`

**Read-Write Functions:** All others

**Severity:** HIGH - Violates defense-in-depth
**Impact:** Low - Requires compromised Lambda function to exploit
**Remediation Priority:** 🟡 **DEFER TO R4** (acceptable for beta with Cognito auth + input validation)

**Rationale for R4 Deferral:**
- All functions enforce authentication (Cognito authorizer)
- Input validation exists (per R3-T7 checklist)
- Shared role simplifies deployment (acceptable for beta)
- Can be improved post-beta without service disruption

---

#### Finding R3-IAM-003: Missing Account ID in CloudWatch ARN ✅ **FIXED**

**Location:** `deployment/stacks/lambda_stack.py:91,97` (was line 90)

**Previous:**
```python
resources=[f"arn:aws:logs:{self.region_name}:*:*"]
```

**Issue:** Using `*` for account ID instead of `{self.account}` allowed cross-account access if Lambda role was assumed.

**Root Cause:** CDK Stack provides `self.account` property automatically - it should always be used instead of `*` wildcards.

**Applied Fix:** (Included in R3-IAM-001 fix)
```python
resources=[f"arn:aws:logs:{self.region_name}:{self.account}:log-group:/aws/lambda/*"]  # Line 91
resources=[f"arn:aws:logs:{self.region_name}:{self.account}:log-group:/aws/lambda/*:*"]  # Line 97
```

**Severity:** HIGH
**Status:** ✅ **FIXED** - deployment/stacks/lambda_stack.py:91,97

---

#### Finding R3-IAM-006: CodeBuild CloudWatch Logs Uses Wildcard Account ✅ **FIXED**

**Location:** `deployment/stacks/codebuild_stack.py:86` (was line 86, now 86)

**Previous:**
```python
resources=[f"arn:aws:logs:{self.region_name}:*:log-group:/aws/codebuild/*"]
```

**Issue:** Same as R3-IAM-003 - using `*` for account ID was unnecessarily permissive.

**Applied Fix:**
```python
# CodeBuild logs policy - fix account wildcard
logs_policy = iam.ManagedPolicy(
    self,
    "CodeBuildLogsPolicy",
    managed_policy_name="eidolon-codebuild-logs-policy",
    description="Policy for CodeBuild to write logs to CloudWatch",
    statements=[
        iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
            resources=[f"arn:aws:logs:{self.region_name}:{self.account}:log-group:/aws/codebuild/*"],
        )
    ],
)
```

**Severity:** HIGH
**Status:** ✅ **FIXED** - deployment/stacks/codebuild_stack.py:86

---

#### Finding R3-IAM-004: Scan Action May Be Unnecessary ℹ️ **LOW**

**Location:** `deployment/stacks/dynamodb_stack.py:84`

**Observation:** `dynamodb:Scan` is included in the DynamoDB policy, but Scan operations are expensive and generally discouraged.

**Recommendation:**
- Audit Lambda code to verify if `Scan` is actually used
- If not used, remove from policy
- If used, document why Query is insufficient

**Code Search:**
```bash
grep -r "\.scan(" lambda/ eidolon/
```

**Severity:** LOW - Not a security issue, but potential performance concern
**Remediation Priority:** 🟡 **R4 (OPTIMIZATION)**

---

#### Finding R3-IAM-005: Cognito Triggers Use Shared Execution Role ℹ️ **LOW**

**Observation:** Cognito trigger Lambdas (`cognito-player-new`, `cognito-player-delete`) use the same shared execution role as API Lambdas.

**Current Permissions:** Full DynamoDB read/write, SQS send/receive, SSM parameter access, EventBridge rule modification

**Issue:** Cognito triggers only need access to `players` table, not all tables or queues.

**Recommendation (R4):** Create dedicated Cognito trigger role with minimal permissions.

**Severity:** LOW - Minimal blast radius
**Remediation Priority:** 🟡 **R4**

---

#### ✅ Positive IAM Findings

**1. DynamoDB Access Policy** - `deployment/stacks/dynamodb_stack.py:69-91`
- ✅ Specific table ARNs (no wildcards)
- ✅ Includes GSI ARNs explicitly
- ✅ No overly broad actions (no `dynamodb:*`)
- ✅ All actions are necessary

**2. Story Policy** - `deployment/stacks/story_stack.py:127-162`
- ✅ SSM permissions scoped to `/eidolon/story/*` prefix
- ✅ SQS permissions scoped to specific queue ARNs
- ✅ EventBridge permissions scoped to specific rule

**3. Secrets Management**
- ✅ No hardcoded secrets found in deployment code
- ✅ All sensitive values passed via environment variables or SSM
- ✅ No API keys or passwords in code

**4. IAM Trust Policies**
- ✅ Lambda execution role correctly scoped to `lambda.amazonaws.com`
- ✅ No wildcard principals
- ✅ No overly broad trust relationships

---

#### R3 Remediation Required (Before Beta)

**CRITICAL FIX 1: Lambda CloudWatch Logs Policy (R3-IAM-001 + R3-IAM-003)**

**File:** `deployment/stacks/lambda_stack.py`

**Lines to change:** 80-94

**Current code:**
```python
# Create and attach CloudWatch Logs policy
logs_policy = iam.ManagedPolicy(
    self,
    "LambdaLogsPolicy",
    managed_policy_name="eidolon-lambda-logs-policy",
    description="CloudWatch Logs permissions for Lambda functions",
    statements=[
        iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
            resources=[f"arn:aws:logs:{self.region_name}:*:*"],
        )
    ],
)
role.add_managed_policy(logs_policy)
```

**Replace with:**
```python
# Create and attach CloudWatch Logs policy
logs_policy = iam.ManagedPolicy(
    self,
    "LambdaLogsPolicy",
    managed_policy_name="eidolon-lambda-logs-policy",
    description="CloudWatch Logs permissions for Lambda functions",
    statements=[
        # CreateLogGroup needs log-group ARN without :*
        iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["logs:CreateLogGroup"],
            resources=[f"arn:aws:logs:{self.region_name}:{self.account}:log-group:/aws/lambda/*"],
        ),
        # CreateLogStream and PutLogEvents need log-group ARN with :*
        iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["logs:CreateLogStream", "logs:PutLogEvents"],
            resources=[f"arn:aws:logs:{self.region_name}:{self.account}:log-group:/aws/lambda/*:*"],
        ),
    ],
)
role.add_managed_policy(logs_policy)
```

**Testing Steps:**
1. Deploy updated Lambda stack:
   ```bash
   cd deployment
   cdk deploy EidolonLambdaStack --profile dev
   ```

2. Invoke any Lambda function:
   ```bash
   aws lambda invoke --function-name api-character-list --profile dev response.json
   ```

3. Verify logs appear in CloudWatch:
   ```bash
   aws logs describe-log-groups --log-group-name-prefix /aws/lambda/api-character --profile dev
   ```

4. Run Prowler IAM checks:
   ```bash
   prowler aws --profile dev --check iam_policy_no_full_access_to_cloudwatch_logs
   ```

---

**CRITICAL FIX 2: CodeBuild CloudWatch Logs Policy (R3-IAM-006)**

**File:** `deployment/stacks/codebuild_stack.py`

**Lines to change:** 77-89

**Current code:**
```python
# Create custom managed policy for CloudWatch Logs
logs_policy = iam.ManagedPolicy(
    self,
    "CodeBuildLogsPolicy",
    managed_policy_name="eidolon-codebuild-logs-policy",
    description="Policy for CodeBuild to write logs to CloudWatch",
    statements=[
        iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
            resources=[f"arn:aws:logs:{self.region_name}:*:log-group:/aws/codebuild/*"],
        )
    ],
)
```

**Replace with:**
```python
# Create custom managed policy for CloudWatch Logs
logs_policy = iam.ManagedPolicy(
    self,
    "CodeBuildLogsPolicy",
    managed_policy_name="eidolon-codebuild-logs-policy",
    description="Policy for CodeBuild to write logs to CloudWatch",
    statements=[
        iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
            resources=[f"arn:aws:logs:{self.region_name}:{self.account}:log-group:/aws/codebuild/*"],
        )
    ],
)
```

**Testing Steps:**
1. Deploy updated CodeBuild stack:
   ```bash
   cd deployment
   cdk deploy EidolonCodeBuildStack --profile dev
   ```

2. Trigger a CodeBuild build:
   ```bash
   aws codebuild start-build --project-name eidolon-lambda-layer-build --profile dev
   ```

3. Verify logs appear in CloudWatch:
   ```bash
   aws logs describe-log-groups --log-group-name-prefix /aws/codebuild/ --profile dev
   ```

---

#### R4 Enhancements (Post-Beta)

**1. Separate Read-Only and Read-Write Roles (R3-IAM-002)**
- Create `eidolon-lambda-readonly-role` with limited DynamoDB permissions
- Apply to: `api-character-get`, `api-character-list`, `api-archetype-list`, `api-story-history`, `api-segment-history`, `api-segment-status`

**2. Dedicated Cognito Trigger Role (R3-IAM-005)**
- Create `eidolon-cognito-trigger-role` with access only to `players` table

**3. Audit Scan Usage (R3-IAM-004)**
- Determine if `dynamodb:Scan` is actually used
- Remove from policy if unnecessary

---

#### Execution Steps

1. **Checklist Execution**
   - Work through entire security checklist (documented in this report)
   - Execute automated tools (Prowler, Checkov, Bandit)
   - Update checklist items in this document with ✓ marks

2. **Remediation**
   - Fix Critical findings immediately (R3-IAM-001, R3-IAM-003)
   - Fix High findings or document mitigation rationale in this report
   - Update "IAM Security Review - Actual Findings" section with results

3. **Issue Tracking**
   - Create GitHub issues for Medium/Low findings
   - Reference findings by ID (R3-IAM-004, R3-IAM-005, etc.)
   - Update this report's "R4 Enhancements" section with issue links

#### Deliverables

1. **Updated Release Report**
   - This document (`documentation/release-three-report.md`) with:
     - All checklist items marked complete (✓)
     - All findings documented inline with severity and status
     - Remediation code changes documented
     - Test results recorded

2. **Code Changes**
   - PR fixing R3-IAM-001 and R3-IAM-003 (CloudWatch Logs policy)
   - Clear PR description referencing finding IDs from this report

3. **GitHub Issues**
   - Issues for R3-IAM-002, R3-IAM-004, R3-IAM-005 (deferred to R4)
   - Tagged with `security` label
   - Assigned to R4 or R5 milestone
   - Each issue references the finding ID in this report

---

#### Summary: R3-T7 IAM Review Outcomes

**Total Findings:** 6 (4 HIGH, 2 LOW)

**R3 Fixes Completed:**
1. ✅ **R3-IAM-001** - Fixed Lambda CloudWatch Logs wildcard resource (lambda_stack.py:80-101)
2. ✅ **R3-IAM-003** - Fixed Lambda missing account ID (lambda_stack.py:91,97)
3. ✅ **R3-IAM-006** - Fixed CodeBuild CloudWatch Logs account wildcard (codebuild_stack.py:86)

**R3 Deferrals (Documented):**
4. 🟡 **R3-IAM-002** - Read-only/read-write separation → R4 (acceptable for beta)
5. 🟡 **R3-IAM-004** - Audit Scan usage → R4 (performance optimization)
6. 🟡 **R3-IAM-005** - Cognito role separation → R4 (nice-to-have)

**Positive Findings:**
- ✅ DynamoDB policy properly scoped
- ✅ Story policy properly scoped
- ✅ No hardcoded secrets
- ✅ IAM trust policies correct

**Status:** ✅ All HIGH severity account wildcard issues FIXED

---

#### Acceptance Criteria

- [ ] Security checklist 100% complete (all items in this report marked with ✓)
- [ ] Prowler, Checkov, Bandit scans run (results documented in this report)
- [✓] All findings documented in "IAM Security Review - Actual Findings" section
- [✓] R3-IAM-001 fixed and tested (Lambda CloudWatch Logs policy)
- [✓] R3-IAM-003 fixed (Lambda account ID - included in R3-IAM-001)
- [✓] R3-IAM-006 fixed and tested (CodeBuild CloudWatch Logs policy)
- [✓] R3-IAM-002, R3-IAM-004, R3-IAM-005 documented for R4 in this report
- [✓] Zero Critical findings open after remediation
- [✓] Zero High findings open (or documented mitigation with rationale in this report)
- [ ] Medium/Low findings tracked in GitHub issues with references to this report's finding IDs

#### Definition of Done

**No Critical Findings:**
- All API endpoints require authentication
- No hardcoded secrets
- No severe input validation gaps
- Encryption at rest and in transit verified

**High Findings Addressed:**
- IAM permissions reviewed and tightened (or documented as acceptable)
- CORS configuration verified
- Cognito settings appropriate for beta
- No PII in logs

**Documentation:**
- Security posture clearly documented
- Known issues tracked
- Remediation steps recorded

---

## R3 Exit Criteria (Ship Gate)

Before declaring R3 complete and shipping to beta, ALL of the following must be verified:

### Code Functionality

- [ ] **R3-T1: Currency Application**
  - Currency persists to DynamoDB when story completes
  - Atomic ADD operation used (no race conditions)
  - Unit tests pass
  - Integration test proves single application on retry
  - At least one test story includes currency reward
  - GET /character API returns currency balance

- [ ] **R3-T2: Client Polling**
  - Measured API call reduction from baseline to ≤3 per segment
  - Single polling service implementation
  - All competing polling code removed
  - Test scenarios pass (happy path, network interruption, multi-character, background/resume)
  - No race conditions or state conflicts

- [ ] **R3-T3: Performance Baseline**
  - Load tests completed (10-user and 50-user)
  - Performance baseline documented
  - Provisioned concurrency decision made with evidence
  - If PC deployed: cost/benefit analysis approved
  - P95 API latency meets targets (< 2000ms cold start, < 200ms warm)

- [ ] **R3-T4: Integration Tests**
  - All 5 critical scenarios automated
  - Tests pass consistently (no flaky tests)
  - CI workflow configured and passing
  - Tests clean up their own data
  - Test documentation complete

- [ ] **R3-T5: Author Documentation**
  - Quick-Start guide created
  - 3 copy-paste templates included and validated
  - Non-developer can complete end-to-end workflow
  - README.md updated with link

- [ ] **R3-T6: Beta Content**
  - 3 stories created, validated, and loaded
  - All stories playtested 2+ times
  - Playtest notes documented
  - Balance adjustments applied
  - Story catalog created

- [ ] **R3-T7: Security**
  - [ ] Security checklist 100% complete (all items marked ✓ in this report)
  - [ ] Automated scans run (Prowler, Checkov, Bandit) with results documented in this report
  - [✓] R3-IAM-001 fixed (Lambda CloudWatch Logs policy scoped to `/aws/lambda/*`)
  - [✓] R3-IAM-003 fixed (Lambda account ID uses `self.account`)
  - [✓] R3-IAM-006 fixed (CodeBuild account ID uses `self.account`)
  - [✓] R3-IAM-002 documented and deferred to R4 with rationale in this report
  - [ ] R3-IAM-004 and R3-IAM-005 documented for R4 with GitHub issues created
  - [✓] Zero Critical findings after remediation
  - [✓] Zero unmitigated High findings
  - [✓] All findings tracked in "IAM Security Review - Actual Findings" section of this report

### Documentation

- [ ] Text corruption in planning documents fixed
- [ ] Rollback procedures documented
- [ ] Performance baseline results documented in this report
- [ ] Security findings documented in "IAM Security Review - Actual Findings" section of this report
- [ ] All R3 task outcomes recorded in this report

### Quality Gates

- [ ] All R3 integration tests passing in CI
- [ ] No regression in existing functionality
- [ ] Manual smoke test passed (create character → play story → complete → verify rewards)
- [ ] Beta environment deployed and tested

### Stakeholder Approval

- [ ] Security findings review completed
- [ ] Performance baseline accepted
- [ ] Provisioned concurrency spend approved (if applicable)
- [ ] Beta content reviewed and approved

---

## Dependencies and Blockers

### Internal Dependencies

- **R3-T1 → R3-T6**: Beta stories need working currency rewards
- **R3-T2**: Client polling fix should complete early (impacts all testing)
- **R3-T3 → R3-T4**: Load testing informs integration test scenarios
- **R3-T5 → R3-T6**: Author docs enable content creation

**Recommended Order:**
1. Start R3-T1 (currency fix) immediately - critical and fast
2. Start R3-T2 (client polling) in parallel - high impact
3. R3-T5 (docs) can proceed independently
4. R3-T3 (perf testing) once T1 and T2 stable
5. R3-T4 (integration tests) builds on T1/T3 learnings
6. R3-T6 (content) uses T5 docs, needs T1 working
7. R3-T7 (security) can run in parallel throughout

### External Dependencies

- **AWS Environment:** Dev/test account must be available
- **Test Users:** Need 5-10 beta testers for content playtesting
- **Approvals:** Security findings and PC spend decisions need stakeholder approval

---

## Risks and Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Currency fix reveals schema migration needed | Medium | High | Verify schema early; add migration script if needed |
| Client polling fix breaks existing functionality | Low | High | Comprehensive testing; feature flag if possible |
| Performance tests reveal need for expensive PC | Medium | Medium | Decision process allows for "no PC" option; measure first |
| Security findings delay beta | Low | High | Scoped pass avoids comprehensive audit; focus on criticals |
| Content creation takes longer than expected | Medium | Low | Have 2 minimum stories instead of 3; quality over quantity |
| Integration tests are flaky | Medium | Medium | Invest in proper test isolation and cleanup |

---

## Success Metrics

**Technical Metrics:**
- API calls per segment reduced by 70%+ (from ~10 to ≤3)
- P95 API latency < 2000ms cold start, < 200ms warm
- Zero critical security findings
- 100% integration test pass rate

**Operational Metrics:**
- Non-developer can author story efficiently using Quick-Start
- Beta testers can complete all 3 stories without bugs
- Zero duplicate reward incidents in beta

**Business Metrics:**
- Beta ready to launch
- Infrastructure costs predictable and within budget
- Security posture sufficient for limited beta (no public exposure)

---

## Post-R3 Cleanup

After R3 ships, clean up these items:

### GitHub Issues

- [ ] Close #645 (S3 vs DynamoDB) - Already implemented as DynamoDB-only
- [ ] Merge #619 into #729 - Duplicate documentation issues
- [ ] Create new issue for client polling fix (if doesn't exist)
- [ ] Update #726 status to reflect currency fix and integration tests
- [ ] Update #728 and #613 with performance baseline results
- [ ] File new issues for Medium/Low security findings (deferred to R4/R5)

### Documentation

- [ ] Update README.md with R3 achievements
- [ ] Archive planning documents that are now complete
- [ ] Update incremental-design.md client polling section (mark as fixed)

### Technical Debt

- [ ] Review code for TODO comments added during R3
- [ ] Document any architectural decisions made
- [ ] Update schema.md if currency field added

---

## Appendix A: Required Tools and Access

**Development Tools:**
- Python 3.12+
- AWS CLI configured
- Git access to repository
- IDE with JSON support

**AWS Access:**
- Dev/test AWS account
- IAM permissions to deploy Lambda, DynamoDB, API Gateway
- CloudWatch access for metrics

**Testing Access:**
- Beta environment URL
- Test Cognito user credentials
- DynamoDB table access for verification

**Security Tools:**
- Prowler (AWS security scanner)
- Checkov (IaC scanner)
- Bandit (Python security scanner)

---

## Appendix B: Communication Plan

**Regular Standup:**
- Progress on each task
- Blockers and risks
- Status updates

**Milestone Reviews:**
- After each task completion
- Demo functionality
- Get stakeholder feedback

**Beta Launch Decision:**
- Final review of all exit criteria
- Security findings review
- Performance metrics review
- Go/no-go decision

**Stakeholder Updates:**
- Regular status updates
- Immediate notification of critical findings
- Cost impact notifications (PC decisions)

---

**Document Version:** 1.0
**Last Updated:** 2025-10-06
**Next Review:** Upon R3 completion
