# Game Mechanics and Experience System

## Overview

This document describes the complete game mechanics and experience system specification for the Eidolon Engine. This specification applies to both MUD and Incremental game modes.

**Implementation:**

- MUD Server (Go): server/experience.go - ResolveOpposedCheckWithXP, ResolveStaticCheckWithXP
- Incremental (Python): eidolon/mechanics.py - resolve_opposed_check_with_xp, calculate_skill_increase

**Code Examples:** This document uses Go syntax from MUD server. Python implementation follows same mathematical formulas and constants.

The system provides two primary resolution methods (opposed checks and static checks) integrated with a continuous skill progression system that rewards character development through actual use rather than abstract point allocation.

## Core Components

### The Resolution Functions

The system provides two types of checks:

#### Opposed Checks

Resolves conflicts between an aggressor and defender using their numeric ratings:

```go
outcome := ResolveOpposedCheck(aggressor, defender)
if outcome.Success {
    // Aggressor wins
} else {
    // Defender wins
}
```

#### Static Checks

Resolves checks against a fixed difficulty:

```go
// Calculate effective score (e.g., skill + attribute)
effectiveScore := int(character.GetSkill("stealth") + character.GetAttribute("dexterity"))
outcome := ResolveStaticCheck(effectiveScore, difficulty)
if outcome.Success {
    // Character succeeds against the difficulty
} else {
    // Character fails
}
```

The `Outcome` struct provides:

- `Success`: Boolean indicating if the check succeeded
- `Sigma`: The raw result value (positive = success, negative = failure)

### Mathematical Model

The system uses a normal distribution with two key transformations:

1. **Mean Shift (μ)**: Based on the rating difference (Δ = aggressor - defender)

   - μ = kShift × Δ
   - Shifts the probability curve to favor the higher-rated participant

2. **Variance Scaling (σ)**: Dynamically adjusts based on rating gap
   - σ = 1 + kVar × tanh(Δ/10)
   - Widens or narrows the outcome distribution

## Integration with Experience System

The mechanics system integrates with the experience system to provide character progression. Mathematical formulas, experience calculations, and implementation constants are documented in the sections below.

**Implementation Files:**

- Go (MUD): server/experience.go
- Python (Incremental): eidolon/mechanics.py
- Constants: eidolon/constants.py (shared values)

## Core Process Flow

### Opposed Check Process

1. **Input Validation**: Verify both participants have valid ratings
2. **Difference Calculation**: Compute rating gap between participants
3. **Probability Distribution**: Apply mathematical model to determine outcome likelihood
4. **Random Resolution**: Generate outcome using controlled randomness
5. **Result Return**: Provide success/failure with outcome strength (sigma value)
6. **Experience Award**: Automatically grant XP based on challenge difficulty (if using XP variant)

### Static Check Process

1. **Input Validation**: Verify character has valid effective score
2. **Challenge Assessment**: Compare character capability to fixed difficulty
3. **Probability Calculation**: Determine success likelihood based on difference
4. **Random Resolution**: Generate outcome with appropriate variance
5. **Result Return**: Provide success/failure with performance measure
6. **Experience Award**: Grant XP based on challenge attempted (if using XP variant)

## Usage Contexts

### Combat Resolution

- **Process**: Character attacks use opposed checks (attacker skill vs defender skill)
- **Inputs**: Character combat skills and relevant attributes
- **Output**: Hit/miss determination with damage scaling based on sigma value

### Skill Challenges

- **Process**: Character abilities tested against environmental difficulties
- **Inputs**: Character skill + attribute vs static difficulty number
- **Output**: Success/failure with quality measure for narrative outcomes

### Social Interactions

- **Process**: Character social skills vs target resistance or static social challenge
- **Inputs**: Social skills (persuasion, deception) + relevant attributes
- **Output**: Interaction success with degree for determining NPC response

### Stealth and Detection

- **Process**: Hiding character stealth vs observer investigation abilities
- **Inputs**: Stealth skill + attribute vs investigation skill + attribute
- **Output**: Detection success/failure determining visibility state

## System Properties

- **Balanced Competition**: Higher skills win more often but upsets remain possible
- **Predictable Randomness**: Outcomes vary within controlled ranges
- **Experience Integration**: XP awarded based on actual challenge difficulty
- **Failure Learning**: Failed attempts still provide character progression

## Experience System Integration

### Philosophy

The experience system implements continuous skill progression designed around these core principles:

1. **Learn by Doing** - Characters improve skills and attributes through actual use, not by spending abstract points
2. **Meaningful Opposition** - Challenging opponents provide more growth than trivial ones
3. **Smooth Progression** - Skills advance continuously (0.00 to 10.00) rather than in discrete levels
4. **Natural Soft Cap** - Exponential XP requirements create a practical limit around 6.0 without hard barriers
5. **Failure Teaches** - Failed attempts against equal or harder challenges grant experience (at 50% rate), encouraging players to take risks against appropriate difficulties

### Core Mechanics

- **No XP Pools** - Skills and attributes ARE the progression. They increase directly through use.
- **Continuous Values** - All skills and attributes are 64-bit floats ranging from 0.00 to 10.00
- **Contested Actions** - Experience is awarded when characters engage in opposed checks
- **Static Challenges** - Experience is awarded when characters face environmental challenges
- **Automatic Awards** - The system automatically grants experience after any mechanics resolution

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

The variance modifier determines XP scaling based on the relationship between effective score (S) and difficulty (D):

```
ratio = min(S, D) / max(S, D)
xp_modifier = ratio^2
```

**XP Scaling Examples:**

- **Even match (S=D)**: ratio = 1.0 → 100% XP (maximum reward)
- **Character stronger (S > D)**:
  - S=10, D=5: ratio = 0.5 → 25% XP (reduced reward for easy challenge)
  - S=10, D=2: ratio = 0.2 → 4% XP (minimal reward for trivial challenge)
- **Challenge harder (D > S)**:
  - S=5, D=10: ratio = 0.5 → 25% XP (reduced from max, but still learning)
  - S=2, D=10: ratio = 0.2 → 4% XP (very hard challenges give less XP)

The quadratic scaling ensures XP rewards drop dramatically when challenges don't match character capability.

### Tuning Parameters

#### **Experience System Parameters**

Located in `eidolon/constants.py`:

- `BASE_XP = 0.25` - Base experience per action
- `FAILURE_XP_PENALTY = 0.5` - Failed actions give 50% XP (when applicable, see below)
- `ATTRIBUTE_XP_RATIO = 0.1` - Attributes gain 10% of skill XP
- `maxScore = 10.0` - Hard cap on progression

#### **Failure Penalty Rules**

The failure penalty varies based on challenge difficulty relative to character capability:

- **When S > D** (character stronger than challenge): **0% XP on failure**

  - Rationale: Failing an easy task provides no learning opportunity
  - Example: S=8, D=5, failed → 0 XP

- **When D ≥ S** (challenge equal or harder): **50% XP on failure**
  - Rationale: Attempting difficult challenges teaches even in failure
  - Example: S=5, D=8, failed → 50% of calculated XP
  - Example: S=5, D=5, failed → 50% of calculated XP

This prevents XP farming by repeatedly failing challenges below skill level while rewarding genuine attempts at growth.

#### **Mechanics System Parameters**

Located in `eidolon/constants.py`:

- `OPPOSED_SHIFT = 0.20` (kShift) - Controls **who wins** by tilting probability distribution
- `OPPOSED_VARIANCE = 0.35` (kVar) - Controls **by how much** winners win through variance scaling
- `OPPOSED_MIN_SIGMA = 0.25` (minSig) - Minimum variance floor to prevent degenerate cases

#### **Tuning Effects**

| Parameter            | Increase Effect        | Decrease Effect          |
| -------------------- | ---------------------- | ------------------------ |
| **OPPOSED_SHIFT**    | Skill dominates more   | More upsets possible     |
| **OPPOSED_VARIANCE** | Bigger victory margins | Tighter, closer outcomes |
| **BASE_XP**          | Faster progression     | Slower progression       |

**Tuning Guidelines:**

- **Too random?** Increase OPPOSED_SHIFT
- **Too predictable?** Decrease OPPOSED_SHIFT
- **Want bigger swings?** Increase OPPOSED_VARIANCE
- **Want tighter games?** Decrease OPPOSED_VARIANCE

### Skill Progression Timeline

| Score Range | Description | Typical Time to Achieve  |
| ----------- | ----------- | ------------------------ |
| 0.0 - 1.0   | Novice      | Hours of play            |
| 1.0 - 3.0   | Competent   | Days to weeks            |
| 3.0 - 5.0   | Expert      | Weeks to months          |
| 5.0 - 6.0   | Master      | Months of dedicated play |
| 6.0 - 8.0   | Legendary   | Years of play            |
| 8.0 - 10.0  | Mythical    | Theoretical maximum      |
