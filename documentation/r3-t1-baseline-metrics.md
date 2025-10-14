# R3-T1: Client Polling Cadence - Baseline Metrics

**Date:** 2025-10-13
**Test Story:** Gremlin Mischief (3 segments, ~180s each)
**Total Duration:** 549 seconds (9m 9s)

## Summary

**Total API Calls:** 15
**Per-Segment Average:** 5 calls
**Target:** 2-3 calls per segment

**Breakdown:**
- GET /segment/status: 9 calls (60%)
- GET /character: 6 calls (40%)
- GET /segment/history: 1 call (completion only)
- POST /story/start: 1 call (initiation only)

## Detailed Call Pattern

### Segment 1: Tracking the gremlin (180s duration)

```
00:16:10.3 - POST /story/start
00:16:13.1 - [SEGMENT #2 STARTED]
00:17:13.2 - GET /segment/status (+60s) → processed, TimeRemaining=116s
00:19:11.1 - GET /character (+178s) → segment boundary reload
00:19:14.6 - GET /segment/status (+181s) → next segment, pending
```

**Calls this segment:** 4 (1 start + 1 status + 1 character + 1 status for next)

### Segment 2: Cornering the gremlin (180s duration)

```
00:19:14.6 - GET /segment/status → pending
00:19:45.3 - GET /segment/status (+31s) → processed, TimeRemaining=145s
00:22:10.9 - GET /character (+177s) → segment boundary reload
00:22:13.5 - GET /segment/status (+3s) → next segment, pending
```

**Calls this segment:** 4 (2 status + 1 character + 1 status for next)

### Segment 3: Fighting the gremlin (180s duration) - BUG DETECTED

```
00:22:13.5 - GET /segment/status → pending
00:22:44.3 - GET /segment/status (+31s) → processed, TimeRemaining=146s
00:25:10.8 - GET /character (+177s) → segment boundary reload
00:25:13.6 - GET /segment/status (+3s) → TimeRemaining=0
00:25:14.2 - GET /character (+0.6s) ⚠️ DUPLICATE
00:25:16.6 - GET /segment/status (+3s) ⚠️ DUPLICATE (TimeRemaining=0)
00:25:16.9 - GET /character (+0.3s) ⚠️ DUPLICATE
00:25:19.4 - GET /segment/status (+3s) ⚠️ DUPLICATE (TimeRemaining=0)
00:25:19.7 - GET /character (+0.3s) ⚠️ DUPLICATE
00:25:22.1 - GET /segment/status (+3s) → 404 No active segment
00:25:22.2 - GET /character (story completion)
00:25:22.7 - GET /segment/history (story completion)
```

**Calls this segment:** 11 (5 status + 5 character + 1 history)
**Duplicate calls:** 7 (4 extra status + 3 extra character)

## Problems Identified

### 1. Hardcoded 60-Second Initial Delay

**Location:** `story_polling_service.dart:26`

```dart
static const int _initialDelaySeconds = 60;
```

**Issue:** Client ignores server's `PollAfter` field and uses hardcoded delay

**Server response includes:**
```json
"ProcessingStatus": "pending",
"PollAfter": "2025-10-13T04:17:09Z"
```

**Impact:**
- Adds fixed 60s wait even if segment processes faster
- Ignores server's polling guidance
- Not truly server-authoritative

### 2. Duplicate Calls at Segment Completion

**Location:** `story_polling_service.dart:172-195`

**Pattern observed:**
- When TimeRemaining reaches 0, service enters retry loop
- Makes repeated GET /segment/status calls every 2-3 seconds
- Eventually gets 404 after 4-5 duplicates

**Root cause:** Logic for "segment complete" triggers multiple times without proper state management

**Impact:** 4-5 extra API calls in final segment

### 3. Excessive Character Reloads

**Location:** `story_polling_service.dart:135, 177`

**Issue:** GET /character called at every segment boundary

**Current pattern:**
- Segment 1 → GET /character
- Segment 2 → GET /character
- Segment 3 → GET /character (multiple times due to bug)
- Story complete → GET /character

**Expected pattern:**
- Story complete → GET /character (once)

**Impact:** 2-3 extra character reloads per story

### 4. Aggressive Pending Retry

**Location:** `story_polling_service.dart:113-123`

**Current:** 30-second fixed retry when ProcessingStatus='pending'

**Observation:** Works correctly but could use exponential backoff

**Impact:** Acceptable for now, low priority

## Expected Improvements

### Fix Impact Projection

| Fix | Calls Saved | Notes |
|-----|-------------|-------|
| Use PollAfter instead of 60s delay | 0 calls | Timing optimization only |
| Fix duplicate call bug | 2-3 calls/story | In final segment only |
| Remove mid-story character reloads | 2 calls/story | Keep only at completion |
| **Total reduction** | **4-5 calls/story** | From 15 → 10-11 calls |

### Per-Segment Projection

**Current:** 5 calls/segment average
**After fixes:** 3.3 calls/segment average (10 calls / 3 segments)
**Stretch goal:** 3 calls/segment (9 calls / 3 segments)

**Breakdown after fixes:**
- Segment 1: 3 calls (start + status + status for next)
- Segment 2: 3 calls (2 status + status for next)
- Segment 3: 3 calls (2 status + 404)
- Completion: 2 calls (character + history)

## Target Architecture

### Server-Authoritative Polling Pattern

```dart
// 1. Start story
POST /story/start → returns initial segment with PollAfter

// 2. Check immediately (no delay)
GET /segment/status
  if ProcessingStatus == 'pending':
    use PollAfter to schedule next check
  if ProcessingStatus == 'processed':
    wait for TimeRemaining, then check for next segment

// 3. At segment boundary
GET /segment/status → next segment or 404

// 4. Story complete (when 404 received)
GET /character → reload character state
GET /segment/history → load completed segments
```

**Expected calls per segment:** 2-3
- 1-2 status checks during segment
- 1 status check for next segment or completion

## Test Scenarios for Validation

After implementing fixes, test:

1. **Happy path:** 3-segment story, verify ≤3 calls per segment
2. **Fast processing:** Segment processes in <10s, verify no unnecessary waits
3. **Slow processing:** Segment takes >60s, verify proper PollAfter usage
4. **Network interruption:** Disconnect mid-segment, verify recovery
5. **Background/resume:** Background app during segment, verify correct state on resume

## Notes

- Instrumentation code (`api_metrics.dart`) to be removed after validation
- All metrics collected via `[API-METRICS]` console logs
- Server's `PollAfter` field currently ignored by client
- Final segment shows buggy retry behavior not present in earlier segments
