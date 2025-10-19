# Project Plan 01: Incremental Mode Completion

**Status**: Active
**Created**: 2025-10-19
**Owner**: Development Team

## Executive Summary

This project plan outlines atomic, incremental tasks to bring Incremental Mode to production-ready status. Each task provides standalone value and can be completed independently. Tasks are ordered by priority, dependencies, and complexity.

**Current State**: Core gameplay functional but critical gaps prevent production deployment.

**Target State**: Production-ready Incremental Mode with complete economy loop, proper death mechanics, and polished user experience.

---

## Task List

### Task 1: Block Dead Characters from Starting Stories ⚠️ CRITICAL

**Priority**: Critical (prevents broken gameplay state)

**Problem**: Dead characters (Health <= 0) can start new stories because `story_eligibility()` only checks GameMode, not CharState

**Current State**:
- CharState enum exists with STANDING, UNCONSCIOUS, DEAD values
- Death is detected and CharState set to DEAD during combat
- `story_eligibility()` at `eidolon/story_validation.py:56` does not check for death

**Implementation**:
1. Import CharState in `eidolon/story_validation.py`
2. Add death check as first validation in `story_eligibility()`
3. Return False if `character.get("CharState") == CharState.DEAD.value`
4. Test with dead character attempting to start story

**Acceptance Criteria**:
- ✅ Dead characters cannot start new stories
- ✅ API returns appropriate error message
- ✅ No change to other eligibility checks

**Files to Modify**:
- `eidolon/story_validation.py`

**Dependencies**: None

---

### Task 2: Fix Story Reward Schema ⚠️ CRITICAL

**Priority**: Critical (blocks currency rewards)

**Problem**: Story JSON files contain reward tier DESCRIPTIONS (text) instead of reward DATA (items and currency)

**Current State**:
- All 3 story files in `data/story/` have wrong RewardTiers schema
- RewardTiers contains text strings: `"Normal": "Your expedition yields useful resources"`
- Should contain reward objects: `"Normal": {"items": ["uuid"], "currency": 30}`
- `calculate_story_rewards()` tries to call `.get("currency")` on strings, returns 0 every time
- This is why currency rewards are always zero

**Implementation**:

1. **Update story reward schema in all story files**
   - Fix `data/story/test_forage_forest.json`
   - Fix `data/story/test_goblins_ambush.json`
   - Fix `data/story/test_gremlin_mischief.json`
   - Convert from text strings to data objects

2. **Define appropriate reward amounts**
   - Death tier: 0 currency, no items
   - Failure tier: 5-10 currency, no items
   - Minimal tier: 15-25 currency, basic items
   - Normal tier: 30-50 currency, useful items
   - Exceptional tier: 75-100 currency, rare items

3. **Preserve narrative text**
   - Move reward descriptions to new field if needed
   - Or add to segment narratives
   - Ensure flavor text not lost

4. **Validate updated files**
   - Run `validate_story_content.py` on all files
   - Run `validate_branching.py` on all files
   - Ensure no validation errors

5. **Reload stories to DynamoDB**
   - Use `database/data_loader.py` to reload updated stories
   - Verify reward data stored correctly

**Acceptance Criteria**:
- ✅ All 3 story files have RewardTiers as objects, not strings
- ✅ Each tier includes currency amounts and item arrays
- ✅ Validation passes on all story files
- ✅ Stories reloaded to DynamoDB successfully
- ✅ `calculate_story_rewards()` returns non-zero currency values

**Files to Modify**:
- `data/story/test_forage_forest.json`
- `data/story/test_goblins_ambush.json`
- `data/story/test_gremlin_mischief.json`

**Dependencies**: None

---

### Task 3: Implement Currency Rewards ⚠️ CRITICAL

**Priority**: Critical (unblocks economy features)

**Problem**: Currency rewards are calculated but not applied to characters

**Current State**:
- `eidolon/story_rewards.py:12` - `calculate_story_rewards()` correctly computes currency from RewardTiers
- `eidolon/story_rewards.py:51` - `apply_story_rewards()` is stubbed (only logs, no DB update)
- `eidolon/story_completion.py:101` - Calls `apply_story_rewards()` but has no effect
- Characters have `Resources: {}` field initialized empty

**Implementation**:
1. Update `apply_story_rewards()` in `eidolon/story_rewards.py`
2. Extract currency amount from rewards dict
3. Update character's Resources.gold using DynamoDB update_item
4. Handle case where Resources field doesn't exist (initialize it)
5. Add proper error handling and logging
6. Test with story that awards currency

**Acceptance Criteria**:
- ✅ Currency rewards correctly applied to character
- ✅ Resources.gold field updated in DynamoDB
- ✅ Currency persists across sessions
- ✅ Currency displayed in API responses

**Files to Modify**:
- `eidolon/story_rewards.py`

**Dependencies**: Task 2 (reward schema must be fixed)

---

### Task 4: Complete Inventory Management with IndexedDB Integration 🔨 HIGH

**Priority**: High (critical for inventory display)

**Problem**: Inventory cannot display item names without IndexedDB integration - shows UUIDs instead

**Current State**:
- Backend: ✅ `api_item_brief.py` exists (78 lines) - Returns ItemID and PrototypeID
- Backend: ✅ `api_item_prototype.py` exists (80 lines) - Returns complete prototype data
- Backend: ✅ `eidolon/items.py` has `get_item_brief()` and `get_item_prototype_full()` functions
- Frontend: ✅ `indexeddb_service.dart` exists (403 lines) with item/prototype stores
- Frontend: ❌ No `item_repository.dart` - Missing integration layer
- Frontend: ❌ `inventory_panel.dart` doesn't use IndexedDB - Falls back to showing ItemIDs

**Implementation**:

1. **Create Item Repository**
   - Create `incremental/lib/repositories/item_repository.dart`
   - Implement two-tier loading strategy:
     - Fetch item brief via `GET /item/brief` (returns ItemID + PrototypeID)
     - Check IndexedDB cache for prototype
     - If cache miss: Fetch via `GET /item/prototype` and cache
     - If cache hit: Use cached prototype data
   - Provide `getItemDetails(String itemId)` method
   - Handle batch loading for inventory (multiple items)

2. **Integrate Inventory Panel with Item Repository**
   - Update `incremental/lib/widgets/game/inventory_panel.dart`
   - Replace `_getItemDetails()` logic to use Item Repository
   - Load item details from IndexedDB cache
   - Display item names, descriptions, stats from cached prototypes
   - Handle missing items gracefully

3. **Add Item Loading to Character Load Flow**
   - When character loads with inventory
   - Trigger item repository to fetch briefs for all inventory items
   - Cache prototypes that aren't already cached
   - Build item details map for display

4. **Test Inventory Display**
   - Create character with items
   - Verify item names display (not UUIDs)
   - Verify prototype caching works (second item of same type uses cache)
   - Test cache miss scenario (new item type)
   - Test empty inventory state

**Acceptance Criteria**:
- ✅ Item Repository created and functional
- ✅ Inventory panel displays item names, descriptions, stats
- ✅ Prototypes cached in IndexedDB (verified via browser DevTools)
- ✅ Two-tier loading strategy working (brief → cached prototype or fetch prototype)
- ✅ No UUIDs displayed in inventory
- ✅ Graceful handling of missing items

**Files to Create**:
- `incremental/lib/repositories/item_repository.dart`

**Files to Modify**:
- `incremental/lib/widgets/game/inventory_panel.dart`
- `incremental/lib/screens/game_screen.dart` (integrate item repository)

**Dependencies**: None

---

### Task 5: Implement Item Consumption 🔨 HIGH

**Priority**: High (completes "use items" part of economy loop)

**Problem**: Players cannot use consumable items (potions, scrolls, etc.)

**Current State**: No consumption endpoint or logic exists

**Implementation**:

1. **Add consumption classification to prototypes**
   - Update prototype schema with Consumable field
   - Define consumption effect types: Healing, Essence, Buff
   - Update test item prototypes

2. **Create consumption API endpoint**
   - Create `lambda/api_item_consume.py`
   - Endpoint: `POST /item/consume`
   - Body: `{"CharacterID": "...", "ItemID": "..."}`
   - Validate character owns item
   - Validate item is consumable

3. **Implement consumption effects**
   - Location: `eidolon/items.py`
   - Function: `apply_item_effects(character: dict, item: dict) -> dict`
   - Healing: Remove wounds (up to item healing amount)
   - Essence: Restore essence points
   - Remove item from inventory after use

4. **Add consumption restrictions**
   - Cannot consume during active story
   - Cannot consume if effect wasted (full health)

5. **Deploy and test**
   - Update API Gateway routes
   - Test consumption with various item types

**Acceptance Criteria**:
- ✅ Consumable items can be used via API
- ✅ Healing items restore health correctly
- ✅ Items removed from inventory after use
- ✅ Cannot consume during active story
- ✅ Proper error handling

**Files to Create**:
- `lambda/api_item_consume.py`

**Files to Modify**:
- `eidolon/items.py`
- `eidolon/character_data.py`
- `deployment/api.py`
- `documentation/incremental-api.md`

**Dependencies**: Task 4 (inventory management must work for consumption)

---

### Task 6: Implement Store System 🔨 HIGH

**Priority**: High (completes "buy items" part of economy loop)

**Problem**: Players cannot spend currency to purchase items

**Current State**: No store endpoints or logic exist

**Implementation**:

1. **Design store data structure**
   - Create store inventory in DynamoDB or S3
   - Define store item format with PrototypeID, Price, Stock
   - Decide: Global store vs per-character availability

2. **Create store listing endpoint**
   - Create `lambda/api_store_list.py`
   - Endpoint: `GET /store/items?StoreID=general-store`
   - Returns available items with prices
   - Include item details from prototypes

3. **Create purchase endpoint**
   - Create `lambda/api_store_purchase.py`
   - Endpoint: `POST /store/purchase`
   - Body: `{"CharacterID": "...", "PrototypeID": "...", "Quantity": 1}`
   - Validate sufficient currency
   - Deduct currency atomically
   - Create item and add to inventory
   - Handle concurrent purchases

4. **Add transaction logging** (optional)
   - Log all purchases for audit trail

5. **Deploy and test**
   - Test purchase with sufficient funds
   - Test insufficient funds error
   - Test concurrent purchases

**Acceptance Criteria**:
- ✅ Store items can be listed via API
- ✅ Players can purchase items with currency
- ✅ Currency correctly deducted
- ✅ Items correctly added to inventory
- ✅ Atomic transactions (no partial purchases)

**Files to Create**:
- `lambda/api_store_list.py`
- `lambda/api_store_purchase.py`
- `eidolon/store.py`

**Files to Modify**:
- `deployment/api.py`
- `documentation/incremental-api.md`

**Dependencies**: Task 3 (currency system must work)

---

### Task 7: Refactor Large Lambda Functions 🔧 MEDIUM

**Priority**: Medium (code quality, maintainability)

**Problem**: Some Lambda functions exceed 300-line recommended limit

**Target Functions**:
- `lambda/api_segment_status.py` (359 lines)
- `lambda/ops_story_advance.py` (315 lines)

**Implementation**:

1. **Refactor api_segment_status.py**
   - Extract `filter_decision_options()` to `eidolon/story_decision.py`
   - Extract `_coerce_unix()` to `eidolon/time_utils.py`
   - Extract segment enrichment logic to `eidolon/segment_core.py`
   - Simplify business logic function
   - Target: 200-250 lines

2. **Refactor ops_story_advance.py**
   - Move advancement logic to `eidolon/story_advancement.py`
   - Extract SQS processing to reusable function
   - Target: 200-250 lines

3. **Test refactored functions**
   - Verify behavior unchanged
   - Run integration tests
   - Performance testing

**Acceptance Criteria**:
- ✅ All Lambda functions under 300 lines
- ✅ Business logic extracted to eidolon library
- ✅ No behavioral changes
- ✅ Tests pass

**Files to Modify**:
- `lambda/api_segment_status.py`
- `lambda/ops_story_advance.py`
- `eidolon/story_decision.py`
- `eidolon/time_utils.py`
- `eidolon/segment_core.py`
- `eidolon/story_advancement.py` (new)

**Dependencies**: None

---

### Task 8: Enhanced Monitoring 📊 LOW

**Priority**: Low (nice-to-have for production)

**Problem**: CloudWatch stack exists but no dashboards or alarms configured

**Current State**:
- CloudWatch stack deployed with log group and metrics namespace
- No dashboards defined in CDK
- No alarms configured
- No custom metrics emitted from Lambda functions

**Implementation**:

1. **Create CloudWatch dashboard**
   - Lambda invocation metrics
   - Lambda error rates
   - DynamoDB operation metrics
   - API Gateway request/error rates
   - Custom business metrics (active stories, characters created)

2. **Set up alarms**
   - Lambda error rate exceeds threshold
   - DynamoDB throttling events
   - API Gateway 5xx errors
   - Dead letter queue messages

3. **Add custom metric emission**
   - Emit story start/completion events
   - Emit segment processing metrics
   - Use CloudWatch PutMetricData API

4. **Create operations runbook**
   - Document common issues and resolutions
   - Alarm response procedures
   - Deployment rollback process
   - Disaster recovery procedures

**Acceptance Criteria**:
- ✅ CloudWatch dashboard with key metrics
- ✅ Alarms configured for critical issues
- ✅ Custom metrics emitted from Lambda functions
- ✅ Runbook documentation complete

**Files to Create**:
- `documentation/operations-runbook.md`

**Files to Modify**:
- `deployment/stacks/cloudwatch_stack.py`
- Lambda functions (add metric emission)

**Dependencies**: None (can be done in parallel)

---

## Task Dependency Graph

```
Task 1: Death Blocking (no deps) ───────────────┐
Task 2: Fix Reward Schema (no deps) ────────────┤
                                                 │
Task 3: Currency Rewards ◄── (needs Task 2) ────┼──┐
Task 4: Inventory Integration (no deps) ────────┤  │
                                                 │  │
Task 5: Item Consumption ◄─── (needs Task 4) ───┤  │
                                                 │  │
Task 6: Store System ◄─────────── (needs Task 3)┘  │
                                                    │
Task 7: Refactor Lambdas (no deps, parallel) ──────┤
                                                    │
Task 8: Monitoring (no deps, parallel) ◄───────────┘
```

---

## Success Criteria

### Critical Fixes Complete (Tasks 1, 2, 3)
- ✅ Dead characters cannot continue playing
- ✅ Story reward schema contains actual data
- ✅ Currency rewards apply correctly

### Economy Loop Complete (Tasks 5, 6)
- ✅ Players can purchase items from store
- ✅ Players can consume items for effects
- ✅ Complete economy loop functional: earn → buy → use

### Quality & Production Ready (Task 7)
- ✅ All Lambda functions under 300 lines

### System Verified (Task 4)
- ✅ Inventory display working with item names

### Nice-to-Have (Task 8)
- ✅ Monitoring dashboard operational

### Overall Success
- ✅ Incremental Mode production-ready
- ✅ All blocking issues resolved
- ✅ Complete economy loop functional
- ✅ Code quality high
- ✅ Documentation complete

---

## Risk Assessment

### High Risk Items
1. **Currency implementation may require schema changes**
   - Mitigation: Test with small currency amounts first, verify Resources field handling
2. **Store transactions must be atomic**
   - Mitigation: Use DynamoDB transactions, add comprehensive error handling
3. **Item consumption during active story could break state**
   - Mitigation: Block consumption during active story, add state validation

### Medium Risk Items
1. **Test coverage goals may slip**
   - Mitigation: Prioritize critical modules, accept lower initial coverage
2. **Frontend changes may require Flutter expertise**
   - Mitigation: Leverage existing Flutter patterns, reference existing code

### Low Risk Items
1. **Death blocking is simple boolean check**
2. **Inventory verification straightforward**

---

## Next Steps

1. Review and approve this project plan
2. Begin Task 1 (Death Blocking - critical bug fix)
3. Proceed to Task 2 (Currency Rewards - critical feature)
4. Continue sequentially through tasks


---

## References

- [Incremental Status Document](INCREMENTAL-STATUS.md)
- [Python Style Guide](python-style.md)
- [Database Schema](schema.md)
- [Incremental Design](incremental-design.md)
- [API Documentation](incremental-api.md)
