# Eidolon Engine Database Schema

## Overview

This document defines the complete database schema for the Eidolon Engine's unified backend infrastructure. The schema provides shared data structures used by both MUD and Incremental game modes, with 14 DynamoDB tables that support all game functionality while preventing concurrent access through the GameMode field on characters.

**Key Design Principles:**

- Front-loaded processing: All outcomes are calculated when segments start, not when they end
- Shared tables: Both game modes use the same character, item, and room data
- Mode exclusivity: GameMode field ensures characters can only be active in one mode at a time
- Event-driven advancement: 1-minute polling system processes completed segments

## Player Table

| Field           | Type     | Key      | Description                                                      |
| --------------- | -------- | -------- | ---------------------------------------------------------------- |
| `PlayerID`      | `STRING` | **HASH** | UUID of the player (UUIDv4).                                     |
| `Email`         | `STRING` |          | Email address of the player.                                     |
| `CharacterList` | `MAP`    |          | Map of character names to character info (UUID, Dead, GameMode). |
| `SeenMotD`      | `LIST`   |          | List of UUIDs of messages of the day the player has seen.        |

**Primary Key:** PlayerID (HASH)

---

## Character Table

| Field              | Type            | Key      | Description                                                                   |
| ------------------ | --------------- | -------- | ----------------------------------------------------------------------------- |
| `CharacterID`      | `STRING`        | **HASH** | UUID of the character.                                                        |
| `PlayerID`         | `STRING`        |          | UUID of the player who owns the character.                                    |
| `CharacterName`    | `STRING`        | **GSI**  | Name of the character.                                                        |
| `GameMode`         | `STRING`        |          | Current mode: "MUD", "Incremental", or "None" (prevents concurrent use)       |
| `RoomID`           | `NUMBER`        |          | ID of the room the character is currently in.                                 |
| `Inventory`        | `MAP`           |          | Map of inventory slots to item UUIDs.                                         |
| `Attributes`       | `MAP`           |          | Map of attribute names to their values (e.g., Strength: 4).                   |
| `Skills`           | `MAP`           |          | Map of skill names to their values (e.g., Stealth: 3).                        |
| `Essence`          | `NUMBER`        |          | The character's essence or magical energy.                                    |
| `MaxHealth`        | `NUMBER`        |          | The character's maximum health levels.                                        |
| `Hidden`           | `BOOL`          |          | Whether the character is currently hidden.                                    |
| `Wounds`           | `LIST` of `MAP` |          | List of wound objects. Each wound is a map with DamageType and HealAt fields. |
| `CharState`        | `STRING`        |          | Current character state (e.g., "standing", "unconscious").                    |
| `LeftHandID`       | `STRING`        |          | UUID of item equipped in left hand (if any).                                  |
| `RightHandID`      | `STRING`        |          | UUID of item equipped in right hand (if any).                                 |
| `AvailableStories` | `LIST`          |          | List of story IDs available to this character.                                |
| `AbandonedStories` | `LIST`          |          | List of story IDs the character has abandoned.                                |
| `CompletedStories` | `LIST`          |          | List of story IDs the character has completed.                                |
| `ActiveStoryID`    | `STRING`        |          | UUID of the currently active story (if any).                                  |
| `ActiveSegmentID`  | `STRING`        |          | UUID of the currently active segment (if any).                                |
| `Archetype`        | `STRING`        |          | Name of the character's archetype.                                            |
| `MaxEssence`       | `NUMBER`        |          | The character's maximum essence points.                                       |
| `Resources`        | `MAP`           |          | Map of resource types to quantities (e.g., gold: 100).                        |
| `Progress`         | `MAP`           |          | Map tracking story progress flags and achievements.                           |
| `CreatedAt`        | `STRING`        |          | ISO 8601 timestamp when character was created.                                |
| `UpdatedAt`        | `STRING`        |          | ISO 8601 timestamp of last character update.                                  |
| `LastPlayed`       | `STRING`        |          | ISO 8601 timestamp when character was last active.                            |

**Primary Key:** CharacterID (HASH)

**Global Secondary Index:**

- **CharacterNameIndex**: CharacterName (HASH) - For ensuring unique character names across all players
  - Projection Type: KEYS_ONLY (only includes keys for name uniqueness checks)

**Health Calculation:**

- Current health is not stored in the database but calculated dynamically as: `Health = MaxHealth - len(Wounds)`
- Each wound in the Wounds list represents exactly one point of damage
- The length of the Wounds list directly indicates the total damage taken

**API Response Transformations:**

- **JSON Field Names**: All fields use PascalCase to match DynamoDB field names (e.g., CharacterID, CharacterName, AvailableStories)
- **Acronyms**: Acronyms in field names are fully capitalized (e.g., StoryID not StoryId, ItemID not ItemId, PlayerID not PlayerId)
- **InventoryDetails**: API responses include an enriched `InventoryDetails` field with item information:
  ```json
  {
    "SlotName": {
      "ItemID": "uuid",
      "Name": "Item Name",
      "Description": "Item description",
      "Mass": 1.5,
      "Value": 100,
      "Wearable": true,
      "WornOn": "head"
    }
  }
  ```

#### **Data Type Conversion Standards**

**DynamoDB Storage → API Response:**

- **All NUMBER fields**: Stored as Decimal in DynamoDB, automatically converted to float in API responses
- **Precision Guarantee**: 64-bit IEEE 754 floats provide sufficient precision for all game values (no precision loss)
- **Value Semantics**:
  - **Integer Semantics**: Health, RoomID, Currency, ItemID counts (display without decimals)
  - **Fractional Semantics**: Skills, Attributes, XP values, Sigma calculations (preserve 2-3 decimal precision)

**Conversion Examples:**

```json
// DynamoDB Storage (internal)
{"Stealth": Decimal("5.375"), "Health": Decimal("12"), "Gold": Decimal("150")}

// API Response (client receives)
{"Stealth": 5.375, "Health": 12.0, "Gold": 150.0}

// Client Display (recommended)
"Stealth: 5.38, Health: 12, Gold: 150"
```

**No Precision Loss**: Game values (0.00-10.00 skills, 0-1000 currency) are well within float64 precision limits.

---

## Rooms Table

| Field         | Type      | Key      | Description                                     |
| ------------- | --------- | -------- | ----------------------------------------------- |
| `RoomID`      | `NUMBER`  | **HASH** | Unique identifier of the room.                  |
| `Area`        | `STRING`  |          | Name of the area or region the room belongs to. |
| `Title`       | `STRING`  |          | Title or name of the room.                      |
| `Description` | `STRING`  |          | Text description of the room.                   |
| `ExitID`      | `LIST`    |          | List of exit UUIDs from this room.              |
| `ScriptID`    | `STRING`  |          | ID of the Lua script associated with the room.  |
| `Persistent`  | `BOOLEAN` |          | Whether the room persists when empty.           |

**Primary Key:** RoomID (HASH)

---

## Exits Table

| Field         | Type      | Key      | Description                                       |
| ------------- | --------- | -------- | ------------------------------------------------- |
| `ExitID`      | `STRING`  | **HASH** | UUID of the exit.                                 |
| `Direction`   | `STRING`  |          | Direction of the exit (e.g., "north", "south").   |
| `TargetRoom`  | `NUMBER`  |          | ID of the room the exit leads to.                 |
| `Visible`     | `BOOLEAN` |          | Indicates if the exit is visible to players.      |
| `Description` | `STRING`  |          | Description of the exit.                          |
| `ArrivalText` | `STRING`  |          | Text shown when character arrives from this exit. |
| `ScriptID`    | `STRING`  |          | ID of the Lua script for exit interactions.       |

**Primary Key:** ExitID (HASH)

---

## Items Table

| Field         | Type      | Key      | Description                                                   |
| ------------- | --------- | -------- | ------------------------------------------------------------- |
| `ItemID`      | `STRING`  | **HASH** | UUID of the item.                                             |
| `PrototypeID` | `STRING`  |          | UUID of the item prototype.                                   |
| `Name`        | `STRING`  |          | Name of the item.                                             |
| `Description` | `STRING`  |          | Description of the item.                                      |
| `Mass`        | `NUMBER`  |          | Weight or mass of the item.                                   |
| `Value`       | `NUMBER`  |          | Monetary value of the item.                                   |
| `Stackable`   | `BOOLEAN` |          | Indicates if the item can be stacked.                         |
| `MaxStack`    | `NUMBER`  |          | Maximum number of items per stack.                            |
| `Quantity`    | `NUMBER`  |          | Current quantity if stackable.                                |
| `Wearable`    | `BOOLEAN` |          | Indicates if the item can be worn.                            |
| `WornOn`      | `STRING`  |          | Body part where the item can be worn (e.g., "head", "feet").  |
| `Verbs`       | `MAP`     |          | Actions associated with the item (e.g., "eat": "You eat..."). |
| `Overrides`   | `MAP`     |          | Overrides for default behaviors or properties.                |
| `TraitMods`   | `MAP`     |          | Modifications to character traits when item is used/worn.     |
| `Container`   | `BOOLEAN` |          | Indicates if the item can contain other items.                |
| `Contents`    | `LIST`    |          | List of item UUIDs contained within this item.                |
| `IsWorn`      | `BOOLEAN` |          | Indicates if the item is currently worn by a character.       |
| `CanPickUp`   | `BOOLEAN` |          | Indicates if the item can be picked up by players.            |
| `Metadata`    | `MAP`     |          | Additional custom data related to the item.                   |

**Primary Key:** ItemID (HASH)

---

## Prototypes Table

| Field           | Type      | Key      | Description                                                   |
| --------------- | --------- | -------- | ------------------------------------------------------------- |
| `PrototypeID`   | `STRING`  | **HASH** | UUID of the item prototype.                                   |
| `PrototypeName` | `STRING`  |          | Name of the item.                                             |
| `Description`   | `STRING`  |          | Description of the item.                                      |
| `Mass`          | `NUMBER`  |          | Weight or mass of the item.                                   |
| `Value`         | `NUMBER`  |          | Monetary value of the item.                                   |
| `Stackable`     | `BOOLEAN` |          | Indicates if the item can be stacked.                         |
| `MaxStack`      | `NUMBER`  |          | Maximum number of items per stack.                            |
| `Quantity`      | `NUMBER`  |          | Default quantity if stackable.                                |
| `Wearable`      | `BOOLEAN` |          | Indicates if the item can be worn.                            |
| `WornOn`        | `LIST`    |          | Body slots where item can be worn                             |
| `Verbs`         | `MAP`     |          | Actions associated with the item (e.g., "Use": "You use..."). |
| `Overrides`     | `MAP`     |          | Overrides for default behaviors or properties.                |
| `TraitMods`     | `MAP`     |          | Modifications to character traits when item is used/worn.     |
| `Container`     | `BOOLEAN` |          | Indicates if the item can contain other items.                |
| `Contents`      | `LIST`    |          | List of item UUIDs contained within this item.                |
| `IsWorn`        | `BOOLEAN` |          | Default worn state when item is created.                      |
| `CanPickUp`     | `BOOLEAN` |          | Indicates if the item can be picked up by players.            |
| `Metadata`      | `MAP`     |          | Additional custom data related to the item.                   |

**Primary Key:** PrototypeID (HASH)

---

## Archetypes Table

| Field              | Type            | Key      | Description                                                 |
| ------------------ | --------------- | -------- | ----------------------------------------------------------- |
| `ArchetypeName`    | `STRING`        | **HASH** | Name of the archetype.                                      |
| `Description`      | `STRING`        |          | Description of the archetype.                               |
| `Attributes`       | `MAP`           |          | Default attributes for the archetype (e.g., Strength: 2.0). |
| `Skills`           | `MAP`           |          | Default skills for the archetype (e.g., Melee: 1.0).        |
| `StartRoom`        | `NUMBER`        |          | ID of the starting room for the archetype.                  |
| `StartingItems`    | `LIST` of `MAP` |          | List of starting item configurations (see structure below). |
| `Health`           | `NUMBER`        |          | Starting health points.                                     |
| `Essence`          | `NUMBER`        |          | Starting essence points.                                    |
| `Player`           | `BOOL`          |          | Whether this archetype is for players.                      |
| `AvailableStories` | `LIST`          |          | List of story IDs available to this archetype.              |

**Primary Key:** ArchetypeName (HASH)

**StartingItems Structure:**

Each item in the StartingItems list is a map containing:

| Field         | Type      | Description                                                      |
| ------------- | --------- | ---------------------------------------------------------------- |
| `PrototypeID` | `STRING`  | UUID of the item prototype to create.                            |
| `Slot`        | `STRING`  | Equipment slot name if worn (e.g., "back", "weapon", "armor").   |
| `IsWorn`      | `BOOLEAN` | Whether the item starts equipped.                                |
| `Container`   | `BOOLEAN` | Whether this item is a container (only first container is used). |

**Implementation Notes:**

1. **Container Logic:** When processing StartingItems, the first item with `Container: true` becomes the primary container. All items with `IsWorn: false` are placed inside this container's Contents array.

2. **Inventory Management:** Only items with `IsWorn: true` and the primary container are added to the character's inventory slots. Non-worn items exist only within the container.

3. **Item Creation:** Items are created in the order they appear in the list. If non-worn items appear before the container in the list, they are collected and added to the container when it is created.

**Example StartingItems:**

```json
[
  {
    "PrototypeID": "a47ac10b-58cc-4372-a567-0e02b2c3d484",
    "Slot": "back",
    "IsWorn": true,
    "Container": true
  },
  {
    "PrototypeID": "947ac10b-58cc-4372-a567-0e02b2c3d485",
    "Slot": "finger",
    "IsWorn": true,
    "Container": false
  },
  {
    "PrototypeID": "e47ac10b-58cc-4372-a567-0e02b2c3d480",
    "Slot": "",
    "IsWorn": false,
    "Container": false
  }
]
```

In this example:

- The backpack (first item) is worn and serves as the container
- The ring (second item) is worn on the finger slot
- The third item is not worn and will be placed inside the backpack's Contents

---

## MOTD Table (Messages of the Day)

| Field       | Type     | Key      | Description                               |
| ----------- | -------- | -------- | ----------------------------------------- |
| `MotdID`    | `STRING` | **HASH** | UUID of the message.                      |
| `Message`   | `STRING` |          | The text content of the message.          |
| `CreatedAt` | `STRING` |          | Timestamp when the message was created.   |
| `Active`    | `BOOL`   |          | Whether this message is currently active. |

**Primary Key:** MotdID (HASH)

---

## Story Table

| Field               | Type     | Key      | Description                                |
| ------------------- | -------- | -------- | ------------------------------------------ |
| `StoryID`           | `STRING` | **HASH** | UUID of the story.                         |
| `Title`             | `STRING` |          | Display title of the story.                |
| `Description`       | `STRING` |          | Brief description of the story.            |
| `NarrativeText`     | `STRING` |          | Full narrative text introducing the story. |
| `StoryType`         | `STRING` |          | Type: one-time, daily, or repeatable.      |
| `EstimatedDuration` | `NUMBER` |          | Estimated completion time in seconds.      |
| `Prerequisites`     | `MAP`    |          | Requirements to start (skills, items).     |
| `DifficultyMap`     | `MAP`    |          | Map of skill checks to base difficulties.  |
| `RewardTiers`       | `MAP`    |          | Reward descriptions by outcome tier.       |
| `FirstSegmentID`    | `STRING` |          | UUID of the starting segment.              |
| `CreatedAt`         | `STRING` |          | ISO timestamp when story was created.      |

**Primary Key:** StoryID (HASH)

## Segments Table

| Field             | Type     | Key       | Description                                                                                           |
| ----------------- | -------- | --------- | ----------------------------------------------------------------------------------------------------- |
| `StoryID`         | `STRING` | **HASH**  | UUID of the parent story.                                                                             |
| `SegmentID`       | `STRING` | **RANGE** | UUID of the segment.                                                                                  |
| `SegmentType`     | `STRING` |           | Type: decision or mechanical.                                                                         |
| `SegmentActivity` | `STRING` |           | Activity indicator text shown while the segment is active.                                            |
| `SegmentTitle`    | `STRING` |           | Title text displayed on the segment card (e.g., "Walking through the forest").                        |
| `SegmentDuration` | `NUMBER` |           | Time in seconds for this segment.                                                                     |
| `DecisionText`    | `STRING` |           | For decision segments: the choice presented to the player.                                            |
| `DecisionOptions` | `MAP`    |           | For decision segments: map of option ID to option data (Text, Description, Narrative, NextSegmentID). |
| `DefaultDecision` | `STRING` |           | For decision segments: which option key to auto-select on timeout.                                    |
| `Challenges`      | `LIST`   |           | For mechanical segments: list of skill/attribute challenges.                                          |
| `Combat`          | `MAP`    |           | For mechanical segments: combat configuration (if applicable).                                        |
| `Results`         | `MAP`    |           | For mechanical segments: outcome-based results (see structure below).                                 |

**Primary Key:** StoryID (HASH), SegmentID (RANGE)

**Challenges Structure:**
Each challenge in the Challenges list contains:

- `Attribute` (STRING): The attribute being tested (e.g., "Perception", "Strength")
- `Skill` (STRING): The skill being tested (e.g., "Investigation", "Stealth")
- `Difficulty` (NUMBER): The difficulty rating for the challenge
- `Attempts` (NUMBER): Maximum number of attempts allowed

**DecisionOptions Structure:**
Each option in the DecisionOptions map contains:

- `Text` (STRING): Short button text for the choice (e.g., "Follow the sound of water")
- `Description` (STRING): Longer description explaining the choice
- `Narrative` (STRING): Story text shown when this choice is made (enriches segment history)
- `NextSegmentID` (STRING): UUID of the segment to transition to when this option is chosen

**Note:** Decision segments present player choices without mechanics. They contain NO Difficulty ratings, skill checks, or mechanical calculations. All game mechanics belong in mechanical segments.

**Combat Structure:**
The Combat map contains:

- `OpponentID` (STRING): UUID of the opponent from the Opponents table
- `MaxRounds` (NUMBER): Maximum combat rounds before timeout
- `Environment` (MAP, optional): Environmental modifiers (e.g., lighting, terrain)

**Results Structure:**
The Results map contains outcome entries for Death, Failure, Minimal, Normal, and Exceptional. Each outcome contains:

- `Narrative` (STRING): The narrative text describing this outcome
- `Effects` (MAP): Changes to apply to the character:
  - `State` (STRING, optional): Character state change (e.g., "dead")
  - `Room` (NUMBER, optional): Room ID to move character to
  - `Wounds` (LIST, optional): List of damage type strings (e.g., ["bashing", "lethal"])
  - `Items` (LIST, optional): Item rewards using the same format as Opponents Items field (see Items Structure above)
- `NextSegmentID` (STRING, nullable): UUID of the next segment, or null to end the story

## ActiveSegments Table

| Field              | Type     | Key      | Description                                                                 |
| ------------------ | -------- | -------- | --------------------------------------------------------------------------- |
| `ActiveSegmentID`  | `STRING` | **HASH** | UUID for this active segment instance.                                      |
| `CharacterID`      | `STRING` | **GSI**  | UUID of the character (for processing context).                             |
| `PlayerID`         | `STRING` |          | UUID of the player who owns the character.                                  |
| `StoryID`          | `STRING` |          | UUID of the story being played.                                             |
| `StoryInstanceID`  | `STRING` |          | UUIDv7 of the story instance for history tracking.                          |
| `SegmentID`        | `STRING` |          | UUID of the current segment definition.                                     |
| `SegmentType`      | `STRING` |          | Type of segment: decision or mechanical.                                    |
| `SegmentTitle`     | `STRING` |          | Title text cached for the segment card header.                              |
| `Status`           | `STRING` |          | Segment status: active, completed, or abandoned.                            |
| `StartTime`        | `NUMBER` |          | Unix timestamp when segment started.                                        |
| `EndTime`          | `NUMBER` | **GSI**  | Unix timestamp when segment will complete.                                  |
| `ProcessedAt`      | `NUMBER` |          | Unix timestamp when outcomes were calculated by ops-segment-process.        |
| `ProcessingStatus` | `STRING` |          | Status: pending (awaiting), processing (in progress), or processed (ready). |
| `NextSegmentID`    | `STRING` |          | Pre-calculated next segment ID based on outcome.                            |
| `ClientEvents`     | `LIST`   |          | Complete event sequence for client to display over time.                    |
| `CharacterUpdates` | `MAP`    |          | All character changes to apply when segment completes.                      |
| `Decision`         | `STRING` |          | For decision segments: choice made by player.                               |
| `DecisionMadeAt`   | `NUMBER` |          | Unix timestamp when player made decision.                                   |
| `DecisionOptions`  | `MAP`    |          | For decision segments: available choices and their next segments.           |
| `ChallengeResults` | `LIST`   |          | For mechanical segments: results of each challenge roll.                    |
| `CombatState`      | `MAP`    |          | For mechanical segments: final combat state (if applicable).                |
| `Outcome`          | `STRING` |          | Final outcome (death/failure/minimal/normal/exceptional).                   |

**Primary Key:** ActiveSegmentID (HASH)

**Global Secondary Indexes:**

- **CharacterID-index**: CharacterID (HASH) - For querying active segments by character
  - Projection Type: ALL (includes all attributes for complete segment data retrieval)
- **EndTimeIndex**: Status (HASH), EndTime (RANGE) - For finding segments by status and monitoring upcoming completions
  - Projection Type: ALL (includes all attributes for segment processing)

## StoryHistory Table

| Field                | Type     | Key       | Description                                                                      |
| -------------------- | -------- | --------- | -------------------------------------------------------------------------------- |
| `CharacterID`        | `STRING` | **HASH**  | UUID of the character.                                                           |
| `StoryInstanceID`    | `STRING` | **RANGE** | UUIDv7 for this story instance (unique per execution).                           |
| `StoryID`            | `STRING` |           | UUID of the story.                                                               |
| `StoryTitle`         | `STRING` |           | Cached title for display without additional lookup.                              |
| `StoryType`          | `STRING` |           | Type: one-time, daily, or repeatable.                                            |
| `StartedAt`          | `STRING` |           | ISO 8601 timestamp when story started.                                           |
| `FinishedAt`         | `STRING` |           | ISO 8601 timestamp when completed or abandoned.                                  |
| `FinalOutcome`       | `STRING` |           | Completed: death/failure/minimal/normal/exceptional, or abandoned (player quit). |
| `TotalDuration`      | `NUMBER` |           | Total seconds from start to finish.                                              |
| `SegmentHistory`     | `LIST`   |           | List of ActiveSegmentIDs in chronological order.                                 |
| `SkillXPAwarded`     | `MAP`    |           | Total skill XP earned: {skill_name: amount}.                                     |
| `AttributeXPAwarded` | `MAP`    |           | Total attribute XP earned: {attribute_name: amount}.                             |
| `ItemsGained`        | `LIST`   |           | Item IDs acquired during story.                                                  |
| `ItemsLost`          | `LIST`   |           | Item IDs lost during story.                                                      |
| `RoomsVisited`       | `LIST`   |           | Room IDs character moved to.                                                     |
| `DecisionsMade`      | `MAP`    |           | Map of segment_id to decision_choice.                                            |

**Primary Key:** CharacterID (HASH), StoryInstanceID (RANGE)

**Implementation Notes:**

- The `StoryInstanceID` is a UUIDv7 generated when the story starts (in `api-story-start`)
- This allows characters to play the same story multiple times with each execution tracked separately
- The `SegmentHistory` list contains ActiveSegmentIDs that reference records in the SegmentHistory table
- Each ActiveSegmentID is added to this list when a segment is created (in `create_active_segment`)
- The actual segment data is stored in the SegmentHistory table
- Since CharacterID is the HASH key, querying all stories for a character is straightforward

**Lifecycle:**

1. **Creation**: Record created when story starts via `create_story_history_entry()`

   - Generates UUIDv7 StoryInstanceID for time-ordered unique identification
   - Sets StartedAt timestamp
   - Initializes empty SegmentHistory list and XP maps

2. **During Play**:

   - ActiveSegmentIDs added to SegmentHistory list as segments are created (not just completed)
   - XP accumulates in SkillXPAwarded/AttributeXPAwarded maps via `update_story_history_xp()`
   - Creates complete audit trail of all segments attempted

3. **Completion (Success or Failure)**: When story reaches its conclusion via `complete_story()`

   - Sets FinishedAt timestamp and FinalOutcome (death/failure/minimal/normal/exceptional)
   - Death and failure outcomes are still considered "completed" attempts, not abandonments
   - Story added to character's CompletedStories list (regardless of outcome)
   - Calculates TotalDuration in seconds
   - Character GameMode reset to "None", ActiveStoryID/ActiveSegmentID cleared

4. **Abandonment (Player-Initiated)**: When player voluntarily quits via `api_story_abandon`

   - Sets FinishedAt timestamp and FinalOutcome to "abandoned"
   - Story added to character's AbandonedStories list (not CompletedStories)
   - Character GameMode reset to "None", ActiveStoryID/ActiveSegmentID cleared
   - **Cannot be resumed** - must start fresh if repeatable
   - Distinct from death/failure - represents player choice to quit, not story outcome

5. **Multiple Executions**:
   - Repeatable stories create new record with new StoryInstanceID each time
   - All instances preserved for complete history
   - Most recent instance used for cooldown checks

## SegmentHistory Table

Records the complete history of each segment played by a character. This table serves as an audit trail and enables player progress tracking, analytics, and debugging. Records are created when segments are created (not just when completed).

| Field              | Type     | Key       | Required | Description                                                       |
| ------------------ | -------- | --------- | -------- | ----------------------------------------------------------------- |
| `CharacterID`      | `STRING` | **HASH**  | **Yes**  | UUID of the character.                                            |
| `ActiveSegmentID`  | `STRING` | **RANGE** | **Yes**  | UUID matching the ActiveSegments record.                          |
| `StoryInstanceID`  | `STRING` |           | **Yes**  | UUIDv7 of the story instance from StoryHistory.                   |
| `StoryID`          | `STRING` |           | **Yes**  | UUID of the parent story.                                         |
| `SegmentID`        | `STRING` |           | **Yes**  | UUID of the segment definition.                                   |
| `SegmentType`      | `STRING` |           | **Yes**  | Type: mechanical or decision.                                     |
| `StartTime`        | `NUMBER` |           | **Yes**  | Unix timestamp when segment started.                              |
| `EndTime`          | `NUMBER` |           | **Yes**  | Unix timestamp when segment will end.                             |
| `ProcessedAt`      | `NUMBER` |           | No       | Unix timestamp when outcomes were calculated.                     |
| `CompletedAt`      | `NUMBER` |           | No       | Unix timestamp when segment was actually completed.               |
| `Outcome`          | `STRING` |           | No       | death, failure, minimal, normal, or exceptional.                  |
| `Decision`         | `STRING` |           | No       | For decision segments: choice made by player.                     |
| `DecisionMadeAt`   | `NUMBER` |           | No       | Unix timestamp when player made decision.                         |
| `ClientEvents`     | `LIST`   |           | No       | Complete event array sent to client.                              |
| `CharacterUpdates` | `MAP`    |           | No       | All character changes applied (contains SkillXP and AttributeXP). |
| `ChallengeResults` | `LIST`   |           | No       | Detailed skill check results (mechanical segments).               |
| `CombatState`      | `MAP`    |           | No       | Final combat results if applicable.                               |

**Primary Key:** CharacterID (HASH), ActiveSegmentID (RANGE)

**Implementation Notes:**

- Records are created when segments start (in `create_active_segment`), not when they complete
- The `StoryInstanceID` links this segment to a specific story execution in the StoryHistory table
- Initial record has StartTime, EndTime, and basic fields; Outcome and CharacterUpdates are added when the segment completes
- The ActiveSegmentID is added to the StoryHistory.SegmentHistory list when the segment is created
- XP data is stored within `CharacterUpdates.SkillXP` and `CharacterUpdates.AttributeXP` maps
- All timestamp fields should be copied directly from the ActiveSegments record
- For segments with no XP awards, the SkillXP and AttributeXP maps within CharacterUpdates should be empty `{}` rather than null

---

## Opponents Table

| Field           | Type     | Key      | Description                                       |
| --------------- | -------- | -------- | ------------------------------------------------- |
| `OpponentID`    | `STRING` | **HASH** | UUID of the opponent (UUIDv4).                    |
| `Name`          | `STRING` |          | Display name of the opponent.                     |
| `Description`   | `STRING` |          | Narrative description of the opponent.            |
| `CombatRating`  | `NUMBER` |          | Combined attack skill (Agility + Melee).          |
| `DefenseRating` | `NUMBER` |          | Combined defense skill (Agility + Dodge).         |
| `DamageRating`  | `NUMBER` |          | Combined damage potential (Strength + Weapon).    |
| `Toughness`     | `NUMBER` |          | Base endurance for damage resistance.             |
| `ArmorRating`   | `NUMBER` |          | Armor protection value.                           |
| `Health`        | `NUMBER` |          | Maximum health levels.                            |
| `WeaponType`    | `STRING` |          | Type of damage dealt (bashing/lethal/aggravated). |
| `WeaponDamage`  | `NUMBER` |          | Bonus damage from weapon.                         |
| `Items`         | `LIST`   |          | List of item rewards (see structure below).       |
| `Tags`          | `LIST`   |          | Categories for filtering and searching.           |
| `CreatedAt`     | `STRING` |          | ISO timestamp of creation.                        |

**Primary Key:** OpponentID (HASH)

**Note:** The Items field uses the common Items Structure defined in the Data Structure Definitions section below, supporting both simple (guaranteed) and probabilistic reward formats.

---

## Data Structure Definitions

### Items Structure

The Items field is used in both Opponents and Segment Results to define item rewards. It supports two formats:

**1. Simple Format (guaranteed rewards):**
List of item prototype IDs as strings. All listed items are granted with 100% probability.

```json
["item-uuid-1", "item-uuid-2", "item-uuid-3"]
```

**2. Probabilistic Format:**
List of maps with ItemID and Chance fields. Each item has an independent probability of being granted.

```json
[
  {"ItemID": "item-uuid-1", "Chance": 0.3},
  {"ItemID": "item-uuid-2", "Chance": 0.5},
  {"ItemID": "item-uuid-3", "Chance": 0.2}
]
```

**Probability Calculation Algorithm:**

When using probabilistic format, items are processed using cumulative probability distribution:

1. Sort items by Chance in ascending order (smallest to highest)
2. Accumulate probabilities cumulatively
3. If cumulative sum exceeds 1.0, clip the current item's chance to `1.0 - previous_cumulative`
4. Roll independently for each item against its final (possibly clipped) probability

**Probability Examples:**

| Configuration | Probabilities | Result |
|--------------|---------------|--------|
| `0.3, 0.5` | 30%, 50% | 80% total chance (20% chance of no reward) |
| `0.4, 0.6` | 40%, 60% | 100% total chance (both items can drop) |
| `0.5, 0.6` | 50%, 50% | 100% total chance (second clipped from 0.6 to 0.5) |
| `0.2, 0.3, 0.7` | 20%, 30%, 50% | 100% total chance (third clipped from 0.7 to 0.5) |

This algorithm ensures:
- Lower-probability items always get their full chance
- Higher-probability items are clipped if needed
- Total probability never exceeds 100%
- Items are independent (both can drop if both succeed)

### Wound Object Structure

Wounds are represented differently depending on context:

#### In Character Table

The Wound object is stored as a MAP within the Character table's Wounds list. Each wound map represents one point of damage:

| Field        | Type     | Description                                                       |
| ------------ | -------- | ----------------------------------------------------------------- |
| `DamageType` | `STRING` | Type of damage: "bashing", "lethal", or "aggravated"              |
| `HealAt`     | `STRING` | ISO 8601 timestamp indicating when this wound will naturally heal |

**Example Wounds List in Character:**

```json
[
  {
    "DamageType": "bashing",
    "HealAt": "2025-01-15T14:30:00Z"
  },
  {
    "DamageType": "lethal",
    "HealAt": "2025-01-15T20:00:00Z"
  }
]
```

This character has taken 2 points of damage (2 wounds in the list), so with MaxHealth of 10, their current health would be 8.

#### In Segment Results

Within the Effects structure of segment Results, wounds are simplified to a list of damage type strings:

**Example Wounds in Segment Effects:**

```json
{
  "Effects": {
    "Wounds": ["bashing", "lethal", "bashing"],
    "Room": 5
  }
}
```

This indicates the segment will inflict three wounds: two bashing and one lethal. The system will convert these to full wound objects with HealAt timestamps when applying them to the character.

### CharacterUpdates Structure

The CharacterUpdates map stored in ActiveSegments and SegmentHistory contains all changes to apply to a character when a segment completes:

```json
{
  "SkillXP": {
    "fighting": 0.5,
    "dodge": 0.25
  },
  "AttributeXP": {
    "strength": 0.1,
    "agility": 0.05
  },
  "Wounds": [
    {
      "DamageType": "bashing",
      "HealAt": "2025-01-15T14:30:00Z"
    }
  ],
  "Room": 12345,
  "Resources": {
    "gold": 10,
    "supplies": -2
  },
  "Inventory": {
    "right_hand": "item-uuid-123"
  }
}
```

**Note:** When recording SegmentHistory, the SkillXP and AttributeXP values must be extracted into the dedicated `SkillXPAwarded` and `AttributeXPAwarded` fields for easier querying and analytics.

---

**Notes:**

- All tables are designed for use with Amazon DynamoDB and are shared between MUD and Incremental game modes.
- The GameMode field on characters ensures a character cannot be active in both modes simultaneously.
- Data types correspond to DynamoDB data types (e.g., `STRING`, `NUMBER`, `MAP`, `LIST`, `BOOLEAN`).
- Maps (`MAP`) and lists (`LIST`) are used to store complex data structures.
- UUIDs are stored as strings to maintain consistency and readability.
- Ensure that any secondary indexes needed for queries are properly configured in DynamoDB.
- Field names in code (e.g., struct tags) should match the attribute names in DynamoDB for seamless data mapping.
