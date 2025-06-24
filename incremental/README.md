# Eidolon Engine - Incremental Game

A modern incremental RPG game built with Flutter, inspired by Progress Quest, designed to introduce players to the Eidolon Engine world and mechanics.

## Overview

This incremental game serves as a gateway to the Eidolon Engine universe, providing players with a simplified, automated RPG experience that showcases the core mechanics and lore of the main game. Players create characters that automatically progress through quests, battles, and equipment upgrades while learning about the game world.

## Key Features

- **Automated Progression**: Characters automatically perform actions, complete quests, and battle monsters
- **Modern UI**: Progress bars, animations, and visual feedback for all actions
- **Character Development**: Skills, attributes, and equipment that improve over time
- **Quest System**: Procedurally generated quests that introduce world lore
- **Equipment Tiers**: Progressively better gear with visual representation
- **Zone Progression**: Unlock new areas as character power increases
- **Shared Authentication**: Uses the same Cognito authentication as the main game
- **Character Export**: Eventually allow exporting characters to the main game

## Technical Architecture

### Frontend (Flutter Web)
- **State Management**: Provider/Riverpod for reactive UI updates
- **Data Models**: Simplified versions of server models
- **Local Storage**: IndexedDB for offline progression
- **Real-time Updates**: WebSocket connection for live data

### Backend Integration
- **Authentication**: AWS Cognito (shared with main server)
- **Data Storage**: DynamoDB for character persistence
- **Metrics**: CloudWatch for player analytics
- **Content Delivery**: JSON-based content that can be updated

### Core Game Systems

#### 1. Character System
- **Attributes**: 
  - Physical: Strength, Agility, Endurance
  - Mental: Intelligence, Perception, Cunning
  - Social: Charisma, Presence, Intrigue
- **Skills**:
  - Combat: Melee, Archery, Brawling, Dodge, Parry
  - Stealth: Stealth, Investigation, Tumbling, Climbing, Lockpicking
  - Magic: Mythos, Arcane
  - Survival: First Aid, Foraging, Appraise
- **Vitals**: Health, Essence (Mana), Experience
- **Equipment Slots**: Head, Chest, Hands, Feet, Weapon, Shield, Back, Finger, Book, Potion

#### 2. Character Archetypes
- **Wizard**: High Intelligence, focus on Mythos/Arcane skills, low Health/high Essence
- **Rogue**: Balanced Agility/Cunning, specialized in Stealth skills, medium Health/Essence
- **Warrior**: High Strength/Endurance, combat-focused skills, high Health/low Essence
- Each archetype starts with unique equipment and progresses differently

#### 3. Progression Loop
1. **Quest Selection**: Automatically picks appropriate quest
2. **Travel Time**: Visual journey to quest location
3. **Action Resolution**: Combat/skill checks with visual feedback
   - Uses skill + attribute for effective score
   - Opposed checks: Your score vs opponent score
   - Static checks: Your score vs difficulty rating
   - Cryptographically secure random resolution
   - Higher scores shift probability of success
4. **Rewards**: Experience, gold, items
5. **Equipment Upgrade**: Auto-equip better items
6. **Zone Unlock**: Access new areas at power thresholds

#### 4. Experience System

Based on the Eidolon Engine's sophisticated XP mechanics:

- **Base XP**: 0.25 per action (success or failure)
- **Variance Modifier**: Rewards based on challenge difficulty
  - Fighting stronger opponents = more XP (up to 4x)
  - Fighting weaker opponents = less XP (down to 0.25x)
  - Formula: (min_score/max_score)^2
- **Failure Penalty**: 50% XP on failed actions
- **Skill Progression**: 
  - XP Required = 10 × 3.5^(current_score)
  - Exponential growth: Score 0→1 needs 10 XP, 1→2 needs 35 XP, etc.
  - Maximum score: 10.0
- **Attribute Growth**: Attributes gain 10% of skill XP
- **Incremental Advancement**: Partial progress toward next level

##### XP Examples:
- Novice (score 0) vs Novice: 0.25 XP on success
- Novice (score 0) vs Expert (score 5): 0.01 XP on success
- Expert (score 5) vs Novice (score 0): 1.0 XP on success
- Equal opponents always give base XP (0.25)

#### 5. Incremental Game Adaptations

The incremental game simplifies and automates the core mechanics:

- **Auto-Combat**: Characters automatically use optimal skill/attribute combinations
- **Visual Progress**: Real-time progress bars showing action completion
- **Accelerated XP**: Faster progression to maintain engagement (2-4x base rates)
- **Offline Progress**: Continue gaining XP while away (at reduced rate)
- **Prestige System**: Reset character for permanent bonuses (future feature)
- **Achievement Multipliers**: Earn XP bonuses for reaching milestones

#### 6. Content Structure
- **Zones**: Tutorial Village → Forest → Mountains → Dark Caverns → etc.
- **Quest Types**: Kill X monsters, Gather Y items, Explore location, Defeat boss
- **Monster Tiers**: Scaled to zone with appropriate rewards
- **Item Rarity**: Common → Uncommon → Rare → Epic → Legendary

## Development Phases

### Phase 1: Core Systems (Current)
- [x] Project setup and architecture planning
- [ ] Basic Flutter app structure
- [ ] Character data models
- [ ] Game loop implementation
- [ ] Basic UI with progress bars

### Phase 2: Content & Polish
- [ ] Quest generation system
- [ ] Monster and item databases
- [ ] Zone progression logic
- [ ] Visual effects and animations
- [ ] Sound effects and music

### Phase 3: Integration
- [ ] Cognito authentication
- [ ] DynamoDB persistence
- [ ] CloudWatch metrics
- [ ] Character export functionality
- [ ] Achievement system

### Phase 4: Platform Expansion
- [ ] Google Play deployment
- [ ] iOS App Store deployment
- [ ] Platform-specific optimizations
- [ ] Push notifications

## Content Loading System

Content is loaded from JSON files that can be updated without app releases:

```json
{
  "zones": [
    {
      "id": "tutorial_village",
      "name": "Starter Village",
      "level_range": [1, 5],
      "monsters": ["rat", "spider", "wolf"],
      "quest_types": ["kill", "gather"]
    }
  ],
  "monsters": [
    {
      "id": "rat",
      "name": "Giant Rat",
      "level": 1,
      "attributes": {"strength": 2, "agility": 3, "perception": 1},
      "loot_table": ["rat_tail", "copper_coin"]
    }
  ]
}
```

## UI/UX Design

### Main Screen Layout
1. **Character Panel** (Left)
   - Name, Class, Level
   - Attribute bars
   - Equipment display

2. **Action Panel** (Center)
   - Current quest/action
   - Progress bar
   - Combat log
   - Recent rewards

3. **Inventory Panel** (Right)
   - Equipment grid
   - Item details
   - Gold counter

### Visual Style
- Dark fantasy theme with glowing accents
- Smooth animations for all progressions
- Particle effects for level-ups and rare drops
- Responsive design for mobile and desktop

## Getting Started

```bash
cd incremental
flutter pub get
flutter run -d chrome
```

## Testing

```bash
flutter test
flutter analyze
```

## Building for Production

```bash
flutter build web --release
flutter build apk --release
flutter build ios --release
```