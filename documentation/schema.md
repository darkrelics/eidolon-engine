**Schema Overview:**

This schema supports the Eidolon Engine's unified backend infrastructure, providing shared data structures used by both MUD and Incremental game modes. All tables listed here are actively used by both game modes, with the GameMode field on characters preventing concurrent access.

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
- **Decimal Values**: All numeric values are converted from DynamoDB Decimal to standard floats

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

| Field             | Type      | Key       | Description                                                               |
| ----------------- | --------- | --------- | ------------------------------------------------------------------------- |
| `StoryID`         | `STRING`  | **HASH**  | UUID of the parent story.                                                 |
| `SegmentID`       | `STRING`  | **RANGE** | UUID of the segment.                                                      |
| `SegmentType`     | `STRING`  |           | Type: decision, mechanical, or rest.                                      |
| `ShortStatus`     | `STRING`  |           | Brief status text shown during segment.                                   |
| `DefaultStatus`   | `STRING`  |           | Status message shown between events (e.g., "Walking through the forest"). |
| `SegmentDuration` | `NUMBER`  |           | Time in seconds for this segment.                                         |
| `DecisionText`    | `STRING`  |           | For decision segments: the choice presented.                              |
| `DecisionOptions` | `MAP`     |           | For decision segments: map of option ID to next segment ID.               |
| `DefaultDecision` | `STRING`  |           | For decision segments: which option to auto-select.                       |
| `Challenges`      | `LIST`    |           | For mechanical segments: list of skill/attribute challenges.              |
| `Combat`          | `MAP`     |           | For mechanical segments: combat configuration (if applicable).            |
| `Results`         | `MAP`     |           | For mechanical segments: outcome-based results (see structure below).     |
| `RestSegment`     | `BOOLEAN` |           | Indicates if this is a rest segment.                                      |

**Primary Key:** StoryID (HASH), SegmentID (RANGE)

**Challenges Structure:**
Each challenge in the Challenges list contains:

- `Attribute` (STRING): The attribute being tested (e.g., "Perception", "Strength")
- `Skill` (STRING): The skill being tested (e.g., "Investigation", "Stealth")
- `Difficulty` (NUMBER): The difficulty rating for the challenge
- `Attempts` (NUMBER): Maximum number of attempts allowed

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
  - `Items` (LIST, optional): List of item prototype IDs to grant
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
| `SegmentType`      | `STRING` |          | Type of segment: decision, mechanical, or rest.                             |
| `DefaultStatus`    | `STRING` |          | Cached status message shown between events.                                 |
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
| `SegmentType`      | `STRING` |           | **Yes**  | Type: mechanical, decision, or rest.                              |
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
| `LootTable`     | `LIST`   |          | List of loot drop objects (see structure below).  |
| `Tags`          | `LIST`   |          | Categories for filtering and searching.           |
| `CreatedAt`     | `STRING` |          | ISO timestamp of creation.                        |

**Primary Key:** OpponentID (HASH)

**LootTable Structure:**
Each item in the LootTable list is a map with the following fields:

- `ItemID` (STRING): UUID of the item prototype that can drop
- `Chance` (NUMBER): Drop probability (0.0 to 1.0)

---

## Data Structure Definitions

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
