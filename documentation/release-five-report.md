# Release 5 Report — Economy & Inventory System

**Date:** 2025-10-07 (Planning)
**Updated:** 2025-10-19 (status review)
**Branch:** TBD (will branch from develop after R4 merge)
**Status:** 📋 PLANNING (R5-T1 complete, remaining tasks pending)
**Previous Release:** R4 (IndexedDB caching layer)

---

## Executive Summary

Release 4 establishes the **economy and inventory management system** by implementing currency persistence, full inventory operations, and a player-facing store. This release transforms items from passive story rewards into an active gameplay system with purchasing, consumption, stacking, and disposal mechanics.

**Core Principle:** Complete the economic loop - earn currency, spend it meaningfully, manage inventory actively, use consumables strategically.

**Ship Gate:** Currency persists and displays correctly, players can buy/use/discard items, inventory UI supports full CRUD operations, store offers balanced item selection, item icons enhance visual presentation.

---

## R5 Task Categories

### Foundation (Economy) — 1 Task

- R5-T1: Fix currency reward application (moved from R3) ✅ COMPLETE

### Inventory Operations — 3 Tasks

- R5-T2: Item consumption system (use items, apply effects) ❌ NOT IMPLEMENTED
- R5-T3: Inventory management (discard items, stack consolidation) ❌ NOT IMPLEMENTED
- R5-T4: Item visual assets (icons, enhanced descriptions) ❌ NOT IMPLEMENTED

### Player Economy — 1 Task

- R5-T5: Store/shop implementation (purchase items with currency) ❌ NOT IMPLEMENTED

### Content Enablement — 1 Task

- R5-T6: Author Quick-Start documentation (moved from R3) ❌ NOT IMPLEMENTED

**Total:** 6 tasks (economy foundation → inventory operations → player store → content enablement)

---

## Current State Assessment

### What Exists

**Backend Infrastructure:**
- ✅ Items table in DynamoDB with full schema
- ✅ Prototypes table for item templates
- ✅ `eidolon/items.py` - Item creation and inventory management
- ✅ `add_items_to_inventory()` - Story reward item grants
- ✅ Item fields: Stackable, MaxStack, Quantity, Value, Mass, Container, Wearable
- ✅ Currency calculation logic in `eidolon/story_rewards.py:12-48`

**Frontend Infrastructure:**
- ✅ `incremental/lib/widgets/game/inventory_panel.dart` - Basic inventory UI
- ✅ Character model includes `inventory` and `inventoryDetails` maps
- ✅ Equipment display for worn items
- ✅ Bag item grid view

### What's Broken or Missing

**Critical Gaps:**
- ❌ Currency rewards calculated but not persisted (R4-T1)
- ❌ No item consumption mechanics (potions, scrolls)
- ❌ Cannot discard/delete unwanted items
- ❌ No stack consolidation (5 individual potions instead of "x5")
- ❌ No item icons (text-only inventory)
- ❌ No store/shop to spend currency
- ❌ Item descriptions exist but not prominently displayed

---

## Task Details

### R5-T1: Fix Currency Reward Application ✅ COMPLETE

**Status:** ✅ COMPLETE
**Priority:** P0 - Must complete first (blocks R5-T5)
**Issues:** #726 (effects integration - resolved), #639 (economy framework - complete)
**Completed:** 2025-10-19 (commit f36095ac)

#### Current State

**Implementation Complete:**

- ✅ `eidolon/story_rewards.py:82-199` - `apply_story_rewards()` fully implemented (199 lines)
- ✅ Coin-based currency system: Bronze (10 FU), Silver (120 FU), Gold (2400 FU)
- ✅ `Resources.Value` field tracks total currency value
- ✅ Stack management with UUIDv7 oldest-wins merging
- ✅ Currency calculation in `calculate_story_rewards()` (lines 12-79)
- ✅ All 3 story JSON files updated with currency rewards in RewardTiers
- ✅ Frontend character model parses Resources (incremental/lib/models/character.dart:123)
- ✅ Story completion screen displays currency rewards (story_completion_screen.dart:306-308)

**How It Works:**

```python
def apply_story_rewards(character_id: str, rewards: dict) -> None:
    """Apply calculated rewards to a character."""
    # 1. Convert currency value to coin items (bronze/silver/gold)
    # 2. Check for existing coin stacks and merge if found
    # 3. Create new coin items for new stacks
    # 4. Update Resources.Value with total currency value
    # 5. Handle direct item rewards from story
    # 6. Update character inventory and resources atomically
```

**Verification:**
- ✅ Backend implementation complete and deployed
- ✅ Frontend receives and displays currency
- ✅ Coins appear in inventory as stackable items
- ✅ Resources.Value tracks total wealth

#### Implementation Requirements

**1. Verify Character Schema**

Check if `Currency` field exists in Characters table:

```python
# Check actual character records in DynamoDB
# Expected: Field may already exist or needs migration
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
            # Item application via add_items_to_inventory()
            item_ids = add_items_to_inventory(character_id, items)
            logger.info(f"Granted {len(item_ids)} items to {character_id}")

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

**3. Update Character API Response**

Ensure `GET /character` includes currency balance:

```python
# In lambda/api_character_get.py or relevant handler
response_data = {
    "CharacterID": character_id,
    "Name": character["Name"],
    "Currency": character.get("Currency", 0),  # ← Add this
    # ... other fields
}
```

**4. Update Frontend Character Model**

Add currency to `incremental/lib/models/character.dart`:

```dart
class Character {
  final String id;
  final String name;
  final int currency;  // ← Add this field
  // ... other fields

  factory Character.fromJson(Map<String, dynamic> json) {
    return Character(
      id: json['CharacterID'] as String,
      name: json['Name'] as String,
      currency: (json['Currency'] as num?)?.toInt() ?? 0,  // ← Parse currency
      // ... other fields
    );
  }
}
```

**5. Display Currency in UI**

Update character info panel to show currency balance:

```dart
// In incremental/lib/widgets/game/character_info_panel.dart or similar
Text('Currency: ${character.currency} gold')
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

def test_apply_currency_new_character():
    """Test currency application when Currency field doesn't exist."""
    character_id = create_test_character()  # No currency field
    rewards = {"currency": 25}

    apply_story_rewards(character_id, rewards)

    character = get_character(character_id)
    assert character["Currency"] == 25  # if_not_exists handles missing field
```

**Integration Test:**

- Start story → complete with currency reward → verify balance increased
- Check character API returns correct currency amount
- Verify UI displays updated balance

#### Files Modified

- ✏️ `eidolon/story_rewards.py` - Implement `apply_story_rewards()`
- ✏️ `lambda/api_character_get.py` - Include Currency in response
- ✏️ `incremental/lib/models/character.dart` - Add currency field
- ✏️ `incremental/lib/widgets/game/character_info_panel.dart` - Display currency
- ✏️ `scripts_python/validate_story_content.py` - Add currency validation

#### Acceptance Criteria

- [ ] Currency field exists in Characters table schema
- [ ] `apply_story_rewards()` persists currency to DynamoDB
- [ ] Uses atomic ADD operation with `if_not_exists` pattern
- [ ] Character GET API returns currency balance
- [ ] Frontend character model includes currency
- [ ] UI displays current currency balance
- [ ] Story content validator checks currency values
- [ ] Test story includes currency reward example

---

### R5-T2: Item Consumption System

**Status:** ❌ NOT IMPLEMENTED
**Priority:** P1 - Required for meaningful item usage
**Issues:** New - "Implement item consumption mechanics"

#### Current State

**What Exists:**

- Items have `Verbs` field for custom actions (schema supports this)
- Item prototype system allows defining item types
- Frontend can display item lists

**What's Missing:**

- No "Use Item" action in UI or backend
- No consumable item effects (healing, buffs, etc.)
- No item quantity decrement on use
- No validation that item is consumable

#### Implementation Requirements

**1. Define Consumable Item Schema**

Extend item prototypes to support consumable types:

```json
{
  "PrototypeID": "health-potion",
  "Name": "Health Potion",
  "Description": "Restores 25 health when consumed",
  "Type": "consumable",
  "Consumable": true,
  "Stackable": true,
  "MaxStack": 99,
  "Value": 15,
  "Effects": {
    "Health": 25,
    "Duration": 0
  },
  "Verbs": {
    "drink": {
      "Action": "consume",
      "Message": "You drink the health potion and feel reinvigorated."
    }
  }
}
```

**2. Create Backend Use Item Endpoint**

New Lambda function: `lambda/api_item_use.py`

```python
def lambda_handler(event, context):
    """
    Use (consume) an item from character inventory.

    POST /item/use
    Body: {
        "CharacterID": "uuid",
        "ItemID": "uuid"
    }

    Returns:
        {
            "success": true,
            "effects": {"Health": 25},
            "message": "You drink the health potion...",
            "remainingQuantity": 4
        }
    """
    # 1. Validate character owns item
    # 2. Check item is consumable
    # 3. Apply effects to character
    # 4. Decrement quantity or remove item
    # 5. Return results
```

**Implementation:**

```python
def use_consumable_item(character_id: str, item_id: str) -> dict:
    """
    Use a consumable item and apply its effects.

    Returns:
        Dict with success status, effects applied, and message
    """
    # Fetch character
    character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
    if not character:
        raise ValueError(f"Character {character_id} not found")

    # Verify item is in inventory
    inventory = character.get("Inventory", {})
    item_slot = None
    for slot, inv_item_id in inventory.items():
        if inv_item_id == item_id:
            item_slot = slot
            break

    if not item_slot:
        raise ValueError(f"Item {item_id} not in character inventory")

    # Fetch item details
    item = dynamo.get_item(TableName.ITEMS, {"ItemID": item_id})
    if not item:
        raise ValueError(f"Item {item_id} not found")

    # Verify item is consumable
    if not item.get("Consumable", False):
        raise ValueError(f"Item {item.get('Name')} is not consumable")

    # Get effects
    effects = item.get("Effects", {})
    message = item.get("Verbs", {}).get("drink", {}).get("Message", "You use the item.")

    # Apply effects to character
    update_expr_parts = []
    attr_values = {}

    if "Health" in effects:
        health_gain = effects["Health"]
        # Add health, capped at max
        update_expr_parts.append("Health = if_not_exists(Health, :zero) + :health_gain")
        attr_values[":health_gain"] = health_gain
        attr_values[":zero"] = 0

    # Decrement quantity or remove item
    quantity = item.get("Quantity", 1)
    remaining_quantity = quantity - 1

    if remaining_quantity <= 0:
        # Remove item from inventory
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression=f"REMOVE Inventory.#{item_slot} SET {', '.join(update_expr_parts)}",
            ExpressionAttributeNames={"#slot": item_slot},
            ExpressionAttributeValues=attr_values if attr_values else None,
        )
        # Delete item record
        dynamo.delete_item(TableName.ITEMS, {"ItemID": item_id})
    else:
        # Decrement quantity
        dynamo.update_item(
            TableName.ITEMS,
            Key={"ItemID": item_id},
            UpdateExpression="SET Quantity = :new_quantity",
            ExpressionAttributeValues={":new_quantity": remaining_quantity},
        )
        # Apply character effects
        if update_expr_parts:
            dynamo.update_item(
                TableName.CHARACTERS,
                Key={"CharacterID": character_id},
                UpdateExpression=f"SET {', '.join(update_expr_parts)}",
                ExpressionAttributeValues=attr_values,
            )

    return {
        "success": True,
        "effects": effects,
        "message": message,
        "remainingQuantity": remaining_quantity,
        "itemRemoved": remaining_quantity <= 0,
    }
```

**3. Add Frontend UI Action**

Update `incremental/lib/widgets/game/inventory_panel.dart`:

```dart
// Add "Use" button for consumable items
Widget _buildItemCard(InventoryItem item) {
  return Card(
    child: Column(
      children: [
        Text(item.name),
        Text('Qty: ${item.quantity}'),
        if (item.consumable)
          ElevatedButton(
            onPressed: () => _useItem(item),
            child: const Text('Use'),
          ),
      ],
    ),
  );
}

Future<void> _useItem(InventoryItem item) async {
  final result = await _apiService.useItem(
    characterId: widget.character.id,
    itemId: item.id,
  );

  if (result['success']) {
    // Show effect message
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result['message'])),
    );

    // Refresh character data
    await _characterProvider.refresh();
  }
}
```

**4. Update API Gateway**

Add new route in `deployment/api.py`:

```python
# POST /item/use
item_use_route = api.root.add_resource("item").add_resource("use")
item_use_route.add_method(
    "POST",
    lambda_integration(lambda_functions["api_item_use"]),
    authorizer=cognito_authorizer,
)
```

#### Testing Requirements

**Unit Tests:**

```python
def test_use_consumable_potion():
    """Test consuming a health potion increases health."""
    character = create_test_character(health=50, max_health=100)
    potion = create_consumable_item("health-potion", effects={"Health": 25})
    add_item_to_inventory(character.id, potion.id)

    result = use_consumable_item(character.id, potion.id)

    assert result["success"] is True
    assert result["effects"]["Health"] == 25

    updated_character = get_character(character.id)
    assert updated_character["Health"] == 75

def test_use_decrements_quantity():
    """Test using stackable item decrements quantity."""
    character = create_test_character()
    potion = create_consumable_item("health-potion", quantity=5)
    add_item_to_inventory(character.id, potion.id)

    result = use_consumable_item(character.id, potion.id)

    assert result["remainingQuantity"] == 4
    assert result["itemRemoved"] is False

    # Use 4 more times
    for _ in range(4):
        result = use_consumable_item(character.id, potion.id)

    assert result["remainingQuantity"] == 0
    assert result["itemRemoved"] is True

    # Verify item removed from inventory
    updated_character = get_character(character.id)
    assert potion.id not in updated_character["Inventory"].values()
```

#### Files Modified

- ➕ `lambda/api_item_use.py` - New Lambda function
- ✏️ `eidolon/items.py` - Add `use_consumable_item()` function
- ✏️ `deployment/api.py` - Add `/item/use` route
- ✏️ `deployment/lambda_functions.py` - Add api_item_use function
- ✏️ `incremental/lib/services/api_service.dart` - Add `useItem()` method
- ✏️ `incremental/lib/widgets/game/inventory_panel.dart` - Add Use button

#### Acceptance Criteria

- [ ] Consumable items defined in prototypes with Effects
- [ ] Backend endpoint validates item ownership and consumable status
- [ ] Using item applies effects to character stats
- [ ] Quantity decrements correctly for stackable items
- [ ] Item removed from inventory when quantity reaches 0
- [ ] Frontend displays "Use" button for consumable items
- [ ] Success message shown after consumption
- [ ] Character state refreshed after item use

---

### R5-T3: Inventory Management (Discard & Stack Consolidation)

**Status:** ❌ NOT IMPLEMENTED
**Priority:** P1 - Quality of life feature
**Issues:** New - "Add inventory discard functionality"

**Note:** Coin stacking is already implemented server-side in `apply_story_rewards()`. This task focuses on UI-driven stack consolidation and item discard functionality.

#### Current State

**What Exists:**

- Items can be added to inventory via story rewards
- Frontend displays inventory items
- Backend has `add_items_to_inventory()` function

**What's Missing:**

- No way to remove/discard unwanted items
- Multiple stacks of same item not consolidated
- No inventory organization tools

#### Implementation Requirements

**1. Create Discard Item Endpoint**

New Lambda function: `lambda/api_item_discard.py`

```python
def lambda_handler(event, context):
    """
    Remove an item from character inventory.

    DELETE /item/discard
    Body: {
        "CharacterID": "uuid",
        "ItemID": "uuid"
    }

    Returns:
        {
            "success": true,
            "message": "Item discarded",
            "itemName": "Rusty Sword"
        }
    """
```

**Implementation:**

```python
def discard_item(character_id: str, item_id: str) -> dict:
    """
    Remove an item from character inventory and delete it.

    Args:
        character_id: Character UUID
        item_id: Item UUID to discard

    Returns:
        Dict with success status and item name
    """
    # Fetch character
    character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
    if not character:
        raise ValueError(f"Character {character_id} not found")

    # Find item in inventory
    inventory = character.get("Inventory", {})
    item_slot = None
    for slot, inv_item_id in inventory.items():
        if inv_item_id == item_id:
            item_slot = slot
            break

    if not item_slot:
        raise ValueError(f"Item {item_id} not in character inventory")

    # Get item details for response
    item = dynamo.get_item(TableName.ITEMS, {"ItemID": item_id})
    item_name = item.get("Name", "Unknown Item") if item else "Unknown Item"

    # Remove from inventory
    dynamo.update_item(
        TableName.CHARACTERS,
        Key={"CharacterID": character_id},
        UpdateExpression="REMOVE Inventory.#slot",
        ExpressionAttributeNames={"#slot": item_slot},
    )

    # Delete item record
    dynamo.delete_item(TableName.ITEMS, {"ItemID": item_id})

    logger.info(f"Character {character_id} discarded item {item_id} ({item_name})")

    return {
        "success": True,
        "message": "Item discarded",
        "itemName": item_name,
    }
```

**2. Add Stack Consolidation Function**

In `eidolon/items.py`:

```python
def consolidate_stacks(character_id: str) -> dict:
    """
    Consolidate stackable items of the same type.

    Example: 3 separate "Health Potion" stacks of 2, 3, 1
             → 1 stack of 6 (or 1x99 + 1x7 if MaxStack=99)

    Returns:
        Dict with consolidation stats
    """
    character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
    if not character:
        raise ValueError(f"Character {character_id} not found")

    inventory = character.get("Inventory", {})
    if not inventory:
        return {"consolidated": 0}

    # Fetch all items
    item_ids = [item_id for item_id in inventory.values() if item_id]
    items = {
        item["ItemID"]: item
        for item in dynamo.batch_get_items(
            TableName.ITEMS,
            [{"ItemID": item_id} for item_id in item_ids]
        )
    }

    # Group by PrototypeID for stackable items
    stackable_groups = {}  # PrototypeID -> [(slot, item_id, quantity)]

    for slot, item_id in inventory.items():
        item = items.get(item_id)
        if not item:
            continue

        if item.get("Stackable", False):
            prototype_id = item.get("PrototypeID")
            if prototype_id not in stackable_groups:
                stackable_groups[prototype_id] = []

            stackable_groups[prototype_id].append(
                (slot, item_id, item.get("Quantity", 1))
            )

    # Consolidate each group
    consolidated_count = 0
    new_inventory = inventory.copy()

    for prototype_id, item_list in stackable_groups.items():
        if len(item_list) <= 1:
            continue  # Nothing to consolidate

        # Sort by quantity descending
        item_list.sort(key=lambda x: x[2], reverse=True)

        # Get max stack size from first item
        first_item = items[item_list[0][1]]
        max_stack = first_item.get("MaxStack", 99)

        # Calculate total quantity
        total_quantity = sum(qty for _, _, qty in item_list)

        # Create consolidated stacks
        remaining_quantity = total_quantity
        kept_items = []  # (slot, item_id, new_quantity)

        for slot, item_id, _ in item_list:
            if remaining_quantity <= 0:
                # Delete excess items
                dynamo.delete_item(TableName.ITEMS, {"ItemID": item_id})
                del new_inventory[slot]
                consolidated_count += 1
            else:
                # Update quantity
                new_quantity = min(remaining_quantity, max_stack)
                dynamo.update_item(
                    TableName.ITEMS,
                    Key={"ItemID": item_id},
                    UpdateExpression="SET Quantity = :qty",
                    ExpressionAttributeValues={":qty": new_quantity},
                )
                kept_items.append((slot, item_id, new_quantity))
                remaining_quantity -= new_quantity

    # Update character inventory if changed
    if consolidated_count > 0:
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET Inventory = :inventory",
            ExpressionAttributeValues={":inventory": new_inventory},
        )

    return {"consolidated": consolidated_count}
```

**3. Frontend Discard Action**

Update `incremental/lib/widgets/game/inventory_panel.dart`:

```dart
Widget _buildItemCard(InventoryItem item) {
  return Card(
    child: Column(
      children: [
        Text(item.name),
        Row(
          children: [
            if (item.consumable)
              IconButton(
                icon: const Icon(Icons.local_drink),
                onPressed: () => _useItem(item),
                tooltip: 'Use',
              ),
            IconButton(
              icon: const Icon(Icons.delete_outline),
              onPressed: () => _confirmDiscard(item),
              tooltip: 'Discard',
            ),
          ],
        ),
      ],
    ),
  );
}

Future<void> _confirmDiscard(InventoryItem item) async {
  final confirmed = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: const Text('Discard Item?'),
      content: Text('Discard ${item.name}? This cannot be undone.'),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context, false),
          child: const Text('Cancel'),
        ),
        TextButton(
          onPressed: () => Navigator.pop(context, true),
          child: const Text('Discard'),
        ),
      ],
    ),
  );

  if (confirmed == true) {
    await _discardItem(item);
  }
}

Future<void> _discardItem(InventoryItem item) async {
  final result = await _apiService.discardItem(
    characterId: widget.character.id,
    itemId: item.id,
  );

  if (result['success']) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Discarded ${result['itemName']}')),
    );

    await _characterProvider.refresh();
  }
}
```

#### Files Modified

- ➕ `lambda/api_item_discard.py` - New Lambda function
- ✏️ `eidolon/items.py` - Add `discard_item()` and `consolidate_stacks()`
- ✏️ `deployment/api.py` - Add `/item/discard` route
- ✏️ `incremental/lib/services/api_service.dart` - Add `discardItem()` method
- ✏️ `incremental/lib/widgets/game/inventory_panel.dart` - Add discard button

#### Acceptance Criteria

- [ ] Discard endpoint removes item from inventory
- [ ] Item record deleted from Items table
- [ ] Confirmation dialog prevents accidental discards
- [ ] Stack consolidation combines identical stackable items
- [ ] Respects MaxStack limits when consolidating
- [ ] UI refreshes after discard operation

---

### R5-T4: Item Visual Assets (Icons & Descriptions)

**Status:** ❌ NOT IMPLEMENTED
**Priority:** P2 - Nice to have for beta
**Issues:** New - "Add item icons and rich descriptions"

#### Current State

**What Exists:**

- Items have Name and Description fields
- Text-only inventory display
- Basic item grid layout

**What's Missing:**

- No item icons/images
- Descriptions not prominently displayed
- No visual distinction between item types

#### Implementation Requirements

**1. Create Icon Asset System**

Add icon field to item prototypes:

```json
{
  "PrototypeID": "health-potion",
  "Name": "Health Potion",
  "Description": "A crimson liquid in a glass vial. Restores 25 health when consumed.",
  "IconPath": "items/consumables/health_potion.png",  // ← New field
  "IconUrl": "https://cdn.example.com/items/health_potion.png",  // ← Or use CDN
  "Type": "consumable",
  "Rarity": "common"  // ← For color coding
}
```

**2. Icon Asset Storage**

Options:
- **Option A:** S3 bucket with CloudFront distribution (preferred for production)
- **Option B:** Bundled assets in Flutter app (faster for beta, limited flexibility)

**Option A Implementation:**

```python
# deployment/s3.py - Add icons bucket
icons_bucket = s3.Bucket(
    self,
    "ItemIconsBucket",
    bucket_name=f"{project_name}-item-icons",
    public_read_access=True,  # Icons are public
    cors=[{
        "allowed_methods": ["GET"],
        "allowed_origins": ["*"],
        "allowed_headers": ["*"],
    }],
)

# CloudFront distribution for icons
icons_distribution = cloudfront.Distribution(
    self,
    "IconsDistribution",
    default_behavior={
        "origin": origins.S3Origin(icons_bucket),
        "cache_policy": cloudfront.CachePolicy.CACHING_OPTIMIZED,
    },
)
```

**Option B Implementation (Bundled Assets):**

```dart
// incremental/lib/utils/item_icons.dart
class ItemIcons {
  static const String basePath = 'assets/images/items';

  static String getIconPath(String prototypeId) {
    // Map prototype IDs to icon file paths
    const iconMap = {
      'health-potion': '$basePath/consumables/health_potion.png',
      'mana-potion': '$basePath/consumables/mana_potion.png',
      'iron-sword': '$basePath/weapons/iron_sword.png',
      'leather-armor': '$basePath/armor/leather_armor.png',
      // ... more mappings
    };

    return iconMap[prototypeId] ?? '$basePath/placeholder.png';
  }
}
```

**3. Update Frontend Item Display**

```dart
// incremental/lib/widgets/game/inventory_item_card.dart
class InventoryItemCard extends StatelessWidget {
  final InventoryItem item;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: InkWell(
        onTap: () => _showItemDetails(context, item),
        child: Column(
          children: [
            // Item icon
            SizedBox(
              width: 64,
              height: 64,
              child: item.iconUrl != null
                ? Image.network(
                    item.iconUrl!,
                    fit: BoxFit.contain,
                    errorBuilder: (_, __, ___) => _placeholderIcon(),
                  )
                : _placeholderIcon(),
            ),

            // Item name with rarity color
            Text(
              item.name,
              style: TextStyle(
                color: _getRarityColor(item.rarity),
                fontWeight: FontWeight.bold,
              ),
              textAlign: TextAlign.center,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),

            // Quantity badge for stackable items
            if (item.stackable && item.quantity > 1)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: Colors.black.withOpacity(0.7),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Text(
                  'x${item.quantity}',
                  style: const TextStyle(color: Colors.white, fontSize: 12),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _placeholderIcon() {
    return Container(
      color: Colors.grey[300],
      child: const Icon(Icons.inventory_2, size: 32),
    );
  }

  Color _getRarityColor(String? rarity) {
    switch (rarity?.toLowerCase()) {
      case 'common': return Colors.grey;
      case 'uncommon': return Colors.green;
      case 'rare': return Colors.blue;
      case 'epic': return Colors.purple;
      case 'legendary': return Colors.orange;
      default: return Colors.black;
    }
  }

  void _showItemDetails(BuildContext context, InventoryItem item) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(
          item.name,
          style: TextStyle(color: _getRarityColor(item.rarity)),
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Item icon (larger)
            Center(
              child: SizedBox(
                width: 128,
                height: 128,
                child: item.iconUrl != null
                  ? Image.network(item.iconUrl!)
                  : _placeholderIcon(),
              ),
            ),
            const SizedBox(height: 16),

            // Description
            Text(
              item.description,
              style: const TextStyle(fontSize: 14),
            ),
            const SizedBox(height: 12),

            // Stats
            if (item.value > 0)
              Text('Value: ${item.value} gold'),
            if (item.mass > 0)
              Text('Weight: ${item.mass}'),
            if (item.stackable)
              Text('Stackable (max ${item.maxStack})'),
          ],
        ),
        actions: [
          if (item.consumable)
            TextButton(
              onPressed: () {
                Navigator.pop(context);
                _useItem(item);
              },
              child: const Text('Use'),
            ),
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }
}
```

**4. Create Default Icon Set**

Minimum viable icon set (can use placeholder icons initially):

- ✅ Health Potion (red vial)
- ✅ Mana Potion (blue vial)
- ✅ Sword (generic weapon)
- ✅ Shield (generic armor)
- ✅ Gold Coins (currency representation)
- ✅ Backpack (container)
- ✅ Scroll (magic item)
- ✅ Placeholder (unknown items)

**Asset Creation Options:**

- Use free game icon sets (e.g., game-icons.net with CC license)
- Commission custom pixel art icons
- Generate with AI tools (MidJourney, DALL-E) then edit

#### Files Modified

- ✏️ `eidolon/items.py` - Update `build_item_payload()` to include IconUrl
- ✏️ `data/prototypes/*.json` - Add IconPath/IconUrl to prototypes
- ✏️ `incremental/lib/models/inventory_item.dart` - Add icon fields
- ➕ `incremental/lib/widgets/game/inventory_item_card.dart` - New widget
- ✏️ `incremental/lib/widgets/game/inventory_panel.dart` - Use new card widget
- ➕ `incremental/assets/images/items/` - Icon assets (if bundled)

#### Acceptance Criteria

- [ ] Item prototypes include IconPath or IconUrl
- [ ] Frontend displays item icons in inventory grid
- [ ] Clicking item shows detailed view with description
- [ ] Rarity color coding implemented
- [ ] Quantity badges shown for stackable items
- [ ] Placeholder icon used for items without icons
- [ ] At least 8 default icons created/sourced

---

### R5-T5: Store/Shop Implementation

**Status:** ❌ NOT IMPLEMENTED
**Priority:** P1 - Required for meaningful currency usage
**Issues:** New - "Implement item shop/store"
**Blocked By:** R5-T1 (✅ complete - currency system operational)

#### Current State

**What Exists:**

- Currency calculation (R4-T1 will persist it)
- Item creation system via prototypes
- Character inventory management

**What's Missing:**

- No way to spend currency
- No store UI in Incremental app
- No purchase transaction logic

#### Implementation Requirements

**1. Define Store Inventory**

Create store configuration in DynamoDB or config file:

**Option A: Static Config (Simple, fast to implement)**

```json
// data/store_inventory.json
{
  "StoreID": "main-store",
  "Name": "General Merchant",
  "Description": "A traveling merchant selling essential supplies.",
  "Inventory": [
    {
      "PrototypeID": "health-potion",
      "Price": 15,
      "Stock": -1,  // -1 = unlimited
      "MinLevel": 0
    },
    {
      "PrototypeID": "mana-potion",
      "Price": 20,
      "Stock": -1,
      "MinLevel": 0
    },
    {
      "PrototypeID": "iron-sword",
      "Price": 100,
      "Stock": 3,  // Limited stock
      "MinLevel": 1
    },
    {
      "PrototypeID": "leather-armor",
      "Price": 150,
      "Stock": 2,
      "MinLevel": 1
    },
    {
      "PrototypeID": "backpack",
      "Price": 50,
      "Stock": -1,
      "MinLevel": 0
    }
  ],
  "RefreshIntervalHours": 24  // Store restocks daily
}
```

**Option B: DynamoDB Table (Flexible, supports multiple stores)**

```python
# deployment/dynamodb.py - Add Store table
store_table = dynamodb.Table(
    self,
    "StoreTable",
    table_name="store",
    partition_key={"name": "StoreID", "type": dynamodb.AttributeType.STRING},
    billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
)
```

**2. Create Purchase Endpoint**

New Lambda function: `lambda/api_store_purchase.py`

```python
def lambda_handler(event, context):
    """
    Purchase an item from the store.

    POST /store/purchase
    Body: {
        "CharacterID": "uuid",
        "StoreID": "main-store",
        "PrototypeID": "health-potion",
        "Quantity": 5
    }

    Returns:
        {
            "success": true,
            "itemsPurchased": 5,
            "totalCost": 75,
            "remainingCurrency": 425,
            "itemID": "new-item-uuid"
        }
    """
```

**Implementation:**

```python
def purchase_item(
    character_id: str,
    store_id: str,
    prototype_id: str,
    quantity: int = 1
) -> dict:
    """
    Purchase item from store, deduct currency, add to inventory.

    Args:
        character_id: Character UUID
        store_id: Store identifier
        prototype_id: Item prototype to purchase
        quantity: Number to purchase

    Returns:
        Dict with purchase results
    """
    # Load store inventory
    store = load_store_config(store_id)  # From S3 or DynamoDB

    # Find item in store
    store_item = None
    for item in store["Inventory"]:
        if item["PrototypeID"] == prototype_id:
            store_item = item
            break

    if not store_item:
        raise ValueError(f"Item {prototype_id} not available in {store_id}")

    # Check stock
    if store_item["Stock"] != -1 and store_item["Stock"] < quantity:
        raise ValueError(f"Insufficient stock: {store_item['Stock']} available")

    # Calculate cost
    unit_price = store_item["Price"]
    total_cost = unit_price * quantity

    # Get character
    character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})
    if not character:
        raise ValueError(f"Character {character_id} not found")

    # Check currency
    current_currency = character.get("Currency", 0)
    if current_currency < total_cost:
        raise ValueError(
            f"Insufficient funds: need {total_cost}, have {current_currency}"
        )

    # Check level requirement (if applicable)
    min_level = store_item.get("MinLevel", 0)
    character_level = character.get("Level", 0)
    if character_level < min_level:
        raise ValueError(f"Level {min_level} required to purchase this item")

    # Create item(s)
    if quantity == 1:
        # Single item
        item = create_item_from_prototype(prototype_id)
        item_ids = [item["ItemID"]]
    else:
        # For stackable items, create one stack
        prototype = get_prototype(prototype_id)
        if prototype.get("Stackable", False):
            item = create_item_from_prototype(prototype_id)
            # Update quantity
            dynamo.update_item(
                TableName.ITEMS,
                Key={"ItemID": item["ItemID"]},
                UpdateExpression="SET Quantity = :qty",
                ExpressionAttributeValues={":qty": quantity},
            )
            item_ids = [item["ItemID"]]
        else:
            # Create multiple non-stackable items
            item_ids = []
            for _ in range(quantity):
                item = create_item_from_prototype(prototype_id)
                item_ids.append(item["ItemID"])

    # Add to inventory
    inventory = character.get("Inventory", {})
    for item_id in item_ids:
        slot = find_next_available_slot(inventory)
        inventory[slot] = item_id

    # Deduct currency and update inventory atomically
    new_currency = current_currency - total_cost
    dynamo.update_item(
        TableName.CHARACTERS,
        Key={"CharacterID": character_id},
        UpdateExpression="SET Currency = :currency, Inventory = :inventory",
        ExpressionAttributeValues={
            ":currency": new_currency,
            ":inventory": inventory,
        },
        ConditionExpression="Currency >= :cost",  # Prevent race conditions
        ExpressionAttributeValues={
            ":cost": total_cost,
        },
    )

    logger.info(
        f"Character {character_id} purchased {quantity}x {prototype_id} "
        f"for {total_cost} currency"
    )

    return {
        "success": True,
        "itemsPurchased": quantity,
        "totalCost": total_cost,
        "remainingCurrency": new_currency,
        "itemIDs": item_ids,
    }
```

**3. Create Store List Endpoint**

```python
def lambda_handler(event, context):
    """
    Get available store inventory.

    GET /store/list?StoreID=main-store&CharacterID=uuid

    Returns:
        {
            "StoreID": "main-store",
            "Name": "General Merchant",
            "Items": [
                {
                    "PrototypeID": "health-potion",
                    "Name": "Health Potion",
                    "Description": "...",
                    "Price": 15,
                    "Stock": -1,
                    "Affordable": true,
                    "MeetsRequirements": true
                },
                ...
            ]
        }
    """
    store_id = event["queryStringParameters"]["StoreID"]
    character_id = event["queryStringParameters"].get("CharacterID")

    store = load_store_config(store_id)

    # Enrich with prototype details and affordability
    character = dynamo.get_item(
        TableName.CHARACTERS,
        {"CharacterID": character_id}
    ) if character_id else None

    currency = character.get("Currency", 0) if character else 0

    enriched_items = []
    for store_item in store["Inventory"]:
        prototype = get_prototype(store_item["PrototypeID"])

        enriched_items.append({
            "PrototypeID": store_item["PrototypeID"],
            "Name": prototype.get("Name"),
            "Description": prototype.get("Description"),
            "IconUrl": prototype.get("IconUrl"),
            "Price": store_item["Price"],
            "Stock": store_item["Stock"],
            "Affordable": currency >= store_item["Price"],
            "MeetsRequirements": True,  # Check level, etc.
        })

    return {
        "statusCode": 200,
        "body": json.dumps({
            "StoreID": store_id,
            "Name": store["Name"],
            "Description": store["Description"],
            "Items": enriched_items,
        }),
    }
```

**4. Frontend Store UI**

Create new screen: `incremental/lib/screens/store_screen.dart`

```dart
class StoreScreen extends StatefulWidget {
  final Character character;
  final String storeId;

  const StoreScreen({
    required this.character,
    this.storeId = 'main-store',
  });

  @override
  State<StoreScreen> createState() => _StoreScreenState();
}

class _StoreScreenState extends State<StoreScreen> {
  List<StoreItem> _items = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadStore();
  }

  Future<void> _loadStore() async {
    setState(() => _loading = true);

    final storeData = await _apiService.getStoreInventory(
      storeId: widget.storeId,
      characterId: widget.character.id,
    );

    setState(() {
      _items = storeData['Items']
        .map<StoreItem>((json) => StoreItem.fromJson(json))
        .toList();
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('General Merchant'),
        actions: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                const Icon(Icons.monetization_on, color: Colors.amber),
                const SizedBox(width: 8),
                Text(
                  '${widget.character.currency}',
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
      body: _loading
        ? const Center(child: CircularProgressIndicator())
        : GridView.builder(
            padding: const EdgeInsets.all(16),
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 2,
              childAspectRatio: 0.75,
              crossAxisSpacing: 16,
              mainAxisSpacing: 16,
            ),
            itemCount: _items.length,
            itemBuilder: (context, index) {
              return _buildStoreItemCard(_items[index]);
            },
          ),
    );
  }

  Widget _buildStoreItemCard(StoreItem item) {
    final affordable = item.affordable;

    return Card(
      elevation: affordable ? 4 : 1,
      child: InkWell(
        onTap: affordable ? () => _showPurchaseDialog(item) : null,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Item icon
              Expanded(
                child: Center(
                  child: item.iconUrl != null
                    ? Image.network(item.iconUrl!, fit: BoxFit.contain)
                    : const Icon(Icons.inventory_2, size: 48),
                ),
              ),

              // Item name
              Text(
                item.name,
                style: const TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 14,
                ),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),

              const SizedBox(height: 8),

              // Price
              Row(
                children: [
                  Icon(
                    Icons.monetization_on,
                    size: 16,
                    color: affordable ? Colors.amber : Colors.grey,
                  ),
                  const SizedBox(width: 4),
                  Text(
                    '${item.price}',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                      color: affordable ? Colors.green : Colors.red,
                    ),
                  ),
                ],
              ),

              // Stock indicator
              if (item.stock != -1)
                Text(
                  'Stock: ${item.stock}',
                  style: TextStyle(
                    fontSize: 12,
                    color: Colors.grey[600],
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _showPurchaseDialog(StoreItem item) async {
    int quantity = 1;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text('Purchase ${item.name}'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(item.description),
              const SizedBox(height: 16),

              // Quantity selector
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  IconButton(
                    icon: const Icon(Icons.remove),
                    onPressed: quantity > 1
                      ? () => setDialogState(() => quantity--)
                      : null,
                  ),
                  Text(
                    '$quantity',
                    style: const TextStyle(fontSize: 18),
                  ),
                  IconButton(
                    icon: const Icon(Icons.add),
                    onPressed: () => setDialogState(() => quantity++),
                  ),
                ],
              ),

              // Total cost
              Text(
                'Total: ${item.price * quantity} gold',
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancel'),
            ),
            ElevatedButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Purchase'),
            ),
          ],
        ),
      ),
    );

    if (confirmed == true) {
      await _purchaseItem(item, quantity);
    }
  }

  Future<void> _purchaseItem(StoreItem item, int quantity) async {
    try {
      final result = await _apiService.purchaseItem(
        characterId: widget.character.id,
        storeId: widget.storeId,
        prototypeId: item.prototypeId,
        quantity: quantity,
      );

      if (result['success']) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              'Purchased ${quantity}x ${item.name} for ${result['totalCost']} gold',
            ),
          ),
        );

        // Refresh character and store
        await _characterProvider.refresh();
        await _loadStore();
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Purchase failed: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }
}
```

**5. Add Store Navigation**

Update game screen to include Store button:

```dart
// In incremental/lib/screens/game_screen.dart
FloatingActionButton(
  onPressed: () {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => StoreScreen(
          character: _character,
        ),
      ),
    );
  },
  child: const Icon(Icons.store),
  tooltip: 'Visit Store',
)
```

#### Testing Requirements

```python
def test_purchase_item_success():
    """Test successful item purchase."""
    character = create_test_character(currency=100)

    result = purchase_item(
        character_id=character.id,
        store_id="main-store",
        prototype_id="health-potion",
        quantity=3,
    )

    assert result["success"] is True
    assert result["totalCost"] == 45  # 3 × 15
    assert result["remainingCurrency"] == 55

    # Verify inventory updated
    updated_character = get_character(character.id)
    assert len(updated_character["Inventory"]) == 1

def test_purchase_insufficient_funds():
    """Test purchase fails with insufficient currency."""
    character = create_test_character(currency=10)

    with pytest.raises(ValueError, match="Insufficient funds"):
        purchase_item(
            character_id=character.id,
            store_id="main-store",
            prototype_id="iron-sword",  # Costs 100
            quantity=1,
        )
```

#### Files Modified

- ➕ `lambda/api_store_purchase.py` - New purchase endpoint
- ➕ `lambda/api_store_list.py` - New store listing endpoint
- ➕ `eidolon/store.py` - Store management functions
- ➕ `data/store_inventory.json` - Store configuration
- ✏️ `deployment/api.py` - Add store routes
- ➕ `incremental/lib/screens/store_screen.dart` - Store UI
- ✏️ `incremental/lib/services/api_service.dart` - Add store API methods
- ✏️ `incremental/lib/models/store_item.dart` - Store item model

#### Acceptance Criteria

- [ ] Store inventory defined with prices and stock
- [ ] Purchase endpoint validates currency and deducts cost
- [ ] Items added to inventory atomically with currency deduction
- [ ] Store UI displays available items with affordability indicators
- [ ] Purchase dialog shows quantity selector and total cost
- [ ] Character currency updates after purchase
- [ ] Store inventory refreshes after purchase
- [ ] Insufficient funds displays error message
- [ ] At least 5 items available in initial store

---

### R5-T6: Author Quick-Start Documentation

**Status:** ❌ NOT IMPLEMENTED (no documentation/story-author-quickstart.md)
**Priority:** P1 - Required for content authoring at scale
**Issues:** #729 (documentation suite), #619 (author handbook - merge duplicate)

**Moved from:** R3-T4 → R4 → R5 (deferred to document complete economy system)

#### Rationale for R5 Inclusion

**Why defer from R3 and R4:**
- R3 focused on core bug fixes and minimal beta readiness
- R4 focused on IndexedDB caching infrastructure
- Author documentation more valuable after R5 economy system complete
- Authors need to understand currency rewards, item drops, store mechanics
- Better to write comprehensive guide once than iterate

**Why include in R5:**
- Currency system now complete (R5-T1) provides foundation to document
- Economy features add complexity requiring clear documentation
- Authors need guidance on reward balancing with working examples
- Quick-start enables non-developer content creation at scale
- Unblocks community content contributions

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
- Copy-paste examples for common patterns including economy features
- Clear workflow: create → validate → load → test
- Guidance on balancing currency rewards and item drops

**NOT Required (deferred to R5+):**

- Comprehensive author handbook
- Story design theory or creative writing guidance
- Advanced balancing formulas
- Visual story editor

#### Implementation Requirements

**Create: `documentation/story-author-quickstart.md`**

**Target Audience:** Non-developers who can edit JSON and run command-line tools.

**Core Sections:**

1. **Prerequisites**
   - Text editor setup
   - Python 3.12+ installation
   - Repository access
   - AWS CLI configuration

2. **Story Creation Workflow**
   - Create story JSON
   - Define segments (mechanical, decision)
   - Add economy features (currency rewards, item drops)
   - Validate content
   - Load to DynamoDB
   - Test in-game

3. **Field Reference**
   - Story metadata fields explained
   - Segment types and fields
   - Challenge definitions
   - Outcome specifications
   - **NEW: Currency reward tiers**
   - **NEW: Item drop configuration**

4. **Copy-Paste Templates** (3 required)
   - Linear 3-segment story with currency reward
   - Branching story with 2 decision points and item drops
   - Combat story with skill challenge and mixed rewards

5. **Common Patterns**
   - Simple quests
   - Branching narratives
   - Combat encounters
   - **NEW: Economy-focused stories (earn/spend loops)**

6. **Balance Guidelines**
   - Segment durations by tier
   - Difficulty progression
   - **NEW: Currency reward scaling**
   - **NEW: Item drop rates and value**
   - **NEW: Store item pricing guidance**

7. **Troubleshooting**
   - Validation errors and fixes
   - Loading issues
   - Testing problems
   - **NEW: Economy balance issues**

**Economy-Specific Content:**

Add sections covering R4 features:

````markdown
### Currency Rewards

Stories can award currency based on outcome quality:

```json
{
  "RewardTiers": {
    "Exceptional": {"Currency": 100, "Items": ["health-potion"]},
    "Success": {"Currency": 50, "Items": []},
    "Minimal": {"Currency": 25, "Items": []},
    "Failure": {"Currency": 0, "Items": []}
  }
}
```text

**Balancing Guidelines:**

- Tier 1 stories (beginner): 10-50 currency per completion
- Tier 2 stories (intermediate): 50-200 currency
- Tier 3 stories (advanced): 200-1000 currency

Consider:
- Story length (longer = higher rewards)
- Difficulty (harder = higher rewards)
- Repeatability (repeatable = lower rewards)

### Item Drops

Items can be rewarded based on outcome:

```json
{
  "RewardTiers": {
    "Exceptional": {
      "Items": [
        {"PrototypeID": "health-potion", "Quantity": 3},
        {"PrototypeID": "iron-sword", "Quantity": 1}
      ]
    }
  }
}
```text

**Item Value Guidance:**

- Consumables (potions): 10-20 currency value
- Common equipment: 50-150 currency value
- Rare equipment: 200-500 currency value

**Drop Rate Guidelines:**

- Consumables: 50-80% chance per completion
- Common equipment: 10-30% chance
- Rare equipment: 1-10% chance

### Store Item Pricing

When creating items for the store, consider:

1. **Crafting Cost** - How much would it cost to obtain via stories?
2. **Utility Value** - How useful is the item?
3. **Scarcity** - Is it a unique/rare item?

**Pricing Formula:**

```
Store Price = (Average Currency Reward × Story Completions Required) × 1.5
```text

Example:
- Health Potion drops 30% of the time from Tier 1 stories (50 currency)
- Expected value: 50 ÷ 0.3 = ~166 currency of story completion
- Store price: 166 × 1.5 = ~250 currency → Round to 15 currency (instant purchase option)
````

#### Additional Documentation Updates

**Update `README.md`:**

```markdown
## Documentation

- [Story Author Quick-Start](documentation/story-author-quickstart.md) - Create your first story
- [Deployment Guide](documentation/deployment.md) - Infrastructure setup
- [Architecture Overview](documentation/architecture.md) - System design
```text

**Update `.github/workflows/story-validation.yml`:**

```yaml
# This workflow validates story content on every PR
# Ensures stories meet structural requirements before merge
# See documentation/story-author-quickstart.md for authoring guide
```text

#### Files Modified

- ➕ `documentation/story-author-quickstart.md` - New comprehensive guide
- ✏️ `README.md` - Add link to quick-start
- ✏️ `.github/workflows/story-validation.yml` - Add documentation reference

#### Acceptance Criteria

- [ ] Quick-Start document created with all core sections
- [ ] Economy-specific sections added (currency, items, pricing)
- [ ] 3 copy-paste templates included and validated
- [ ] All examples include economy features (rewards, items)
- [ ] Balance guidelines cover currency and item scaling
- [ ] README.md updated with link
- [ ] CI workflow commented with documentation reference
- [ ] Non-developer can follow guide end-to-end without additional help
- [ ] All examples pass validation when copy-pasted

#### Definition of Done

**Documentation Quality:**

- Guide is scannable (clear headings, short paragraphs)
- Examples are complete and immediately usable
- Balance guidelines are practical and testable
- Troubleshooting covers common issues

**Validation:**

- Have a non-developer (or simulated non-developer) follow the guide
- They should successfully create, validate, load, and test a story
- No questions should arise that aren't answered in the guide

**Integration:**

- Guide linked from README
- Examples referenced in validation workflow
- Community can find and use documentation

---

## Current Status Summary (2025-10-19)

### Completed (1 of 6 tasks)

**R5-T1: Currency System ✅**
- Coin-based currency implementation complete (eidolon/story_rewards.py:82-199)
- Resources.Value tracks total wealth
- Story rewards apply currency and create coin items
- Frontend displays currency rewards
- Server-side coin stacking implemented

### Remaining Tasks (5 of 6 tasks)

**R5-T2: Item Consumption** ❌
- No api_item_use.py endpoint
- No consumption UI in inventory panel
- Required for meaningful item usage

**R5-T3: Inventory Management** ❌
- No api_item_discard.py endpoint
- No discard UI in inventory panel
- Coin stacking works server-side, but no UI consolidation tool

**R5-T4: Item Icons** ❌
- No IconPath/IconUrl in prototypes
- Text-only inventory display
- No visual distinction between item types

**R5-T5: Store/Shop** ❌
- No store API endpoints (api_store_purchase.py, api_store_list.py)
- No store UI (StoreScreen)
- Cannot spend currency despite earning it
- **Unblocked:** R5-T1 complete, can now implement store

**R5-T6: Author Documentation** ❌
- No documentation/story-author-quickstart.md
- Authors lack guidance on currency balancing
- No copy-paste templates for economy features

## R5 Success Criteria

### Economy Foundation
- ✅ Currency persists correctly from story rewards (R5-T1 complete)
- ✅ Currency displays in character UI (R5-T1 complete)
- ❌ Currency can be spent in store (R5-T5 pending)

**Inventory Operations:**
- ❌ Items can be used (consumables apply effects) - R5-T2 pending
- ❌ Items can be discarded with confirmation - R5-T3 pending
- ✅ Stackable items consolidate properly (coins only, server-side)
- ❌ Item icons enhance visual presentation - R5-T4 pending
- ❌ Item details accessible via click/tap - R5-T4 pending

**Player Store:**
- ❌ Store lists purchasable items with prices - R5-T5 pending
- ❌ Purchase flow validates currency and inventory space - R5-T5 pending
- ❌ Transactions are atomic (no partial purchases) - R5-T5 pending
- ❌ Store inventory includes diverse item types - R5-T5 pending

### Post-R5 Capabilities (When Complete)

**Players Can (Current):**
- ✅ Earn currency from story completion (R5-T1)
- ✅ Track currency balance (Resources.Value)
- ✅ Receive coin items in inventory
- ❌ Purchase items from store (R5-T5 pending)
- ❌ Use consumable items for immediate effects (R5-T2 pending)
- ❌ Manage inventory (discard unwanted items) (R5-T3 pending)
- ❌ See item icons and detailed descriptions (R5-T4 pending)

**System Supports (Current):**
- ✅ Currency earning (R5-T1)
- ✅ Coin stacking and merging
- ✅ Resources.Value tracking
- ❌ Full economic loop (earn → spend → use) - partial
- ❌ Item lifecycle management (acquire → use → discard) - partial
- ❌ Extensible store system (multiple stores, dynamic inventory) - not started
- ❌ Visual item presentation (icons, rarity colors) - not started

---

## Dependencies

**R5-T1 (Currency) blocks:**
- R5-T5 (Store) - ✅ UNBLOCKED (R5-T1 complete)

**R5-T4 (Icons) enhances:**
- R5-T5 (Store) - Better visual presentation
- R5-T2 (Consumption) - Clearer item identification

**No other blocking dependencies** - R5-T2, R5-T3, R5-T4, R5-T5, R5-T6 can be parallelized

---

## Deferred to R6+

**Advanced Inventory Features:**
- Container navigation and nested inventory
- Equipment optimization suggestions
- Inventory search and filtering
- Drag-and-drop item organization
- IndexedDB client-side caching (see `inventory-complexity-analysis.md`)

**Advanced Economy Features:**
- Multiple currencies (gold, gems, tokens)
- Item crafting and enhancement
- Player-to-player trading
- Auction house
- Dynamic pricing based on supply/demand

**Advanced Store Features:**
- Multiple stores with different inventories
- Store reputation and unlock system
- Limited-time offers and sales
- Quest-locked items

---

## Open Questions

1. **Icon Asset Source:** Use bundled assets (faster) or S3 + CloudFront (flexible)?
2. **Store Stock Refresh:** Daily reset, per-character cooldown, or unlimited?
3. **Currency Display Format:** "Gold", "Currency", or custom name from config?
4. **Item Rarity System:** Implement color coding now or defer to R5?
5. **Consumable Effects:** Support only Health initially, or include buffs/debuffs?

---

## Next Steps After R5

**Release 6 Planning** should focus on:
- Character progression visualization (skill trees, achievements)
- Advanced combat mechanics (abilities, status effects)
- Social features (leaderboards, player profiles)
- Content authoring tools (visual story editor)
- Performance optimization (caching, lazy loading)

---

**Document Version:** 1.1
**Created:** 2025-10-07
**Updated:** 2025-10-19
**Status:** Planning (1 of 6 tasks complete)

**Revision History:**
- v1.0 (2025-10-07): Initial planning document for R4 economy system
- v1.1 (2025-10-19): Updated to reflect R5-T1 completion, corrected release numbering (R4→R5), updated all task references
