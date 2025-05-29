# Game Mechanics System

## Overview

The mechanics module provides a system for opposed checks in the game. It uses a sophisticated probability model that balances skill differences with controlled randomness, creating engaging gameplay where outcomes are neither too predictable nor too chaotic.

## Core Components

### The Resolution Function

The system resolves conflicts between an aggressor and defender using their numeric ratings:

```go
outcome := ResolveOpposedCheck(aggressor, defender)
if outcome.Success {
    // Aggressor wins
} else {
    // Defender wins
}
```

The `Outcome` struct provides:
- `Success`: Boolean indicating if the aggressor won
- `Sigma`: The raw result value (positive = success, negative = failure)

### Mathematical Model

The system uses a normal distribution with two key transformations:

1. **Mean Shift (μ)**: Based on the rating difference (Δ = aggressor - defender)
   - μ = kShift × Δ
   - Shifts the probability curve to favor the higher-rated participant

2. **Variance Scaling (σ)**: Dynamically adjusts based on rating gap
   - σ = 1 + kVar × tanh(Δ/10)
   - Widens or narrows the outcome distribution

## Tuning Parameters

The system exposes two constants that control game feel:

### kShift (Default: 0.20) - The Gravity Well

kShift controls **who wins** by tilting the probability distribution.

| kShift Value | Effect | Game Feel |
|--------------|--------|-----------|
| 0.10 | Weak bias | High upset potential, luck matters more |
| 0.20 | Moderate bias | Balanced skill vs luck |
| 0.30 | Strong bias | Skill dominates, upsets are rare |

**Tuning Guide:**
- Increase if experts lose to novices too often
- Decrease if matches feel too predictable
- Each 0.05 change shifts win rates by ~3-5% per rating point

### kVar (Default: 0.35) - The Springiness

kVar controls **by how much** winners win through variance scaling.

| kVar Value | Effect | Game Feel |
|------------|--------|-----------|
| 0.20 | Tight outcomes | Close margins, consistent results |
| 0.35 | Moderate swing | Balanced drama vs predictability |
| 0.50 | High variance | Spectacular victories and crushing defeats |

**Tuning Guide:**
- Increase for more cinematic, swingy results
- Decrease for tighter, more chess-like play
- Does NOT affect overall win rates, only margin of victory

## Practical Examples

### Win Probability by Rating Difference

| Rating Difference | Win Probability | Description |
|-------------------|-----------------|-------------|
| 0 | 50% | Fair contest |
| 2 | 65% | Slight advantage |
| 5 | 79% | Clear favorite |
| 10 | 94% | Dominant position |
| 15 | 99% | Near certain victory |

### Outcome Ranges (Sigma Values)

For a contest between equals (Δ = 0):
- 68% of outcomes fall within [-1.0, +1.0]
- 95% of outcomes fall within [-2.0, +2.0]
- Extreme results (|σ| > 3) occur ~0.3% of the time

## Integration Guide

### Basic Usage

```go
// Simple combat resolution
attackerSkill := 15
defenderSkill := 12

outcome := ResolveOpposedCheck(attackerSkill, defenderSkill)
if outcome.Success {
    // Apply damage based on outcome.Sigma
    damage := baseDamage + int(outcome.Sigma * damageScale)
} else {
    // Defender blocks/dodges
}
```

### Advanced Usage

```go
// Use Sigma for degrees of success
outcome := ResolveOpposedCheck(thief.Stealth, guard.Perception)
switch {
case outcome.Sigma > 2.0:
    // Critical success - completely undetected
case outcome.Sigma > 0:
    // Success - sneaks past
case outcome.Sigma > -2.0:
    // Failure - spotted but can flee
default:
    // Critical failure - caught red-handed
}
```

## Performance Considerations

- Uses cryptographically secure random numbers (slower but truly random)
- Each resolution requires ~2-3 microseconds on modern hardware
- No caching or state - each check is independent
- Thread-safe - can be called concurrently

## Security Notes

The system uses `crypto/rand` for true randomness:
- Prevents prediction or manipulation of outcomes
- Suitable for competitive or high-stakes gameplay
- Cannot be seeded for replay/debugging (use test framework for deterministic testing)

## Tuning Workflow

1. **Start with defaults** (kShift=0.20, kVar=0.35)
2. **Run playtests** focusing on:
   - Do skill differences feel meaningful?
   - Are upsets exciting but not frustrating?
   - Do victories feel earned?
3. **Adjust one parameter at a time**:
   - Too random? Increase kShift
   - Too predictable? Decrease kShift
   - Want bigger swings? Increase kVar
   - Want tighter games? Decrease kVar
4. **Test edge cases**:
   - Novice vs Expert (large Δ)
   - Evenly matched opponents (Δ ≈ 0)
   - Chain multiple checks

## Common Patterns

### Best of N

```go
// First to 2 wins
wins := 0
for rounds := 0; rounds < 5 && wins < 2; rounds++ {
    if ResolveOpposedCheck(a, d).Success {
        wins++
    }
}
success := wins >= 2
```

### Advantage/Disadvantage

```go
// Roll twice, take better/worse
outcome1 := ResolveOpposedCheck(a, d)
outcome2 := ResolveOpposedCheck(a, d)
bestOutcome := outcome1
if outcome2.Sigma > outcome1.Sigma {
    bestOutcome = outcome2
}
```

## FAQ

**Q: Why use crypto/rand instead of math/rand?**
A: Prevents any possibility of prediction or manipulation, essential for fair multiplayer games.

**Q: Can I save/replay random sequences?**
A: No, but the test framework supports deterministic testing with seeded random numbers.

**Q: How do I handle ties?**
A: True ties (Sigma = 0.0) are astronomically rare. The system always determines a winner.

**Q: What about more than two participants?**
A: Run pairwise checks or implement a tournament structure. The system handles only binary oppositions.