# Eidolon Engine Incremental Game Technical Design Document

## 1. Executive Summary

This document provides the technical design specifications for implementing the Incremental Game component of the Eidolon Engine. It details the system architecture, data flows, API specifications, and integration patterns required to deliver a timer-based story progression system that seamlessly integrates with the existing MUD infrastructure using a simplified serverless approach.

### 1.1 Key Design Updates

The incremental system implements a timer-based processing architecture with four distinct segment types, each with specific processing requirements:

Major architectural decisions:

1. **Four Segment Types**:
   - **Rest**: Time-bound segments where wounds heal naturally based on their HealAt timestamps
   - **Decision**: Await player input via API or apply default on timeout
   - **Narrative**: Story with skill challenges, processed via SQS/ops_process_segment
   - **Combat**: Battle encounters, processed via SQS/ops_process_segment

2. **Processing Flow**:
   - Segments created when players start stories or make decisions
   - EventBridge polls every 30 seconds for expired segments
   - Decision/Rest handled directly by poller
   - Narrative/Combat queued to SQS for mechanical processing
   - Results written to History table
   - New API endpoint retrieves results for client display

3. **History Table**: 
   - Stores processed segment results for client retrieval
   - Composite key (CharacterID, StoryID) for efficient queries
   - Contains narrative events, skill check results, combat logs

4. **Smart Polling System**: 
   - 30-second EventBridge polling with SSM parameter control
   - Automatic enable/disable based on active segments
   - Handles decision defaults when timers expire
   - Queues complex segments to SQS

5. **MUD Mechanics Integration**: 
   - Static checks for narrative challenges
   - Opposed checks for combat simulation
   - Results stored in history for client narrative generation

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
3. **Timing Service**: EventBridge-triggered Lambda polling at 30-second intervals
   - SSM parameter controls polling state (run/stop)
   - SQS queue ensures reliable segment processing
   - Automatic enable/disable based on active segments
4. **Stateless Compute**: Lambda functions handle all game logic
   - Segment processing happens immediately on creation
   - Polling system only applies pre-calculated results
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

**Important Design Constraint**: Each segment should contain approximately 10 events (narrative beats, challenges, or combat rounds) and must not exceed 20 events. This ensures segments remain manageable in scope while providing meaningful progression chunks for players.

**DefaultStatus Field**: All segment types now include a DefaultStatus field that provides fallback status text when ShortStatus is not available. This ensures the UI always has descriptive text to display during segment progression.

```python
# Decision segment example
{
    "StoryID": "forest-adventure-uuid",   # HASH
    "SegmentID": "seg-uuid-001",          # RANGE
    "SegmentType": "decision",
    "ShortStatus": "Choosing your path",
    "DefaultStatus": "Contemplating your options",  # Status shown between events
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
    "DefaultStatus": "Walking through the dark forest",  # Status shown between events
    "SegmentDuration": 600,               # 10 minutes
    "NextSegmentID": "seg-uuid-003",     # Single linked list
    "Challenges": [
        {"attribute": "agility", "skill": "perception", "difficulty": 8, "attempts": 2},
        {"attribute": "strength", "skill": "survival", "difficulty": 7, "attempts": 3}
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
    "DefaultStatus": "Engaged in combat",  # Status shown between events
    "SegmentDuration": 120,               # 2 minutes for combat
    "NextSegmentID": "seg-uuid-004",
    "Combat": {
        "OpponentID": "a7b8c9d0-1e2f-3a4b-5c6d-7e8f9a0b1c2d",
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
# Tracks runtime segment instances with front-loaded processing
{
    # Identity
    "ActiveSegmentID": "active-seg-uuid-123",  # HASH - Unique ID for this instance
    "CharacterID": "char-uuid-456",            # GSI - CharacterID-index
    "PlayerID": "player-uuid-123",             # For ownership validation
    
    # Story Context
    "StoryID": "forest-adventure-uuid",        # Parent story
    "StoryTitle": "The Whispering Woods",      # Cached for display
    "SegmentID": "seg-uuid-002a",              # Definition in Segments table
    "SegmentType": "narrative",                # narrative|combat|decision|rest
    
    # Timing
    "StartTime": 1737000300,                   # Unix timestamp when created
    "EndTime": 1737003900,                     # GSI - EndTimeIndex - When segment should advance
    
    # Processing State (Front-loaded)
    "ProcessedAt": 1737000305,                 # When outcomes calculated
    "ProcessingStatus": "processed",           # pending|processed|failed|awaiting_decision
    "ProcessingError": null,                   # Error details if failed
    
    # Outcomes (Set by processor)
    "Outcome": "minimal",                      # death|failure|minimal|normal|exceptional
    "NextSegmentID": "seg-uuid-003",           # Pre-calculated next segment
    
    # Client Events - Complete narrative sequence for progressive display
    "ClientEvents": [
        {
            "eventType": "narrative",
            "title": "Into the Woods",
            "description": "The morning mist clings to the forest floor as you step into the shadowy forest...",
            "data": {}
        },
        {
            "eventType": "skillCheck",
            "title": "Perception Challenge",
            "description": "You scan the forest for hidden dangers...",
            "data": {
                "skill": "perception",
                "attribute": "agility",
                "effectiveScore": 12,
                "difficulty": 8,
                "sigma": 0.82,
                "success": true,
                "skillXPAwarded": 0.25,
                "attributeXPAwarded": 0.025
            }
        },
        {
            "eventType": "skillCheck", 
            "title": "Perception Challenge - Second Attempt",
            "description": "The shadows play tricks on your eyes...",
            "data": {
                "skill": "perception",
                "attribute": "agility",
                "effectiveScore": 12,
                "difficulty": 8,
                "sigma": -0.45,
                "success": false,
                "skillXPAwarded": 0.125,
                "attributeXPAwarded": 0.0125
            }
        },
        {
            "eventType": "narrative",
            "title": "Lost in the Woods",
            "description": "Despite your best efforts, the forest paths confuse you. You wander in circles...",
            "data": {}
        },
        {
            "eventType": "status",
            "title": "Wound Taken",
            "description": "The thorny undergrowth scratches you as you push through.",
            "data": {
                "woundType": "bashing",
                "amount": 1
            }
        },
        {
            "eventType": "reward",
            "title": "Experience Gained",
            "description": "You learn from your struggles in the forest.",
            "data": {
                "skillsImproved": {
                    "perception": 0.375,
                    "survival": 0.75
                },
                "attributesImproved": {
                    "agility": 0.0375,
                    "strength": 0.075
                }
            }
        }
    ],
    
    # Character Updates - All changes to apply when segment completes
    "CharacterUpdates": {
        "Wounds": [{"DamageType": "bashing", "HealAt": "2025-01-15T14:30:00Z"}],
        "SkillXP": {
            "perception": 0.375,               # Total from all skill checks
            "survival": 0.75
        },
        "AttributeXP": {
            "agility": 0.0375,                 # 10% of skill XP
            "strength": 0.075
        }
    },
    
    # History Entry - Pre-formatted for History table
    "HistoryEntry": {
        "SegmentID": "seg-uuid-002a",
        "SegmentType": "narrative",
        "Outcome": "minimal",
        "ResultText": "You stumble through the forest, learning from your mistakes.",
        "ChallengeResults": [
            {"skill": "perception", "success": true, "sigma": 0.82},
            {"skill": "perception", "success": false, "sigma": -0.45},
            {"skill": "survival", "success": true, "sigma": 0.63}
        ]
    },
    
    # Decision Tracking
    "Decision": null,                          # Choice made (decision segments)
    "DecisionMadeAt": null,                    # When player decided
    
    # Advancement State
    "Transmitted": null,                       # Set true when sent to SQS
    "TransmittedAt": null,                     # Unix timestamp when sent
    "RunningFlag": null                        # Request ID of processor
}

# Global Secondary Indexes
GSI: CharacterID-index
  - CharacterID field only
  - Projection: ALL
  - For querying active segments by character

GSI: EndTimeIndex
  - EndTime field only
  - Projection: ALL
  - For finding segments ready to process
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
        {"ItemID": "b47ac10b-58cc-4372-a567-0e02b2c3d483", "chance": 0.5},  # Healing potion
        {"ItemID": "d47ac10b-58cc-4372-a567-0e02b2c3d481", "chance": 0.3}   # Rusty blade
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

#### 3.1.6 StoryHistory Table

```python
# Tracks overall story attempts and completions
{
    "CharacterID": "char-uuid-456",           # HASH
    "StoryID": "forest-adventure-uuid",       # RANGE
    "StoryTitle": "The Whispering Woods",     # Cached for display
    "StoryType": "daily",                     # one-time|daily|repeatable
    "StartedAt": "2025-01-23T08:00:00Z",     # When story began
    "FinishedAt": "2025-01-23T10:30:00Z",    # When story ended
    "FinalOutcome": "normal",                 # death|failure|minimal|normal|exceptional|abandoned
    "TotalDuration": 9000,                    # Seconds from start to finish
    "TotalSegments": 12,                      # Number of segments completed
    "Rewards": {                              # Aggregated rewards from all segments
        "skillXP": {
            "perception": 2.5,
            "survival": 3.0,
            "melee": 1.5
        },
        "attributeXP": {
            "agility": 0.25,
            "strength": 0.45,
            "intelligence": 0.15
        },
        "items": ["herb_bundle", "goblin_pouch", "rusty_blade"],
        "gold": 150,
        "finalRoom": 42                       # Where character ended up
    },
    "AbandonedAt": null,                      # Set if story was abandoned
    "AbandonedReason": null                   # Player-provided or system reason
}
```

#### 3.1.7 SegmentHistory Table

```python
# Detailed segment-by-segment progression records
{
    "CharacterID": "char-uuid-456",           # HASH
    "CompletedAt": "2025-01-23T08:10:00Z",   # RANGE - When segment completed
    "SegmentID": "seg-uuid-002a",             # For reference
    "StoryID": "forest-adventure-uuid",       # Parent story
    "ActiveSegmentID": "active-seg-uuid-123", # Original runtime instance
    "SegmentType": "narrative",               # narrative|combat|decision|rest
    "Outcome": "minimal",                     # Segment outcome
    "Duration": 600,                          # Actual time taken (seconds)
    
    # Segment-specific details
    "Decision": null,                         # For decision segments
    "ChallengeResults": [                     # For narrative segments
        {"skill": "perception", "success": true, "sigma": 0.82},
        {"skill": "perception", "success": false, "sigma": -0.45},
        {"skill": "survival", "success": true, "sigma": 0.63}
    ],
    "CombatSummary": null,                    # For combat segments: rounds, wounds, etc.
    
    # Applied changes
    "CharacterUpdates": {
        "SkillXP": {"perception": 0.375, "survival": 0.75},
        "AttributeXP": {"agility": 0.0375, "strength": 0.075},
        "Wounds": [{"DamageType": "lethal", "HealAt": "2025-01-15T20:00:00Z"}],
        "Items": {"added": [], "removed": []}
    },
    
    # Narrative record
    "NarrativeEvents": [                      # Key events shown to player
        "Entered the dark forest",
        "Failed to spot the hidden trap",
        "Successfully navigated using survival skills"
    ]
}
```

- **StoryHistory**: High-level story tracking for achievements and progression
- **SegmentHistory**: Detailed play-by-play for analysis and debugging
- **Separation Benefits**:
  - Story completion queries don't scan segment details
  - Segment analysis doesn't require story context
  - Stories provide permanent achievement record
  - Cleaner data model with appropriate granularity

### 3.2 Data Access Patterns

#### 3.2.1 Primary Access Patterns

1. **Get Available Stories**: Read character's AvailableStories list
2. **Check Story Status**: Check if story in Abandoned/Completed lists
3. **Get Active Segments**: Query ActiveSegments by CharacterID
4. **Process Segment Completion**: Update ActiveSegments record
5. **Update Story Lists**: Move story IDs between Available/Abandoned/Completed

#### 3.2.2 Global Secondary Index Usage

The system uses two critical GSIs for efficient operations:

- **CharacterID-index**: Enables querying all active segments for a character
- **EndTimeIndex**: Powers the polling system to find segments ready for completion
- These indexes are essential for the 30-second polling cycle to remain performant

### 3.3 Transaction Design Patterns

#### 3.3.1 DynamoDB Transaction Considerations

**GUIDANCE**: Use DynamoDB transactions judiciously, balancing consistency requirements with performance and cost (2x capacity consumption).

**Transaction Limitations**:
- Maximum 100 unique items per transaction
- Maximum 4MB total size
- All items must be in same Region
- Cannot target same item multiple times
- Consumes double the read/write capacity units

#### 3.3.2 Story Start Transaction (Recommended)

When starting a story, use a transaction to prevent orphaned segments:

```
TransactWriteItems:
1. Update Character:
   - ConditionExpression: GameMode = "None"
   - Set GameMode = "Incremental"
   - Set ActiveStoryID and ActiveSegmentID
   - Remove story from AvailableStories

2. Put ActiveSegments:
   - ConditionExpression: attribute_not_exists(ActiveSegmentID)
   - Create segment with timing data

3. Put History:
   - Create story start record
```

**Rationale**: Prevents partial state where character is locked but no segment exists.

#### 3.3.3 Segment Processing Patterns

For high-frequency segment advancement, consider non-transactional approaches:

**Option 1: Idempotent Operations**
- Use unique request IDs
- Check if already processed before applying updates
- Store processing results for retry scenarios

**Option 2: Eventual Consistency**
- Update character state first
- Write history asynchronously
- Use conditional updates to prevent conflicts

**Option 3: Transaction for Story Completion Only**
- Use standard operations during gameplay
- Use transaction only for final cleanup
- Balances consistency with performance

#### 3.3.4 Story Abandonment Transaction (Recommended)

Clean state transitions benefit from atomic operations:

```
TransactWriteItems:
1. Update Character:
   - ConditionExpression: GameMode = "Incremental"
   - Set GameMode = "None"
   - Clear ActiveStoryID
   - Add to AbandonedStories

2. Delete ActiveSegments:
   - Remove all segments for story

3. Put StoryHistory:
   - Record abandonment
```

#### 3.3.5 Design Trade-offs

**Use Transactions When**:
- State transitions must be atomic (start/end story)
- Multiple tables must remain consistent
- Failure would leave unrecoverable state

**Avoid Transactions When**:
- Operations are frequent (every segment)
- Eventual consistency is acceptable
- Cost is a primary concern
- Operations can be made idempotent

## 4. API Design

### 4.1 RESTful Endpoints

All endpoints follow existing Lambda patterns and extend the current API Gateway.

**Field Naming Conventions:**

- All API request and response fields use PascalCase
- Acronyms in field names are fully capitalized (e.g., StoryID not StoryId, ItemID not ItemId, PlayerID not PlayerId)
- This maintains consistency with DynamoDB field names

#### 4.1.1 Character Management APIs

**GET /archetypes**

```python
# Lambda: api_get_archetypes
Purpose: Retrieve player-available archetypes for character creation
Authentication: Required (Cognito JWT)
Query Parameters: None
Response: {
    "Archetypes": [
        {
            "ArchetypeName": "Warrior",
            "Description": "A strong fighter skilled in combat",
            "Attributes": {"strength": 4, "agility": 2, ...},
            "Skills": {"melee": 3, "dodge": 2, ...},
            "StartRoom": 0,
            "StartingItems": [
                {"PrototypeID": "sword-uuid", "Slot": "RightHand", "IsWorn": false}
            ],
            "Health": 12,
            "Essence": 2,
            "AvailableStories": ["tutorial-uuid", "basic-quest-uuid"]
        }
    ],
    "Count": 5
}

Notes:
- Archetypes are filtered to show only Player=true records
- Attribute and skill keys are normalized to lowercase
- AvailableStories determines initial story access for new characters
- Results are cached at Lambda instance level for performance
```

**GET /characters**

```python
# Lambda: api_list_characters
Purpose: List all characters for the authenticated player
Query Parameters: None (uses authenticated player ID from JWT)
Response: {
    "Characters": [
        {
            "CharacterID": "char-uuid-456",
            "CharacterName": "Thorin",
            "Dead": false
        },
        {
            "CharacterID": "char-uuid-789",
            "CharacterName": "Gandalf",
            "Dead": true
        }
    ]
}

Notes:
- Returns minimal character information for selection screens
- Character data comes from Player table's CharacterList field
- Dead status indicates if character needs resurrection
- Used by Flutter client for character selection flow
```

**GET /character**

```python
# Lambda: api_get_character
Purpose: Retrieve full character data including active segments
Query Parameters: characterId (required)
Response: {
    "Character": {
        "CharacterID": "char-uuid-456",
        "CharacterName": "Thorin",
        "PlayerID": "player-uuid-123",
        "GameMode": "Incremental",
        "RoomID": 5,
        "Inventory": {"RightHand": "sword-uuid", "LeftHand": "shield-uuid"},
        "InventoryDetails": {
            "RightHand": {
                "ItemID": "sword-uuid",
                "name": "Iron Sword",
                "description": "A well-crafted iron sword",
                "mass": 2.5,
                "value": 50,
                "wearable": false,
                "wornOn": null
            },
            "LeftHand": {
                "ItemID": "shield-uuid",
                "name": "Wooden Shield",
                "description": "A sturdy wooden shield",
                "mass": 3.0,
                "value": 30,
                "wearable": false,
                "wornOn": null
            }
        },
        "Attributes": {"strength": 4, "agility": 2, "endurance": 3},  // Normalized to lowercase
        "Skills": {"melee": 3, "dodge": 2, "perception": 1},          // Normalized to lowercase
        "Essence": 3,
        "MaxHealth": 12,
        "MaxEssence": 5,
        "Hidden": false,
        "Wounds": [],
        "CharState": "standing",
        "AvailableStories": ["forest-adventure-uuid", "daily-patrol-uuid"],
        "CompletedStories": ["intro-quest-uuid"],
        "AbandonedStories": [],
        "ActiveStoryID": "forest-adventure-uuid",
        "ActiveSegmentID": "active-seg-uuid-123",
        "Archetype": "Warrior",
        "Resources": {"gold": 100},
        "Progress": {},
        "CreatedAt": "2025-01-15T10:00:00Z",
        "UpdatedAt": "2025-01-23T08:00:00Z",
        "LastPlayed": "2025-01-23T08:00:00Z"
    },
    "ActiveSegment": {  // Only included if character has an active segment
        "ActiveSegmentID": "active-seg-uuid-123",
        "StoryID": "forest-adventure-uuid",
        "StoryTitle": "The Whispering Woods",
        "SegmentID": "seg-uuid-002a",
        "SegmentType": "narrative",
        "Status": "active",
        "StartTime": 1737000300,
        "EndTime": 1737003900,
        "ProcessingStatus": "processed",
        "ShortStatus": "Navigating the moonlit path"  // From segment or DefaultStatus
    }
}

Error Cases:
- 400: Invalid character ID format
- 401: Not authenticated or player ID mismatch
- 404: Character not found
- 500: Database operation failed

Notes:
- Attributes and Skills keys are normalized to lowercase for Flutter compatibility
- InventoryDetails enriches raw inventory UUIDs with full item information
- ActiveSegment field only present when character has an active story segment
- All numeric values converted from DynamoDB Decimal to standard floats
- Requires ITEMS_TABLE and ACTIVE_SEGMENTS_TABLE environment variables
```

#### 4.1.2 Story Management APIs

**GET /stories**

```python
# Lambda: api_get_stories
Purpose: Retrieve available stories for character
Query Parameters: characterId
Response: {
    "Stories": [
        {
            "StoryID": "forest-adventure",
            "Title": "The Whispering Woods",
            "Description": "A mysterious forest beckons adventurers",
            "Type": "daily",  // one-time, daily, or repeatable
            "Available": true,
            "CooldownRemaining": 0,  // seconds until available
            "EstimatedDuration": 3600  // seconds
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
    "CharacterID": "char-uuid-456",
    "StoryID": "forest-adventure"
}
Response: {
    "success": true,
    "segment": {
        "activeSegmentId": "active-seg-uuid-123",
        "segmentType": "narrative",
        "startTime": 1737000000,
        "endTime": 1737000600,
        "shortStatus": "Navigating the Dark Forest",
        "duration": 600
    }
}
Error Cases:
- 409: Character already in story or MUD mode
- 403: Story not available
- 400: Invalid parameters
```

**GET /stories/current**

```python
# Lambda: api_get_current_story
Purpose: Get active story state
Query Parameters: characterId
Response: Current story and segment details
```

#### 4.1.3 Segment APIs

**POST /segments/decision**

```python
# Lambda: api_submit_decision
Purpose: Submit player decision
Request: {
    "CharacterID": "char-uuid-456",
    "Decision": "take-left-path"
}
Response: {
    "Accepted": true,
    "NextSegmentTime": 1737003600
}
```

**GET /segments/status**

```python
# Lambda: api_get_segment_status
Purpose: Check if segment is ready for advancement
Query Parameters: characterId
Response: {
    "segmentReady": true,
    "activeSegmentId": "active-seg-uuid-123",
    "endTime": 1737000600,
    "currentTime": 1737000605,
    "processingStatus": "processed"
}

Notes:
- Called frequently by client near segment completion
- Used to detect stuck segments (ready but not advanced)
- Simple status check without heavy data transfer
```

**GET /segments/history**

```python
# Lambda: api_get_segment_history
Purpose: Retrieve processed segment results from history
Query Parameters: characterId, segmentId
Response: {
    "success": true,
    "segmentComplete": true,
    "outcome": "minimal",
    "events": [
        {
            "eventType": "narrative",
            "title": "Into the Woods",
            "description": "You step into the shadowy forest...",
            "data": {}
        },
        {
            "eventType": "skillCheck",
            "title": "Navigation Challenge",
            "description": "You attempt to find your way...",
            "data": {
                "skill": "survival",
                "attribute": "intelligence",
                "success": false,
                "sigma": -0.43
            }
        },
        {
            "eventType": "combat",
            "title": "Goblin Attack",
            "description": "A goblin scout leaps from the shadows!",
            "data": {
                "rounds": 5,
                "playerWounds": 2,
                "victory": true
            }
        }
    ],
    "nextSegment": {
        "activeSegmentId": "active-seg-uuid-124",
        "segmentType": "decision",
        "duration": 300
    }
}

Notes:
- Called by client during segment runtime to display results
- Returns empty events array if segment not yet processed
- Narrative and combat segments only - not for rest/decision
```

**POST /stories/abandon**

```python
# Lambda: api_abandon_story
Purpose: Exit current story
Query Parameters: characterId=char-uuid-456
Request Body: None (uses query parameter)
Response: {
    "Abandoned": true,
    "CharacterID": "char-uuid-456",
    "StoryID": "forest-adventure-uuid",
    "StoryTitle": "The Whispering Woods",
    "Message": "Story abandoned successfully"
}
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

### 5.1 Lambda Function Architecture Pattern

Each Lambda function in the Eidolon Engine follows a strict architectural pattern to maintain consistency, testability, and separation of concerns:

#### Lambda Handler Structure

Each Lambda function must have a Lambda handler which handles the event, calls a function with the business logic, then handles the response. The business logic function will call functions from the `./eidolon` library to perform their tasks. None of the database or I/O code should be present in the Lambda function beyond the event feed to the handler and the response back to the API.

**Example Pattern:**

```python
def lambda_handler(event: dict, context: object) -> dict:
    """Lambda entry point - handles AWS-specific concerns."""
    # 1. Log invocation
    # 2. Handle CORS preflight
    # 3. Extract and validate authentication
    # 4. Parse request body
    # 5. Call business logic function
    # 6. Format and return response with CORS headers

def business_logic_function(param1: str, param2: str) -> dict:
    """Pure business logic - testable and AWS-agnostic."""
    # 1. Validate business rules
    # 2. Call eidolon library functions
    # 3. Orchestrate operations
    # 4. Return success/error dictionary
```

This pattern ensures:

- Lambda handlers remain thin and focused on AWS integration
- Business logic is testable without AWS dependencies
- Database operations are centralized in the eidolon library
- Error handling is consistent across all functions

### 5.2 Core Lambda Functions

All Lambda functions follow the existing pattern in the `lambda/` directory and use the `eidolon` package for standardized responses, logging, and error handling.

#### 5.2.1 api_get_stories

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

#### 5.2.2 api_start_story

```python
"""Initialize story participation."""
# Key Operations:
- Verify character ownership and GameMode is "None"
- Validate story is in character's AvailableStories list
- Load story metadata and first segment from DynamoDB
- Use DynamoDB transaction to atomically:
  - Update Character table:
    - Set GameMode to "Incremental"
    - Set ActiveStoryID and ActiveSegmentID
    - Remove story from AvailableStories
  - Create ActiveSegments record with:
    - Unique ActiveSegmentID
    - Start/End times based on segment duration
  - Create History table entry for tracking
- Return formatted segment response based on type
# Transaction Design:
- Use TransactWriteItems with conditional expressions
- Character update: ConditionExpression GameMode = "None"
- Segment creation: ConditionExpression attribute_not_exists
- Handle TransactionCanceledException for conflicts
# Error Handling:
- 401: Authentication failures
- 403: Story not available to character
- 409: Character already in game mode or transaction conflict
- 400: Invalid request parameters
```

#### 5.2.3 api_submit_decision

```python
"""Record player decision and schedule next segment."""
# Key Operations:
- Validate decision against current segment options
- Update ActiveSegment record with decision
- For decision segments, outcomes are simple - just record the choice
- Return acknowledgment with next segment timing
```

#### 5.2.4 ops_process_segment

```python
"""Process narrative and combat segments from SQS queue."""
# Trigger: SQS messages from segment poller
# Segment Types Handled: NARRATIVE and COMBAT only
# Key Operations:
- Receives SQS messages containing segment data
- For each segment in batch:
  - Extract ActiveSegmentID and metadata from message
  - Load active segment, segment definition, and character data
  - Evaluate wound healing: remove wounds where current time > HealAt
  - Recalculate health as MaxHealth - len(wounds)
  
  # Narrative Segment Processing:
  - Run all challenge attempts using simulated MUD mechanics
  - Calculate effective score: skill + attribute
  - Use normal distribution for outcome (sigma values)
  - Determine overall outcome based on average sigma
  - Generate narrative events for each challenge
  
  # Combat Segment Processing:
  - Load opponent data from Opponents table
  - Simulate round-by-round combat using opposed checks
  - Track wounds inflicted on both sides
  - Determine victory/defeat based on health/rounds
  - Generate combat log with round details
  
  # After Processing:
  - Write complete results to History table:
    - Outcome (death/failure/minimal/normal/exceptional)
    - Events array for client display
    - Challenge results or combat log
  - Create next segment if story continues
  - Update character GameMode to "None" if story ends
  - Delete processed ActiveSegment record
  
- Check if ActiveSegments table is empty
- Update SSM parameter to "stop" if no segments remain

# Error Handling:
- Return failed message IDs for SQS retry
- Log processing failures with full context
- Failed segments remain in queue for retry
```

#### 5.2.5 ops_segment_poller

```python
"""Find and handle expired segments (EventBridge triggered every 30 seconds)."""
# Trigger: EventBridge rule every 30 seconds
# Key Operations:
- Read SSM parameter /eidolon/segment-poller-state
- Query for expired segments where EndTime <= current time
- Process by segment type:
  
  # Rest Segments:
  - Healing is evaluated at the beginning of each segment
  - Expired wounds (where current time > HealAt) are removed from wounds list
  - Simply advance to next segment or complete story
  - Delete segment record
  
  # Decision Segments (expired without player input):
  - Check if Decision field is null
  - Apply DefaultDecision from segment definition
  - Update segment with decision
  - Create next segment based on decision
  - Delete current segment
  
  # Narrative/Combat Segments:
  - Add to SQS queue for mechanical processing
  - Message includes: ActiveSegmentID, CharacterID, StoryID, SegmentID, SegmentType
  - ops_process_segment will handle skill checks/combat simulation
  
- Batch SQS operations (max 10 messages per batch)
- State management:
  - If parameter "stop" and segments found: set to "run"
  - If parameter "run" and no segments: check if table empty
  - If table empty: set parameter to "stop"
  
# Responsibilities:
- Rest: Just advance story (no mechanics)
- Decision: Apply defaults and advance
- Narrative/Combat: Queue for processing
```


#### 5.2.6 cognito_new_player

```python
"""Create player record after Cognito registration."""
# Trigger: Cognito Post Confirmation
# Key Operations:
- Extract user UUID (sub) and email from Cognito event
- Create Player table record with initial empty state
- Record serves both MUD and Incremental games
# Error Handling:
- Logs errors but returns event to continue Cognito flow
- Prevents registration failures if player record creation fails
# Note: System-level function for player lifecycle
```

#### 5.2.7 cognito_delete_player

```python
"""Complete player data deletion for GDPR compliance."""
# Triggers:
- CloudWatch Events from Cognito user deletion
- API Gateway with authenticated request
- Direct invocation with player_id
# Key Operations:
- Delete from Player table and all associated data
- Remove all characters and their incremental data
- Clear from ActiveSegments, History tables
- Remove from all game-related tables
# Response:
- Returns deletion summary with counts
- Status 207 if partial deletion (some errors)
- Supports multiple trigger sources with appropriate response formats
# Note: Critical for GDPR compliance and data cleanup
```

#### 5.2.8 api_get_segment_history

```python
"""Retrieve processed segment results from History table."""
# Key Operations:
- Validate character ownership
- Query History table by CharacterID and SegmentID
- Return processed results for narrative/combat segments
- Empty response if segment not yet processed

# Response Structure:
- segmentComplete: boolean indicating if processed
- outcome: death/failure/minimal/normal/exceptional
- events: Array of narrative events for client display
  - eventType: narrative/skillCheck/combat
  - title: Brief description
  - description: Full narrative text
  - data: Type-specific details (skill checks, combat rounds)
- nextSegment: Information about following segment if any

# Use Cases:
- Client polls during narrative segment runtime
- Client polls during combat segment runtime  
- Display results progressively during timer countdown
- Not used for rest or decision segments

# Error Handling:
- 404 if segment not found
- 403 if character not owned by player
- Empty events array if not yet processed
```

### 5.3 Polling System Architecture

The segment advancement system uses a sophisticated polling mechanism with EventBridge, SQS, and SSM Parameter Store to reliably process completed segments while maintaining cost efficiency.

#### EventBridge Rule Configuration

The system uses a single EventBridge rule named 'eidolon-segment-poller' that triggers every 30 seconds. This rule starts disabled and activates only when players have active story segments. The 30-second interval balances timely segment advancement with operational costs.

#### SSM Parameter Control

The polling system uses SSM Parameter Store (`/eidolon/segment-poller-state`) to coordinate state across Lambda executions:

- **"run"**: Polling is active, segments need processing
- **"stop"**: No active segments, polling should disable itself

This parameter enables graceful startup/shutdown and prevents race conditions between concurrent executions.

#### Dual-Scan Polling Strategy

The segment poller implements a two-phase scanning approach:

**Phase 1 - Ready Segments**:
- Queries EndTimeIndex for segments where `EndTime <= (CurrentTime + 15)`
- The 15-second buffer (half the polling interval) ensures segments are found before they expire
- Filters for segments without `Transmitted` or `RunningFlag` attributes
- Claims segments by setting `Transmitted = true` with conditional updates
- Successfully claimed segments are batched to SQS

**Phase 2 - Stuck Segment Recovery**:
- Identifies segments where `Transmitted = true` AND `TransmittedAt < (CurrentTime - 900)`
- These are segments that were queued but not processed within 15 minutes
- Clears the `RunningFlag` without condition checking (force clear)
- Updates `TransmittedAt` to current time
- Re-queues for processing with warning logs

#### SQS Integration

The poller sends discovered segments to an SQS queue for processing:

- Batches up to 10 segments per SQS send operation
- Each message contains the ActiveSegmentID
- SQS provides reliable delivery and automatic retries
- Dead letter queue captures persistent failures

#### Segment Processing Flow

When `ops_advance_story` receives an SQS message:

1. **Ownership Claim**: Sets `RunningFlag = RequestID` with conditional update
2. **Validation**: Ensures `ProcessingStatus = "processed"`
3. **Application**: Applies pre-calculated CharacterUpdates
4. **Progression**: Creates next segment if story continues
5. **Cleanup**: Deletes completed segment

#### Dynamic Enable/Disable Logic

The polling system self-manages based on table state:

**When Starting Stories**:
- `api_start_story` checks SSM parameter
- If "stop", sets to "run" and enables EventBridge rule
- Ensures polling is active for new segments

**During Polling Cycles**:
- If parameter is "stop" but segments found: set to "run"
- If parameter is "run" but table empty: set to "stop"
- Next "stop" cycle disables the EventBridge rule

**Cost Optimization**:
- Zero Lambda invocations when no stories active
- 30-second polling reduces costs vs 10-second
- Efficient GSI queries minimize read capacity
- Batch operations reduce API calls

This architecture ensures reliable segment processing while maintaining cost efficiency through intelligent self-management.

### 5.4 Outcome Calculation Logic

The narrative outcome system leverages the MUD mechanics to create consistent, fair results based on character abilities. This ensures that character progression in the incremental game directly impacts story success rates.

#### MUD Mechanics Integration

The system uses two core MUD functions for all skill checks:

1. **ResolveStaticCheckWithXP**: Used for narrative challenges against fixed difficulties
   - Automatically awards skill XP based on difficulty and outcome
   - Failed attempts award 50% XP to encourage learning from failure
   - Returns sigma value indicating degree of success/failure

2. **ResolveOpposedCheckWithXP**: Used for combat and contested actions
   - Awards XP to both participants based on relative skill levels
   - Handles asymmetric contests (e.g., attack vs dodge)
   - Provides realistic combat progression

#### Challenge Resolution Process

When a narrative segment contains challenges, the system evaluates each one:

1. **Skill Combination**: Each challenge specifies an attribute (like strength or agility) and a skill (like survival or perception). The effective score is calculated as:
   ```
   effectiveScore = character.skills[skill] + character.attributes[attribute]
   ```

2. **XP Award Calculation**: The MUD functions automatically calculate XP awards:
   - Skill XP is based on the difficulty and outcome
   - Attribute XP is always 10% of the skill XP award
   - Both are added to the CharacterUpdates for later application

3. **Multiple Attempts**: Challenges can require multiple attempts, with each attempt:
   - Calling ResolveStaticCheckWithXP independently
   - Awarding XP for every attempt (full or 50%)
   - Contributing to the overall outcome determination

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

### 5.5 Combat Resolution Logic

Combat segments implement the complete MUD combat system using the ResolveOpposedCheckWithXP function for all combat actions. This ensures authentic battles with proper skill progression.

#### Combat Initialization

When processing a combat segment, the system:
- Loads opponent statistics from the Opponents table
- Retrieves character's current combat capabilities
- Applies environmental modifiers from segment definition
- Initializes round counter and combat state

#### Round-by-Round Combat Resolution

Combat simulation proceeds through alternating attacks, with each round representing a few seconds of intense battle. The system uses the MUD's opposed check mechanics to create realistic combat outcomes where skill differences matter but aren't deterministic.

**Attack Resolution**:

Each attack begins with the attacker attempting to land a blow on their opponent. The system calls ResolveOpposedCheckWithXP, pitting the attacker's offensive capabilities against the defender's defensive skills:

```python
# Player attacks opponent
attack_result = ResolveOpposedCheckWithXP(
    character, opponent,
    "melee", "strength",      # Attacker uses melee + strength
    "dodge", "agility"        # Defender uses dodge + agility
)
```

The function returns a sigma value representing the degree of success. A sigma of 1.0 or higher indicates a successful hit, with higher values representing more solid connections. Importantly, both combatants receive XP from every exchange - the attacker gains melee experience while the defender improves their dodge skill, even on misses.

**Damage Calculation**:

When an attack succeeds, the system determines how much damage penetrates the defender's armor and toughness. This uses a second opposed check that models the impact force versus the defender's ability to absorb punishment:

```python
# Damage roll using opposed check
damage_result = ResolveOpposedCheck(
    character, opponent,
    "melee", "strength",      # Damage based on strength + weapon
    "toughness", "endurance"  # Resistance based on toughness + armor
)
```

The resulting sigma value is floored to determine the number of wounds inflicted. Each point of damage creates one wound map in the character's wounds list. A glancing blow might create only one wound, while a critical strike could inflict three or more wounds, each with its own DamageType and HealAt timestamp.

**Environmental Factors**:

The combat environment plays a crucial role in battle outcomes. Before each attack or defense roll, the system applies environmental modifiers that reflect the fighting conditions. Dim lighting makes it harder to spot openings (reducing attack accuracy by 1), while muddy terrain hampers footwork (reducing dodge effectiveness by 1). These modifiers affect both combatants equally, adding tactical depth to encounter design.

**Progressive XP Awards**:

Combat provides rich opportunities for skill development. Throughout each round:
- Every attack attempt improves the attacker's melee skill
- Every defense attempt enhances the defender's dodge skill  
- Successful damage rolls may award additional weapon skill XP
- Failed attempts still award 50% of normal XP, reflecting learning from mistakes
- The continuous XP flow ensures that even losing battles contribute to character growth

#### Wound System Integration

The combat system fully implements the MUD wound mechanics with sophisticated tracking:

**Wound Structure:**
- Each point of damage creates a wound map in the character's wounds list
- Wound maps contain two fields:
  - `DamageType`: The category of damage ("bashing", "lethal", or "aggravated")
  - `HealAt`: ISO 8601 timestamp indicating when the wound will heal

**Damage Types:**
- **Bashing damage** creates bruises that heal within 15 minutes
- **Lethal damage** causes serious injuries requiring 6 hours to heal
- **Aggravated damage** inflicts grievous wounds needing 7 days of recovery

**Health Calculation:**
- Health is dynamically calculated as: `Health = MaxHealth - len(wounds)`
- Each wound in the list represents exactly one point of damage
- Health is not stored but computed on-demand when needed

**Cross-Mode Persistence:**
These wounds persist across game modes, meaning a character injured in an incremental combat will still bear those wounds when returning to the MUD. Healing continues in real-time regardless of which mode the character is actively playing.

#### Combat Outcome Determination

The final outcome depends on the combat's resolution and wounds sustained:

- **Death**: The character's health reaches zero (when `len(wounds) >= MaxHealth`)
- **Failure**: Maximum rounds expire with the opponent still standing
- **Minimal Victory**: The character wins but sustains 3 or more wounds
- **Normal Victory**: Victory achieved with 1-2 wounds
- **Exceptional Victory**: Flawless combat performance without taking any wounds

Character states are determined by health level and wound composition:
- **Standing**: Health > 0 (normal combat state)
- **Unconscious**: Health = 0 with at least one bashing wound
- **Dead**: Health = 0 with only lethal/aggravated wounds

This nuanced outcome system rewards skilled character builds while maintaining the risk inherent in combat encounters.

### 5.6 Difficulty Guidelines

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
   - All wounds persist as maps in the wounds list across modes
   - Each wound contains DamageType and HealAt timestamp fields
   - Health calculated dynamically as `MaxHealth - len(wounds)`
   - Character entering Incremental mode with MUD wounds starts injured
   - Combat wounds from Incremental stories affect MUD gameplay
   - Healing continues in real-time based on HealAt timestamps:
     - Bashing wounds heal in 15 minutes
     - Lethal wounds heal in 6 hours
     - Aggravated wounds heal in 7 days
   - Character states (standing, unconscious, dead) persist across modes
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

### 7.3 Data Consistency Strategy

#### Balanced Approach to Consistency

**PRINCIPLE**: Use DynamoDB transactions where atomicity is critical, but consider alternatives for high-frequency operations to manage costs and performance.

#### Critical Consistency Points

1. **State Transitions** (Use Transactions):
   - Story start: Character + ActiveSegments + History must be atomic
   - Story end: GameMode reset + cleanup must be atomic
   - Character deletion: Complete removal across all tables

2. **Gameplay Updates** (Consider Alternatives):
   - Segment processing: May use idempotent operations
   - XP/health updates: Conditional updates with version numbers
   - Item rewards: Evaluate criticality case-by-case

3. **Design Patterns**:
   - **Idempotency**: Use unique request IDs to prevent duplicate processing
   - **Conditional Updates**: Use DynamoDB conditions to prevent conflicts
   - **Eventually Consistent**: Accept delayed History writes where appropriate
   - **Compensating Actions**: Design rollback procedures for failures

#### Cost-Performance Trade-offs

1. **Transaction Costs**:
   - 2x read/write capacity consumption
   - Can significantly impact high-frequency operations
   - Monitor CloudWatch metrics for capacity usage

2. **When to Accept Eventual Consistency**:
   - History recording (can be async)
   - Non-critical stat updates
   - Analytics and reporting data

3. **When Atomicity is Required**:
   - Mode transitions (prevent locked characters)
   - Financial operations (item transfers)
   - State cleanup (prevent orphaned data)

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

The deployment adds nine Lambda functions to support story and player lifecycle operations:

**API Functions**: Five functions handle client-facing operations including story retrieval, story initiation, decision submission, outcome retrieval, and story abandonment. Each function follows the established naming convention and handler patterns.

**Processing Functions**: Two backend functions manage the story engine. The segment poller runs on a scheduled basis to check for completed segments, while the process segment function handles the actual outcome calculations and state updates.

**Cognito Integration Functions**: Two functions handle player lifecycle management. The new player function creates initial player records upon registration, while the delete player function ensures complete data removal for GDPR compliance. These system-level functions support both MUD and Incremental game modes.

**EventBridge Integration**: A new EventBridge rule triggers the segment poller every 30 seconds. This rule can be dynamically enabled or disabled based on whether any stories are active, optimizing costs during idle periods.

### 9.2 API Gateway Routes

The incremental APIs extend the existing API Gateway configuration with seven new routes, maintaining consistency with established URL patterns and authentication requirements.

**Character Management Routes**: GET endpoint for listing player characters and retrieving individual character details. These support the character selection flow essential for game entry.

**Story Management Routes**: GET endpoints allow retrieving available stories and current story state. POST endpoints handle story initiation and abandonment. These routes follow RESTful conventions while accommodating the unique requirements of time-based gameplay.

**Segment Interaction Routes**: A POST endpoint accepts player decisions for decision segments, while a GET endpoint retrieves completed segment outcomes. These routes implement proper idempotency to handle network retries gracefully.

**Route Organization**: All incremental routes are grouped under logical paths that clearly indicate their purpose, making the API intuitive for client developers while maintaining backward compatibility with existing endpoints.

### 9.3 Database Updates

The deployment extends the DynamoDB infrastructure with new tables that follow established patterns while supporting incremental-specific requirements.

**Table Definitions**: Five new tables support the incremental module: Story and Segments tables store content definitions, ActiveSegments tracks in-progress gameplay, Opponents defines combat encounters, and History preserves completed story records. Each table uses appropriate key structures for efficient querying.

**Global Secondary Indexes**: Two GSIs optimize critical query patterns. The EndTimeIndex on ActiveSegments enables efficient polling for completed segments, while the CharacterNameIndex on the Characters table ensures name uniqueness across all players.

**Schema Consistency**: All new tables follow the established DynamoDB patterns, using HASH and RANGE keys appropriately, maintaining consistent field naming conventions, and implementing proper data types for seamless integration with existing code patterns.

## 10. Cost Analysis

### 10.1 Cost Structure with 30-Second Polling

The front-loaded processing architecture with 30-second polling significantly reduces operational costs while maintaining responsive gameplay.

**Monthly Costs (10,000 concurrent users)**:

- **Lambda Invocations**: ~$80-120
  - Segment processing happens once per creation (not polling)
  - 30-second polling reduces invocations by 3x vs 10-second
  - SQS-triggered processing only when segments ready
- **EventBridge Rules**: <$1 (single polling rule)
- **SQS**: ~$5-10 (message passing between poller and processor)
- **DynamoDB**: ~$150-200
  - Pay-per-request pricing
  - Efficient GSI queries (EndTimeIndex)
  - Reduced reads due to front-loaded processing
- **SSM Parameter Store**: <$1 (polling state management)
- **Total: ~$235-335/month**

### 10.2 Cost Optimization Strategies

**Smart Polling Management**:
- Automatic enable/disable based on active segments eliminates idle polling costs
- 30-second intervals provide good UX while reducing Lambda invocations by 67%
- SSM parameter coordination prevents redundant state checks

**Efficient Processing Architecture**:
- Front-loaded outcome calculation eliminates repeated processing
- SQS batching reduces API calls and improves throughput
- Stuck segment recovery prevents infinite retries

**DynamoDB Optimization**:
- GSI queries target only ready segments, avoiding table scans
- Automatic segment deletion keeps table size minimal
- Batch operations reduce write capacity consumption

**Additional Savings Opportunities**:
- Use Lambda ARM architecture for 20% cost reduction
- Implement Reserved Capacity for predictable DynamoDB usage
- Consider Savings Plans for Lambda if usage is stable

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

This technical design implements a sophisticated incremental game system that seamlessly integrates with the existing Eidolon Engine infrastructure. The architecture properly handles four distinct segment types with appropriate processing for each.

Key architectural decisions:

- **Four Segment Types**: Rest (healing), Decision (player choice), Narrative (skill challenges), Combat (battles)
- **Smart Polling System**: 30-second EventBridge with type-specific handling
- **Mechanical Processing**: Narrative/Combat segments processed via SQS and ops_process_segment
- **History API**: New endpoint for clients to retrieve processed results during runtime
- **MUD Mechanics**: Simulated skill checks and combat using established algorithms
- **Cost Optimization**: ~$235-335/month for 10,000 concurrent users

The system successfully implements the incremental game pattern:
- **Set Actions in Motion**: Players start segments then wait for timers
- **Timer-Based Progress**: Segments advance automatically when timers expire
- **Retrieve Results**: Clients fetch processed results from History API
- **Player Agency**: Decision segments allow choices before timeout
- **Mechanical Depth**: Narrative and combat use character skills/attributes

This design creates an engaging timer-based story system where players can start adventures, make meaningful decisions, and return later to see the results of their character's actions.
