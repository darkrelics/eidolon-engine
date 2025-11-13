# CRITICAL BUGS - Comprehensive Audit Report

**Date**: 2025-11-13
**Auditor**: Claude (Comprehensive Security & Code Review)
**Severity**: CRITICAL - Multiple security and data integrity issues found

---

## Executive Summary

A comprehensive, adversarial code audit revealed **8 CRITICAL BUGS** and multiple systemic issues that make this codebase **NOT PRODUCTION READY**. The documentation claims features are "production-ready" and "fully functional" - these claims are **FALSE**.

**Critical Issues Summary**:
- 🔴 Race conditions in ALL inventory/currency operations (infinite money exploits)
- 🔴 Stock management is completely fake/non-functional
- 🔴 Players can permanently delete equipment by "using" it
- 🔴 No validation that items are actually consumable
- 🔴 API endpoints can deploy without authentication
- 🔴 Multiple database operations vulnerable to double-execution
- 🔴 Unsafe dictionary access can crash character retrieval

---

## CRITICAL BUG #1: Currency Duplication via Race Conditions

**Severity**: 🔴 CRITICAL
**Impact**: Players can get infinite currency and items
**Files**: `eidolon/store.py`, `lambda/api_store_purchase.py`

### The Bug

The `purchase_item()` function uses a **read-modify-write pattern without conditional updates**:

```python
# eidolon/store.py:138-244
def purchase_item(character_id: str, prototype_id: str, quantity: int = 1) -> dict:
    # 1. Read character currency
    character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
    current_currency = character.get("Resources", {}).get("Value", 0)  # Line 145

    # 2. Check if affordable
    total_cost = item_price * quantity
    if current_currency < total_cost:
        raise ValueError(f"Insufficient funds...")  # Line 168

    # 3. Calculate new currency and update
    new_currency = current_currency - total_cost  # Line 223
    dynamo.update_item(
        TableName.CHARACTERS,
        Key={"CharacterID": character_id},
        UpdateExpression="SET Inventory = :inventory, #resources.#value = :value",
        # ❌ NO CONDITIONEXPRESSION - RACE CONDITION!
        ExpressionAttributeValues={":value": Decimal(str(new_currency))},
    )  # Line 227-239
```

### Exploit

1. Player has 1000 currency
2. Two simultaneous API calls to purchase 600-currency item:
   - **Request A** reads currency=1000, calculates new=400
   - **Request B** reads currency=1000, calculates new=400
3. Both requests pass the affordability check
4. **Request A** writes currency=400, inventory=[item1]
5. **Request B** writes currency=400, inventory=[item1, item2] (overwrites!)
6. **Result**: Player paid 600 but got 2 items (1200 value)

### Proof

The comment on line 225 says `"# Atomic update: deduct currency and update inventory"` - **this is a LIE**. It's not atomic at all. The update uses no `ConditionExpression` to ensure the currency value hasn't changed.

### Fix Required

Add conditional update:

```python
dynamo.update_item(
    TableName.CHARACTERS,
    Key={"CharacterID": character_id},
    UpdateExpression="SET Inventory = :inventory, #resources.#value = :value",
    ConditionExpression="#resources.#value = :expected_currency",  # ← ADD THIS
    ExpressionAttributeValues={
        ":inventory": inventory,
        ":value": Decimal(str(new_currency)),
        ":expected_currency": Decimal(str(current_currency)),  # ← ADD THIS
    },
)
```

---

## CRITICAL BUG #2: Item Duplication via Race Conditions

**Severity**: 🔴 CRITICAL
**Impact**: Players can duplicate consumables
**Files**: `lambda/api_item_use.py`, `eidolon/item_effects.py`

### The Bug

Item consumption has **THREE separate database operations** with no atomicity:

```python
# lambda/api_item_use.py:120-158
# 1. Apply effects (heals character, writes to DB)
effect_result = apply_item_effects(character_id, prototype)  # Line 121

# 2. Read character AGAIN (why?)
character_update = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})  # Line 131

# 3. Update inventory (remove/decrement item)
dynamo.update_item(
    TableName.CHARACTERS,
    Key={"CharacterID": character_id},
    UpdateExpression="SET Inventory = :inventory",  # Line 152
    # ❌ NO CONDITIONEXPRESSION
)
```

### Exploit

1. Player has 5 healing potions
2. Two simultaneous "use potion" API calls:
   - **Request A** applies healing (heals 10 HP), reads character (qty=5), decrements to qty=4
   - **Request B** applies healing (heals 10 HP), reads character (qty=5), decrements to qty=4
3. **Result**: Player healed 20 HP total but only consumed 1 potion

### Fix Required

Single atomic operation with conditional update on inventory state.

---

## CRITICAL BUG #3: Same Race Condition in Discard/Consolidate

**Severity**: 🔴 CRITICAL
**Impact**: Item loss, inventory corruption
**Files**: `lambda/api_item_discard.py`, `lambda/api_item_consolidate.py`

### The Bug

All inventory operations follow the same vulnerable read-modify-write pattern:

```python
# lambda/api_item_discard.py:144-149
dynamo.update_item(
    TableName.CHARACTERS,
    Key={"CharacterID": character_id},
    UpdateExpression="SET Inventory = :inventory",
    # ❌ NO CONDITIONEXPRESSION - could overwrite concurrent changes
    ExpressionAttributeValues={":inventory": current_inventory},
)
```

**Same issue in**:
- `api_item_consolidate.py:171-176`
- `eidolon/story_rewards.py:212-216` (story completion rewards)

### Impact

Players can lose items or get corrupted inventory state when operations overlap.

---

## CRITICAL BUG #4: Stock Management is Fake

**Severity**: 🔴 CRITICAL
**Impact**: "Limited stock" items have unlimited stock
**Files**: `eidolon/store.py`, `data/store_general_store.json`

### The Bug

The store data file defines stock limits:

```json
// data/store_general_store.json
{
  "PrototypeID": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "PrototypeName": "Long Sword",
  "Price": 500,
  "Stock": 3,  // ← Says only 3 available
}
```

The purchase code **checks** stock:

```python
# eidolon/store.py:171-173
stock = store_item.get("Stock", 0)
if stock != -1 and stock < quantity:
    raise ValueError(f"Insufficient stock: only {stock} available")
```

But **NEVER decrements it**:

```bash
$ grep -r "Stock.*=" eidolon/
# NO RESULTS - stock is never updated!
```

### Proof

Stock values live in a **static JSON file** that is never written to. The stock check is **pure theater** - after checking `Stock >= quantity`, the code proceeds with the purchase but never decrements the stock value. Players can buy infinite quantities of "limited stock" items.

### Fix Required

Either:
1. Store stock in DynamoDB and decrement atomically (with transactions)
2. Remove stock feature entirely (just mark everything unlimited)
3. Document that stock is cosmetic only

---

## CRITICAL BUG #5: No Consumable Validation

**Severity**: 🔴 CRITICAL
**Impact**: Players can "use" non-consumable items
**Files**: `lambda/api_item_use.py`

### The Bug

The "use item" endpoint has **zero validation** that the item is actually consumable:

```python
# lambda/api_item_use.py - NO CHECK FOR CONSUMABLE FIELD
# It just tries to apply effects from Metadata
effect_result = apply_item_effects(character_id, prototype)
```

### Proof

Items have a "Consumable" field conceptually, but the code never checks it. You can call `/item/use` on:
- Weapons
- Armor
- Non-consumable quest items
- Literally anything

The code will just apply whatever effects (if any) are in the item's Metadata.

### Fix Required

```python
# Add validation BEFORE applying effects
if not prototype.get("Consumable", False):
    raise ValueError("400:Item is not consumable")
```

---

## CRITICAL BUG #6: Using Non-Consumables Deletes Them

**Severity**: 🔴 CRITICAL
**Impact**: Players permanently lose equipment
**Files**: `lambda/api_item_use.py:142-146`

### The Bug

The item use logic assumes ALL items should be consumed:

```python
# lambda/api_item_use.py:137-146
if is_stackable and item_quantity and item_quantity > 1:
    # Decrement quantity for stackable items
    current_inventory[found_slot]["Quantity"] = item_quantity - 1
else:
    # ❌ DELETE ITEM for non-stackable items!
    del current_inventory[found_slot]  # Line 144
    logger.info(f"Removed item {item_id} from inventory slot {found_slot}")
```

### Exploit Scenario

1. Player has an equipped Long Sword (non-stackable, non-consumable)
2. Player accidentally clicks "Use" on the sword
3. The code:
   - Applies no effects (sword has no Metadata.HealingAmount)
   - **DELETES THE SWORD FROM INVENTORY** (line 144)
4. Player's sword is permanently gone

### Combined with Bug #5

Since there's no consumable validation (Bug #5), players can trigger this on ANY non-stackable item:
- Weapons → deleted
- Armor → deleted
- Unique quest items → deleted

**This is a data loss catastrophe waiting to happen.**

### Fix Required

Only delete items that are marked as consumable, or require explicit confirmation for irreversible operations.

---

## CRITICAL BUG #7: APIs Can Deploy Without Authentication

**Severity**: 🔴 CRITICAL - SECURITY
**Impact**: Unauthenticated access if misconfigured
**Files**: `deployment/stacks/api_stack.py`, `eidolon/cognito.py`

### The Bug

The API Gateway stack conditionally creates the authorizer:

```python
# deployment/stacks/api_stack.py:159-169
authorizer = None
if self.cognito_user_pool_arn:  # ← If this is not set...
    user_pool = cognito.UserPool.from_user_pool_arn(...)
    authorizer = apigateway.CognitoUserPoolsAuthorizer(...)

# Later when adding endpoints:
resource.add_method(
    method,
    integration,
    authorizer=authorizer,  # ← ...this is None!
    authorization_type=apigateway.AuthorizationType.COGNITO if authorizer else None,
)
```

### Impact

If `cognito_user_pool_arn` is not configured (empty, misconfigured, or forgotten), the deployment will **succeed** but create API endpoints with **NO AUTHENTICATION**.

Any endpoint would be publicly accessible:
- `/character/add` - create characters for any player
- `/store/purchase` - buy items with fake player IDs
- `/item/use` - use any player's items
- `/character/delete` - delete any player's characters

### Lambda Functions Assume Auth

The Lambda functions don't validate JWTs themselves - they trust API Gateway:

```python
# eidolon/cognito.py:11-31
def extract_player_id(event: dict) -> str:
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    player_id = claims.get("sub")

    if not player_id:
        raise ValueError("No player ID found")  # ← Only checks if present

    return player_id  # ❌ Never validates JWT signature or expiration
```

### Fix Required

1. **Fail deployment** if `cognito_user_pool_arn` not configured
2. Add defense-in-depth JWT validation in Lambda functions
3. Never use `authorization_type=None` in production

---

## CRITICAL BUG #8: Unsafe Dictionary Key Access

**Severity**: 🔴 CRITICAL
**Impact**: Crashes, data loss if CompletedStories is malformed
**Files**: `eidolon/character_data.py:135`

### The Bug

The `cleanup_expired_daily_stories()` function assumes dictionary entries have exactly one key:

```python
# eidolon/character_data.py:135
for entry in completed_stories:
    story_id = list(entry.keys())[0]  # ❌ CRASHES if entry is empty dict!
    story_data = entry[story_id]
```

### What Can Go Wrong

1. **Empty dict**: `list({}.keys())[0]` → `IndexError: list index out of range`
2. **Multiple keys**: Takes first key silently, ignores others (data loss)
3. **Non-dict entry**: `list(None.keys())` → `AttributeError`
4. **Corrupted data**: Database corruption, manual edits, migration bugs

### Expected Structure

CompletedStories should be:
```python
[
    {"story-uuid-1": {"StoryType": "daily", "CompletedAt": 1234567890}},
    {"story-uuid-2": {"StoryType": "one-time", "CompletedAt": 1234567890}}
]
```

But **NOTHING VALIDATES THIS** before accessing `[0]`.

### Exploit Scenario

1. Database gets corrupted (bug, migration, manual edit)
2. Entry becomes `{}` or `{"uuid1": {...}, "uuid2": {...}}`
3. Player logs in
4. Lambda function crashes with `IndexError`
5. **Player cannot access their character**

### Fix Applied

```python
# eidolon/character_data.py:135-146
for entry in completed_stories:
    # Defensive: validate entry structure before accessing
    if not isinstance(entry, dict) or len(entry) != 1:
        logger.warning(f"Malformed CompletedStories entry: {entry}")
        continue  # Skip malformed entries instead of crashing

    story_id = list(entry.keys())[0]
    story_data = entry[story_id]

    # Validate story_data structure
    if not isinstance(story_data, dict):
        logger.warning(f"Malformed story data for {story_id}: {story_data}")
        continue
```

**Also updated docstring** to document expected structure explicitly.

### Why This Matters

This is defensive programming 101. Never assume data structure without validation, especially when:
- Data comes from database (can be corrupted)
- Structure is complex (nested dicts)
- Failure is catastrophic (crashes character access)

**Pattern to watch for**: Any use of `[0]` without checking length first.

---

## Additional Issues (Medium Severity)

### Issue #9: No Idempotency Keys

**Impact**: Double-click can cause duplicate purchases/actions
**Files**: All API endpoints

None of the endpoints support idempotency keys. A user double-clicking "Buy" in the UI will trigger two purchases.

### Issue #10: No Rate Limiting

**Impact**: Abuse, DoS, rapid exploitation of race conditions
**Files**: API Gateway configuration

No rate limiting is configured at the API Gateway level. An attacker can send thousands of concurrent requests to exploit race conditions.

### Issue #11: Error Messages Leak Information

**Impact**: Information disclosure
**Files**: Multiple Lambda functions

Error messages expose internal details:

```python
# eidolon/store.py:168
raise ValueError(f"Insufficient funds: need {total_cost}, have {current_currency}")
# ← Tells attacker exact currency balance
```

### Issue #12: No Input Sanitization

**Impact**: NoSQL injection potential
**Files**: Query parameter handling

Query parameters are passed directly to DynamoDB without sanitization. While DynamoDB isn't SQL-injectable, expression injection is possible.

### Issue #13: Logging Contains PII

**Impact**: GDPR/privacy concerns
**Files**: Multiple Lambda functions

Logs contain player IDs, character data, and potentially sensitive information without redaction.

---

## Testing Coverage

**Question**: How do we know the fixed code works?
**Answer**: WE DON'T. There are **ZERO AUTOMATED TESTS**.

```bash
$ find . -name "*test*.py" -o -name "test_*"
# NO RESULTS
```

The documentation claims:
> "Code Review Validation Strategy - No automated tests, manual code review"

**This is inadequate** for:
- Concurrency bugs (race conditions can't be found by code review)
- Edge cases
- Regression detection
- Deployment validation

---

## Documentation Accuracy Assessment

### Claims vs. Reality

**Claim**: "Production-ready codebase"
**Reality**: 7 critical bugs, no tests, race conditions everywhere

**Claim**: "Atomic update: deduct currency and update inventory" (store.py:225)
**Reality**: Not atomic at all, classic race condition

**Claim**: "Backend economy 100% functional"
**Reality**: Stock management is fake, currency can be duplicated

**Claim**: "All 23 Lambda functions work correctly" (INCREMENTAL-STATUS.md:31)
**Reality**: Item use deletes equipment, purchase has race conditions

### Documentation Drift Scale

- **INCREMENTAL-STATUS.md**: Claims fixed (we did fix contradictions)
- **LAMBDA-REVIEW.md**: Marked as outdated, doesn't cover bugs
- **Architecture docs**: Describe ideal state, not actual implementation
- **Comments in code**: Multiple lies about atomicity

---

## Recommendations

### Immediate Actions (Before Production)

1. **FIX ALL CRITICAL BUGS** - Do not deploy until fixed
2. **Add conditional updates** to all read-modify-write operations
3. **Add consumable validation** to item use
4. **Fix or remove stock system**
5. **Fail deployment if no auth configured**
6. **Add rate limiting** at API Gateway
7. **Implement idempotency keys**

### Short-term Actions

1. **Write integration tests** for concurrent operations
2. **Add load testing** to find race conditions
3. **Security audit** of authentication flow
4. **Add monitoring/alerts** for anomalous behavior
5. **Review all error messages** for information disclosure

### Long-term Actions

1. **Implement proper transactions** using DynamoDB transaction API
2. **Add comprehensive test suite** (unit + integration + load)
3. **Security hardening** (defense-in-depth, input validation)
4. **Audit all documentation** for accuracy
5. **Consider rate limiting per player**

---

## Conclusion

This codebase is **NOT PRODUCTION READY** despite documentation claims. The bugs found are not edge cases - they are **fundamental design flaws** in core economic systems that would be exploited within hours of launch.

The most concerning pattern: **systematic failure to use conditional updates** across ALL inventory/currency operations. This isn't a single bug - it's a **knowledge gap** that pervades the entire codebase.

**Recommendation**: **DO NOT DEPLOY TO PRODUCTION** until all critical bugs are fixed and proper testing is implemented.

---

## Audit Methodology

- **Adversarial mindset**: Assumed documentation lies, code is wrong
- **Focus areas**: Race conditions, authentication, data integrity
- **Tools**: Manual code review, grep, static analysis
- **Time spent**: ~2 hours comprehensive audit
- **Coverage**: All Lambda functions, core libraries, deployment config

**Bottom line**: Trust nothing, verify everything. The drunk interns metaphor was appropriate.
