# Eidolon Engine Incremental Game Implementation Guide

This guide documents the actual implementation of the Incremental Game system as deployed in production. For architecture diagrams and design concepts, see incremental-design.md. For current bugs and missing features, see INCREMENTAL-STATUS.md.

**Deployment Status:** All infrastructure deployed and operational. Core gameplay functional with known bugs in economy system and death mechanics.

## Table of Contents

1. [Infrastructure Overview](#1-infrastructure-overview)
2. [Database Implementation](#2-database-implementation)
3. [Lambda Functions](#3-lambda-functions)
4. [Game Mechanics](#4-game-mechanics)
5. [Processing Flows](#5-processing-flows)
6. [Flutter Client](#6-flutter-client)
7. [Known Issues](#7-known-issues)

## 1. Infrastructure Overview

### 1.1 Deployment Components

**AWS Infrastructure:**

- 10 CDK Stacks: CodeBuild, DynamoDB, Lambda, Player, Character, Story, S3, CloudWatch, API, Client
- 17 Lambda Functions deployed (18 total, cognito-player-delete not deployed)
- 14 DynamoDB Tables with RemovalPolicy.RETAIN
- 2 SQS Queues (processing, advancement)
- 1 EventBridge Rule (1-minute polling, disabled by default)
- 1 SSM Parameter (polling state)

**Lambda Distribution:**

- Character Stack: 7 functions (character APIs, item APIs, archetype)
- Story Stack: 9 functions (story APIs, segment APIs, operations)
- Player Stack: 1 function (cognito-player-new)

### 1.2 Service Architecture

**Client → API Gateway → Lambda → DynamoDB**

All API calls authenticated via Cognito JWT tokens. Lambda functions use shared execution role with managed policies.

## 2. Database Implementation

### 2.1 DynamoDB Tables

**14 Tables:**

**Core Tables:**

- players: User accounts with CharacterList
- characters: Character data with GameMode field
- archetypes: Character class templates
- items: Item instances
- prototypes: Item templates
- rooms: MUD world rooms
- exits: MUD world connections
- motd: Message of the day

**Story Tables (Incremental/Hybrid modes):**

- story: Immutable story definitions
- segments: Immutable segment templates
- active_segments: Runtime segment instances
- story_history: Completed story records
- segment_history: Completed segment records
- opponents: Combat opponent definitions

### 2.2 ActiveSegments Table Structure

**Purpose:** Tracks runtime segment instances with pre-calculated outcomes.

**Key Fields:**

- ActiveSegmentID (PK): UUIDv7 for time-based ordering
- CharacterID (GSI): Query segments by character
- ProcessingStatus: pending/processing/processed state machine
- StartTime: Unix timestamp when segment started
- EndTime (GSI): Unix timestamp when segment expires
- Outcome: Calculated outcome (death/failure/minimal/normal/exceptional)
- ClientEvents: Array of display events
- CharacterUpdates: XP, wounds, items to apply
- ChallengeResults: Combat/challenge results

**Indexes:**

- CharacterID-index: Query by character
- EndTimeIndex: Find expired segments for polling

### 2.3 Characters Table Structure

**Key Fields:**

- CharacterID (PK): UUIDv4
- PlayerID: Owner reference
- CharacterName (GSI): Unique name enforcement
- GameMode: None/Incremental/MUD (exclusive access)
- ActiveStoryID: Current story UUID
- ActiveSegmentID: Current segment UUID
- Attributes: Map of attribute scores
- Skills: Map of skill scores
- Resources: Map of resources (currently always empty - bug)
- Inventory: Map of slot → ItemID
- Wounds: List of wound objects
- MaxHealth: Integer
- CharState: standing/unconscious/dead (not returned in API - gap)

**Calculated Fields:**

- Health: MaxHealth - len(Wounds) (calculated on read)

### 2.4 Items Table Structure

**Key Fields:**

- ItemID (PK): UUIDv4
- PrototypeID: Reference to Prototypes table
- Quantity: Stack quantity (for stackable items only)
- Stackable: Boolean
- Equipped: Boolean
- Mass, Value: Numeric properties
- Container, Contents: Container support

**Note:** Item instances store only ItemID and PrototypeID (plus Quantity for stackables). Name, Description, and other attributes come from the Prototype table and are cached in IndexedDB on the client.

## 3. Lambda Functions

### 3.1 Function Inventory

**API Functions (13 total):**

**Character Stack (7 functions):**

- api-archetype-list: GET /archetype
- api-character-add: POST /character
- api-character-delete: DELETE /character
- api-character-get: GET /character
- api-character-list: GET /character/list
- api-item-brief: GET /item/brief
- api-item-prototype: GET /item/prototype
- api-item-consume: POST /item/consume

**Story Stack (6 functions):**

- api-story-start: POST /story/start
- api-story-abandon: POST /story/abandon
- api-story-history: GET /story/history
- api-segment-decision: POST /segment/decision
- api-segment-history: GET /segment/history
- api-segment-status: GET /segment/status

**Operational Functions (3 total):**

**Story Stack (3 functions):**

- ops-segment-poller: EventBridge triggered (1 minute)
- ops-segment-process: SQS triggered (mechanical segments)
- ops-story-advance: SQS triggered (segment advancement)

**Cognito Functions (1 total):**

**Player Stack (1 function):**

- cognito-player-new: PostConfirmation trigger

**Not Deployed (1 total):**

- cognito-player-delete: Code exists, not deployed (awaiting API implementation)

### 3.2 Lambda Handler Pattern

All Lambda functions follow this pattern:

```python
from eidolon.cors import cors_handler
from eidolon.responses import lambda_response, lambda_error
from eidolon.cognito import extract_player_id
from eidolon.logger import log_lambda_statistics

def lambda_handler(event: dict, context: object) -> dict:
    # Log invocation
    log_lambda_statistics(event, context)

    # Handle CORS preflight
    preflight_response = cors_handler.handle_preflight(event)
    if preflight_response:
        return preflight_response

    # Extract player ID from JWT
    try:
        player_id = extract_player_id(event)
    except ValueError as err:
        return lambda_response(401, {"Error": "Unauthorized"}, event)

    # Parse request
    # Validate parameters
    # Call business logic from eidolon library
    # Return response with CORS headers

    return lambda_response(200, response_data, event)
```

**Key Points:**

- All AWS concerns in Lambda handler
- All business logic in eidolon library
- CORS handled by cors_handler utility
- Errors never raised - always returned as HTTP responses

### 3.3 Environment Variables

**Common Variables (all functions):**

```python
APPLICATION_NAME: "eidolon-engine"
LOG_LEVEL: "INFO"
ALLOWED_ORIGINS: "https://portal.{domain}"
CORS_ALLOW_CREDENTIALS: "true"
CORS_ALLOW_HEADERS: "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token"
CORS_ALLOW_METHODS: "GET,POST,PUT,DELETE,OPTIONS"
CORS_MAX_AGE: "86400"
```

**Table Names:**

```python
players_table: "players"
characters_table: "characters"
archetypes_table: "archetypes"
items_table: "items"
prototypes_table: "prototypes"
story_table: "story"
segments_table: "segments"
active_segments_table: "active_segments"
story_history_table: "story_history"
segment_history_table: "segment_history"
opponents_table: "opponents"
```

**Story Stack Variables:**

```python
SEGMENT_QUEUE_URL: SQS processing queue URL
STORY_ADVANCEMENT_QUEUE_URL: SQS advancement queue URL
SSM_POLLER_STATE_PARAMETER: "/eidolon/story/config"
SEGMENT_BATCH_SIZE: "10"
```

## 4. Game Mechanics

### 4.1 XP System

**Implementation:** eidolon/mechanics.py

**Formula:**

```python
# Base XP with variance modifier
base_xp = BASE_XP * variance_modifier
variance_modifier = (min(S, D) / max(S, D)) ** 2

# Apply failure penalty
if not success and effective_score >= difficulty:
    base_xp = 0.0  # No XP for failing easy checks
elif not success:
    base_xp *= FAILURE_XP_PENALTY  # 50% XP for failing hard checks

# Calculate increment
xp_required = 10.0 * (3.5 ** current_skill)
increment = base_xp / xp_required
```

**Constants:**

- BASE_XP = 0.25
- FAILURE_XP_PENALTY = 0.5
- ATTRIBUTE_XP_RATIO = 0.1 (attributes get 10% of skill XP)
- MAX_SKILL_LEVEL = 10.0

**Application:**

- SkillXP and AttributeXP accumulated during segment processing
- Applied immediately via apply_character_updates()
- Uses atomic ADD operations in DynamoDB
- Persists across game modes

### 4.2 Wound System

**Implementation:** eidolon/mechanics.py, eidolon/constants.py

**Health Calculation:**

```python
Health = MaxHealth - len(Wounds)
```

**Wound Structure:**

```python
{
    "DamageType": "bashing" | "lethal" | "aggravated",
    "HealAt": "2025-01-15T20:00:00Z"  # ISO 8601 timestamp
}
```

**Heal Times:**

- Bashing: 15 minutes (BASHING_HEAL_TIME)
- Lethal: 6 hours (LETHAL_HEAL_TIME)
- Aggravated: 7 days (AGGRAVATED_HEAL_TIME)

**Character States:**

- Standing: Health > 0
- Unconscious: Health = 0 with at least one bashing wound
- Dead: Health = 0 with only lethal/aggravated wounds

**Unconscious Rules:**

- New bashing damage converts to lethal
- Implemented in segment_combat.py:231-241

**Design Specification:** See health.md for complete health system design. Incremental partially implements this (missing Ghost state, death enforcement broken).

### 4.3 Currency System

**Implementation:** eidolon/items.py, eidolon/story_rewards.py

**Fundamental Units (FU):**

- Hidden base currency unit
- All values internally tracked in FU
- Enables economic flexibility without player confusion

**Coin Types:**

```python
# Coin values and exchange rates
Bronze Coin: 10 FU (PrototypeID: 3d8a6f2e-1c4b-4e9f-a5d2-7b3e9f0c1d8a)
Silver Coin: 120 FU (PrototypeID: 8f5b3c9e-2d7a-4f8e-b6c1-9a4e7d2b5f3c)
Gold Coin: 2400 FU (PrototypeID: 6e9f1d4a-3c8b-4a7f-d2e5-8b3f6c9a1e7d)

# Exchange rates
1 Silver = 12 Bronze
1 Gold = 20 Silver = 240 Bronze
```

**Stack Management:**

- Coins are stackable items with Quantity field
- Stack merging uses UUIDv7 oldest-wins logic
- Automatic consolidation when receiving rewards
- Implemented in items.py:merge_stacks(), find_matching_stack()

**Currency Application:**

- Story rewards converted to coins via create_coins_from_value()
- Coins added to inventory with proper stacking
- Resources.Value tracks total currency in FU
- Characters start with 1 gold coin (2400 FU)

**Design Specification:** See currency.md for complete currency system design.

### 4.4 Combat System

**Implementation:** eidolon/segment_combat.py

**Dual Action System:**

- Each combatant performs offensive + defensive per round
- Character uses best offensive skill (Arcane/Brawling/Melee/Archery)
- Defense determined by offensive choice (Parry for Melee, Dodge otherwise)

**Damage Application:**

- Opposed check success = damage to opponent
- Sigma > 3.0 = critical hit (2 wounds)
- Normal hit = 1 wound
- Wound type from weapon

**Victory Conditions:**

- Opponent Defeated: Lethal wounds >= Health OR Total wounds >= Health \* 2
- Character Defeated: Lethal wounds >= 5 OR Total wounds >= 10
- Timeout: Max rounds reached (failure outcome)

**Outcome Quality:**

- Exceptional: Victory with 0 wounds
- Normal: Victory with 1-2 wounds
- Minimal: Victory with 3+ wounds
- Failure: Opponent escapes or character incapacitated
- Death: Character reaches lethal threshold

### 4.4 Segment Outcomes

**Five Outcome Levels:**

1. Death: Character dies or catastrophic failure
2. Failure: Unsuccessful with consequences
3. Minimal: Barely successful
4. Normal: Standard success
5. Exceptional: Outstanding success

**For Challenges:** Based on average sigma across all attempts
**For Combat:** Based on wounds taken during victory
**For Combined:** Worse outcome takes precedence

## 5. Processing Flows

### 5.1 Story Start Flow

**Lambda:** api-story-start

**File:** lambda/api_story_start.py

**Process:**

1. Get character and validate ownership (character_get)
2. Check story_eligibility() - validates GameMode="None" AND CharState != "dead"
3. Validate story in AvailableStories
4. Get story definition and first segment
5. Create StoryHistory entry (UUIDv7 StoryInstanceID)
6. Create ActiveSegment record (UUIDv7 ActiveSegmentID)
7. Update character: GameMode="Incremental", ActiveStoryID, ActiveSegmentID
8. If mechanical segment: enqueue to processing queue
9. Enable polling system (SSM parameter + EventBridge rule)
10. Return segment details to client

**Eidolon Functions Used:**

- character_get (character_data.py)
- story_eligibility (story_validation.py) [FIXED]
- get_story_and_first_segment (story_retrieval.py)
- create_story_history_entry (story_history.py)
- create_active_segment (story_segment.py)
- story_update_character (story_active.py)
- queue_segment_for_processing (sqs.py)
- ensure_polling_enabled (polling.py)

### 5.2 Mechanical Segment Processing

**Lambda:** ops-segment-process

**File:** lambda/ops_segment_process.py

**Process:**

1. Receive ActiveSegmentID from SQS
2. Get ActiveSegment record
3. Check if already processed (idempotency)
4. Claim segment atomically (ProcessingStatus: pending → processing)
5. Get segment definition
6. Get character data
7. Route to processor:
   - process_challenges() for skill challenges
   - process_combat_segment() for combat
8. Calculate outcome from results
9. Generate ClientEvents array
10. Build CharacterUpdates dict
11. Update ActiveSegment: ProcessingStatus="processed", store all results
12. Done (segment waits for EndTime)

**Eidolon Functions Used:**

- get_active_segment (segment_core.py)
- claim_segment_for_processing (segment_polling.py)
- get_segment_definition (segment_core.py)
- get_character (character_data.py)
- route_segment_processing (segment_processing.py)
- update_active_segment_outcome (segment_state.py)

**Key Files:**

- segment_processing.py - Orchestration
- segment_challenges.py - Challenge resolution
- segment_combat.py - Combat resolution
- mechanics.py - XP calculations and opposed checks

### 5.3 Story Advancement Flow

**Lambda:** ops-story-advance

**File:** lambda/ops_story_advance.py

**Process:**

1. Receive ActiveSegmentID from SQS (sent by ops-segment-poller when EndTime reached)
2. Get ActiveSegment record
3. Check if already completed (idempotency)
4. Atomically claim by marking as "completed"
5. If decision segment: process decision (apply DefaultDecision if not submitted)
6. Get character data
7. Apply death outcome if needed (apply_death_or_unconscious_outcome)
8. Call apply_combat_rewards() - EMPTY FUNCTION (bug)
9. Record segment history
10. Add to story history SegmentHistory array
11. Update story history with XP totals
12. Determine next segment (weighted branching with prerequisites)
13. If story continues:
    - Create next ActiveSegment
    - Update character ActiveSegmentID
    - Queue mechanical segments
14. If story ends:
    - Clear character: GameMode="None", remove ActiveStoryID/ActiveSegmentID
    - Calculate story rewards
    - Call apply_story_rewards() - EMPTY FUNCTION (bug)
    - Update StoryHistory with FinalOutcome
15. Delete processed ActiveSegment
16. Check if any active segments remain, update polling state

**Known Issues:**

- apply_combat_rewards() is empty (story_rewards.py:72-95)
- apply_story_rewards() is empty (story_rewards.py:51-66)
- Story rewards never applied (currency stays at 0)

**Eidolon Functions Used:**

- get_active_segment (segment_core.py)
- mark_segment_as_completed (segment_state.py)
- process_decision_segment (segment_processing.py)
- get_character (character_data.py)
- apply_death_or_unconscious_outcome (mechanics.py)
- apply_combat_rewards (story_rewards.py) - EMPTY
- record_segment_history (segment_history.py)
- add_segment_to_history (story_history.py)
- update_story_history_xp (story_history.py)
- determine_next_segment (segment_processing.py)
- create_next_active_segment (segment_state.py)
- complete_story (story_completion.py) - calls apply_story_rewards (EMPTY)
- delete_active_segment (segment_polling.py)

### 5.4 Polling System

**Lambda:** ops-segment-poller

**File:** lambda/ops_segment_poller.py

**Trigger:** EventBridge rule every 1 minute

**Process:**

1. Check SSM parameter state (run/stop)
2. Find segments approaching expiry (EndTime <= now + 60 seconds):
   - If ProcessingStatus="processed": enqueue to advancement queue
   - If mechanical + unprocessed: mark "exceptional" outcome, enqueue to advancement
   - If decision + unprocessed: enqueue to advancement (will apply DefaultDecision)
3. Find stuck mechanical segments (>5 min old, >15 min remaining):
   - Reset ProcessingStatus to pending
   - Re-enqueue to processing queue
4. Manage polling state:
   - If state="run" and no segments: set state="stop"
   - If state="stop" and has segments: set state="run"
   - If state="stop" and no segments: disable EventBridge rule

**Timeout Protection:**

- Mechanical segments past EndTime marked "exceptional" (best outcome)
- Player-protective: system failures never punish players

**Eidolon Functions Used:**

- get_polling_state (polling.py)
- get_segments_approaching_expiry (segment_polling.py)
- get_stuck_mechanical_segments (segment_polling.py)
- mark_segment_as_completed_exceptional (segment_state.py)
- reset_segment_processing_status (segment_state.py)
- send_message_batch (sqs.py)
- update_polling_state (polling.py)
- manage_eventbridge_rule (polling.py)
- check_active_segments_exist (segment_polling.py)

## 6. Flutter Client

### 6.1 Architecture

**File Structure:**

```
incremental/lib/
├── constants/        # Navigation routes (1 file)
├── main.dart        # App entry point
├── models/          # Data models (6 files)
├── providers/       # State management (6 files)
├── repositories/    # Data access with caching (1 file)
├── screens/         # Full screens (8 files)
├── services/        # API and utilities (9 files)
├── utils/           # Helpers (10 files)
└── widgets/         # UI components (26 files)
```

**Total:** 67 Dart files

**Note:** repositories/ directory should be moved to services/ or utils/ per project standards.

### 6.2 State Management

**Provider Pattern:**

**AuthProvider:** Authentication state and sign in/out flows
**CharacterProvider:** Character state with SharedPreferences persistence
**SegmentProvider:** Polling disabled (line 67 comment), data access only
**ThemeProvider:** Theme persistence and dark/light mode
**TimerProvider:** Global timer coordination

### 6.3 API Service

**File:** incremental/lib/services/api_service.dart

**Extends:** BaseApiService (handles HTTP, auth, retries)

**Key Methods (13 total):**

- getCharacterById(characterId)
- listCharacters()
- addCharacter(name, archetype)
- deleteCharacter(characterId)
- getArchetypes()
- startStory(characterId, storyId)
- abandonStory(characterId)
- submitDecision(characterId, decision)
- getSegmentStatus(characterId)
- getSegmentHistory(characterId)
- getStoryHistory(characterId, storyInstanceIds) - added in Release 4
- getItemBrief(itemId) - added in Release 4
- getItemPrototype(prototypeId) - added in Release 4

**BaseApiService provides:**

- JWT token injection
- Error handling with status code interpretation
- Retry logic with exponential backoff
- CORS header handling

### 6.4 Character Repository

**File:** incremental/lib/repositories/character_repository.dart

**Purpose:** Cache-first data access with IndexedDB

**Key Methods:**

**loadPlayerCharacters():**

- Fetches all characters from server
- Caches each in IndexedDB
- Returns list for character selection

**getCharacter(characterId):**

- Tries IndexedDB first
- Falls back to server on cache miss
- Caches result

**refreshCharacterFromServer(characterId):**

- Forces server fetch
- Updates cache
- Used after story completion

**updateCharacterFromSegment(characterId, segmentUpdates):**

- Gets cached character
- Applies CharacterUpdates incrementally (lines 176-260)
- Updates Skills, Attributes, Resources, Wounds, Inventory
- Caches updated character
- Falls back to server fetch on error

**\_applyUpdates() Method:**

```dart
Character _applyUpdates(Character character, Map<String, dynamic> updates) {
  // Apply skill XP (additive)
  final skillUpdates = updates['Skills'] as Map<String, dynamic>?;
  final updatedSkills = Map<String, double>.from(character.skills);
  if (skillUpdates != null) {
    skillUpdates.forEach((key, value) {
      updatedSkills[key] = (updatedSkills[key] ?? 0.0) + value.toDouble();
    });
  }

  // Apply attribute XP (additive)
  // Apply resources (additive)
  // Apply wounds, inventory, progress
  // Return new Character instance
}
```

### 6.5 Polling Implementation

**File:** incremental/lib/services/story_polling_service.dart

**Design Specification:**

- First poll at T+60 seconds after StartTime (backend INITIAL_POLL_DELAY constant)
- Use server PollAfter field for subsequent timing
- Apply incremental character updates from CharacterUpdates

**Actual Implementation:**

**BUG:** Polls immediately at T+0, not T+60

- Line 72: "Check immediately to get current status and PollAfter guidance from server"
- Violates INITIAL_POLL_DELAY specification

**Correct Behaviors:**

- Uses server PollAfter field for subsequent polls
- Applies incremental updates via CharacterRepository
- Single polling source (only GameScreen calls startPolling)
- Deduplication via \_lastReloadedSegmentId tracking
- Error handling with consecutive error counter (max 3)
- Stops on 404 or null ActiveSegmentID

**Process:**

1. GET /segment/status immediately (BUG: should wait 60 seconds from StartTime)
2. Reset consecutive error counter on success
3. Update UI via onStatusUpdate callback
4. Check if story complete (ActiveSegmentID == null)
5. Handle by ProcessingStatus:
   - "pending": Use server PollAfter field for next check delay
   - "processed" with TimeRemaining > 0: Wait for timer, then apply updates
   - "processed" with TimeRemaining = 0: Apply updates immediately
6. Apply updates via onSegmentComplete callback
7. onSegmentComplete calls CharacterRepository.updateCharacterFromSegment()
8. Schedule next poll with \_scheduleNextPoll()
9. On error: increment error counter, retry after 30 seconds
10. After 3 consecutive errors: stop polling

### 6.6 GameScreen Integration

**File:** incremental/lib/screens/game_screen.dart (1,784 lines)

**Complexity:** High - manages entire game UI and state

**Key Features:**

**Single Polling Source:**

- Line 563: \_runtime.startPolling() - only polling location
- SegmentProvider polling disabled to avoid dual-polling bug

**Story Lifecycle State Machine:**

- none: No active story
- running: Story in progress
- completed: Story confirmed complete

**Segment History Tracking:**

- Tracks all segments in \_segmentHistory array
- Deduplicates by \_segmentIdentity()
- Assigns \_index for chronological ordering
- Filters completed vs active segments

**Character Update Timer:**

- Runs every 2 minutes when NOT in active story
- Auto-refreshes character state
- Stops after 60 ticks or when story starts

**Decision Submission:**

- Multi-layer duplicate prevention
- Atomic flag + debouncer (300ms) + rate limiter (15s)
- Backend conditional update (ultimate protection)

**Responsive Layout:**

- Desktop: 3-column (Character | Story | Inventory)
- Tablet: Collapsible side panels
- Mobile: Bottom navigation between panels

### 6.7 IndexedDB Caching

**File:** incremental/lib/services/indexeddb_service.dart

**Database:** EidolonDB version 1

**Object Stores (5 total):**

1. **stories** - Completed story history
   - Key: [characterId, storyInstanceId]
   - Indexes: by-character, by-completion-date, by-outcome, by-story-type

2. **story_segments** - Completed segment history
   - Key: [characterId, storyInstanceId, activeSegmentId]
   - Indexes: by-story-instance, by-segment-type, by-outcome

3. **characters** - Character data cache
   - Key: characterId
   - Indexes: by-player, by-last-updated

4. **items** - Item instances
   - Key: itemId
   - Index: by-character
   - Stores: ItemID + PrototypeID only

5. **item_prototypes** - Item templates
   - Key: prototypeId
   - Index: by-last-fetched
   - Stores: Full prototype data

**Integration:**

- ✅ CharacterRepository uses characters store for caching
- ✅ ItemRepository uses items and item_prototypes stores (2025-10-21)
- ✅ Cache-first reads with server fallback
- ✅ Incremental updates from segment responses
- ✅ Fresh fetch at character selection and story completion
- ✅ Three-tier caching for prototypes: memory → IndexedDB → server

**Performance:**

- 90% reduction in character API calls
- 75% reduction in item/prototype API calls (2025-10-21)
- 94% reduction in item data transfer (200KB → 12KB)
- 95% faster inventory load times (4-10s → <500ms)

### 6.8 UI Components

**Game Panels (3 widgets):**

**CharacterPanel (character_panel.dart):**

- Displays name, archetype, health/essence bars
- Attributes section
- Skills section
- Resources section (hidden when empty - currently always empty due to bug)
- GameMode badge
- Wounds indicator
- Last updated timestamp

**StoryPanel (story_panel.dart):**

- Available stories grid (when no active story)
- Active story card with abandon button
- Segment display (mechanical progress or decision options)
- Segment history viewer
- Story completion screen

**InventoryPanel (inventory_panel.dart):**

- Equipped items section
- Bag items grid
- Item count badge
- ✅ Displays item names and quantities via ItemRepository (fixed 2025-10-21)

**Responsive Support:**

- All panels adapt to mobile/tablet/desktop
- Consistent card-based design
- Material Design 3 theming

## 7. Known Issues

### 7.1 Flutter Client Bugs

**Polling Timing:**

- File: incremental/lib/services/story_polling_service.dart:72
- Bug: Polls immediately (T+0) instead of waiting 60 seconds
- Design: INITIAL_POLL_DELAY = 60 seconds
- Fix: Calculate delay from StartTime, wait 60 seconds before first poll

**Repository Directory:**

- File: incremental/lib/repositories/character_repository.dart
- Issue: repositories/ should be under services/ or utils/
- Fix: Move file and update imports

### 7.2 Backend Library Bugs

**✅ RESOLVED: Inventory Enrichment (2025-10-21)**

- eidolon/items.py:get_item_brief() - Returns ItemID, PrototypeID, Quantity
- incremental/lib/repositories/item_repository.dart - Three-tier caching
- Solution: Client-side caching with ItemRepository instead of server-side enrichment
- Result: Players see "Bronze Coin x5" instead of UUIDs
- Performance: 75% reduction in API calls, 95% faster load times

### 7.3 Data Structure Issues

**Story Reward Schema**

- Files: data/story/\*.json
- [OK] RewardTiers now contains proper reward objects with narrative
- [OK] Format: `"Normal": {"narrative": "text", "currency": 300, "items": []}`
- [OK] Currency values implemented for all tiers
- [OK] Fixed: calculate_story_rewards() returns correct values

**Resources Field**

- Characters created with Resources: {"Value": 2400} (start with 1 gold coin)
- [OK] Resources.Value now tracks total currency in FU
- [OK] Updated by apply_story_rewards() when receiving currency
- Frontend ready to display but backend never sends data
- Impact: No currency display

**CharState Field:**

- Backend sets CharState in Characters table
- Backend doesn't return it in GET /character API response
- Frontend uses Dead flag from CharacterList as proxy
- Impact: Inconsistent death status tracking

**Missing Ghost State:**

- health.md specifies 4 states: standing/unconscious/dead/ghost
- MUD server implements all 4
- Python constants.py only has 3 (missing ghost)
- Impact: Incremental doesn't fully implement health.md specification

## 8. Performance Characteristics

### 8.1 API Call Patterns

**Character Selection:**

- GET /character/list (once)
- GET /character for each character (N calls)
- Caches all in IndexedDB

**Story Gameplay (per segment):**

- GET /segment/status (1-3 calls depending on processing time)
- No GET /character calls (uses incremental updates)

**Story Completion:**

- GET /character (once to refresh)
- GET /segment/history (optional for history display)

**Typical Session (3 stories, 18 segments each):**

- Without caching: ~60 character fetches
- With caching: ~5 character fetches (selection + 3 completions + error fallbacks)
- 90% reduction

### 8.2 Database Operations

**DynamoDB Access Patterns:**

- Pay-per-request billing (no capacity planning)
- GSI queries for efficient secondary access
- Batch operations where possible (batch_get_items for inventory)
- Conditional writes for atomic operations
- Transaction for story start (Character + ActiveSegment)

### 8.3 Lambda Performance

**Configuration:**

- Runtime: Python 3.12
- Memory: 128MB (sufficient for all functions)
- Timeout: 30 seconds
- Layer: eidolon-dependencies (shared library)

**Optimization:**

- Cold start caching of archetype data (api-archetype-list)
- Shared execution role across all functions
- Post-deployment updates from S3 artifacts

## 9. Deployment

### 9.1 Infrastructure as Code

**10 CDK Stacks:**

1. CodeBuild: Build projects and artifacts bucket
2. DynamoDB: 14 tables with managed policy
3. Lambda: Shared layer and execution role
4. Player: Cognito User Pool and cognito-player-new function
5. Character: 7 Lambda functions
6. Story: 9 Lambda functions, SQS queues, EventBridge, SSM
7. S3: Scripts bucket (MUD/Hybrid only)
8. CloudWatch: Logging (MUD/Hybrid only)
9. API: API Gateway with Lambda integrations
10. Client: CloudFront, S3, automated portal build

**Post-Deployment:**

- Phase 11: Lambda function code updates from S3
- Cognito trigger configuration for imported pools
- S3 bucket policies for CloudFront
- Portal build via CodeBuild

### 9.2 Deployment Modes

**MUD Mode (9 stacks):** Excludes Story stack
**Incremental Mode (8 stacks):** Excludes S3 and CloudWatch stacks
**Hybrid Mode (10 stacks):** All stacks

All modes deploy same 17 Lambda functions.

### 9.3 Fixed Logical IDs

All resources use fixed logical IDs to prevent recreation:

- Lambda functions: ApiCharacterGetFunction, OpsSegmentPoller, etc.
- DynamoDB tables: Stable logical IDs
- S3 buckets, Cognito pools: Fixed names

## 10. Testing

### 10.1 Integration Testing

Per project policy (unit-tests.md): Focus on integration testing, not unit tests.

**Functional Tests:**

- Character creation with starting items
- Story start and progression
- Mechanical segment challenges
- Decision segment branching
- Combat with wounds
- XP gains and skill increases
- Wound healing
- Story completion
- Character deletion

**All tests pass via manual verification and deployed infrastructure.**

### 10.2 Known Test Failures

**Cannot Test (Remaining Issues):**

- Store purchases (no endpoints)
- Item discarding (no endpoint)

**Fixed Issues (2025-10-19):**

- ✅ Dead character prevention (now properly blocks story starts)
- ✅ Currency rewards (now properly calculated and applied)

## 11. Testing Requirements

### Stack Operations Testing

Testing requirements for the stackable item system:

**Unit Tests:**

- Stack merging logic with UUIDv7 oldest-wins
- Stack splitting for trade/drop operations
- Stackable vs non-stackable validation rules
- Coin creation from currency values
- Inventory consolidation logic

**Integration Tests:**

- Story rewards creating coin stacks
- Automatic stack merging on item pickup
- Currency transactions with proper coin conversion
- Inventory updates preserving stack integrity

**Edge Cases:**

- Merging stacks at integer limits
- Stack operations with invalid quantities
- Mixed stackable/non-stackable inventory operations
- Currency conversion with odd values

### Frontend Testing (Flutter)

Required testing for client-side stack handling:

**Display Testing:**

- Stack quantity display in inventory panel (x123 format)
- Singular vs plural item names
- Coin stack formatting with proper denominations
- Currency value display in inventory header
- Coin icons distinguishable (gold/silver/bronze)
- Total currency value in character panel

**Interaction Testing:**

- Drag-drop stack merging
- Stack splitting UI (when implemented)
- Store purchases with coin stacks

**Story Rewards Testing:**

- Currency rewards convert to coin display
- Narrative text displays if present
- Zero rewards handled gracefully
- Individual coin amounts shown correctly

**Character Resources Testing:**

- Value field updates correctly
- Currency formatting works for all amounts (0, partial, large)
- Resources persist across sessions
- Backward compatibility with characters without Value field

### Performance Testing

- Stack operations with large inventories (1000+ items)
- Batch stack merging efficiency
- Database query optimization for stack lookups

## 12. References

**Implementation Files:**

- Lambda: lambda/\*.py (18 files)
- Eidolon Library: eidolon/\*.py (45 files, 9,640 lines)
- Flutter: incremental/lib/\*_/_.dart (67 files)
- Deployment: deployment/stacks/\*.py (13 files)

**Documentation:**

- INCREMENTAL-STATUS.md - Current status, bugs, missing features
- LAMBDA-REVIEW.md - Complete Lambda review (17 functions)
- FLUTTER-REVIEW.md - Complete Flutter review (67 files)
- incremental-api.md - API endpoint specifications
- incremental-design.md - Architecture and design
- health.md - Health system specification
- deployment.md - Deployment procedures
- eidolon-library.md - Library module reference

**Code Reviews:**

- All Lambda functions reviewed - 17 working, bugs in library functions
- All Flutter files reviewed - 1 bug (polling timing), otherwise production-ready
- All eidolon modules catalogued - 3 empty functions, 1 missing validation
