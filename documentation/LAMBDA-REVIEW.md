# Lambda Function Review - Complete Analysis

All 18 Lambda functions reviewed from code, not documentation.

**Review Date:** 2025-01-24
**Updated:** 2025-10-19

---

## Summary

**Total Functions:** 18
**Functionally Correct:** 18

All Lambda functions follow proper patterns:

- ✅ Proper error handling (ValueError → 400/404, RuntimeError → 500)
- ✅ CORS handling
- ✅ Authentication via Cognito authorizer
- ✅ Business logic separated from Lambda handler
- ✅ Consistent logging
- ✅ No exceptions raised (all caught and returned as HTTP responses)

---

## API Functions (13 total)

### 1. api_archetype_list.py

**Purpose:** Return list of player-available archetypes

**Status:** ✅ WORKS CORRECTLY

**Implementation:**

- Loads archetypes at module initialization (cold start)
- Caches results in module-level variable
- Filters for Player=true archetypes only
- Fallback: retries load if cache initialization failed

**No Issues Found**

---

### 2. api_character_add.py

**Purpose:** Create new character for authenticated player

**Status:** ✅ WORKS CORRECTLY

**Implementation:**

- Validates character name format and checks bloom filter for obscenity
- Checks player character limit (MAX_CHARACTERS_PER_PLAYER)
- Validates archetype or uses defaults
- Creates character record with starting items
- Adds to player's CharacterList

**No Issues Found**

---

### 3. api_character_delete.py

**Purpose:** Delete character and all associated data

**Status:** ✅ WORKS CORRECTLY

**Implementation:**

- Verifies ownership via character_get()
- Deletes character record
- Deletes all character items
- Deletes active segments
- Removes from player's CharacterList
- Returns deletion statistics

**No Issues Found**

---

### 4. api_character_get.py

**Purpose:** Retrieve full character data with inventory details

**Status:** ✅ WORKS CORRECTLY (but inventory enrichment may be failing)

**Implementation:**

- Gets character and validates ownership
- Gets active story and segment (handles broken chains)
- **Calls get_inventory() to enrich inventory with item details**
- Returns character + active story + active segment OR available stories

**Potential Issue:**
The function calls `get_inventory(inventory)` to populate `InventoryDetails`, but players report seeing UUIDs instead of item names. This suggests either:

1. get_inventory() is failing silently
2. Items table doesn't contain Name field
3. Data structure mismatch

**The Lambda function itself is correct. The bug is in get_inventory() library function or Items table data.**

---

### 5. api_character_list.py

**Purpose:** List all characters for authenticated player

**Status:** ✅ WORKS CORRECTLY

**Implementation:**

- Extracts player ID from JWT
- Gets player's CharacterList from Players table
- Returns character names and Dead status

**No Issues Found**

---

### 6. api_item_brief.py

**Purpose:** Return lightweight item metadata (ItemID + PrototypeID) for IndexedDB caching

**Status:** ✅ WORKS CORRECTLY

**Implementation:**

- Validates player authentication
- Validates ItemID parameter
- Fetches item from Items table
- Returns only ItemID and PrototypeID (minimizes payload)

**No Issues Found**

---

### 7. api_item_prototype.py

**Purpose:** Return complete prototype definition for IndexedDB caching

**Status:** ✅ WORKS CORRECTLY

**Implementation:**

- Validates player authentication
- Validates PrototypeID parameter
- Fetches prototype from Prototypes table
- Converts Decimal to float
- Returns full prototype data

**No Issues Found**

---

### 8. api_segment_decision.py

**Purpose:** Submit player's decision for decision segment

**Status:** ✅ WORKS CORRECTLY

**Implementation:**

- Validates player authentication
- Parses CharacterID and Decision from request body
- Calls submit_decision_for_character() to store decision
- Returns accepted status

**No Issues Found**

---

### 9. api_segment_history.py

**Purpose:** Retrieve completed segment history for character's story

**Status:** ✅ WORKS CORRECTLY

**Implementation:**

- Verifies character ownership
- Tries to get StoryInstanceID from active segment
- Falls back to story history if no active segment
- Queries SegmentHistory table
- Formats and enriches segment data for Flutter
- Excludes current active segment from history
- Sorts by completion time descending

**No Issues Found**

---

### 10. api_segment_status.py

**Purpose:** Poll active segment status and return results when ready

**Status:** ✅ WORKS CORRECTLY

**Implementation:**

- Verifies character ownership
- Gets active segment data
- Calculates TimeRemaining and PollAfter guidance
- Returns basic status if still processing
- Returns full results (Narrative, ClientEvents, CharacterUpdates) when ProcessingStatus="processed"
- Filters decision options to exclude Difficulty and Narrative (security)
- Includes NextSegmentPreview for smooth transitions

**No Issues Found**

---

### 11. api_story_abandon.py

**Purpose:** Abandon active story and clean up state

**Status:** ✅ WORKS CORRECTLY

**Implementation:**

- Validates character is in Incremental mode
- Marks active segment as "abandoned"
- Updates character: adds to AbandonedStories set, clears GameMode/ActiveStoryID/ActiveSegmentID
- Records abandonment in story history
- Records abandoned segment in segment history
- Leaves segment record with status="abandoned" (doesn't delete)

**No Issues Found**

---

### 12. api_story_history.py

**Purpose:** Retrieve story history entries for character

**Status:** ✅ WORKS CORRECTLY

**Implementation:**

- Accepts up to 10 StoryInstanceIDs (comma-separated or JSON array)
- Verifies character ownership
- Batch gets story history records
- Returns stories in requested order with Missing array for not found

**No Issues Found**

---

### 13. api_story_start.py

**Purpose:** Start new story for character

**Status:** ✅ WORKS CORRECTLY

**Implementation:**

- Gets character and validates ownership
- ✅ Calls story_eligibility() which NOW checks both GameMode AND CharState
- Validates story is in character's AvailableStories
- Gets story and first segment
- Creates story history entry
- Creates initial active segment
- Updates character with ActiveStoryID and ActiveSegmentID
- Queues mechanical segments for processing
- Enables polling system

**Previous Bug:** Dead characters with GameMode="None" could start stories
**Fix Applied:**

- Added CharState check to story_eligibility() in eidolon/story_validation.py
- Enhanced error handling to return clear message for dead characters
- Dead characters now properly blocked with error: "Dead characters cannot start new stories"

---

## Cognito Functions (2 total)

### 14. cognito_player_new.py

**Purpose:** Create player record after Cognito user confirmation

**Status:** ✅ WORKS CORRECTLY

**Implementation:**

- Triggered by Cognito Post Confirmation
- Extracts sub (UUID) and email from Cognito event
- Creates player record in Players table
- Handles retries gracefully (Cognito may retry)
- Returns original event for Cognito to continue

**No Issues Found**

---

### 15. cognito_player_delete.py

**Purpose:** Delete all player data for GDPR compliance

**Status:** ✅ WORKS CORRECTLY

**Implementation:**

- Supports multiple invocation methods (CloudWatch Events, API Gateway, direct)
- Extracts player_id from various event formats
- Calls delete_player_data() which deletes:
  - All characters
  - All character items
  - All active segments
  - All story history
  - All segment history
  - Player record
- Returns deletion statistics

**No Issues Found**

---

## Operations Functions (3 total)

### 16. ops_segment_poller.py

**Purpose:** Poll for segments needing attention (EventBridge triggered every minute)

**Status:** ✅ WORKS CORRECTLY

**Implementation:**

- Checks SSM parameter for polling state ("run" or "stop")
- Finds segments approaching expiry (within 60s)
  - If processed: queues for advancement
  - If mechanical + unprocessed: marks exceptional and queues
  - If decision + unprocessed: queues for default decision handling
- Finds stuck mechanical segments (>5 min, >15 min remaining)
  - Resets ProcessingStatus from "processing" to null
  - Re-queues for processing
- Manages polling state:
  - "run" + no segments → set to "stop"
  - "stop" + has segments → set to "run"
  - "stop" + no segments → disable EventBridge rule
- Batch sends messages to SQS

**No Issues Found**

---

### 17. ops_segment_process.py

**Purpose:** Process mechanical segments (SQS triggered)

**Status:** ✅ WORKS CORRECTLY

**Implementation:**

- Receives ActiveSegmentID from SQS
- Checks if already processed (idempotency)
- Claims segment atomically for processing
- Gets segment definition
- Gets character data
- Routes to appropriate processor (challenges or combat)
- Updates segment with outcome and results
- Marks ProcessingStatus="processed"

**No Issues Found**

---

### 18. ops_story_advance.py

**Purpose:** Advance story after segment completion (SQS triggered)

**Status:** ✅ WORKS CORRECTLY (but calls broken library function)

**Implementation:**

- Receives ActiveSegmentID from SQS
- Checks if already processed (idempotency)
- Atomically claims segment by marking as "completed"
- Processes decision segments if needed
- **Calls apply_death_or_unconscious_outcome() for death outcomes** ✅
- **Calls apply_combat_rewards() - empty function** ⚠️
- **Calls apply_story_rewards() on story completion - empty function** ❌
- Records segment history
- Updates story history with XP
- Determines next segment (with weighted branching)
- If story complete: clears character state, completes story
- If next segment exists: creates it and updates character
- Queues mechanical segments for processing
- Deletes processed segment from ActiveSegments
- Manages polling state when no segments remain

**Issue:** Function is correct but calls two empty library functions:

- apply_combat_rewards() (story_rewards.py:72-95) - does nothing
- apply_story_rewards() (story_rewards.py:51-66) - does nothing

**The Lambda is fine. The library functions are broken.**

---

## Critical Findings

### 1. Death Check Missing - api_story_start.py

**Location:** lambda/api_story_start.py:48
**Bug:** Calls story_eligibility() which only checks GameMode, not CharState
**Impact:** Dead characters can start new stories
**Fix:** Add CharState check to eidolon/story_validation.py:story_eligibility()

### 2. Inventory Enrichment - api_character_get.py

**Location:** lambda/api_character_get.py:66-68
**Issue:** Calls get_inventory() but players see UUIDs
**Root Cause:** Not in Lambda - either get_inventory() fails or Items table empty
**Investigation Needed:** Check if Items table populated correctly

### 3. Empty Reward Functions - ops_story_advance.py

**Location:** lambda/ops_story_advance.py:135 and :101
**Issue:** Calls apply_combat_rewards() and apply_story_rewards()
**Root Cause:** Both library functions are empty (story_rewards.py)
**Impact:** No currency or combat rewards applied
**Fix:** Implement the library functions, not the Lambda

---

## Lambda Function Quality Assessment

**Code Quality:** HIGH

- Consistent error handling patterns
- Proper separation of concerns
- Good logging
- Idempotent operations where needed
- Atomic operations for concurrency safety
- No direct database operations in handlers (use library functions)

**Architecture:** SOLID

- Business logic in eidolon library functions
- Lambda handlers only handle AWS concerns (auth, CORS, HTTP)
- Clear error propagation (ValueError → 400, RuntimeError → 500)
- Consistent response formats

**Maintainability:** HIGH

- Readable code
- Descriptive function names
- Consistent patterns across all functions
- Good error messages

---

## Recommendations

### Immediate Fixes Required

1. **Fix story_eligibility() check** (eidolon/story_validation.py)

   - Add CharState check
   - Prevent dead characters from starting stories

2. **Implement apply_story_rewards()** (eidolon/story_rewards.py)

   - Add currency persistence
   - Add item grants (if not redundant with segment drops)

3. **Implement apply_combat_rewards()** (eidolon/story_rewards.py)

   - Currently does nothing
   - Comment says "segment/story data must trigger distribution"
   - May be intentionally empty if items come from segment Results

4. **Investigate inventory enrichment** (eidolon/items.py:get_inventory())
   - Why does get_inventory() return empty InventoryDetails?
   - Are Items created with Name field?
   - Is batch_get_items() working?

### Lambda Functions Are Not The Problem

The Lambda functions are well-implemented. The bugs are in:

- Library functions (story_rewards.py, story_validation.py)
- Data structures (story reward schema)
- Database content (Items table may not have Name field)

No Lambda function code changes needed except indirectly via library function fixes.

---

**Document Status:** Complete review of all 18 Lambda functions
