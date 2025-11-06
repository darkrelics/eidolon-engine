# Currency System Documentation

**Created**: 2025-10-19
**Status**: Design Document
**Version**: 2.0

## Overview

The Multi-User Dungeon economy operates on a hybrid system where currency exists as both physical items (coins) and tracked value. Coins are stackable items that can be dropped, traded, or stolen, while the Value field tracks total wealth for quick calculations.

## Currency Architecture

### Fundamental Units (Hidden Layer)

The **Fundamental Unit (FU)** is the atomic economic value that underlies all currency and items in the game world. This value is:
- Never displayed to players
- Used for all internal calculations
- The basis for all economic transactions
- Allows dynamic revaluation based on world events

**Key Properties:**
- All items, including coins, have a Value in FU
- The Value field tracks total fundamental units
- Physical coins exist as inventory items

### Currency as Items

Coins are physical items with prototype definitions:

| Coin Type | PrototypeID | Value per Coin | Weight |
|-----------|-------------|----------------|---------|
| Bronze Coin | bronze-coin-001 | 10 FU | 0.01 kg |
| Silver Coin | silver-coin-001 | 120 FU | 0.02 kg |
| Gold Coin | gold-coin-001 | 2,400 FU | 0.05 kg |

### Exchange Rates

**Fixed Player-Visible Rates:**
- 1 Silver = 12 Bronze
- 1 Gold = 20 Silver
- 1 Gold = 240 Bronze

**Fundamental Conversion:**
- 1 Bronze = 10 FU
- 1 Silver = 120 FU (12 × 10)
- 1 Gold = 2,400 FU (20 × 120)

## Stacking System

### Stackable vs Non-Stackable Items

**Critical Design Principles**:

**Stackable Items** (`"Stackable": true`):
- Immutable except for Quantity field
- Cannot have individual modifications, enchantments, or unique properties
- All items with same PrototypeID are identical
- MUST have a Quantity field (1 or more)
- Examples: coins, berries, arrows, basic materials

**Non-Stackable Items** (`"Stackable": false`):
- Fully mutable - can have modifications
- Do NOT have a Quantity attribute (always implicitly 1)
- Each instance can have unique properties (enchantments, condition, etc.)
- Examples: weapons, armor, unique items, enchanted items

### Item Storage Examples

**Stackable Item** (coins, materials):
```json
{
  "ItemID": "unique-item-uuid",
  "PrototypeID": "bronze-coin-001",
  "Quantity": 247,  // Stack of 247 identical bronze coins
  "OwnerID": "character-uuid"
}
```

**Non-Stackable Item** (weapon with modifications):
```json
{
  "ItemID": "unique-sword-uuid",
  "PrototypeID": "long-sword-001",
  "OwnerID": "character-uuid",
  "Enchantment": "flaming",  // Custom property
  "Condition": 0.85,  // Custom property
  "CreatedBy": "master-smith"  // Custom property
  // Note: NO Quantity field - always implicitly 1
}
```

**Invalid Examples**:
```json
// INVALID - stackable item with modifications
{
  "ItemID": "coin-uuid",
  "PrototypeID": "bronze-coin-001",
  "Quantity": 50,
  "Enchantment": "blessed"  // ERROR: Stackable items can't have modifications
}

// INVALID - non-stackable item with quantity
{
  "ItemID": "sword-uuid",
  "PrototypeID": "long-sword-001",
  "Quantity": 3  // ERROR: Non-stackable items don't have quantity
}
```

### Stack Limits

No artificial limits - stacks can grow to any size (limited only by integer representation).

### Stack Operations

```python
def can_stack(item1: dict, item2: dict, prototype: dict) -> bool:
    """Check if two items can stack together."""
    # Must be stackable type
    if not prototype.get("Stackable", False):
        return False

    # Must be same prototype
    if item1["PrototypeID"] != item2["PrototypeID"]:
        return False

    # Must have no modifications (only base fields)
    allowed_fields = {"ItemID", "PrototypeID", "Quantity", "OwnerID"}
    if set(item1.keys()) != allowed_fields or set(item2.keys()) != allowed_fields:
        return False

    return True  # No stack limit

def merge_stacks(item1: dict, item2: dict) -> dict:
    """
    Merge two stackable items.
    The older stack (by UUIDv7 timestamp) keeps its ItemID.
    """
    # UUIDv7 has timestamp, so lexicographic comparison gives older item
    if item1["ItemID"] < item2["ItemID"]:
        # item1 is older, keep its ID
        return {
            "ItemID": item1["ItemID"],
            "PrototypeID": item1["PrototypeID"],
            "Quantity": item1.get("Quantity", 1) + item2.get("Quantity", 1),
            "OwnerID": item1["OwnerID"]
        }
    else:
        # item2 is older, keep its ID
        return {
            "ItemID": item2["ItemID"],
            "PrototypeID": item2["PrototypeID"],
            "Quantity": item1.get("Quantity", 1) + item2.get("Quantity", 1),
            "OwnerID": item2["OwnerID"]
        }
```

## Implementation Structure

### Database Storage

Characters have both a Value tracker and physical coin items:

```json
{
  "CharacterID": "uuid",
  "Resources": {
    "Value": 3650  // Total wealth in FU for quick calculations
  },
  "Inventory": [
    {
      "ItemID": "coin-stack-001",
      "PrototypeID": "gold-coin-001",
      "Quantity": 1
    },
    {
      "ItemID": "coin-stack-002",
      "PrototypeID": "silver-coin-001",
      "Quantity": 10
    },
    {
      "ItemID": "coin-stack-003",
      "PrototypeID": "bronze-coin-001",
      "Quantity": 50
    }
  ]
}
```

### Coin Creation

When awarding currency, create coin items like any other stackable items:

```python
def create_coins_from_value(value: int) -> list:
    """Convert value into coin items - just regular item creation."""
    items_to_create = []

    # Calculate optimal coin distribution
    gold_coins = value // 2400
    remainder = value % 2400
    silver_coins = remainder // 120
    bronze_coins = (remainder % 120) // 10

    # These are just regular item creation requests
    if gold_coins > 0:
        items_to_create.append({
            "PrototypeID": "gold-coin-001",
            "Quantity": gold_coins
        })
    if silver_coins > 0:
        items_to_create.append({
            "PrototypeID": "silver-coin-001",
            "Quantity": silver_coins
        })
    if bronze_coins > 0:
        items_to_create.append({
            "PrototypeID": "bronze-coin-001",
            "Quantity": bronze_coins
        })

    # Use standard item creation for each
    return items_to_create

# Example: 3650 value creates 3 regular stackable items (gold, silver, bronze coin stacks)
```

### Transaction Processing

Transactions deduct from both coin inventory and Value tracker:

```python
def process_purchase(character: dict, item_cost: int) -> bool:
    """Process a purchase using physical coins."""
    if character["Resources"]["Value"] >= item_cost:
        # Deduct from Value tracker
        character["Resources"]["Value"] -= item_cost

        # Remove physical coins from inventory
        coins_to_remove = calculate_coin_payment(character["Inventory"], item_cost)
        remove_coins_from_inventory(character, coins_to_remove)

        # Give change if necessary
        change = calculate_change(coins_to_remove, item_cost)
        if change > 0:
            change_coins = create_coin_items(change)
            add_coins_to_inventory(character, change_coins)

        return True
    return False
```

## Story Rewards Configuration

Story rewards define value and items to award. The system converts value into appropriate coin items:

### Reward Schema

```json
"RewardTiers": {
  "Death": {
    "items": [],
    "currency": 0  // Value in fundamental units
  },
  "Normal": {
    "items": ["item-uuid-1", "item-uuid-2"],
    "currency": 450  // Creates 3 silver, 9 bronze coins
  }
}
```

### Reward Tier Guidelines (in Value)

| Outcome | Value Range | Coins Created | Rationale |
|---------|------------|---------------|-----------|
| Death | 0 | None | No reward for failure |
| Failure | 50-100 | 5-10 Bronze | Consolation prize |
| Minimal | 150-250 | 15-25 Bronze | Basic success |
| Normal | 300-500 | 2-4 Silver + Bronze | Standard reward |
| Exceptional | 750-1000 | 6-8 Silver + Bronze | Excellent performance |

### Story-Specific Modifiers

Different story types warrant different reward scales:

- **Low Risk** (Foraging): 0.8× base rewards
- **Medium Risk** (Puzzles): 1.0× base rewards
- **High Risk** (Combat): 1.5× base rewards

### Coin Generation Example

When a player completes a story with 450 value reward:
1. System calculates: 450 ÷ 120 = 3 silver, 90 remainder
2. Remainder: 90 ÷ 10 = 9 bronze
3. Creates items:
   - 1 stack of 3 silver coins
   - 1 stack of 9 bronze coins
4. Updates character Resources.Value += 450

## Item Valuation

All items have a fundamental value for economic consistency:

### Value Categories

| Category | FU Range | Example Items |
|----------|----------|---------------|
| Trivial | 1-50 | Berries, common herbs |
| Common | 51-200 | Basic tools, simple potions |
| Uncommon | 201-1000 | Quality weapons, armor |
| Rare | 1001-5000 | Magic items, rare materials |
| Legendary | 5001+ | Unique artifacts |

## Economic Dynamics

### World State Modifiers

The fundamental unit system enables dynamic economy based on world events:

```python
class EconomicState:
    """Track economic modifiers for world state."""

    def __init__(self):
        self.currency_multipliers = {
            "bronze": 1.0,  # Can adjust if bronze becomes scarce
            "silver": 1.0,  # Can adjust for silver shortage
            "gold": 1.0     # Can adjust for gold inflation
        }

        self.item_category_multipliers = {
            "consumables": 1.0,  # Food shortage = higher multiplier
            "weapons": 1.0,      # War = higher multiplier
            "materials": 1.0     # Scarcity = higher multiplier
        }
```

### Inflation/Deflation Mechanics

Future implementation can adjust FU values globally:
- **Inflation**: Increase FU requirements (items cost more)
- **Deflation**: Decrease FU requirements (items cost less)
- **Scarcity**: Individual item/category multipliers
- **Events**: Temporary economic modifiers

## Store Pricing

### Base Pricing Formula

```python
def calculate_store_price(base_value: int, demand_modifier: float = 1.0) -> int:
    """Calculate store price with markup and demand."""
    STORE_MARKUP = 1.3  # 30% markup over base value
    price = int(base_value * STORE_MARKUP * demand_modifier)
    return price
```

### Buy-Back Pricing

```python
def calculate_buyback_price(base_value: int, condition: float = 0.8) -> int:
    """Calculate price store pays for items."""
    BUYBACK_RATE = 0.4  # Store pays 40% of base value
    price = int(base_value * BUYBACK_RATE * condition)
    return price
```

## API Response Format

### Character Resources Display

```json
{
  "CharacterID": "uuid",
  "Resources": {
    "display": {
      "gold": 1,
      "silver": 10,
      "bronze": 5
    },
    "total_bronze_equivalent": 365
  }
}
```

### Transaction Response

```json
{
  "success": true,
  "previous_balance": {
    "gold": 2, "silver": 5, "bronze": 8
  },
  "cost": {
    "gold": 0, "silver": 12, "bronze": 0
  },
  "new_balance": {
    "gold": 1, "silver": 13, "bronze": 8
  }
}
```

## Coin Prototype Definitions

### Bronze Coin Prototype

```json
{
  "PrototypeID": "bronze-coin-001",
  "PrototypeName": "Bronze Coin",
  "PrototypeNamePlural": "Bronze Coins",
  "Description": "A small bronze coin, the basic currency of the realm.",
  "Mass": 0.01,
  "Value": 10,
  "Stackable": true,
  "Quantity": 1,
  "Wearable": false,
  "WornOn": [],
  "Verbs": {
    "Use": "You examine the bronze coin.",
    "Examine": "A simple bronze coin with the realm's seal."
  },
  "Overrides": {},
  "TraitMods": {},
  "Container": false,
  "Contents": [],
  "IsWorn": false,
  "CanPickUp": true,
  "Metadata": {
    "CurrencyType": "bronze",
    "Denomination": 1
  }
}
```

### Silver Coin Prototype

```json
{
  "PrototypeID": "silver-coin-001",
  "PrototypeName": "Silver Coin",
  "PrototypeNamePlural": "Silver Coins",
  "Description": "A gleaming silver coin worth twelve bronze.",
  "Mass": 0.02,
  "Value": 120,
  "Stackable": true,
  "Quantity": 1,
  "Wearable": false,
  "WornOn": [],
  "Verbs": {
    "Use": "You examine the silver coin.",
    "Examine": "A polished silver coin bearing the royal crest."
  },
  "Overrides": {},
  "TraitMods": {},
  "Container": false,
  "Contents": [],
  "IsWorn": false,
  "CanPickUp": true,
  "Metadata": {
    "CurrencyType": "silver",
    "Denomination": 12
  }
}
```

### Gold Coin Prototype

```json
{
  "PrototypeID": "gold-coin-001",
  "PrototypeName": "Gold Coin",
  "PrototypeNamePlural": "Gold Coins",
  "Description": "A valuable gold coin worth twenty silver.",
  "Mass": 0.05,
  "Value": 2400,
  "Stackable": true,
  "Quantity": 1,
  "Wearable": false,
  "WornOn": [],
  "Verbs": {
    "Use": "You examine the gold coin.",
    "Examine": "A heavy gold coin inscribed with ancient runes."
  },
  "Overrides": {},
  "TraitMods": {},
  "Container": false,
  "Contents": [],
  "IsWorn": false,
  "CanPickUp": true,
  "Metadata": {
    "CurrencyType": "gold",
    "Denomination": 240
  }
}
```

## Migration Notes

### Current Implementation Status

- Database: `Resources` field exists but empty `{}`
- Story rewards: Currently text strings (needs conversion to value)
- Coin prototypes: Not yet added to test_prototypes.json
- Stacking system: Not yet implemented
- API: No currency endpoints yet implemented
- Display: Frontend ready to show currency when provided

### Migration Steps

1. Add coin prototypes to `data/test_prototypes.json`
2. Update story files: Convert RewardTiers to value-based rewards
3. Implement stacking system in `eidolon/items.py`
4. Implement currency utilities in `eidolon/currency.py`
5. Update `apply_story_rewards()` to create coin items and update Value
6. Add currency display to character API responses
7. Implement store endpoints with value-based pricing
8. Update inventory management to handle stacks

## Testing Guidelines

### Unit Tests Required

- FU to display currency conversion
- Display currency to FU conversion
- Transaction processing with exact amounts
- Transaction processing with change making
- Overflow handling (max currency limits)

### Integration Tests Required

- Story completion awards correct FU
- Store purchases deduct correct FU
- API returns proper display format
- Currency persists across sessions

## Future Enhancements

### Phase 2 Features

- Currency exchange NPCs (with exchange fees)
- Bank system for currency storage
- Interest/investment mechanics
- Currency-specific purchases (some items only accept gold)

### Phase 3 Features

- Regional currencies with exchange rates
- Dynamic economy based on player actions
- Market speculation mechanics
- Crafting economy with material values

## Design Principles

1. **Transparency**: Players see familiar G/S/B denominations
2. **Flexibility**: FU system allows economic tuning without player disruption
3. **Consistency**: All economic calculations use FU internally
4. **Scalability**: System supports future economic complexity
5. **Simplicity**: Player-facing system remains straightforward

## Technical Constraints

- FU values stored as integers (no fractional units)
- Maximum FU per character: 2,147,483,647 (32-bit signed int)
- Minimum transaction: 1 FU
- Currency display always rounds down (no fractional coins)

## Security Considerations

- All currency modifications through controlled Lambda functions
- No client-side currency calculations
- Transaction logging for audit trail
- Atomic operations for currency transfers
- Rate limiting on currency-generating actions

---

## Implementation Checklist

### Phase 1: Core Currency System
- [ ] Add coin prototypes to `data/test_prototypes.json`
- [ ] Add stack management functions to `eidolon/items.py`
- [ ] Add `create_coins_from_value()` helper to `eidolon/items.py`

### Phase 2: Story Rewards
- [ ] Update story JSON files with value-based rewards
- [ ] Implement `apply_story_rewards()` to create coin items
- [ ] Update character Value tracker on reward
- [ ] Test coin creation from story rewards

### Phase 3: Inventory Management
- [ ] Update `eidolon/items.py` with stacking logic
- [ ] Implement stack merging on item pickup
- [ ] Handle stack overflow (create new stacks)
- [ ] Update inventory display for stacked items

### Phase 4: Transactions
- [ ] Implement coin payment calculation
- [ ] Handle change-making logic
- [ ] Create store pricing functions
- [ ] Implement purchase transaction logic

### Phase 5: API Integration
- [ ] Add currency display to character API responses
- [ ] Update inventory endpoints for stack display
- [ ] Create coin exchange endpoints
- [ ] Document all currency API endpoints

### Phase 6: Testing & Polish
- [ ] Write unit tests for stacking system
- [ ] Write unit tests for currency conversion
- [ ] Integration tests for transactions
- [ ] Create admin tools for currency management

---

## References

- [Story Rewards Documentation](incremental-implementation.md)
- [Database Schema](schema.md)
- [API Documentation](incremental-api.md)
- [Project Plan Task 3-4](project-plan-01.md)