# Item System Documentation

**Created**: 2025-10-19
**Status**: Core Design Document
**Version**: 1.0

## Overview

The Multi-User Dungeon item system is built on a fundamental distinction between stackable and non-stackable items. This design enables both efficient inventory management for consumables/currency and rich customization for equipment.

## Core Philosophy

### The Two-Type System

Every item in the game falls into one of two categories:

1. **Stackable Items**: Immutable, fungible items that exist in quantities
2. **Non-Stackable Items**: Unique, mutable items with individual properties

This is not just an implementation detail - it's a core game design principle that affects crafting, trading, enchanting, and the entire economy.

## Stackable Items

### Definition

Items marked with `"Stackable": true` in their prototype are fungible - every instance is identical to every other instance of the same prototype.

### Characteristics

- **Immutable**: Cannot be modified after creation (except Quantity)
- **Fungible**: All items with same PrototypeID are interchangeable
- **Quantity Field**: MUST have a Quantity attribute (minimum 1)
- **No Customization**: Cannot have enchantments, conditions, or modifications
- **Efficient Storage**: Multiple items stored as single database entry

### Use Cases

- **Currency**: Bronze, silver, gold coins
- **Consumables**: Potions, food, scrolls
- **Materials**: Ore, wood, cloth, gems
- **Ammunition**: Arrows, bolts, bullets
- **Trade Goods**: Bulk commodities

### Database Schema

```json
{
  "ItemID": "stack-uuid-001",
  "PrototypeID": "bronze-coin-001",
  "Quantity": 247,
  "OwnerID": "character-uuid"
}
```

**Only these fields are valid for stackable items**:

- `ItemID`: Unique identifier for this stack
- `PrototypeID`: Reference to item prototype
- `Quantity`: Number of items in stack (1 or more)
- `OwnerID`: Character or container holding the stack
- `LocationID`: Reserved - not used by the current implementation

> Implementation note: items reference their prototype rather than copying it.
> All type properties (Name, Mass, Value, Stackable, Container, ConsumableEffects,
> TraitMods, and so on) are resolved from the prototype at read time through
> `eidolon/prototypes.py` and are not stored on the item record. Placement is
> tracked by the character-as-container `Contents` tree together with `OwnerID`,
> so the persisted stackable record is `{ItemID, PrototypeID, Quantity, OwnerID}`.

## Non-Stackable Items

### Definition

Items marked with `"Stackable": false` in their prototype are unique instances that can be individually customized.

### Characteristics

- **Mutable**: Can be modified with custom properties
- **Unique**: Each instance is distinct
- **No Quantity**: Never has a Quantity field (always implicitly 1)
- **Customizable**: Can have enchantments, conditions, history
- **Individual Storage**: Each item is a separate database entry

### Use Cases

- **Equipment**: Weapons, armor, jewelry
- **Enchanted Items**: Any item with magical properties
- **Named Items**: Legendary or unique items
- **Crafted Items**: Items with maker's mark or quality variations
- **Quest Items**: Unique story objects

### Database Schema

```json
{
  "ItemID": "sword-uuid-001",
  "PrototypeID": "long-sword-001",
  "OwnerID": "character-uuid",
  "Enchantment": "flaming",
  "Condition": 0.85,
  "CraftedBy": "master-smith",
  "NameOverride": "Flamebrand",
  "History": ["Found in Dragon's Lair", "Reforged by Elven Smith"]
}
```

**Allowed fields for non-stackable items**:

- All base fields (ItemID, PrototypeID, OwnerID)
- Any custom properties defined by game logic
- NO Quantity field

> Implementation note: the persisted non-stackable record is
> `{ItemID, PrototypeID, OwnerID}`, plus `Contents` for containers and `IsWorn`
> for wearable items. `IsWorn` is the single canonical worn-state field. As with
> stackable items, all type properties resolve from the prototype at read time.

## Item Prototypes

### Prototype Structure

All items reference a prototype that defines their base properties:

```json
{
  "PrototypeID": "item-type-001",
  "PrototypeName": "Item Name",
  "Description": "Base description",
  "Stackable": true, // CRITICAL: Determines item type
  "Value": 10, // REQUIRED: All items must have value for economy
  "Mass": 0.1, // Weight in kg
  "Wearable": false,
  "WornOn": [],
  "Container": false,
  "CanPickUp": true,
  "Metadata": {}
}
```

### Stackable Prototype Example

```json
{
  "PrototypeID": "health-potion-001",
  "PrototypeName": "Health Potion",
  "PrototypeNamePlural": "Health Potions",
  "Description": "A red potion that restores health",
  "Stackable": true,
  "Value": 50,
  "Mass": 0.2,
  "Consumable": true,
  "Effect": "heal_wounds",
  "EffectValue": 3
}
```

### Non-Stackable Prototype Example

```json
{
  "PrototypeID": "iron-sword-001",
  "PrototypeName": "Iron Sword",
  "Description": "A standard iron sword",
  "Stackable": false,
  "Value": 200,
  "Mass": 2.0,
  "Wearable": true,
  "WornOn": ["weapon"],
  "BaseDamage": 5,
  "DamageType": "slashing"
}
```

## Stack Display Names

Stackable items require both singular and plural names for proper display:

```python
def get_stack_display_name(prototype: dict, quantity: int) -> str:
    """Generate display name for a stack based on quantity."""
    if quantity == 1:
        singular = prototype.get('PrototypeName', 'item')
        article = prototype.get('Article', 'a')
        return f"{article} {singular}"
    else:
        plural = prototype.get('PrototypeNamePlural', prototype.get('PrototypeName', 'item') + 's')
        return f"{quantity} {plural}"
```

Examples:

- 1 coin: "a bronze coin"
- 2 coins: "2 bronze coins"
- 10 arrows: "10 arrows"
- 50 berries: "50 berries"
- 247 coins: "247 bronze coins"

## Stack Operations

### Stack Merging

Stacking happens when stackable items are created (store purchases and story
rewards). New quantity is merged into existing top-level stacks of the same
prototype, up to the prototype's `MaxStack`, before any new stack records are
minted. A `MaxStack` of zero or less means the stack is unbounded - everything
merges into the existing stack and overflow never splits; coins use
`MaxStack: -1`. The shared helpers `load_top_level_stacks(top_level_ids,
prototype_id)` and `stack_merge_quantity(current, add, max_stack)` in
`eidolon/items.py` find existing stacks by `PrototypeID` and decide how much
fits; merging is purely by quantity and does not depend on item-ID ordering.
Item IDs are random UUIDv4 and carry no timestamp, so there is no "older
stack" relation to rely on.

### Stack Splitting

For trading or dropping partial stacks:

```python
def split_stack(stack: dict, split_quantity: int) -> tuple:
    """
    Split a stack into two parts.
    Returns (original_reduced, new_stack).
    """
    if split_quantity >= stack.get("Quantity", 1):
        return None, stack  # Taking whole stack

    new_stack = {
        "ItemID": generate_uuid(),
        "PrototypeID": stack["PrototypeID"],
        "Quantity": split_quantity,
        "OwnerID": stack["OwnerID"]
    }

    stack["Quantity"] -= split_quantity
    return stack, new_stack
```

## Equipment

Wearable items are equipped into character slots. An item is equipped when a
slot references it and the item's `IsWorn` flag is set; the two facts are kept
in step by committing them in a single transaction.

### Slots

There are two kinds of slot:

- **Hand slots** `left_hand` and `right_hand`, stored on the character as
  `LeftHandID` and `RightHandID`. An empty hand is represented by the field
  being absent.
- **Body slots**, stored in the character's `WornSlots` map (`{slot: ItemID}`),
  keyed by the slot name (for example `armor`, `back`, `finger`, `weapon`). One
  item per slot.

A prototype's `Wearable` flag gates equipping, and its `WornOn` list enumerates
the slots an item may occupy. The equip request names the target slot, which
must appear in `WornOn`. Slot names that are not `left_hand` / `right_hand` are
body slots and live in `WornSlots`.

### Equip and Unequip

`eidolon/equipment.py` provides `equip_item` and `unequip_item`, exposed as
`POST /item/equip` and `POST /item/unequip`. Equipping validates ownership (the
item is in the character's inventory), that the prototype is wearable, that the
requested slot is permitted, and that the item is not already worn. The change
is a single `transact_write_items` over two records: the character slot
(conditional on the slot being empty) and the item's `IsWorn` flag (conditional
on it not already being worn). Either condition failing cancels the whole
transaction, so a slot and an item can never disagree about what is worn.
Unequip is the inverse, conditional on the slot still holding the item.

Starting equipment from an archetype follows the same invariant: a worn starting
item is assigned the first free, valid slot at character creation, and stays
worn only if a slot backs it.

### Effect on Combat

Combat and derived-stat calculation read the equipped set through
`compute_effective_combat_traits`, which sums each equipped item's prototype
`TraitMods` into the character's attributes and skills (a mod whose name matches
an attribute boosts that attribute; otherwise it applies to skills, where combat
reads Melee, Parry, Dodge, and the rest). The character's stored attributes and
skills are not mutated. `Overrides` has no defined stat semantics and is
reserved; it is not consumed by combat.

## Item Movement

`contents.move_item` (exposed as `POST /item/move`) relocates an item to a new
parent: another owned container, or the character root when the destination is
the character's own id. It validates that the item is in the character's tree and
not currently worn (worn items are unequipped first), that the destination is the
character or an owned container, that the move is not a no-op, and that a
container is never moved into itself or one of its descendants. The relocation is
a single transaction that removes the item from its current parent's `Contents`
and appends it to the destination's, each guarded by a conditional check, so
concurrent moves cannot duplicate or lose the item. Numeric container capacity is
not modeled yet, so containers are treated as unbounded.

## Validation Rules

### Stackable Item Validation

```python
def validate_stackable_item(item: dict, prototype: dict) -> list:
    """Validate a stackable item against rules."""
    errors = []

    if not prototype.get("Stackable"):
        errors.append("Prototype not marked as stackable")

    # Must have quantity
    if "Quantity" not in item:
        errors.append("Stackable item missing Quantity")
    elif item["Quantity"] < 1:
        errors.append("Quantity must be at least 1")

    # Check for forbidden fields
    allowed_fields = {"ItemID", "PrototypeID", "Quantity", "OwnerID", "LocationID"}
    extra_fields = set(item.keys()) - allowed_fields
    if extra_fields:
        errors.append(f"Stackable item has forbidden fields: {extra_fields}")

    return errors
```

### Non-Stackable Item Validation

```python
def validate_non_stackable_item(item: dict, prototype: dict) -> list:
    """Validate a non-stackable item against rules."""
    errors = []

    if prototype.get("Stackable"):
        errors.append("Prototype marked as stackable")

    # Must NOT have quantity
    if "Quantity" in item:
        errors.append("Non-stackable item cannot have Quantity field")

    # Must have required base fields
    required = {"ItemID", "PrototypeID", "OwnerID"}
    missing = required - set(item.keys())
    if missing:
        errors.append(f"Missing required fields: {missing}")

    return errors
```

## Migration Impact

### Database Changes Required

1. **ITEM Table Schema**:

   - Add validation to enforce Quantity for stackable items
   - Add validation to prevent Quantity on non-stackable items
   - Index on (OwnerID, PrototypeID) for stack finding

2. **PROTOTYPE Table**:
   - Add `Stackable` boolean field (required)

### API Changes Required

1. **Inventory Endpoints**:

   - Display stacks with quantities
   - Handle stack splitting in trade/drop operations
   - Merge stacks automatically on pickup

2. **Item Creation**:

   - Validate stackable/non-stackable rules
   - Auto-merge with existing stacks when creating stackable items

3. **Store/Trade**:
   - Support buying specific quantities of stackable items
   - Prevent stacking of non-stackable items in trade windows

### Code Changes Required

1. **eidolon/items.py**:

   - Implement stack merging logic
   - Implement stack splitting logic
   - Add validation functions

2. **eidolon/currency.py**:

   - Create coins as stackable items
   - Handle coin stack management

3. **Lambda Functions**:
   - Update inventory display logic
   - Update item pickup logic
   - Update trade/store logic

## Testing Requirements

### Unit Tests

- Stack merging with various quantities
- Stack overflow handling
- Stack splitting operations
- Validation of stackable items
- Validation of non-stackable items
- Coin creation and management

### Integration Tests

- Picking up stackable items
- Trading with stacks
- Store purchases of stacks
- Inventory display with mixed items
- Save/load with stacks

## Design Rationale

### Why Two Types?

**Performance**: Stackable items as single entries dramatically reduce database operations for common items like coins and materials.

**Gameplay**: Non-stackable items enable rich RPG mechanics like:

- Weapon enchantment and naming
- Item wear and repair
- Crafting with maker's marks
- Unique quest items

**Economy**: Clear distinction between:

- Fungible currency and materials (stackable)
- Unique equipment and artifacts (non-stackable)

### Why Immutable Stacks?

If stackable items could have individual properties, they couldn't stack efficiently. By making them immutable:

- Stack merging is simple
- No confusion about which properties apply
- Database queries are efficient
- Trading is straightforward

### Why No Quantity on Non-Stackable?

Non-stackable items are unique instances. Having a quantity would be meaningless and confusing. If you have three unique swords, that's three separate database entries, not one entry with quantity=3.

## Future Enhancements

### Phase 2

- Container items that can hold stacks
- Stack quick-actions (split in half, take one)
- Visual stack indicators in UI
- Bulk operations on stacks

### Phase 3

- Quality variations within stackable items (separate stacks by quality)
- Transmutation of stacks (combine materials)
- Stack-based crafting recipes
- Automatic stack organization

## References

- [Currency System](currency.md) - Coins as stackable items
- [Database Schema](schema.md) - Item table structure
- [API Documentation](incremental-api.md) - Item endpoints
- [Validation Scripts](../scripts_python/validate_story_content.py) - Item validation
