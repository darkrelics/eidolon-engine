# Health and Damage System

## Overview

The health and damage system in Eidolon Engine implements a sophisticated wound tracking mechanism that goes beyond simple hit point deduction. Rather than treating health as a single numerical value that decreases with damage, the system models individual wounds that heal over time, creating a more realistic and strategic damage model.

## Core Concepts

### Health System Components

The health system consists of three key components:

1. **MaxHealth**: An integer representing the maximum number of health levels a character can have
2. **Health**: The current number of healthy (undamaged) levels available, calculated dynamically
3. **Wounds**: A list of wound maps, where each wound represents one point of damage

### Health Calculation

Current health represents the number of undamaged health levels and is calculated as:

```
Health = MaxHealth - len(wounds)
```

This calculation is performed on-demand through the `GetHealth()` method rather than being stored in the database. Since each wound in the wounds list represents exactly one point of damage, the length of the wounds list directly indicates how many health levels are damaged.

### Wound System

The wounds field is a list of maps where each map represents a single point of damage. Each wound map contains:
- **DamageType**: The category of damage (bashing, lethal, or aggravated)
- **HealAt**: An ISO 8601 timestamp indicating when the wound will naturally heal

Example wound structure:
```json
{
  "DamageType": "lethal",
  "HealAt": "2025-01-15T20:00:00Z"
}
```

This design means:
- Taking 3 points of damage creates 3 wound maps in the list
- A character with MaxHealth of 10 and 3 wounds has 7 health remaining
- When a wound's heal time expires, it's removed from the list, effectively restoring one health level

## Damage Types

The system recognizes three distinct damage types, each with different healing times and consequences:

### Bashing Damage
- **Healing Time**: 15 minutes
- **Description**: Non-lethal damage from blunt force, exhaustion, or stunning attacks
- **Special Rules**: When unconscious, new bashing damage converts to lethal damage
- **Death Condition**: Cannot directly cause death; only causes unconsciousness

### Lethal Damage
- **Healing Time**: 6 hours
- **Description**: Serious injuries from cutting weapons, gunshots, or severe trauma
- **Special Rules**: When unconscious, can replace existing bashing wounds
- **Death Condition**: Can cause death when health reaches zero

### Aggravated Damage
- **Healing Time**: 7 days
- **Description**: Catastrophic damage that resists natural healing (fire, acid, supernatural attacks)
- **Special Rules**: When unconscious, can replace existing bashing wounds
- **Death Condition**: Can cause death when health reaches zero

## Character States

Characters exist in one of four states based on their health and wound conditions:

### Standing
The normal state where characters can perform all actions. Characters remain standing as long as they have at least 1 health point.

### Unconscious
Triggered when health reaches zero with at least one bashing wound present. While unconscious:
- New bashing damage converts to lethal damage
- Lethal and aggravated damage first replace existing bashing wounds
- Character cannot perform actions
- Natural healing continues

### Dead
Occurs when health reaches zero with no bashing wounds remaining (only lethal/aggravated). Death is permanent for the character instance, though the player account retains the character record marked as deceased.

### Ghost
A special state referenced in the code constants but not implemented in the current damage system. Likely reserved for future supernatural or respawn mechanics.

## Damage Processing

### Standard Damage Application

When a character takes damage:
1. The system checks if the character is unconscious for special damage rules
2. Creates new wound maps with appropriate heal times
3. Recalculates current health
4. Notifies the player of damage taken and current health
5. Checks for state transitions (unconsciousness or death)

### Unconscious Damage Rules

The system implements sophisticated rules for unconscious characters:

1. **Bashing Damage Conversion**: New bashing damage becomes lethal when applied to an unconscious character
2. **Wound Replacement**: Lethal and aggravated damage first replace existing bashing wounds before adding new wounds
3. **Progressive Severity**: This mechanism ensures unconscious characters progress toward death rather than accumulating non-lethal injuries

## Healing Mechanics

### Natural Healing

Wounds heal automatically over time without player intervention:
- The system tracks a precise heal time for each wound
- During health calculation, expired wounds are removed
- Players receive notifications when wounds heal
- Multiple wounds can heal simultaneously if their timers expire

### Health Recalculation

The `CalculateCurrentHealth` function runs periodically to:
1. Remove wounds that have passed their heal time
2. Update the character's current health
3. Check for consciousness recovery
4. Send healing notifications to the player

### Consciousness Recovery

When an unconscious character heals enough wounds to have positive health:
- Character state automatically changes from unconscious to standing
- Player receives a consciousness recovery message
- Full actions become available again

## Strategic Implications

### Tactical Considerations

The wound system creates several tactical considerations:
- **Damage Type Matters**: Bashing damage for non-lethal takedowns vs lethal for permanent solutions
- **Time Management**: Different heal times affect long-term character effectiveness
- **Unconscious Vulnerability**: Downed characters face escalated danger from additional attacks

### Resource Management

Unlike traditional healing systems:
- No healing potions or spells are required for basic recovery
- Time becomes the primary healing resource
- Aggravated damage represents a serious long-term impediment

### Combat Pacing

The graduated healing times create natural combat rhythms:
- Quick recovery from brawls (15-minute bashing heals)
- Extended downtime from serious fights (6-hour lethal heals)  
- Major consequences for supernatural encounters (7-day aggravated heals)

## Implementation Details

### Thread Safety

All damage and healing operations use mutex locks to ensure thread-safe access to character wound data, critical for a multi-user environment where multiple damage sources might affect a character simultaneously.

### Notification System

The system sends formatted messages through the character's command output channel:
- Damage notifications include damage type and current health
- State changes produce color-coded messages (yellow for unconscious, red for death)
- Healing notifications report wounds healed and updated health

### Death Handling

When a character dies:
1. Character state changes to dead
2. Player receives death notification
3. Player account updates to mark the character as deceased
4. Character remains in the game world but cannot perform actions

## Future Considerations

The current implementation provides hooks for several potential enhancements:
- **Ghost State**: Currently defined but unused, could enable post-death gameplay
- **Healing Modifiers**: Character abilities or items could modify heal times
- **Damage Resistance**: System could easily incorporate damage reduction mechanics
- **Wound Penalties**: Specific wound types could impose action penalties while active

The health and damage system demonstrates a philosophy of meaningful consequences and natural recovery, where time and tactical decisions matter more than resource consumption. This creates a more immersive and strategic combat experience that fits well within a persistent multi-user dungeon environment.