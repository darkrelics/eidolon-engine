# Stealth System Documentation

## Overview

The stealth system allows characters to hide from observation and move undetected through the game world. It integrates with the experience system to provide skill progression and uses the mechanics system for contested checks.

## Core Mechanics

### Hide Command

- **Skill Check**: Stealth + Agility vs difficulty 4
- **Action Time**: 3 seconds
- **Rate Limiting**: 10-second cooldown between attempts
- **Detection**: All observers immediately roll Perception + Investigation vs Stealth + Agility

### Sneak Command

- **Prerequisite**: Character must be hidden
- **Skill Check**: Stealth + Agility vs difficulty 4 for movement
- **Action Time**: 5 seconds
- **Detection**: Upon entering new room, all observers roll detection checks

### Search Command

- **Skill Check**: Perception + Investigation vs each hidden character's Stealth + Agility
- **Action Time**: 3 seconds
- **Limitation**: Finds only one hidden character per search attempt

### Point Command

- **Prerequisite**: Must first succeed at detection check
- **Effect**: Instantly reveals the targeted hidden character
- **No Action Time**: Instantaneous reveal

## State Management

### Hidden State

- **Storage**: Persisted in database as boolean field
- **Scope**: Character remains hidden across room changes until revealed
- **Reset**: Does not reset on disconnect/reconnect

### Rate Limiting

- **Storage**: Session-only (not persisted)
- **Purpose**: Prevents hide command spam
- **Reset**: Fresh cooldown on each connection

## Integration Points

### Experience System

- All hide, sneak, search, and detection attempts award experience
- Uses `ResolveStaticCheckWithXP` for environmental challenges
- Uses `ResolveOpposedCheckWithXP` for character vs character detection

### Visibility System

- Room descriptions filter hidden characters
- Look command respects visibility
- WHO command shows all characters (out-of-character information)

### Action Restrictions

- Movement (except sneak) reveals hidden characters
- Item interactions reveal hidden characters
- Speaking while hidden shows as "a voice" without revealing location

## Constants

| Parameter              | Typical Value | Purpose                           |
| ---------------------- | ------------- | --------------------------------- |
| Hide base difficulty   | 4             | Base difficulty for hide attempts |
| Hide action time       | 3 seconds     | Time blocked after hide attempt   |
| Hide rate limit        | 10 seconds    | Cooldown between hide attempts    |
| Sneak action time      | 5 seconds     | Time blocked after sneak attempt  |
| Search action time     | 3 seconds     | Time blocked after search attempt |

## Future Enhancements

### Environmental Factors

- Room-based hiding difficulty modifiers
- Light level considerations
- Crowd hiding bonuses

### Combat Integration

- Hidden characters revealed when attacking
- Attack from hiding bonuses
- Stealth attack mechanics

### Advanced Detection

- Partial detection states (glimpsed, suspected)
- Time-based detection degradation
- Group detection coordination
