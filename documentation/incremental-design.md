# Eidolon Engine Incremental Game Technical Design Document

## 1. Executive Summary

This document provides the technical design specifications for implementing the Incremental Game component of the Eidolon Engine. It details the system architecture, data flows, API specifications, and integration patterns required to deliver a timer-based story progression system that seamlessly integrates with the existing MUD infrastructure using a simplified serverless approach.

## 2. System Architecture Overview

### 2.1 High-Level Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Flutter Web    │────▶│   API Gateway    │────▶│ Lambda Functions│
│  Portal (Shared)│     │   (Existing)     │     │  (Dual-Purpose) │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                           │
                    ┌──────────────────────────────────────┼──────┐
                    │                                      │      │
              ┌─────▼─────┐                        ┌──────▼──────┐
              │ DynamoDB  │                        │ EventBridge │
              │ (Shared)  │                        │  (Polling)  │
              └───────────┘                        └─────────────┘
```

### 2.2 Component Interactions

The Incremental Game system operates as an alternative gameplay mode to the MUD, leveraging the existing infrastructure:

1. **Shared Data Layer**: All existing DynamoDB tables used by both modes
2. **Mode Exclusivity**: GameMode field prevents concurrent access
3. **Timing Service**: DynamoDB polling with EventBridge-triggered Lambda at 10-second intervals
4. **Stateless Compute**: Lambda functions handle all game logic
5. **Unified Portal**: Single Flutter web app serves both game modes

## 3. Data Architecture

### 3.1 DynamoDB Table Designs

#### 3.1.1 Story Table (New)

```python
# Master story definitions
{
    "StoryID": "forest-adventure-uuid",  # PK
    "Title": "The Whispering Woods",
    "Description": "A mysterious force draws you into the ancient forest...",
    "NarrativeText": "The morning mist clings to the forest floor as you approach...",
    "StoryType": "daily",               # one-time|daily|repeatable
    "EstimatedDuration": 3600,          # seconds
    "Prerequisites": {
        "minSkills": {"survival": 10, "combat": 5},
        "requiredItems": ["map_fragment"],
        "requiredRooms": ["town_square"]
    },
    "FirstSegmentID": "seg-uuid-001",
    "CreatedAt": "2025-01-15T10:00:00Z",
    "Version": 1
}
```

#### 3.1.2 Segments Table (New)

```python
# Decision segment example
{
    "StoryID": "forest-adventure-uuid",   # PK
    "SegmentID": "seg-uuid-001",          # SK
    "SegmentType": "decision",
    "ShortStatus": "Choosing your path",
    "Duration": 300,                      # 5 minutes to decide
    "DecisionText": "You stand at the forest edge. The path splits into two directions.",
    "DecisionOptions": {
        "take-left-path": "seg-uuid-002a",
        "follow-markers": "seg-uuid-002b"
    },
    "DefaultDecision": "take-left-path"
}

# Narrative segment example
{
    "StoryID": "forest-adventure-uuid",   # PK
    "SegmentID": "seg-uuid-002a",         # SK
    "SegmentType": "narrative",
    "ShortStatus": "Navigating the moonlit path",
    "Duration": 600,                      # 10 minutes
    "NextSegmentID": "seg-uuid-003",     # Single linked list
    "Challenges": [
        {"attribute": "Agility", "skill": "Perception", "difficulty": 8, "attempts": 2},
        {"attribute": "Strength", "skill": "Survival", "difficulty": 7, "attempts": 3}
    ],
    "Results": {
        "death": {
            "narrative": "The forest claims another victim...",
            "effects": {"room": "death_realm"}
        },
        "failure": {
            "narrative": "You stumble through brambles...",
            "effects": {"experience": 10}
        },
        "minimal": {
            "narrative": "You make slow progress...",
            "effects": {"experience": 25}
        },
        "normal": {
            "narrative": "You navigate successfully...",
            "effects": {"experience": 50, "items": ["herb_bundle"]}
        },
        "exceptional": {
            "narrative": "Your expertise shines through...",
            "effects": {"experience": 100, "items": ["rare_herb"], "gold": 50}
        }
    }
}

# Combat segment example
{
    "StoryID": "forest-adventure-uuid",   # PK
    "SegmentID": "seg-uuid-combat-001",   # SK
    "SegmentType": "combat",
    "ShortStatus": "Fighting the goblin scout",
    "Duration": 120,                      # 2 minutes for combat
    "NextSegmentID": "seg-uuid-004",
    "Combat": {
        "opponentId": "a7b8c9d0-1e2f-3a4b-5c6d-7e8f9a0b1c2d",
        "maxRounds": 15,              # Combat ends after this many rounds
        "environment": {
            "lighting": "dim",        # -1 to hit rolls
            "terrain": "muddy"        # -1 to dodge
        }
    },
    "Results": {
        "death": {
            "narrative": "The goblin's blade pierces your heart...",
            "effects": {}
        },
        "failure": {
            "narrative": "The battle drags on too long. Exhausted and wounded, you're forced to retreat...",
            "effects": {"room": 5}
        },
        "minimal": {
            "narrative": "You defeat the goblin but suffer grievous wounds...",
            "effects": {"room": 7, "items": ["goblin_pouch"]}
        },
        "normal": {
            "narrative": "Your combat training prevails. The goblin falls...",
            "effects": {"room": 7, "items": ["goblin_pouch", "rusty_blade"]}
        },
        "exceptional": {
            "narrative": "You dispatch the goblin without taking a scratch!",
            "effects": {"room": 7, "items": ["goblin_pouch", "rusty_blade", "goblin_ear"]}
        }
    }
}
```

#### 3.1.3 ActiveSegments Table (New)

```python
# Tracks runtime segment instances - Narrative example
{
    "ActiveSegmentID": "active-seg-uuid-123",  # PK (unique instance)
    "CharacterID": "char-uuid-456",
    "PlayerID": "player-uuid-789",
    "StoryID": "forest-adventure-uuid",
    "SegmentID": "seg-uuid-002a",
    "StartTime": 1737000300,
    "EndTime": 1737003900,              # When this segment completes
    "Status": "active",                 # active|completed
    "Decision": null,                   # For decision segments
    "ChallengeResults": [               # For narrative segments
        {"attribute": "Agility", "skill": "Perception", "effectiveScore": 12, "difficulty": 8, "sigma": 0.82, "success": true},
        {"attribute": "Agility", "skill": "Perception", "effectiveScore": 12, "difficulty": 8, "sigma": -0.45, "success": false},
        {"attribute": "Strength", "skill": "Survival", "effectiveScore": 10, "difficulty": 7, "sigma": 0.63, "success": true},
        {"attribute": "Strength", "skill": "Survival", "effectiveScore": 10, "difficulty": 7, "sigma": 1.21, "success": true},
        {"attribute": "Strength", "skill": "Survival", "effectiveScore": 10, "difficulty": 7, "sigma": 0.94, "success": true}
    ],
    "Outcome": "minimal",               # Calculated from challenges
    "TTL": 1737090300                  # Auto-cleanup after 24 hours
}

# Combat segment example
{
    "ActiveSegmentID": "active-seg-uuid-combat",  # PK
    "CharacterID": "char-uuid-456",
    "PlayerID": "player-uuid-789",
    "StoryID": "forest-adventure-uuid",
    "SegmentID": "seg-uuid-combat-001",
    "StartTime": 1737000300,
    "EndTime": 1737000420,              # 2 minutes for combat
    "Status": "active",
    "CombatState": {                    # For combat segments
        "round": 3,
        "playerWounds": [
            {"type": "lethal", "healAt": "2025-01-23T10:30:00Z"},
            {"type": "bashing", "healAt": "2025-01-23T08:15:00Z"}
        ],
        "opponentHealth": 4
    },
    "Outcome": null,                    # Set when combat completes
    "TTL": 1737086700
}

# Global Secondary Index for polling
GSI: CompletionTimeIndex
  - PK: Status (active)
  - SK: EndTime
  - Projection: ALL
```

#### 3.1.4 Opponents Table (New)

```python
# Reusable opponent definitions
{
    "OpponentID": "a7b8c9d0-1e2f-3a4b-5c6d-7e8f9a0b1c2d",  # PK (UUIDv4)
    "Name": "Goblin Scout",
    "Description": "A scrawny goblin armed with a rusty blade and wearing tattered leather",
    "CombatRating": 8,          # Agility + Melee skill
    "DefenseRating": 7,         # Agility + Dodge skill
    "DamageRating": 6,          # Strength + Weapon skill
    "Toughness": 5,             # Endurance
    "ArmorRating": 1,           # Leather scraps
    "Health": 6,                # Max health levels
    "WeaponType": "lethal",     # Damage type
    "WeaponDamage": 2,          # Weapon bonus
    "LootTable": [
        {"itemId": "b47ac10b-58cc-4372-a567-0e02b2c3d483", "chance": 0.5},  # Healing potion
        {"itemId": "d47ac10b-58cc-4372-a567-0e02b2c3d481", "chance": 0.3}   # Rusty blade
    ],
    "Tags": ["goblinoid", "forest", "weak"],
    "CreatedAt": "2025-01-23T10:00:00Z"
}
```

#### 3.1.5 Character Table (Existing Fields Utilized)

```python
# No schema changes needed, using existing fields
{
    "CharacterID": "char-uuid-456",     # PK
    "PlayerID": "player-uuid-123",      # Existing attribute
    "GameMode": "Incremental",          # Existing field (MUD|Incremental|None)
    "AvailableStories": [               # Stories the character can start
        "forest-adventure-uuid",        # Initially populated from archetype
        "daily-patrol-uuid",            # Additional stories can be unlocked
        "tutorial-uuid"                 # through gameplay
    ],
    "AbandonedStories": [               # Stories started but not finished
        "hard-quest-uuid"
    ],
    "CompletedStories": [               # Stories successfully completed
        "intro-quest-uuid",
        "easy-quest-uuid"
    ],
    # All other existing MUD fields remain unchanged...
}
```

#### 3.1.6 History Table (New)

```python
# Tracks completed and abandoned story runs
{
    "CharacterID": "char-uuid-456",           # PK (HASH key)
    "StoryID": "forest-adventure-uuid",       # SK (RANGE key)
    "StoryTitle": "The Whispering Woods",     # Cached story title
    "StartedAt": "2025-01-23T08:00:00Z",     # When story began
    "FinishedAt": "2025-01-23T10:30:00Z",    # When story ended
    "StoryType": "daily",                     # one-time|daily|repeatable
    "SegmentHistory": [                       # Detailed segment outcomes
        {
            "SegmentID": "seg-uuid-001",
            "SegmentType": "decision",
            "Comment": "Chose the left path through the forest",
            "Decision": "Take the left path",
            "CompletedAt": "2025-01-23T08:00:00Z"
        },
        {
            "SegmentID": "seg-uuid-002a",
            "SegmentType": "narrative",
            "Comment": "Navigated the moonlit path with mixed success",
            "Outcome": "minimal",
            "ResultText": "You make slow progress through brambles and thick undergrowth. Your survival skills help you find the way, though not without difficulty.",
            "ChallengeResults": [
                {"skill": "Perception", "success": true},
                {"skill": "Perception", "success": false},
                {"skill": "Survival", "success": true}
            ],
            "CompletedAt": "2025-01-23T08:10:00Z"
        },
        {
            "SegmentID": "seg-uuid-combat-001",
            "SegmentType": "combat",
            "Comment": "Fought a goblin scout and emerged victorious",
            "Outcome": "normal",
            "ResultText": "Your combat training prevails. The goblin falls beneath your blade, leaving behind its meager possessions.",
            "FinalCombatState": {
                "rounds": 8,
                "playerWoundsReceived": 2,
                "opponentDefeated": true
            },
            "CompletedAt": "2025-01-23T08:12:00Z"
        }
    ],
    "FinalOutcome": "normal",                 # Overall story outcome
    "TotalDuration": 9000,                    # Seconds from start to finish
    "Rewards": {                              # Aggregated rewards
        "experience": 150,
        "items": ["herb_bundle", "goblin_pouch", "rusty_blade"],
        "gold": 50,
        "roomChanges": [5, 7]
    },
    "AbandonedCount": 0                       # Prior abandonment attempts
}
```

- **`CharacterID` + `StoryID`**: Composite key enables efficient queries by character
- **`StoryTitle`**: Cached story title eliminates need for Story table lookup
- **`StartedAt`/`FinishedAt`**: Track full story duration for analytics
- **`SegmentHistory`**: Preserves complete path through story with:
  - Comment describing what happened in each segment
  - Decision text for player choices
  - ResultText containing the narrative shown to player
  - Full outcome details for analysis
- **`No TTL`**: Data persists until character deletion
- **Cleanup**: Character deletion Lambda removes all associated history

### 3.2 Data Access Patterns

#### 3.2.1 Primary Access Patterns

1. **Get Available Stories**: Read character's AvailableStories list
2. **Check Story Status**: Check if story in Abandoned/Completed lists
3. **Get Active Segments**: Query ActiveSegments by CharacterID
4. **Process Segment Completion**: Update ActiveSegments record
5. **Update Story Lists**: Move story IDs between Available/Abandoned/Completed

#### 3.2.2 No GSIs Required

The simplified architecture avoids Global Secondary Indexes by:

- Using direct key lookups where possible
- Accepting slightly less efficient queries for admin operations
- Leveraging existing table structures

## 4. API Design

### 4.1 RESTful Endpoints

All endpoints follow existing Lambda patterns and extend the current API Gateway.

#### 4.1.1 Story Management APIs

**GET /stories**

```python
# Lambda: api_get_stories
Purpose: Retrieve available stories for character
Query Parameters: characterId
Response: {
    "stories": [
        {
            "storyId": "forest-adventure",
            "title": "The Whispering Woods",
            "type": "daily",
            "available": true,
            "cooldownRemaining": 0,
            "estimatedDuration": 3600
        }
    ]
}
```

**POST /stories/start**

```python
# Lambda: api_start_story
Purpose: Begin a new story
Request: {
    "characterId": "char-uuid-456",
    "storyId": "forest-adventure"
}
Response: {
    "segment": {
        "segmentId": "seg-001",
        "type": "decision",
        "content": "You stand at the forest edge...",
        "options": [...],
        "timeRemaining": 300
    }
}
Error Cases:
- 409: Character already in story or MUD mode
- 403: Story not available
```

**GET /stories/current**

```python
# Lambda: api_get_current_story
Purpose: Get active story state
Query Parameters: characterId
Response: Current story and segment details
```

#### 4.1.2 Segment APIs

**POST /segments/decision**

```python
# Lambda: api_submit_decision
Purpose: Submit player decision
Request: {
    "characterId": "char-uuid-456",
    "decision": "take-left-path"
}
Response: {
    "accepted": true,
    "nextSegmentTime": 1737003600
}
```

**GET /segments/outcome**

```python
# Lambda: api_get_segment_outcome
Purpose: Retrieve completed segment results
Query Parameters: characterId, segmentId
Response: {
    "outcome": "normal",
    "narrative": "You navigate successfully...",
    "effects": {
        "experience": 50,
        "items": ["herb_bundle"]
    }
}
```

**POST /stories/abandon**

```python
# Lambda: api_abandon_story
Purpose: Exit current story
Request: { "characterId": "char-uuid-456" }
Response: { "abandoned": true }
```

### 4.2 Client Communication Strategy

The Flutter portal implements smart polling:

1. **Active Story Polling**
   - Poll `/stories/current` based on segment duration
   - Start frequent polling 30 seconds before completion
   - Use exponential backoff: 30s → 15s → 5s → 1s

2. **Decision Windows**
   - Check every 30 seconds during decision segments
   - Immediate update after decision submission

3. **Idle Optimization**
   - No polling when no active story
   - Check for new stories on screen focus

## 5. Lambda Function Specifications

### 5.1 Core Lambda Functions

All Lambda functions follow the existing pattern in the `lambda/` directory and use the `eidolon` package for standardized responses, logging, and error handling.

#### 5.1.1 api_get_stories

```python
"""Get available stories for a character."""
# Key Operations:
- Fetch character record to get AvailableStories list
- Load story definitions from cache or DynamoDB
- Check participation history for cooldowns
- Filter by prerequisites
- Return formatted list using eidolon.responses
```

#### 5.1.2 api_start_story

```python
"""Initialize story participation."""
# Key Operations:
- Verify character GameMode is "None"
- Set GameMode to "Incremental" (atomic update)
- Create first ActiveSegments record
- Remove story from AvailableStories list
- Enable polling rule if first active segment
- Return first segment details
# Error Handling:
- Use eidolon.responses.error_response for conflicts
- Log with eidolon.logger
```

#### 5.1.3 api_submit_decision

```python
"""Record player decision and schedule next segment."""
# Key Operations:
- Validate decision against current segment options
- Update story record with decision
- Calculate and set NextCompletionTime in story record
- Return acknowledgment
```

#### 5.1.4 api_process_segment

```python
"""Process segment completion (triggered by EventBridge)."""
# Key Operations:
- Retrieve story and character data
- Calculate outcome based on character stats/skills
- Apply effects to character record
- Update story progression with new NextCompletionTime
- If story complete, check if polling should be disabled
# Note: Called by segment poller Lambda
```

### 5.2 DynamoDB Polling Implementation

Use a single EventBridge rule to trigger polling Lambda every 10 seconds:

```python
def setup_polling_rule():
    """Create EventBridge rule for segment polling."""
    eventbridge.put_rule(
        Name='incremental-segment-poller',
        ScheduleExpression='rate(10 seconds)',
        State='DISABLED'  # Enable when incremental mode has active users
    )

    eventbridge.put_targets(
        Rule='incremental-segment-poller',
        Targets=[{
            'Id': '1',
            'Arn': segment_poller_lambda_arn
        }]
    )

def segment_poller_handler(event, context):
    """Poll for segments ready to complete."""
    current_time = int(time.time())

    # Query GSI for segments due for completion
    response = dynamodb.query(
        TableName='active_segments',
        IndexName='CompletionTimeIndex',
        KeyConditionExpression='#status = :active AND EndTime <= :now',
        ExpressionAttributeNames={'#status': 'Status'},
        ExpressionAttributeValues={
            ':active': 'active',
            ':now': current_time
        }
    )

    # Process each due segment
    for segment in response['Items']:
        process_segment_completion(
            segment['SegmentID'],
            segment['PlayerID'],
            segment['CharacterID'],
            segment['StoryID'],
            segment['SegmentDefinitionID']
        )

def enable_polling_if_needed():
    """Enable polling when active segments exist."""
    # Check if any active segments exist
    response = dynamodb.query(
        TableName='active_segments',
        IndexName='CompletionTimeIndex',
        KeyConditionExpression='#status = :active',
        ExpressionAttributeNames={'#status': 'Status'},
        ExpressionAttributeValues={':active': 'active'},
        Limit=1
    )

    if response['Count'] > 0:
        eventbridge.enable_rule(Name='incremental-segment-poller')
    else:
        eventbridge.disable_rule(Name='incremental-segment-poller')
```

### 5.3 Outcome Calculation Logic

The segment processor implements MUD-compatible mechanics:

```python
def calculate_narrative_outcome(character, segment):
    """Determine narrative outcome based on character stats using MUD mechanics."""
    from eidolon.mechanics import ResolveStaticCheck

    total_sigma = 0.0
    total_attempts = 0
    critical_failures = 0

    # Process each challenge using the MUD mechanics system
    for challenge in segment.get('Challenges', []):
        attribute_value = character.get('Attributes', {}).get(challenge['attribute'], 0)
        skill_value = character.get('Skills', {}).get(challenge['skill'], 0)

        # Combined effective score (attribute + skill)
        effective_score = attribute_value + skill_value
        difficulty = challenge['difficulty']  # Typically 7-10

        # Run multiple attempts for this challenge
        for _ in range(challenge['attempts']):
            outcome = ResolveStaticCheck(effective_score, difficulty)
            total_attempts += 1
            total_sigma += outcome.Sigma

            # Track critical failures (very negative sigma)
            if outcome.Sigma < -2.0:
                critical_failures += 1

    # Calculate average sigma across all attempts
    if total_attempts == 0:
        return 'failure'

    avg_sigma = total_sigma / total_attempts

    # Map sigma values to story outcomes
    # Critical failures can lead to death
    if critical_failures >= 2 or avg_sigma < -2.0:
        return 'death'
    elif avg_sigma < -1.0:
        return 'failure'
    elif avg_sigma < 0:
        return 'minimal'
    elif avg_sigma < 1.0:
        return 'normal'
    else:
        return 'exceptional'
```

### 5.4 Combat Resolution Logic

Combat segments use the full MUD combat mechanics with wounds:

```python
def process_combat_segment(character, segment, active_segment):
    """Process combat using full MUD mechanics."""
    from eidolon.mechanics import ResolveOpposedCheck
    from eidolon.damage import apply_damage

    # Load opponent from Opponents table
    opponent_id = segment['Combat']['opponentId']
    opponent = load_opponent(opponent_id)

    # Initialize or restore combat state
    combat_state = active_segment.get('CombatState', {
        'round': 0,
        'playerWounds': [],
        'opponentHealth': opponent['Health']
    })

    # Get character equipment
    weapon = get_equipped_weapon(character)
    armor = get_equipped_armor(character)

    # Run combat rounds
    while (combat_state['round'] < segment['Combat']['maxRounds'] and
           character.health > 0 and
           combat_state['opponentHealth'] > 0):

        combat_state['round'] += 1

        # Apply environment modifiers
        env = segment['Combat'].get('environment', {})
        hit_modifier = -1 if env.get('lighting') == 'dim' else 0
        dodge_modifier = -1 if env.get('terrain') == 'muddy' else 0

        # Player attacks
        hit_check = ResolveOpposedCheck(
            character.agility + character.melee + hit_modifier,
            opponent['DefenseRating'] + dodge_modifier
        )

        if hit_check.Sigma >= 1.0:
            # Damage resolution
            damage_check = ResolveOpposedCheck(
                character.strength + weapon.damage_rating,
                opponent['Toughness'] + opponent['ArmorRating']
            )

            if damage_check.Sigma >= 1.0:
                damage = math.floor(damage_check.Sigma)
                combat_state['opponentHealth'] -= damage

        # Opponent attacks if still alive
        if combat_state['opponentHealth'] > 0:
            hit_check = ResolveOpposedCheck(
                opponent['CombatRating'],
                character.agility + character.dodge + dodge_modifier
            )

            if hit_check.Sigma >= 1.0:
                damage_check = ResolveOpposedCheck(
                    opponent['DamageRating'] + opponent['WeaponDamage'],
                    character.endurance + armor.protection_value
                )

                if damage_check.Sigma >= 1.0:
                    damage = math.floor(damage_check.Sigma)
                    # Apply damage using MUD wound system
                    apply_damage(character, opponent['WeaponType'], damage)

                    # Update wound tracking in combat state
                    new_wounds = get_recent_wounds(character, damage)
                    combat_state['playerWounds'].extend(new_wounds)

    # Determine outcome
    return determine_combat_outcome(character, combat_state)

def determine_combat_outcome(character, combat_state):
    """Determine combat outcome based on final state."""
    # Death - character at 0 health
    if character.health <= 0:
        return 'death'

    # Failure - max rounds reached without victory
    if combat_state['opponentHealth'] > 0:
        return 'failure'

    # Victory outcomes based on wounds taken
    wounds = character.GetWoundsByType()
    total_wounds = sum(wounds.values())
    serious_wounds = wounds.get('lethal', 0) + wounds.get('aggravated', 0)

    # Opponent defeated - determine victory quality
    if total_wounds == 0:
        return 'exceptional'  # Flawless victory
    elif serious_wounds == 0 and total_wounds <= 2:
        return 'normal'      # Minor wounds only
    else:
        return 'minimal'     # Significant wounds
```

### 5.5 Difficulty Guidelines

Following the MUD mechanics system, story challenges use these difficulty levels:

- **4**: Easy task (high success rate)
- **6**: Moderate task
- **8**: Hard task (typical for most story challenges)
- **10**: Very hard task
- **12+**: Exceptional task (rare, for epic moments)

Most incremental story challenges will use difficulties between 7-10, providing a balanced experience where character progression matters but outcomes aren't guaranteed.

## 6. Flutter Portal Integration

### 6.1 New Screens

Add to existing portal structure:

```dart
// portal/lib/screens/incremental/
story_selection_screen.dart    // List available stories
story_display_screen.dart      // Show current segment
equipment_screen.dart          // Manage equipment (reuse existing)
```

### 6.2 State Management

Extend existing providers:

```dart
// portal/lib/providers/incremental_state.dart
class IncrementalState extends ChangeNotifier {
  Story? activeStory;
  Segment? currentSegment;
  Timer? pollingTimer;
  DateTime? segmentCompleteTime;

  // Reuse existing ApiService for all calls
  final ApiService _api;

  Future<void> startStory(String storyId) async {
    final response = await _api.post('/stories/start', {
      'characterId': currentCharacter.id,
      'storyId': storyId
    });
    // Update state and start polling
  }
}
```

### 6.3 Navigation Integration

Update character management screen:

```dart
// Add button to enter incremental mode
if (character.gameMode == 'None') {
  ElevatedButton(
    onPressed: () => Navigator.pushNamed(
      context,
      '/incremental/stories'
    ),
    child: Text('Play Story Mode'),
  );
} else if (character.gameMode == 'Incremental') {
  ElevatedButton(
    onPressed: () => Navigator.pushNamed(
      context,
      '/incremental/current'
    ),
    child: Text('Continue Story'),
  );
}
```

## 7. Security and Validation

### 7.1 Bidirectional Consequences

The Incremental and MUD modes share persistent character state, ensuring consequences carry between game modes:

#### Shared Persistent State

1. **Wounds and Health**:
   - All wounds (bashing, lethal, aggravated) persist across modes
   - Character entering Incremental mode with MUD wounds starts injured
   - Combat wounds from Incremental stories affect MUD gameplay
   - Death in either mode requires resurrection/respawn

2. **Inventory and Items**:
   - Items gained in Incremental stories appear in MUD inventory
   - Equipment worn in MUD affects Incremental combat stats
   - Item loss/destruction persists across modes

3. **Character Location**:
   - Room changes from story effects update MUD position
   - Character returns to new room when switching to MUD mode
   - Death effects may transport to death realm in both modes

4. **Experience and Progression**:
   - Experience gained in either mode contributes to character growth
   - Skill improvements from either mode are permanent
   - Attribute changes persist across modes

#### Implementation Example

```python
def apply_story_consequences(character, outcome_effects):
    """Apply story outcomes that persist to MUD mode."""
    # Room changes
    if 'room' in outcome_effects:
        character['RoomID'] = outcome_effects['room']

    # Item rewards
    if 'items' in outcome_effects:
        for item_id in outcome_effects['items']:
            add_to_inventory(character['CharacterID'], item_id)

    # Experience (if implemented)
    if 'experience' in outcome_effects:
        character['Experience'] = character.get('Experience', 0) + outcome_effects['experience']

    # Wounds are applied during combat resolution using MUD damage system
    # No separate wound application needed in outcome_effects
```

### 7.2 Mode Exclusivity

Enforce through GameMode field:

```python
def validate_mode_transition(character, target_mode):
    """Ensure character can transition to target mode."""
    current_mode = character.get('GameMode', 'None')

    if current_mode == target_mode:
        return True

    if current_mode == 'MUD':
        raise ValueError("Character active in MUD")

    if current_mode == 'Incremental':
        raise ValueError("Character in story mode")

    # Check for expired locks (1 hour timeout)
    last_transition = character.get('LastModeTransition', 0)
    if time.time() - last_transition < 3600:
        return True

    return True
```

### 7.2 Input Validation

Use existing eidolon validation patterns:

```python
from eidolon.validation_utils import validate_uuid, validate_string

def validate_story_request(event):
    """Validate story API request."""
    character_id = event.get('characterId')
    if not validate_uuid(character_id):
        return error_response("Invalid character ID")

    story_id = event.get('storyId')
    if not validate_string(story_id, max_length=50):
        return error_response("Invalid story ID")
```

## 8. Monitoring and Analytics

### 8.1 CloudWatch Metrics

Emit custom metrics using existing patterns:

```python
from eidolon.logger import get_logger
logger = get_logger(__name__)

# Log story events
logger.info("Story started", extra={
    "story_id": story_id,
    "character_id": character_id,
    "story_type": story_type
})

# Track completion rates
cloudwatch.put_metric_data(
    Namespace='eidolon/incremental',
    MetricData=[{
        'MetricName': 'StoryCompletion',
        'Value': 1,
        'Dimensions': [
            {'Name': 'StoryId', 'Value': story_id},
            {'Name': 'Outcome', 'Value': outcome}
        ]
    }]
)
```

### 8.2 Error Tracking

Leverage existing error patterns:

```python
try:
    # Story logic
except ValidationError as e:
    logger.warning("Validation failed", extra={"error": str(e)})
    return validation_error_response(e.field, e.message)
except Exception as e:
    logger.error("Story processing failed", extra={"error": str(e)}, exc_info=True)
    return internal_error_response(context.aws_request_id)
```

## 9. Deployment Strategy

### 9.1 CDK Integration

Add new Lambda functions to existing stack:

```python
# deployment/cdk/stacks/lambda_stack.py
# Add to existing Lambda definitions:

self.story_functions = [
    ("api-get-story", "api_get_story.lambda_handler"),
    ("api-start-story", "api_start_story.lambda_handler"),
    ("api-submit-decision", "api_submit_decision.lambda_handler"),
    ("api-get-segment-outcome", "api_get_segment_outcome.lambda_handler"),
    ("api-abandon-story", "api_abandon_story.lambda_handler"),
    ("segment-poller", "segment_poller.lambda_handler"),
    ("process-segment", "process_segment.lambda_handler"),
]

# Add EventBridge rule for segment polling
self.segment_poller_rule = events.Rule(
    self, "incremental-segment-poller",
    schedule=events.Schedule.rate(Duration.seconds(10)),
    enabled=False  # Enable dynamically when needed
)
```

### 9.2 API Gateway Routes

Extend existing API:

```python
# Add to API Gateway configuration
story_routes = [
    ("GET", "/story", "api-get-story"),
    ("POST", "/story/start", "api-start-story"),
    ("GET", "/story/current", "api-get-current-story"),
    ("POST", "/segments/decision", "api-submit-decision"),
    ("GET", "/segments/outcome", "api-get-segment-outcome"),
    ("POST", "/stories/abandon", "api-abandon-story"),
]
```

### 9.3 Database Updates

Add new tables to DynamoDB stack:

```python
# deployment/cdk/stacks/dynamodb_stack.py
# Add to table configurations:
{"name": "story", "pk": "StoryID", "pk_type": "S"}
{"name": "opponents", "pk": "OpponentID", "pk_type": "S"}
{"name": "history", "pk": "CharacterID", "pk_type": "S", "sk": "StoryID", "sk_type": "S"}

# Add GSI to active_segments table:
{"name": "CompletionTimeIndex", "pk": "Status", "sk": "EndTime"}
```

## 10. Cost Analysis

### 10.1 Simplified Cost Structure

With the DynamoDB polling approach:

**Monthly Costs (10,000 concurrent users)**:

- Lambda invocations: ~$100-150 (includes polling overhead)
- EventBridge rules: <$1 (single polling rule)
- DynamoDB (pay-per-request): ~$150-250 (includes GSI queries)
- No Fargate costs: $0
- **Total: ~$250-400/month**

### 10.2 Cost Optimization

1. **Lambda Optimization**:
   - Minimize cold starts by keeping functions warm
   - Use appropriate memory allocation (256MB typical)
   - Disable polling when no active stories

2. **Polling Efficiency**:
   - 10-second intervals balance precision vs cost
   - Process multiple segments per poll cycle
   - Use GSI for efficient time-based queries

3. **DynamoDB Efficiency**:
   - Use TTL for automatic cleanup
   - Batch process segment updates
   - Efficient GSI usage for polling queries

## 11. Implementation Timeline

### 11.1 Phase 1: Core Story System (Week 1-2)

- Create story definition table with GSI
- Implement core Lambda functions
- DynamoDB polling infrastructure
- Manual story creation tools

### 11.2 Phase 2: Flutter Integration (Week 3-4)

- Story selection screen
- Story display/decision UI
- Polling implementation
- Error handling

### 11.3 Phase 3: Game Mechanics (Week 5-6)

- Skill check calculations
- Equipment integration
- Progression balancing
- Daily story reset logic

### 11.4 Phase 4: Polish & Testing (Week 7-8)

- Performance optimization
- Comprehensive testing
- Analytics implementation
- Documentation

## 12. Benefits of Simplified Architecture

### 12.1 Development Benefits

- No new infrastructure patterns to learn
- Reuse existing Lambda/API patterns
- Consistent error handling via eidolon
- Single deployment pipeline

### 12.2 Operational Benefits

- No container management
- Automatic scaling with Lambda
- Pay-per-use pricing
- Unified monitoring
- Enable/disable polling based on usage

### 12.3 Maintenance Benefits

- Fewer moving parts
- Standard AWS services only
- Simple polling pattern to maintain
- Efficient debugging with CloudWatch
- GSI provides fast time-based queries

## 13. Conclusion

This simplified technical design leverages the existing Eidolon Engine infrastructure to implement the incremental game with minimal additional complexity. By using shared tables, dual-purpose Lambda functions, and DynamoDB polling with EventBridge, the system can support 10,000 concurrent users while maintaining consistency with the MUD game mechanics and keeping operational costs low.

Key architectural decisions:

- Shared DynamoDB tables eliminate synchronization needs
- DynamoDB + 10-second polling provides scalable timing
- GSI enables efficient time-based queries
- Enable/disable polling based on active stories
- Existing Lambda patterns ensure consistency
- GameMode field provides simple mode exclusivity
- 10-second resolution balances precision and cost
