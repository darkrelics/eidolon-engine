**Schema Overview:**

This schema supports the Eidolon Engine's unified backend infrastructure, providing shared data structures used by both MUD and Incremental game modes. All tables listed here are actively used by both game modes, with the GameMode field on characters preventing concurrent access.

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

| Field              | Type     | Key      | Description                                                    |
| ------------------ | -------- | -------- | -------------------------------------------------------------- |
| `CharacterID`      | `STRING` | **HASH** | UUID of the character.                                         |
| `PlayerID`         | `STRING` |          | UUID of the player who owns the character.                     |
| `CharacterName`    | `STRING` | **GSI**  | Name of the character.                                         |
| `GameMode`         | `STRING` |          | Current mode: "MUD" or "Incremental" (prevents concurrent use) |
| `RoomID`           | `NUMBER` |          | ID of the room the character is currently in.                  |
| `Inventory`        | `MAP`    |          | Map of inventory slots to item UUIDs.                          |
| `Attributes`       | `MAP`    |          | Map of attribute names to their values (e.g., Strength: 4).    |
| `Skills`           | `MAP`    |          | Map of skill names to their values (e.g., Stealth: 3).         |
| `Essence`          | `NUMBER` |          | The character's essence or magical energy.                     |
| `Health`           | `NUMBER` |          | The character's current health points.                         |
| `MaxHealth`        | `NUMBER` |          | The character's maximum health points.                         |
| `Hidden`           | `BOOL`   |          | Whether the character is currently hidden.                     |
| `Wounds`           | `LIST`   |          | List of wound objects affecting the character.                 |
| `CharState`        | `STRING` |          | Current character state (e.g., "standing", "unconscious").     |
| `LeftHandID`       | `STRING` |          | UUID of item equipped in left hand (if any).                   |
| `RightHandID`      | `STRING` |          | UUID of item equipped in right hand (if any).                  |
| `AvailableStories` | `LIST`   |          | List of story IDs available to this character.                 |
| `AbandonedStories` | `LIST`   |          | List of story IDs the character has abandoned.                 |
| `CompletedStories` | `LIST`   |          | List of story IDs the character has completed.                 |
| `ActiveStoryID`    | `STRING` |          | UUID of the currently active story (if any).                   |
| `ActiveSegmentID`  | `STRING` |          | UUID of the currently active segment (if any).                 |
| `Archetype`        | `STRING` |          | Name of the character's archetype.                             |
| `MaxEssence`       | `NUMBER` |          | The character's maximum essence points.                        |
| `Resources`        | `MAP`    |          | Map of resource types to quantities (e.g., gold: 100).        |
| `Progress`         | `MAP`    |          | Map tracking story progress flags and achievements.            |
| `CreatedAt`        | `STRING` |          | ISO 8601 timestamp when character was created.                 |
| `UpdatedAt`        | `STRING` |          | ISO 8601 timestamp of last character update.                   |
| `LastPlayed`       | `STRING` |          | ISO 8601 timestamp when character was last active.            |

**Primary Key:** CharacterID (HASH)

**Global Secondary Index:**

- **CharacterNameIndex**: CharacterName - For ensuring unique character names across all players

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

| Field             | Type     | Key       | Description                                                 |
| ----------------- | -------- | --------- | ----------------------------------------------------------- |
| `StoryID`         | `STRING` | **HASH**  | UUID of the parent story.                                   |
| `SegmentID`       | `STRING` | **RANGE** | UUID of the segment.                                        |
| `SegmentType`     | `STRING` |           | Type: decision, narrative, or combat.                       |
| `ShortStatus`     | `STRING` |           | Brief status text shown during segment.                     |
| `SegmentDuration` | `NUMBER` |           | Time in seconds for this segment.                           |
| `DecisionText`    | `STRING` |           | For decision segments: the choice presented.                |
| `DecisionOptions` | `MAP`    |           | For decision segments: map of option ID to next segment ID. |
| `NextSegmentID`   | `STRING` |           | For narrative/combat segments: UUID of the next segment.    |
| `DefaultDecision` | `STRING` |           | For decision segments: which option to auto-select.         |
| `Challenges`      | `LIST`   |           | For narrative segments: list of skill/attribute challenges. |
| `Combat`          | `MAP`    |           | For combat segments: combat configuration.                  |
| `Results`         | `MAP`    |           | For narrative/combat segments: outcomes mapped to updates.  |

**Primary Key:** StoryID (HASH), SegmentID (RANGE)

## ActiveSegments Table

| Field              | Type     | Key      | Description                                               |
| ------------------ | -------- | -------- | --------------------------------------------------------- |
| `ActiveSegmentID`  | `STRING` | **HASH** | UUID for this active segment instance.                    |
| `CharacterID`      | `STRING` | **GSI**  | UUID of the character (for processing context).           |
| `PlayerID`         | `STRING` |          | UUID of the player who owns the character.                |
| `StoryID`          | `STRING` |          | UUID of the story being played.                           |
| `StoryTitle`       | `STRING` |          | Cached title of the story for quick access.              |
| `SegmentID`        | `STRING` |          | UUID of the current segment definition.                   |
| `SegmentType`      | `STRING` |          | Type of segment: decision, narrative, or combat.          |
| `Status`           | `STRING` |          | Segment status: active, abandoned, or completed.          |
| `StartTime`        | `NUMBER` |          | Unix timestamp when segment started.                      |
| `EndTime`          | `NUMBER` | **GSI**  | Unix timestamp when segment will complete.                |
| `Decision`         | `STRING` |          | For decision segments: choice made by player.             |
| `ChallengeResults` | `LIST`   |          | For narrative segments: results of each challenge roll.   |
| `CombatState`      | `MAP`    |          | For combat segments: tracks ongoing combat state.         |
| `Outcome`          | `STRING` |          | Final outcome (death/failure/minimal/normal/exceptional). |
| `TTL`              | `NUMBER` |          | Time-to-live for automatic cleanup of old segments.       |

**Primary Key:** ActiveSegmentID (HASH)

**Global Secondary Indexes:**

- **CharacterID-index**: CharacterID - For querying active segments by character
- **EndTimeIndex**: EndTime - For finding segments ready to process and monitoring upcoming completions

## History Table

| Field            | Type     | Key       | Description                                                          |
| ---------------- | -------- | --------- | -------------------------------------------------------------------- |
| `CharacterID`    | `STRING` | **HASH**  | UUID of the character.                                               |
| `StoryID`        | `STRING` | **RANGE** | UUID of the story.                                                   |
| `StoryTitle`     | `STRING` |           | Title of the story for display without additional lookup.            |
| `StartedAt`      | `STRING` |           | ISO timestamp when the story began.                                  |
| `FinishedAt`     | `STRING` |           | ISO timestamp when the story ended (completion or abandonment).      |
| `StoryType`      | `STRING` |           | Type of story (one-time, daily, or repeatable).                      |
| `SegmentHistory` | `LIST`   |           | Detailed record of each segment's progression and outcomes.          |
| `FinalOutcome`   | `STRING` |           | Overall story result (death, failure, minimal, normal, exceptional). |
| `TotalDuration`  | `NUMBER` |           | Total seconds from start to finish.                                  |
| `Rewards`        | `MAP`    |           | Aggregated rewards earned (experience, items, gold, room changes).   |
| `AbandonedCount` | `NUMBER` |           | Number of times this story was abandoned before completion.          |

**Primary Key:** CharacterID (HASH), StoryID (RANGE)

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

**Notes:**

- All tables are designed for use with Amazon DynamoDB and are shared between MUD and Incremental game modes.
- The GameMode field on characters ensures a character cannot be active in both modes simultaneously.
- Data types correspond to DynamoDB data types (e.g., `STRING`, `NUMBER`, `MAP`, `LIST`, `BOOLEAN`).
- Maps (`MAP`) and lists (`LIST`) are used to store complex data structures.
- UUIDs are stored as strings to maintain consistency and readability.
- Ensure that any secondary indexes needed for queries are properly configured in DynamoDB.
- Field names in code (e.g., struct tags) should match the attribute names in DynamoDB for seamless data mapping.
