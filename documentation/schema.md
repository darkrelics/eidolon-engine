**Schema Overview:**

This schema supports the Eidolon Engine's unified backend infrastructure, providing shared data structures used by both MUD and Incremental game modes. All tables listed here are actively used by both game modes, with the GameMode field on characters preventing concurrent access.

**Key Design Principles:**

- Front-loaded processing: All outcomes are calculated when segments start, not when they end
- Shared tables: Both game modes use the same character, item, and room data
- Mode exclusivity: GameMode field ensures characters can only be active in one mode at a time
- Event-driven advancement: 30-second polling system processes completed segments

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

- **CharacterNameIndex**: CharacterName - For ensuring unique character names across all players

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

| Field         | Type      | Key      | Description                                                   |
| ------------- | --------- | -------- | ------------------------------------------------------------- |
| `PrototypeID` | `STRING`  | **HASH** | UUID of the item.                                             |
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
| `CanPickUp`   | `BOOLEAN` |          | Indicates if the item can be picked up by players.            |
| `Metadata`    | `MAP`     |          | Additional custom data related to the item.                   |

**Primary Key:** PrototypeID (HASH)

---

## Archetypes Table

| Field              | Type     | Key      | Description                                    |
| ------------------ | -------- | -------- | ---------------------------------------------- |
| `ArchetypeName`    | `STRING` | **HASH** | Name of the archetype.                         |
| `Description`      | `STRING` |          | Description of the archetype.                  |
| `Attributes`       | `MAP`    |          | Default attributes for the archetype.          |
| `Skills`           | `MAP`    |          | Default skills for the archetype.              |
| `StartRoom`        | `NUMBER` |          | ID of the starting room for the archetype.     |
| `StartingItems`    | `LIST`   |          | List of items given at character creation.     |
| `Health`           | `NUMBER` |          | Starting health points.                        |
| `Essence`          | `NUMBER` |          | Starting essence points.                       |
| `Player`           | `BOOL`   |          | Whether this archetype is for players.         |
| `AvailableStories` | `LIST`   |          | List of story IDs available to this archetype. |

**Primary Key:** ArchetypeName (HASH)

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

| Field               | Type     | Key      | Description                                   |
| ------------------- | -------- | -------- | --------------------------------------------- |
| `StoryID`           | `STRING` | **HASH** | UUID of the story.                            |
| `Title`             | `STRING` |          | Display title of the story.                   |
| `Description`       | `STRING` |          | Brief description of the story.               |
| `NarrativeText`     | `STRING` |          | Full narrative text introducing the story.    |
| `StoryType`         | `STRING` |          | Type: one-time, daily, or repeatable.         |
| `EstimatedDuration` | `NUMBER` |          | Estimated completion time in seconds.         |
| `Prerequisites`     | `MAP`    |          | Requirements to start (skills, items, rooms). |
| `FirstSegmentID`    | `STRING` |          | UUID of the starting segment.                 |
| `CreatedAt`         | `STRING` |          | ISO timestamp when story was created.         |
| `Version`           | `NUMBER` |          | Story version for updates.                    |

**Primary Key:** StoryID (HASH)

## Segments Table

| Field             | Type      | Key       | Description                                                               |
| ----------------- | --------- | --------- | ------------------------------------------------------------------------- |
| `StoryID`         | `STRING`  | **HASH**  | UUID of the parent story.                                                 |
| `SegmentID`       | `STRING`  | **RANGE** | UUID of the segment.                                                      |
| `SegmentType`     | `STRING`  |           | Type: decision, narrative, combat, or rest.                               |
| `ShortStatus`     | `STRING`  |           | Brief status text shown during segment.                                   |
| `DefaultStatus`   | `STRING`  |           | Status message shown between events (e.g., "Walking through the forest"). |
| `SegmentDuration` | `NUMBER`  |           | Time in seconds for this segment.                                         |
| `DecisionText`    | `STRING`  |           | For decision segments: the choice presented.                              |
| `DecisionOptions` | `MAP`     |           | For decision segments: map of option ID to next segment ID.               |
| `NextSegmentID`   | `STRING`  |           | For narrative/combat segments: UUID of the next segment.                  |
| `DefaultDecision` | `STRING`  |           | For decision segments: which option to auto-select.                       |
| `Challenges`      | `LIST`    |           | For narrative segments: list of skill/attribute challenges.               |
| `Combat`          | `MAP`     |           | For combat segments: combat configuration.                                |
| `RestSegment`     | `BOOLEAN` |           | Indicates if this is a rest segment.                                      |

**Primary Key:** StoryID (HASH), SegmentID (RANGE)

## ActiveSegments Table

| Field              | Type      | Key      | Description                                                                |
| ------------------ | --------- | -------- | -------------------------------------------------------------------------- |
| `ActiveSegmentID`  | `STRING`  | **HASH** | UUID for this active segment instance.                                     |
| `CharacterID`      | `STRING`  | **GSI**  | UUID of the character (for processing context).                            |
| `PlayerID`         | `STRING`  |          | UUID of the player who owns the character.                                 |
| `StoryID`          | `STRING`  |          | UUID of the story being played.                                            |
| `StoryTitle`       | `STRING`  |          | Cached title of the story for quick access.                                |
| `SegmentID`        | `STRING`  |          | UUID of the current segment definition.                                    |
| `SegmentType`      | `STRING`  |          | Type of segment: decision, narrative, combat, or rest.                     |
| `DefaultStatus`    | `STRING`  |          | Cached status message shown between events.                                |
| `StartTime`        | `NUMBER`  |          | Unix timestamp when segment started.                                       |
| `EndTime`          | `NUMBER`  | **GSI**  | Unix timestamp when segment will complete.                                 |
| `ProcessedAt`      | `NUMBER`  |          | Unix timestamp when outcomes were calculated (immediately after creation). |
| `ProcessingStatus` | `STRING`  |          | Status: pending, processed, failed, or awaiting_decision.                  |
| `ProcessingError`  | `STRING`  |          | Error details if processing failed.                                        |
| `NextSegmentID`    | `STRING`  |          | Pre-calculated next segment ID based on outcome.                           |
| `ClientEvents`     | `LIST`    |          | Complete event sequence for client to display over time.                   |
| `CharacterUpdates` | `MAP`     |          | All character changes to apply when segment completes.                     |
| `Decision`         | `STRING`  |          | For decision segments: choice made by player.                              |
| `DecisionMadeAt`   | `NUMBER`  |          | Unix timestamp when player made decision.                                  |
| `ChallengeResults` | `LIST`    |          | For narrative segments: results of each challenge roll.                    |
| `CombatState`      | `MAP`     |          | For combat segments: final combat state.                                   |
| `Outcome`          | `STRING`  |          | Final outcome (death/failure/minimal/normal/exceptional).                  |
| `Transmitted`      | `BOOLEAN` |          | Set when segment has been sent to SQS for processing.                      |
| `TransmittedAt`    | `NUMBER`  |          | Unix timestamp when sent to SQS.                                           |
| `RunningFlag`      | `STRING`  |          | Request ID of Lambda currently processing this segment.                    |

**Primary Key:** ActiveSegmentID (HASH)

**Global Secondary Indexes:**

- **CharacterID-index**: CharacterID - For querying active segments by character
- **EndTimeIndex**: EndTime - For finding segments ready to process and monitoring upcoming completions

## StoryHistory Table

| Field                | Type      | Key       | Description                                                 |
| -------------------- | --------- | --------- | ----------------------------------------------------------- |
| `CharacterID`        | `STRING`  | **HASH**  | UUID of the character.                                      |
| `StoryID`            | `STRING`  | **RANGE** | UUID of the story.                                          |
| `AttemptNumber`      | `NUMBER`  | **RANGE** | Increments for each attempt of this story.                  |
| `StoryTitle`         | `STRING`  |           | Cached title for display without additional lookup.         |
| `StoryType`          | `STRING`  |           | Type: one-time, daily, or repeatable.                       |
| `StartedAt`          | `NUMBER`  |           | Unix timestamp when story started.                          |
| `CompletedAt`        | `NUMBER`  |           | Unix timestamp when completed or abandoned.                 |
| `Abandoned`          | `BOOLEAN` |           | True if story was abandoned.                                |
| `FinalOutcome`       | `STRING`  |           | death, failure, minimal, normal, exceptional, or abandoned. |
| `TotalDuration`      | `NUMBER`  |           | Total seconds from start to finish.                         |
| `SegmentCount`       | `NUMBER`  |           | Number of segments completed.                               |
| `SkillXPAwarded`     | `MAP`     |           | Total skill XP earned: {skill_name: amount}.                |
| `AttributeXPAwarded` | `MAP`     |           | Total attribute XP earned: {attribute_name: amount}.        |
| `ItemsGained`        | `LIST`    |           | Item IDs acquired during story.                             |
| `ItemsLost`          | `LIST`    |           | Item IDs lost during story.                                 |
| `RoomsVisited`       | `LIST`    |           | Room IDs character moved to.                                |
| `DecisionsMade`      | `MAP`     |           | Map of segment_id to decision_choice.                       |

**Primary Key:** CharacterID (HASH), StoryID (RANGE)

## SegmentHistory Table

| Field                | Type     | Key       | Description                                               |
| -------------------- | -------- | --------- | --------------------------------------------------------- |
| `CharacterID`        | `STRING` | **HASH**  | UUID of the character.                                    |
| `ActiveSegmentID`    | `STRING` | **RANGE** | UUID matching the ActiveSegments record.                  |
| `PlayerID`           | `STRING` |           | UUID of the player for ownership verification.            |
| `StoryID`            | `STRING` |           | UUID of the parent story.                                 |
| `SegmentID`          | `STRING` |           | UUID of the segment definition.                           |
| `SegmentType`        | `STRING` |           | Type: narrative, combat, decision, or rest.               |
| `StartTime`          | `NUMBER` |           | Unix timestamp when segment started.                      |
| `EndTime`            | `NUMBER` |           | Unix timestamp when segment ended.                        |
| `ProcessedAt`        | `NUMBER` |           | Unix timestamp when outcomes were calculated.             |
| `CompletedAt`        | `NUMBER` |           | Unix timestamp when segment was advanced.                 |
| `Outcome`            | `STRING` |           | death, failure, minimal, normal, or exceptional.          |
| `Decision`           | `STRING` |           | For decision segments: choice made by player.             |
| `DecisionMadeAt`     | `NUMBER` |           | Unix timestamp when player made decision.                 |
| `ClientEvents`       | `LIST`   |           | Complete event array sent to client.                      |
| `CharacterUpdates`   | `MAP`    |           | All character changes applied.                            |
| `ChallengeResults`   | `LIST`   |           | Detailed skill check results.                             |
| `CombatState`        | `MAP`    |           | Final combat results if applicable.                       |
| `SkillXPAwarded`     | `MAP`    |           | Skill XP from this segment: {skill_name: amount}.         |
| `AttributeXPAwarded` | `MAP`    |           | Attribute XP from this segment: {attribute_name: amount}. |

**Primary Key:** CharacterID (HASH), ActiveSegmentID (RANGE)

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
| `LootTable`     | `LIST`   |          | Items and drop chances upon defeat.               |
| `Tags`          | `LIST`   |          | Categories for filtering and searching.           |
| `CreatedAt`     | `STRING` |          | ISO timestamp of creation.                        |

**Primary Key:** OpponentID (HASH)

---

## Data Structure Definitions

### Wound Object Structure

The Wound object is stored as a MAP within the Character table's Wounds list. Each wound map represents one point of damage:

| Field        | Type     | Description                                                       |
| ------------ | -------- | ----------------------------------------------------------------- |
| `DamageType` | `STRING` | Type of damage: "bashing", "lethal", or "aggravated"              |
| `HealAt`     | `STRING` | ISO 8601 timestamp indicating when this wound will naturally heal |

**Example Wounds List:**

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

---

**Notes:**

- All tables are designed for use with Amazon DynamoDB and are shared between MUD and Incremental game modes.
- The GameMode field on characters ensures a character cannot be active in both modes simultaneously.
- Data types correspond to DynamoDB data types (e.g., `STRING`, `NUMBER`, `MAP`, `LIST`, `BOOLEAN`).
- Maps (`MAP`) and lists (`LIST`) are used to store complex data structures.
- UUIDs are stored as strings to maintain consistency and readability.
- Ensure that any secondary indexes needed for queries are properly configured in DynamoDB.
- Field names in code (e.g., struct tags) should match the attribute names in DynamoDB for seamless data mapping.
