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

#### 3.1.1 Story Table

```python
# Master story definitions
{
    "StoryID": "forest-adventure-uuid",  # HASH
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

#### 3.1.2 Segments Table

```python
# Decision segment example
{
    "StoryID": "forest-adventure-uuid",   # HASH
    "SegmentID": "seg-uuid-001",          # RANGE
    "SegmentType": "decision",
    "ShortStatus": "Choosing your path",
    "SegmentDuration": 300,               # 5 minutes to decide
    "DecisionText": "You stand at the forest edge. The path splits into two directions.",
    "DecisionOptions": {
        "left-path": "seg-uuid-002a",
        "trail-markers": "seg-uuid-002b"
    },
    "DefaultDecision": "left-path"
}

# Narrative segment example
{
    "StoryID": "forest-adventure-uuid",   # HASH
    "SegmentID": "seg-uuid-002a",         # RANGE
    "SegmentType": "narrative",
    "ShortStatus": "Navigating the moonlit path",
    "SegmentDuration": 600,               # 10 minutes
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
    "StoryID": "forest-adventure-uuid",   # HASH
    "SegmentID": "seg-uuid-combat-001",   # RANGE
    "SegmentType": "combat",
    "ShortStatus": "Fighting the goblin scout",
    "SegmentDuration": 120,               # 2 minutes for combat
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

#### 3.1.3 ActiveSegments Table

```python
# Tracks runtime segment instances - Narrative example
{
    "ActiveSegmentID": "active-seg-uuid-123",  # HASH
    "CharacterID": "char-uuid-456",
    "StoryID": "forest-adventure-uuid",
    "SegmentID": "seg-uuid-002a",
    "StartTime": 1737000300,
    "EndTime": 1737003900,              # GSI - EndTimeIndex
    "Decision": null,                   # For decision segments
    "ChallengeResults": [               # For narrative segments
        {"attribute": "Agility", "skill": "Perception", "effectiveScore": 12, "difficulty": 8, "sigma": 0.82, "success": true},
        {"attribute": "Agility", "skill": "Perception", "effectiveScore": 12, "difficulty": 8, "sigma": -0.45, "success": false},
        {"attribute": "Strength", "skill": "Survival", "effectiveScore": 10, "difficulty": 7, "sigma": 0.63, "success": true},
        {"attribute": "Strength", "skill": "Survival", "effectiveScore": 10, "difficulty": 7, "sigma": 1.21, "success": true},
        {"attribute": "Strength", "skill": "Survival", "effectiveScore": 10, "difficulty": 7, "sigma": 0.94, "success": true}
    ],
    "Outcome": "minimal"                # Calculated from challenges
}

# Combat segment example
{
    "ActiveSegmentID": "active-seg-uuid-combat",  # HASH
    "CharacterID": "char-uuid-456",
    "StoryID": "forest-adventure-uuid",
    "SegmentID": "seg-uuid-combat-001",
    "StartTime": 1737000300,
    "EndTime": 1737000420,              # GSI - EndTimeIndex
    "CombatState": {                    # For combat segments
        "round": 3,
        "playerWounds": [
            {"type": "lethal", "healAt": "2025-01-23T10:30:00Z"},
            {"type": "bashing", "healAt": "2025-01-23T08:15:00Z"}
        ],
        "opponentHealth": 4
    },
    "Outcome": null                     # Set when combat completes
}

# Global Secondary Index for polling
GSI: EndTimeIndex
  - EndTime field only
  - Projection: ALL
```

#### 3.1.4 Opponents Table

```python
# Reusable opponent definitions
{
    "OpponentID": "a7b8c9d0-1e2f-3a4b-5c6d-7e8f9a0b1c2d",  # HASH
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
# Extended with incremental-specific fields
{
    "CharacterID": "char-uuid-456",     # HASH
    "CharacterName": "Thorin",          # GSI - CharacterNameIndex
    "PlayerID": "player-uuid-123",      # Existing attribute
    "GameMode": "Incremental",          # MUD|Incremental|None
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
    "ActiveStoryID": "forest-adventure-uuid",    # Currently active story
    "ActiveSegmentID": "active-seg-uuid-123",    # Currently active segment
    # All other existing MUD fields remain unchanged...
}
```

#### 3.1.6 History Table

```python
# Tracks completed and abandoned story runs
{
    "CharacterID": "char-uuid-456",           # HASH
    "StoryID": "forest-adventure-uuid",       # RANGE
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
            "description": "A mysterious forest beckons adventurers",
            "type": "daily",  // one-time, daily, or repeatable
            "available": true,
            "cooldownRemaining": 0,  // seconds until available
            "estimatedDuration": 3600  // seconds
        }
    ]
}

Notes:
- Stories are filtered by character prerequisites
- Cooldown logic enforces story type restrictions
- One-time stories disappear after successful completion
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
        "segmentId": "active-seg-uuid",
        "storyId": "forest-adventure",
        "type": "decision|narrative|combat",
        "timeRemaining": 300,
        // Additional fields based on type:
        // Decision: "content", "options"
        // Narrative: "shortStatus", "narrative"
        // Combat: "shortStatus", "opponentId"
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
- Load story definitions from Story table
- Check History table for cooldowns based on story type:
  - one-time: Check if completed successfully (permanent cooldown)
  - daily: Calculate seconds until midnight UTC
  - repeatable: Always available (cooldown = 0)
- Filter by prerequisites (minSkills, requiredItems, requiredRooms)
- Return formatted list with availability status
- Uses eidolon.responses.create_response for consistent formatting
```

#### 5.1.2 api_start_story

```python
"""Initialize story participation."""
# Key Operations:
- Verify character ownership and GameMode is "None"
- Validate story is in character's AvailableStories list
- Load story metadata and first segment from DynamoDB
- Atomically update character:
  - Set GameMode to "Incremental"
  - Remove story from AvailableStories
- Create ActiveSegments record with:
  - Unique ActiveSegmentID
  - Start/End times based on segment duration
  - Explicit deletion after processing
- Create History table entry for tracking
- Return formatted segment response based on type
# Error Handling:
- 401: Authentication failures
- 403: Story not available to character
- 409: Character already in game mode or state conflict
- 400: Invalid request parameters
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

The segment completion system uses EventBridge to create a serverless polling mechanism that processes story segments when their timers expire. This approach eliminates the need for always-on infrastructure while maintaining precise timing control.

#### EventBridge Rule Configuration

The system establishes a single EventBridge rule named 'incremental-segment-poller' that triggers every 10 seconds. This rule starts in a disabled state and only activates when players have active story segments. The rule targets a Lambda function responsible for checking and processing completed segments.

#### Segment Polling Process

When the polling Lambda executes, it performs these operations:

1. **Time-based Query**: The function queries the ActiveSegments table using the EndTimeIndex GSI, searching for all segments where the EndTime is less than or equal to the current timestamp. This efficient query leverages the index to avoid scanning the entire table.

2. **Batch Processing**: For each segment found ready for completion, the system invokes the segment completion processor with the necessary identifiers: SegmentID, CharacterID, StoryID, and SegmentDefinitionID. This allows parallel processing of multiple completed segments.

3. **Automatic Cleanup**: After processing, segments are deleted from the ActiveSegments table, keeping the table size manageable and query performance optimal.

#### Dynamic Polling Control

The system implements intelligent polling management to minimize costs:

- **Activation Logic**: When a new story segment begins, the system checks if polling is already active. If not, it enables the EventBridge rule to start the 10-second polling cycle.

- **Deactivation Logic**: After processing segments, if no active segments remain in the table, the system disables the EventBridge rule to stop unnecessary Lambda invocations. This check uses a simple scan with a limit of 1 to determine if any records exist.

- **Cost Optimization**: This on-demand polling approach ensures Lambda functions only execute when there's actual work to process, significantly reducing operational costs compared to continuous polling.

The combination of EventBridge scheduling, GSI-based queries, and dynamic rule management creates an efficient, scalable system for handling thousands of concurrent story progressions without requiring dedicated infrastructure.

### 5.3 Outcome Calculation Logic

The narrative outcome system leverages the MUD mechanics to create consistent, fair results based on character abilities. This ensures that character progression in the incremental game directly impacts story success rates.

#### Challenge Resolution Process

When a narrative segment contains challenges, the system evaluates each one using the character's relevant attributes and skills:

1. **Skill Combination**: Each challenge specifies an attribute (like Strength or Agility) and a skill (like Survival or Perception). The system combines these values to create an effective score representing the character's total capability for that challenge.

2. **Multiple Attempts**: Challenges can require multiple dice rolls, simulating extended efforts. For example, navigating through a forest might require three Survival checks, representing different obstacles encountered along the way.

3. **Statistical Accumulation**: The system tracks the statistical outcome (sigma value) of each roll using the MUD's ResolveStaticCheck function. These sigma values represent degrees of success or failure, with positive values indicating success and negative values indicating failure.

#### Outcome Determination

The system determines the final narrative outcome by aggregating the sigma values from all challenge attempts:

- **Sigma Accumulation**: Each challenge produces a sigma value representing the degree of success or failure. These values are summed across all attempts to create a total performance score.

- **Average Performance**: The total sigma is divided by the number of attempts to calculate an average performance level. This ensures that segments with different numbers of challenges remain balanced.

- **Critical Override**: Extreme individual results can override the average:

  - Any sigma ≤ -3.0 represents a catastrophic failure that triggers immediate death
  - Multiple critical failures (sigma < -2.0) can downgrade the final outcome
  - Multiple critical successes (sigma > 2.0) can upgrade the final outcome

- **Outcome Thresholds**: The final outcome is determined by the average sigma value:
  - **Death**: Any catastrophic failure (-3.0 or worse) or average sigma < -2.0
  - **Failure**: Average sigma between -2.0 and -0.5
  - **Minimal Success**: Average sigma between -0.5 and 0.5
  - **Normal Success**: Average sigma between 0.5 and 1.5
  - **Exceptional Success**: Average sigma > 1.5

This approach directly leverages the MUD mechanics system's probability model. A character with higher skills will naturally achieve higher sigma values, leading to better narrative outcomes. The system preserves the significance of individual rolls while creating a smooth progression of outcomes based on overall performance.

### 5.4 Combat Resolution Logic

Combat segments implement the complete MUD combat system, ensuring that battles in the incremental game feel authentic and consequential. The system preserves all the tactical depth of MUD combat while automating the round-by-round resolution.

#### Combat Initialization

When a combat segment begins, the system loads the opponent's statistics from the Opponents table and establishes the initial combat state. This includes tracking the current round number, any wounds inflicted on the player, and the opponent's remaining health. If resuming an interrupted combat, the system restores the previous state to continue where the battle left off.

#### Round-by-Round Combat Flow

Combat proceeds through a series of alternating attacks until one of three conditions is met: the character dies, the opponent is defeated, or the maximum number of rounds is reached. Each round follows this sequence:

**Environmental Factors**: The combat environment affects both combatants. Dim lighting impairs accuracy, while difficult terrain like mud hampers defensive maneuvers. These modifiers apply equally to both sides, creating tactical considerations for story designers.

**Player Attack Phase**: The character attempts to strike their opponent using a two-stage resolution process:

- First, an attack roll determines if the character hits, combining their Agility and Melee skill against the opponent's Defense Rating
- If successful (sigma ≥ 1.0), a damage roll follows, pitting the character's Strength and weapon damage against the opponent's Toughness and armor
- Successful damage rolls reduce the opponent's health by the sigma value (rounded down)

**Opponent Counter-Attack**: If still standing, the opponent retaliates using the same two-stage process:

- The opponent's Combat Rating contests the character's defensive capabilities (Agility + Dodge)
- Successful hits trigger damage resolution against the character's Endurance and equipped armor
- Damage inflicted creates wounds using the MUD wound system, with wound types determined by the opponent's weapon

#### Wound System Integration

The combat system fully implements the MUD wound mechanics:

- **Bashing damage** creates bruises that heal within 15 minutes
- **Lethal damage** causes serious injuries requiring 6 hours to heal
- **Aggravated damage** inflicts grievous wounds needing 7 days of recovery

These wounds persist across game modes, meaning a character injured in an incremental combat will still bear those wounds when returning to the MUD.

#### Combat Outcome Determination

The final outcome depends on the combat's resolution:

- **Death**: The character's health reaches zero, triggering death mechanics
- **Failure**: Maximum rounds expire with the opponent still standing
- **Minimal Victory**: The character wins but sustains significant wounds
- **Normal Victory**: Victory achieved with only minor injuries
- **Exceptional Victory**: Flawless combat performance without taking damage

This nuanced outcome system rewards skilled character builds while maintaining the risk inherent in combat encounters.

### 5.5 Difficulty Guidelines

Following the MUD mechanics system, story challenges use these difficulty levels:

- **4**: Easy task (high success rate)
- **6**: Moderate task
- **8**: Hard task (typical for most story challenges)
- **10**: Very hard task
- **12+**: Exceptional task (rare, for epic moments)

Most incremental story challenges will use difficulties between 7-10, providing a balanced experience where character progression matters but outcomes aren't guaranteed.

## 6. Flutter Incremental Client

### 6.1 Application Structure

The incremental game client is a standalone Flutter web application focused on story-driven gameplay:

```
incremental/
├── lib/
│   ├── screens/
│   │   ├── home_screen.dart          // Character selection/creation
│   │   ├── story_selection_screen.dart // Available stories list
│   │   ├── game_screen.dart           // Active story display
│   │   └── history_screen.dart        // Completed stories
│   ├── services/
│   │   ├── api_service.dart           // Backend communication
│   │   └── auth_service.dart          // Cognito integration
│   ├── models/
│   │   ├── character.dart             // Character data model
│   │   ├── story.dart                 // Story/segment models
│   │   └── active_segment.dart        // Active gameplay state
│   └── widgets/
│       ├── progress_timer.dart        // Countdown display
│       ├── decision_panel.dart        // Choice selection UI
│       └── outcome_display.dart       // Results presentation
```

### 6.2 State Management

The application uses Provider for state management, maintaining synchronization with the server through a centralized GameState class. This state manager tracks the active character, current story, and active segment, ensuring the UI always reflects the latest game state.

The state management system implements several key behaviors:

**Polling Mechanism**: When a story segment is active, the application establishes a polling timer that checks for segment completion every second. This ensures timely updates when segments complete on the server, allowing the UI to immediately display outcomes and progression options.

**Local Time Tracking**: To provide smooth countdown displays without constant server queries, the state manager calculates remaining time locally. It compares the segment's server-provided end time with the current device time, updating the display every frame for a seamless countdown experience.

**State Synchronization**: The state manager acts as the single source of truth for the application, notifying all dependent widgets when game state changes. This reactive pattern ensures that story progression, character updates, and timer displays remain perfectly synchronized across all screens.

**Resource Management**: The polling system intelligently manages resources by starting timers only when needed and cleaning them up when segments complete or the user navigates away. This prevents memory leaks and unnecessary network traffic.

### 6.3 User Experience Flow

The incremental client follows a hierarchical screen structure that guides players from authentication through gameplay:

**Authentication Layer**: The entry point presents login and account creation screens. New players can register with email and password, while returning players authenticate through AWS Cognito. Upon successful authentication, players proceed to character management.

**Character Management**: This intermediate layer displays all characters associated with the player's account. Players can create new characters by selecting an archetype and choosing a unique name, or select an existing character to play. Characters currently active in MUD mode are marked as unavailable. Selecting a character transitions to the main game interface.

**Game Screen Hub**: The primary gameplay interface organizes three interconnected panels:

1. **Character Sheet**: Displays current attributes, skills, health, and active effects. This panel updates in real-time as story outcomes modify character state. Players can track their progression and understand how their abilities affect story outcomes.

2. **Story Interface**: The central gameplay area with three modes:

   - **Story Selection**: Browse available stories filtered by prerequisites and cooldowns. Each story shows its type (one-time, daily, repeatable), estimated duration, and brief description.
   - **Active Progression**: During active segments, displays the current narrative, countdown timer, and appropriate interaction elements (decision buttons for choices, status text for combat/challenges).
   - **History View**: Access completed story outcomes, reviewing past narratives and rewards earned. This provides context for character development and story continuity.

3. **Inventory Interface**: Manages equipment and items gained through story completion. Players can examine item properties and manage their loadout, with changes immediately affecting combat statistics for future story segments.

This structure ensures players always understand their location in the game flow while maintaining easy access to all critical information during story progression.

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

### 7.2 Mode Exclusivity

The system enforces strict mode exclusivity through the GameMode field on each character. This validation ensures that a character cannot be simultaneously active in both the MUD and Incremental game modes, preventing state conflicts and ensuring data consistency.

The mode transition validation implements several key checks:

**Current Mode Verification**: The system first examines the character's current GameMode value. If the character is already in the requested mode, the transition is approved immediately. This handles cases where clients may redundantly request mode changes.

**Active Mode Blocking**: Characters currently marked as active in either MUD or Incremental mode cannot transition until properly exited from their current mode. This prevents abandoning active game sessions and ensures proper cleanup of game state.

**Timeout Protection**: To handle edge cases where mode transitions fail to complete properly, the system implements a one-hour timeout. If a character's last mode transition timestamp exceeds this threshold, the system allows a forced transition, preventing characters from becoming permanently locked in an inaccessible state.

**Error Messaging**: When transitions are blocked, the system provides clear error messages indicating why the transition failed, guiding players to properly exit their current game mode before switching.

### 7.3 Input Validation

The incremental module leverages the Eidolon Engine's established validation patterns to ensure data integrity across all API endpoints. This consistent approach prevents malformed data from entering the system while providing clear feedback to clients.

The validation system performs several types of checks:

**UUID Validation**: All character and story identifiers must conform to proper UUID v4 format. The system validates these identifiers before any database operations, preventing injection attempts and ensuring referential integrity.

**String Validation**: Text inputs such as story IDs and decision choices undergo length and content validation. The system enforces maximum lengths appropriate to each field type and sanitizes input to prevent malicious content.

**Request Structure**: Each API endpoint validates the complete request structure, ensuring all required fields are present and properly typed. Missing or malformed fields result in detailed error responses that help clients correct their requests.

**Business Logic Validation**: Beyond format checking, the system validates that requested operations make sense within the game context. This includes verifying story availability, checking prerequisites, and ensuring characters meet requirements for requested actions.

## 8. Monitoring and Analytics

### 8.1 CloudWatch Metrics

The incremental module integrates with the Eidolon Engine's established monitoring infrastructure, using CloudWatch for comprehensive metrics and logging. This integration provides real-time visibility into system health and player engagement.

The monitoring system captures several categories of events:

**Story Lifecycle Events**: Every story start, completion, and abandonment is logged with structured data including story ID, character ID, and story type. These logs enable tracking of player engagement patterns and story popularity.

**Performance Metrics**: The system emits custom CloudWatch metrics to track story completion rates, outcome distributions, and processing times. Metrics are organized under the 'eidolon/incremental' namespace with dimensions for story ID and outcome type, enabling detailed analysis of content performance.

**Player Behavior Analytics**: The system tracks decision patterns, time-to-completion statistics, and abandonment rates. This data helps content creators understand which stories resonate with players and where difficulty adjustments might be needed.

### 8.2 Error Tracking

The error handling strategy leverages existing Eidolon patterns to ensure consistent error reporting and recovery across the incremental module.

**Structured Error Handling**: The system implements a hierarchical error handling approach. Validation errors generate warning-level logs with field-specific details, helping identify common user mistakes. System errors trigger error-level logs with full stack traces, enabling rapid debugging.

**Contextual Error Information**: All error logs include contextual data such as AWS request IDs, character states, and story progression details. This context accelerates troubleshooting by providing complete information about the circumstances leading to errors.

**User-Friendly Responses**: When errors occur, the system returns appropriate HTTP status codes with clear, actionable error messages. Validation errors include specific field names and requirements, while system errors provide request IDs for support reference without exposing internal details.

## 9. Deployment Strategy

### 9.1 CDK Integration

The incremental module seamlessly integrates into the existing AWS CDK infrastructure, adding new Lambda functions to the established deployment patterns. This approach ensures consistency across the entire Eidolon Engine ecosystem.

The deployment adds seven new Lambda functions to support story operations:

**API Functions**: Five functions handle client-facing operations including story retrieval, story initiation, decision submission, outcome retrieval, and story abandonment. Each function follows the established naming convention and handler patterns.

**Processing Functions**: Two backend functions manage the story engine. The segment poller runs on a scheduled basis to check for completed segments, while the process segment function handles the actual outcome calculations and state updates.

**EventBridge Integration**: A new EventBridge rule triggers the segment poller every 10 seconds. This rule can be dynamically enabled or disabled based on whether any stories are active, optimizing costs during idle periods.

### 9.2 API Gateway Routes

The incremental APIs extend the existing API Gateway configuration with six new routes, maintaining consistency with established URL patterns and authentication requirements.

**Story Management Routes**: GET endpoints allow retrieving available stories and current story state. POST endpoints handle story initiation and abandonment. These routes follow RESTful conventions while accommodating the unique requirements of time-based gameplay.

**Segment Interaction Routes**: A POST endpoint accepts player decisions for decision segments, while a GET endpoint retrieves completed segment outcomes. These routes implement proper idempotency to handle network retries gracefully.

**Route Organization**: All incremental routes are grouped under logical paths that clearly indicate their purpose, making the API intuitive for client developers while maintaining backward compatibility with existing endpoints.

### 9.3 Database Updates

The deployment extends the DynamoDB infrastructure with new tables that follow established patterns while supporting incremental-specific requirements.

**Table Definitions**: Five new tables support the incremental module: Story and Segments tables store content definitions, ActiveSegments tracks in-progress gameplay, Opponents defines combat encounters, and History preserves completed story records. Each table uses appropriate key structures for efficient querying.

**Global Secondary Indexes**: Two GSIs optimize critical query patterns. The EndTimeIndex on ActiveSegments enables efficient polling for completed segments, while the CharacterNameIndex on the Characters table ensures name uniqueness across all players.

**Schema Consistency**: All new tables follow the established DynamoDB patterns, using HASH and RANGE keys appropriately, maintaining consistent field naming conventions, and implementing proper data types for seamless integration with existing code patterns.

## 10. Cost Analysis

### 10.1 Simplified Cost Structure

With the DynamoDB polling approach:

**Monthly Costs (10,000 concurrent users)**:

- Lambda invocations: ~$100-150 (includes polling overhead)
- EventBridge rules: <$1 (single polling rule)
- DynamoDB (pay-per-request): ~$150-250 (includes GSI queries)
- **Total: ~$250-400/month**

### 10.2 Cost Optimization

1. **Lambda Optimization**:

   - Use appropriate memory allocation (128MB typical)
   - Disable polling when no active stories

2. **Polling Efficiency**:

   - 10-second intervals balance precision vs cost
   - Process multiple segments per poll cycle
   - Use GSI for efficient time-based queries

3. **DynamoDB Efficiency**:
   - Delete segments after processing
   - Batch process segment updates
   - Efficient GSI usage for polling queries

## 11. Implementation Plan

### 11.1 Phase 1: Core Story System

- Create story definition table with GSI
- Implement core Lambda functions
- DynamoDB polling infrastructure
- Manual story creation tools

### 11.2 Phase 2: Flutter Integration

- Story selection screen
- Story display/decision UI
- Polling implementation
- Error handling

### 11.3 Phase 3: Game Mechanics

- Skill check calculations
- Equipment integration
- Progression balancing
- Daily story reset logic

### 11.4 Phase 4: Polish & Testing

- Performance optimization
- Comprehensive testing
- Analytics implementation
- Documentation

## 12. Conclusion

This simplified technical design leverages the existing Eidolon Engine infrastructure to implement the incremental game with minimal additional complexity. By using shared tables, dual-purpose Lambda functions, and DynamoDB polling with EventBridge, the system can support 10,000 concurrent users while maintaining consistency with the MUD game mechanics and keeping operational costs low.

Key architectural decisions:

- Shared DynamoDB tables eliminate synchronization needs
- DynamoDB + 10-second polling provides scalable timing
- GSI enables efficient time-based queries
- Enable/disable polling based on active stories
- Existing Lambda patterns ensure consistency
- GameMode field provides simple mode exclusivity
- 10-second resolution balances precision and cost
