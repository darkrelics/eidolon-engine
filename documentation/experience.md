# Experience System Documentation

## Philosophy

The Eidolon Engine implements a continuous skill progression system designed around these core principles:

1. **Learn by Doing** - Characters improve skills and attributes through actual use, not by spending abstract points
2. **Meaningful Opposition** - Challenging opponents provide more growth than trivial ones
3. **Smooth Progression** - Skills advance continuously (0.00 to 10.00) rather than in discrete levels
4. **Natural Soft Cap** - Exponential XP requirements create a practical limit around 6.0 without hard barriers
5. **Failure Teaches** - Even failed attempts grant experience (at 50% rate), encouraging players to take risks

## System Overview

### Core Mechanics

- **No XP Pools** - Skills and attributes ARE the progression. They increase directly through use.
- **Continuous Values** - All skills and attributes are 64-bit floats ranging from 0.00 to 10.00
- **Contested Actions** - Experience is awarded when characters engage in opposed checks
- **Static Challenges** - Experience is awarded when characters face environmental challenges
- **Automatic Awards** - The system automatically grants experience after any `ResolveOpposedCheck` or `ResolveStaticCheckWithXP`

### Mathematical Model

#### XP Requirement Formula

```
XP_required(score) = 10 * 3.5^score
```

This creates an exponential curve where:

- 0→1: ~80 actions at even odds
- 5→6: ~42,000 actions at even odds
- 9→10: ~4.4 million actions at even odds

#### Variance Modifier

```
ratio = min(E_att, E_def) / max(E_att, E_def)
xp_modifier = ratio^2
```

This ensures:

- Even match (10 vs 10): 100% XP
- Moderate advantage (10 vs 5): 25% XP for stronger, 400% for weaker
- Extreme mismatch (10 vs 2): 4% XP for stronger, 2500% for weaker

#### Base Constants

- `BASE_XP = 0.25` - Base experience per action
- `FAILURE_PENALTY = 0.5` - Failed actions give 50% XP
- `ATTRIBUTE_XP_RATIO = 0.1` - Attributes gain 10% of skill XP

## Developer Guide

### Integration Points

#### Using ResolveOpposedCheckWithXP

For any contested action that should award experience:

```go
outcome := ResolveOpposedCheckWithXP(
    attacker,           // *Character - aggressor
    defender,           // *Character - defender
    "swordsmanship",    // aggressor's skill
    "strength",         // aggressor's attribute
    "defense",          // defender's skill
    "agility",          // defender's attribute
)

if outcome.Success {
    // Attacker succeeded
} else {
    // Defender succeeded
}
```

#### Using ResolveStaticCheckWithXP

For environmental challenges that should award experience:

```go
// Hiding attempt against difficulty 4
outcome := ResolveStaticCheckWithXP(
    character,          // *Character attempting the check
    "stealth",         // skill being tested
    "agility",         // attribute being tested
    4,                 // difficulty level
)

if outcome.Success {
    // Character succeeded at the task
} else {
    // Character failed the task
}
```

The experience award is calculated based on the character's effective score versus the difficulty:

- Challenging tasks (where character skill ≈ difficulty) give full XP
- Trivial tasks (skill >> difficulty) give minimal XP
- Impossible tasks (skill << difficulty) give bonus XP even on failure

#### Manual Experience Awards

For non-contested actions:

```go
// Award skill experience directly
character.AwardSkillXP("crafting", 0.1)

// Award attribute experience directly
character.AwardAttributeXP("intelligence", 0.01)
```

### Character Methods

- `GetSkill(name string) float64` - Safely retrieve skill value (0 if not found)
- `GetAttribute(name string) float64` - Safely retrieve attribute value (0 if not found)
- `AwardSkillXP(name string, amount float64)` - Award XP to a skill
- `AwardAttributeXP(name string, amount float64)` - Award XP to an attribute

### Experience Context

When implementing new contested mechanics:

```go
context := ExperienceContext{
    AggressorSkill:     "persuasion",
    AggressorAttr:      "charisma",
    DefenderSkill:      "willpower",
    DefenderAttr:       "wisdom",
    AggressorSuccess:   true,
    DefenderSuccess:    false,
    AggressorEffective: 8,  // skill + attribute
    DefenderEffective:  5,   // skill + attribute
}

AwardExperience(aggressor, defender, context)
```

## Game Operator Guide

### Skill Progression Expectations

| Score Range | Description | Typical Time to Achieve  |
| ----------- | ----------- | ------------------------ |
| 0.0 - 1.0   | Novice      | Hours of play            |
| 1.0 - 3.0   | Competent   | Days to weeks            |
| 3.0 - 5.0   | Expert      | Weeks to months          |
| 5.0 - 6.0   | Master      | Months of dedicated play |
| 6.0 - 8.0   | Legendary   | Years of play            |
| 8.0 - 10.0  | Mythical    | Theoretical maximum      |

### Tuning Parameters

Located in `experience.go`:

- `baseXP = 0.25` - Decrease for slower progression
- `varianceExponent = 2.0` - Increase to make mismatches less rewarding
- `xpProgressionRatio = 3.5` - Increase for steeper exponential curve
- `attributeXPRatio = 0.1` - Adjust attribute vs skill progression rate
- `failurePenalty = 0.5` - Reduce to make failure less educational
- `maxScore = 10.0` - Hard cap on progression

### Monitoring Tools

#### Player Commands

- `info` - Shows skills/attributes as integers
- `skill` - Shows precise skill values (##.##)

#### Progression Metrics

The continuous system makes it easy to track:

- Average skill levels across the player base
- Progression velocity for different skills
- Time to reach various milestones

### Balance Considerations

1. **Skill Availability** - Ensure all skills have sufficient opportunities for contested use
2. **Attribute Coverage** - Each attribute should support multiple skills
3. **Opposition Variety** - Provide opponents across the full spectrum of challenge
4. **Failure Recovery** - Failed actions still progress character, preventing frustration

### Common Scenarios

#### New Player Experience

- Start with attributes/skills between 1.0-3.0 (defined by archetype)
- Early progression is rapid and rewarding
- Can reach competence (3.0) in core skills within days

#### Mid-Game Plateau

- Around score 5.0-6.0, progression naturally slows
- Players must seek greater challenges for meaningful growth
- Encourages exploration of different skills rather than grinding

#### End-Game Mastery

- Scores above 6.0 represent true dedication
- Months or years of play required
- Prestige comes from the rarity of high scores

#### Example: Hide Mechanism

The hide system demonstrates both static and opposed checks working together:

1. **Initial Hide Attempt** - Static check (Stealth + Agility vs difficulty 4)
   - Success: Character becomes hidden, gains XP based on skill vs difficulty
   - Failure: Character remains visible, gains 50% XP

2. **Detection Checks** - Opposed checks (Observer's Investigation + Perception vs Hidden's Stealth + Agility)
   - Each observer makes a check, both parties gain XP
   - Success: Observer detects the hidden character
   - Failure: Character remains hidden from that observer

3. **Continuous Learning** - All participants improve their skills through the interaction

## Implementation Notes

### Thread Safety

All experience operations are mutex-protected for safe concurrent access.

### Persistence

Skills and attributes are automatically saved with character data - no separate experience tracking needed.

### Floating Point Precision

The system uses 64-bit floats, providing sufficient precision for millions of increments without drift.

### Performance

Experience calculations are lightweight (a few multiplications and one power operation) and suitable for real-time combat.
