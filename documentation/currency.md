# Currency System Documentation

**Created**: 2025-10-19
**Status**: Design Document
**Version**: 2.0

## Overview

The Multi-User Dungeon economy uses physical coin items as the single source of truth for currency. Coins are stackable items that can be dropped, traded, or stolen; a character's balance is the sum of their coins' Fundamental Unit (FU) value, computed on demand. There is no separate scalar balance field.

## Implemented Model

This is the model implemented in `eidolon/currency.py`:

- **Coins are ordinary stackable items with unbounded stacks.** A coin prototype carries `Metadata.Denomination` and `MaxStack: -1` (a MaxStack of zero or less means the stack is unbounded), and its worth is the prototype's `Value` in FU (Bronze 10, Silver 120, Gold 2,400). Coins are minimal stackable records `{ItemID, PrototypeID, Quantity, OwnerID}` per the [item system](item-system.md).
- **Balance is derived, not stored.** `wallet_total(character)` sums the FU value of the coin stacks at the character's top-level Contents (the purse). There is no `Resources.Value` scalar; the earlier hybrid design that tracked both is superseded.
- **Currency is granted through the standard item-reward path.** `calculate_story_rewards` converts a reward tier's `currency` amount (FU) into coin item entries via `coin_rewards_for_amount` (greedy split, largest denomination first), and `apply_story_rewards` merges them into the character's existing coin stacks like any other stackable item. There is no separate currency-granting transaction.
- **Spending canonicalizes.** A purchase replaces the coin stacks with the minimal canonical set for the post-payment balance, so coin ItemIDs change when coins are spent. Between spends a wallet may hold a non-canonical mix (for example, earned bronze alongside a gold coin); the next purchase normalizes it.
- **Purchases pay with coins atomically.** `purchase_item` spends coins via `plan_coin_spend`, and the goods records, coin changes, and the character Contents update all commit in a single transaction.

The remainder of this document is the broader design rationale. Where it shows a `Resources.Value` scalar, exact change-making, or UUIDv7 stack merging, treat the canonicalized coin model above as authoritative.

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

| Coin Type   | PrototypeID     | Value per Coin | Weight  |
| ----------- | --------------- | -------------- | ------- |
| Bronze Coin | bronze-coin-001 | 10 FU          | 0.01 kg |
| Silver Coin | silver-coin-001 | 120 FU         | 0.02 kg |
| Gold Coin   | gold-coin-001   | 2,400 FU       | 0.05 kg |

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
  "Quantity": 247, // Stack of 247 identical bronze coins
  "OwnerID": "character-uuid"
}
```

**Non-Stackable Item** (weapon with modifications):

```json
{
  "ItemID": "unique-sword-uuid",
  "PrototypeID": "long-sword-001",
  "OwnerID": "character-uuid",
  "Enchantment": "flaming", // Custom property
  "Condition": 0.85, // Custom property
  "CreatedBy": "master-smith" // Custom property
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

Coin stacks are unbounded: the coin prototypes set `MaxStack: -1`, and a
MaxStack of zero or less means no limit, so a stack can grow to any size
(limited only by integer representation). Stack merging is described in the
[item system](item-system.md#stack-merging); coins use the same shared helpers
as every other stackable item.

## Implementation Structure

### Database Storage

Characters have both a Value tracker and physical coin items:

```json
{
  "CharacterID": "uuid",
  "Resources": {
    "Value": 3650 // Total wealth in FU for quick calculations
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

When awarding currency, create coin items like any other stackable items
(implemented as `coin_rewards_for_amount` in `eidolon/currency.py`):

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

Story rewards define value and items to award. This is the live mechanism:
`calculate_story_rewards` reads the outcome tier's `currency` amount and
converts it into coin item entries (greedy split, largest denomination first),
which then merge into the character's coin stacks through the same path as the
tier's other item rewards. Amounts that are not a multiple of the smallest coin
(10 FU) are floored, and the dropped remainder is logged.

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

| Outcome     | Value Range | Coins Created       | Rationale             |
| ----------- | ----------- | ------------------- | --------------------- |
| Death       | 0           | None                | No reward for failure |
| Failure     | 50-100      | 5-10 Bronze         | Consolation prize     |
| Minimal     | 150-250     | 15-25 Bronze        | Basic success         |
| Normal      | 300-500     | 2-4 Silver + Bronze | Standard reward       |
| Exceptional | 750-1000    | 6-8 Silver + Bronze | Excellent performance |

### Story-Specific Modifiers

Different story types warrant different reward scales:

- **Low Risk** (Foraging): 0.8× base rewards
- **Medium Risk** (Puzzles): 1.0× base rewards
- **High Risk** (Combat): 1.5× base rewards

### Coin Generation Example

When a player completes a story with 450 value reward:

1. System calculates: 450 ÷ 120 = 3 silver, 90 remainder
2. Remainder: 90 ÷ 10 = 9 bronze
3. Grants coin items, merging into the character's existing silver and bronze
   stacks (or minting new stacks when none exist)

## Item Valuation

All items have a fundamental value for economic consistency:

### Value Categories

| Category  | FU Range  | Example Items               |
| --------- | --------- | --------------------------- |
| Trivial   | 1-50      | Berries, common herbs       |
| Common    | 51-200    | Basic tools, simple potions |
| Uncommon  | 201-1000  | Quality weapons, armor      |
| Rare      | 1001-5000 | Magic items, rare materials |
| Legendary | 5001+     | Unique artifacts            |

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
    "gold": 2,
    "silver": 5,
    "bronze": 8
  },
  "cost": {
    "gold": 0,
    "silver": 12,
    "bronze": 0
  },
  "new_balance": {
    "gold": 1,
    "silver": 13,
    "bronze": 8
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

## Implementation Status

The core currency system is implemented end to end:

- Coin prototypes exist in `data/test_prototypes.json` with `MaxStack: -1`
  (unbounded stacks)
- Stacking and merge helpers live in `eidolon/items.py`
  (`stack_merge_quantity`, `distribute_into_stacks`, `load_top_level_stacks`)
- Currency utilities live in `eidolon/currency.py` (wallet derivation, greedy
  coin split, reward conversion, spend planning)
- Story rewards grant currency: `calculate_story_rewards` converts the tier's
  `currency` FU into coin items applied by `apply_story_rewards`
- Store purchases spend coins atomically (`eidolon/store.py`)

Not yet implemented: a dedicated currency display in character API responses
(clients derive the balance from the coin stacks), buy-back, exchange NPCs, and
the other Phase 2+ features below.

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

## References

- [Story Rewards Documentation](incremental-implementation.md)
- [Database Schema](schema.md)
- [API Documentation](incremental-api.md)
- [Project Plan Task 3-4](project-plan-01.md)
