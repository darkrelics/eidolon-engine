**Schema Overview:**

This schema supports the Eidolon Engine's unified backend infrastructure, providing shared data structures used by both MUD and Incremental game modes. All tables listed here are actively used by both game modes, with the GameMode field on characters preventing concurrent access.

The schema facilitates:

- Unified player management across both game modes
- Character progression with attributes, skills, inventory, and location tracking
- Character safety through GameMode field (prevents simultaneous MUD/Incremental use)
- Room definitions with descriptions, items, and exits
- Item management including stacking, containment, and usage mechanics
- Archetype templates for character creation
- Storage of messages of the day for player engagement
- Incremental story system with segments, active tracking, and time-based progression

By adhering to this schema, developers can ensure data consistency and ease of access across both game modes, while leveraging DynamoDB's capabilities for scalability and performance.

## Player Table

| Field           | Type     | Description                                                      |
| --------------- | -------- | ---------------------------------------------------------------- |
| `PlayerID`      | `STRING` | UUID of the player (UUIDv4).                                     |
| `Email`         | `STRING` | Email address of the player.                                     |
| `CharacterList` | `MAP`    | Map of character names to character info (UUID, Dead, GameMode). |
| `SeenMotD`      | `LIST`   | List of UUIDs of messages of the day the player has seen.        |

- **`PlayerID`**: A UUIDv4 stored as a string, serving as the primary key.
- **`Email`**: The email address associated with the player account.
- **`CharacterList`**: A map where the key is the character's name and the value contains character info including UUID, Dead status, and GameMode.
- **`SeenMotD`**: A list of UUIDs representing the messages of the day that the player has viewed.

---

## Character Table

| Field              | Type     | Description                                                    |
| ------------------ | -------- | -------------------------------------------------------------- |
| `CharacterID`      | `STRING` | UUID of the character.                                         |
| `PlayerID`         | `STRING` | UUID of the player who owns the character.                     |
| `CharacterName`    | `STRING` | Name of the character.                                         |
| `GameMode`         | `STRING` | Current mode: "MUD" or "Incremental" (prevents concurrent use) |
| `RoomID`           | `NUMBER` | ID of the room the character is currently in.                  |
| `Inventory`        | `MAP`    | Map of inventory slots to item UUIDs.                          |
| `Attributes`       | `MAP`    | Map of attribute names to their values (e.g., Strength: 4).    |
| `Skills`           | `MAP`    | Map of skill names to their values (e.g., Stealth: 3).         |
| `Essence`          | `NUMBER` | The character's essence or magical energy.                     |
| `Health`           | `NUMBER` | The character's current health points.                         |
| `MaxHealth`        | `NUMBER` | The character's maximum health points.                         |
| `Hidden`           | `BOOL`   | Whether the character is currently hidden.                     |
| `Wounds`           | `LIST`   | List of wound objects affecting the character.                 |
| `CharState`        | `STRING` | Current character state (e.g., "standing", "unconscious").     |
| `AvailableStories` | `LIST`   | List of story IDs available to this character.                 |
| `AbandonedStories` | `LIST`   | List of story IDs the character has abandoned.                 |
| `CompletedStories` | `LIST`   | List of story IDs the character has completed.                 |

- **`CharacterID`**: The UUID of the character, serving as the primary key.
- **`PlayerID`**: The UUID of the player who owns this character.
- **`CharacterName`**: The name given to the character by the player.
- **`GameMode`**: Indicates whether character is currently in "MUD" or "Incremental" mode. This field prevents a character from being used in both modes simultaneously.
- **`RoomID`**: The ID of the room where the character is located.
- **`Inventory`**: A map where keys represent inventory slots or item names, and values are item UUIDs.
- **`Attributes`**: A map of character attributes (e.g., Strength, Agility) to their numerical values.
- **`Skills`**: A map of character skills (e.g., Stealth, Archery) to their numerical values.
- **`Essence`**: Represents the character's magical energy or mana.
- **`Health`**: Indicates the character's current health status.
- **`MaxHealth`**: The character's maximum health capacity.
- **`Hidden`**: Boolean indicating whether the character is currently hidden from other players.
- **`Wounds`**: List of wound objects affecting the character's performance. Each wound object contains:
  - `damage_type`: STRING - Type of damage ("bashing", "lethal", or "aggravated")
  - `heal_at`: STRING - ISO timestamp when the wound will heal
- **`CharState`**: Current state of the character ("standing", "unconscious", "dead", "ghost").
- **`AvailableStories`**: List of story IDs the character can participate in (e.g., ["forest-adventure-uuid", "daily-patrol-uuid"]).
- **`AbandonedStories`**: List of story IDs the character started but didn't complete.
- **`CompletedStories`**: List of story IDs the character has successfully finished.

### Wound System Details

The wound system is shared between MUD and Incremental modes:

- **Bashing Damage**: Non-lethal bruising that heals in 15 minutes
- **Lethal Damage**: Serious wounds that heal in 6 hours
- **Aggravated Damage**: Severe wounds that heal in 7 days
- Characters at 0 health with only bashing damage become unconscious
- Characters at 0 health with any lethal/aggravated damage die
- Wounds persist across game modes - injuries from MUD combat affect Incremental stories and vice versa

---

## Rooms Table

| Field         | Type      | Description                                     |
| ------------- | --------- | ----------------------------------------------- |
| `RoomID`      | `NUMBER`  | Unique identifier of the room.                  |
| `Area`        | `STRING`  | Name of the area or region the room belongs to. |
| `Title`       | `STRING`  | Title or name of the room.                      |
| `Description` | `STRING`  | Text description of the room.                   |
| `ExitID`      | `LIST`    | List of exit UUIDs from this room.              |
| `ScriptID`    | `STRING`  | ID of the Lua script associated with the room.  |
| `Persistent`  | `BOOLEAN` | Whether the room persists when empty.           |

- **`RoomID`**: Serves as the primary key for the room.
- **`Area`**: The broader area or zone where the room is located.
- **`Title`**: A short name or title for the room.
- **`Description`**: A detailed description that players see upon entering.
- **`ExitID`**: A list of UUIDs representing exits from the room.
- **`ScriptID`**: The filename (without .lua extension) of the Lua script associated with this room. Scripts are stored in S3.
- **`Persistent`**: Whether the room remains in memory when no characters are present.

---

## Exits Table

| Field         | Type      | Description                                       |
| ------------- | --------- | ------------------------------------------------- |
| `ExitID`      | `STRING`  | UUID of the exit.                                 |
| `Direction`   | `STRING`  | Direction of the exit (e.g., "north", "south").   |
| `TargetRoom`  | `NUMBER`  | ID of the room the exit leads to.                 |
| `Visible`     | `BOOLEAN` | Indicates if the exit is visible to players.      |
| `Description` | `STRING`  | Description of the exit.                          |
| `ArrivalText` | `STRING`  | Text shown when character arrives from this exit. |
| `ScriptID`    | `STRING`  | ID of the Lua script for exit interactions.       |

- **`ExitID`**: The UUID of the exit, serving as the primary key.
- **`Direction`**: The cardinal direction or named exit.
- **`TargetRoom`**: The `RoomID` of the destination room.
- **`Visible`**: A flag indicating whether the exit is visible to players.
- **`Description`**: Optional description of what the exit looks like.
- **`ArrivalText`**: Custom message shown when entering from this exit.
- **`ScriptID`**: Optional Lua script for special exit behavior.

---

## Items Table

| Field         | Type      | Description                                                   |
| ------------- | --------- | ------------------------------------------------------------- |
| `ItemID`      | `STRING`  | UUID of the item.                                             |
| `PrototypeID` | `STRING`  | UUID of the item prototype.                                   |
| `Name`        | `STRING`  | Name of the item.                                             |
| `Description` | `STRING`  | Description of the item.                                      |
| `Mass`        | `NUMBER`  | Weight or mass of the item.                                   |
| `Value`       | `NUMBER`  | Monetary value of the item.                                   |
| `Stackable`   | `BOOLEAN` | Indicates if the item can be stacked.                         |
| `MaxStack`    | `NUMBER`  | Maximum number of items per stack.                            |
| `Quantity`    | `NUMBER`  | Current quantity if stackable.                                |
| `Wearable`    | `BOOLEAN` | Indicates if the item can be worn.                            |
| `WornOn`      | `STRING`  | Body part where the item can be worn (e.g., "head", "feet").  |
| `Verbs`       | `MAP`     | Actions associated with the item (e.g., "eat": "You eat..."). |
| `Overrides`   | `MAP`     | Overrides for default behaviors or properties.                |
| `TraitMods`   | `MAP`     | Modifications to character traits when item is used/worn.     |
| `Container`   | `BOOLEAN` | Indicates if the item can contain other items.                |
| `Contents`    | `LIST`    | List of item UUIDs contained within this item.                |
| `IsWorn`      | `BOOLEAN` | Indicates if the item is currently worn by a character.       |
| `CanPickUp`   | `BOOLEAN` | Indicates if the item can be picked up by players.            |
| `Metadata`    | `MAP`     | Additional custom data related to the item.                   |

- **`ID`**: Primary key, uniquely identifies the item.
- **`PrototypeID`**: The UUID of the item prototype used to create this item.
- **`Name`**: The item's name as displayed to players.
- **`Description`**: Detailed text about the item.
- **`Mass`**: Used for weight calculations and inventory limits.
- **`Value`**: The in-game currency value.
- **`Stackable`**: If true, multiple items can occupy a single inventory slot.
- **`MaxStack`**: The maximum stack size for this item type.
- **`Quantity`**: The number of items in the stack.
- **`Wearable`**: Determines if the item can be equipped.
- **`WornOn`**: Specifies where on the body the item is worn.
- **`Verbs`**: Custom actions that can be performed with the item.
- **`Overrides`**: Allows modification of default behaviors.
- **`TraitMods`**: Adjustments to character attributes when item is used.
- **`Container`**: If true, item can hold other items.
- **`Contents`**: List of items contained within this item.
- **`IsWorn`**: Indicates the wear status of the item.
- **`CanPickUp`**: Determines if the item can be picked up.
- **`Metadata`**: Stores additional data for extensibility.

---

## Prototypes Table

| Field         | Type      | Description                                                   |
| ------------- | --------- | ------------------------------------------------------------- |
| `PrototypeID` | `STRING`  | UUID of the item.                                             |
| `Name`        | `STRING`  | Name of the item.                                             |
| `Description` | `STRING`  | Description of the item.                                      |
| `Mass`        | `NUMBER`  | Weight or mass of the item.                                   |
| `Value`       | `NUMBER`  | Monetary value of the item.                                   |
| `Stackable`   | `BOOLEAN` | Indicates if the item can be stacked.                         |
| `MaxStack`    | `NUMBER`  | Maximum number of items per stack.                            |
| `Quantity`    | `NUMBER`  | Current quantity if stackable.                                |
| `Wearable`    | `BOOLEAN` | Indicates if the item can be worn.                            |
| `WornOn`      | `STRING`  | Body part where the item can be worn (e.g., "head", "feet").  |
| `Verbs`       | `MAP`     | Actions associated with the item (e.g., "eat": "You eat..."). |
| `Overrides`   | `MAP`     | Overrides for default behaviors or properties.                |
| `TraitMods`   | `MAP`     | Modifications to character traits when item is used/worn.     |
| `Container`   | `BOOLEAN` | Indicates if the item can contain other items.                |
| `Contents`    | `LIST`    | List of item UUIDs contained within this item.                |
| `CanPickUp`   | `BOOLEAN` | Indicates if the item can be picked up by players.            |
| `Metadata`    | `MAP`     | Additional custom data related to the item.                   |

- **`PrototypeID`**: Primary key, uniquely identifies the item.
- **`Name`**: The item's name as displayed to players.
- **`Description`**: Detailed text about the item.
- **`Mass`**: Used for weight calculations and inventory limits.
- **`Value`**: The in-game currency value.
- **`Stackable`**: If true, multiple items can occupy a single inventory slot.
- **`MaxStack`**: The maximum stack size for this item type.
- **`Quantity`**: The number of items in the stack.
- **`Wearable`**: Determines if the item can be equipped.
- **`WornOn`**: Specifies where on the body the item is worn.
- **`Verbs`**: Custom actions that can be performed with the item.
- **`Overrides`**: Allows modification of default behaviors.
- **`TraitMods`**: Adjustments to character attributes when item is used.
- **`Container`**: If true, item can hold other items.
- **`Contents`**: List of items contained within this item.
- **`CanPickUp`**: Determines if the item can be picked up.
- **`Metadata`**: Stores additional data for extensibility.

- This table stores item templates used to create actual items.
- Prototypes are not interactable in-game but serve as blueprints.

---

## Archetypes Table

| Field              | Type     | Description                                    |
| ------------------ | -------- | ---------------------------------------------- |
| `ArchetypeName`    | `STRING` | Name of the archetype.                         |
| `Description`      | `STRING` | Description of the archetype.                  |
| `Attributes`       | `MAP`    | Default attributes for the archetype.          |
| `Skills`           | `MAP`    | Default skills for the archetype.              |
| `StartRoom`        | `NUMBER` | ID of the starting room for the archetype.     |
| `StartingItems`    | `LIST`   | List of items given at character creation.     |
| `Health`           | `NUMBER` | Starting health points.                        |
| `Essence`          | `NUMBER` | Starting essence points.                       |
| `Player`           | `BOOL`   | Whether this archetype is for players.         |
| `AvailableStories` | `LIST`   | List of story IDs available to this archetype. |

- **`ArchetypeName`**: Primary key for the archetype.
- **`Description`**: Explains the archetype's role or characteristics.
- **`Attributes`**: Base attribute values assigned to the archetype (e.g., Strength: 4).
- **`Skills`**: Starting skill values for the archetype (e.g., Swordsmanship: 2).
- **`StartRoom`**: The room ID where characters of this archetype begin.
- **`StartingItems`**: Items automatically given when a character is created.
- **`Health`**: Base health points for the archetype.
- **`Essence`**: Base essence/mana points for the archetype.
- **`Player`**: Indicates if this archetype is available for player characters.
- **`AvailableStories`**: List of story IDs (UUIDs) that are made available to characters of this archetype upon creation (e.g., ["f7b3d9a4-8e2c-4f6a-b1d5-3c9e7a2f8b6d"]).

---

## MOTD Table (Messages of the Day)

| Field       | Type     | Description                               |
| ----------- | -------- | ----------------------------------------- |
| `MotdID`    | `STRING` | UUID of the message.                      |
| `Message`   | `STRING` | The text content of the message.          |
| `CreatedAt` | `STRING` | Timestamp when the message was created.   |
| `Active`    | `BOOL`   | Whether this message is currently active. |

- **`MotdID`**: Primary key, uniquely identifies the message.
- **`Message`**: The actual message displayed to players.
- **`CreatedAt`**: Timestamp used to determine if players have seen the latest message.
- **`Active`**: Flag to enable/disable messages without deletion.

---

## Scripting System

The Eidolon Engine supports Lua scripting for dynamic room behavior. Scripts are stored in Amazon S3 and loaded on-demand when rooms are initialized.

### Script Storage

- Scripts are stored in S3 with the naming convention: `{script_id}.lua`
- The S3 bucket and prefix are configured in the server configuration
- Scripts are cached in memory for performance, with automatic cache expiration

### Script Metadata

Scripts can define a `SCRIPT_INFO` table to declare their capabilities:

```lua
SCRIPT_INFO = {
    commands = {"pull", "push", "turn"},  -- Commands this script handles
    events = {"onCharacterEnter", "onRoomStart"},  -- Events this script handles
    periodic = true  -- Whether script has periodic tick function
}
```

### Available Events

Scripts can handle the following events:

- **`onRoomStart`**: Called when the room is initialized
- **`onCharacterEnter(character)`**: Called when a character enters the room
- **`onCharacterLeave(character)`**: Called when a character leaves the room
- **`onCommand{Verb}(character, args)`**: Called for custom commands (e.g., `onCommandPull`)

### Script API

Scripts have access to the Eidolon API through the global `eidolon` table:

#### Room Functions

- **`eidolon.room.sendMessage(message)`**: Send a message to all characters in the room
- **`eidolon.room.sendToCharacter(name, message)`**: Send a message to a specific character
- **`eidolon.room.getCharacters()`**: Get list of characters in the room
- **`eidolon.room.getItems()`**: Get list of items in the room
- **`eidolon.room.addItem(name, description)`**: Add an item to the room
- **`eidolon.room.removeItem(name)`**: Remove an item from the room by name
- **`eidolon.room.setDescription(description)`**: Change the room's description
- **`eidolon.room.getExits()`**: Get list of exits from the room

#### Logging Functions

- **`eidolon.log.info(message)`**: Log an info message
- **`eidolon.log.debug(message)`**: Log a debug message
- **`eidolon.log.error(message)`**: Log an error message

### Example Script

```lua
-- Declare script capabilities
SCRIPT_INFO = {
    commands = {"pull", "push"},
    events = {"onCharacterEnter", "onRoomStart"},
    periodic = false
}

-- Handle room initialization
function onRoomStart()
    eidolon.log.info("Tavern script initialized")
end

-- Handle character entering
function onCharacterEnter(character)
    eidolon.room.sendMessage("The bartender nods at " .. character.name)
end

-- Handle custom command
function onCommandPull(character, args)
    if args[1] == "lever" then
        eidolon.room.sendMessage(character.name .. " pulls the lever!")
        eidolon.room.setDescription("A secret door has opened!")
        return true  -- Command was handled
    end
    return false  -- Command not handled
end
```

---

## Story Table

| Field               | Type     | Description                                   |
| ------------------- | -------- | --------------------------------------------- |
| `StoryID`           | `STRING` | UUID of the story (partition key).            |
| `Title`             | `STRING` | Display title of the story.                   |
| `Description`       | `STRING` | Brief description of the story.               |
| `NarrativeText`     | `STRING` | Full narrative text introducing the story.    |
| `StoryType`         | `STRING` | Type: one-time, daily, or repeatable.         |
| `EstimatedDuration` | `NUMBER` | Estimated completion time in seconds.         |
| `Prerequisites`     | `MAP`    | Requirements to start (skills, items, rooms). |
| `FirstSegmentID`    | `STRING` | UUID of the starting segment.                 |
| `CreatedAt`         | `STRING` | ISO timestamp when story was created.         |
| `Version`           | `NUMBER` | Story version for updates.                    |

- **`StoryID`**: Unique identifier for the story definition.
- **`Title`**: The display name of the story shown in story selection.
- **`Description`**: Brief summary of the story for the player.
- **`NarrativeText`**: The full introductory text shown when starting the story.
- **`StoryType`**: Determines availability - one-time stories can only be completed once per character, daily stories reset at server midnight, repeatable stories have no restrictions.
- **`EstimatedDuration`**: Total estimated time in seconds to complete all segments.
- **`Prerequisites`**: Map containing minSkills (minimum skill levels), requiredItems (item IDs), requiredRooms (room IDs the character must have visited).
- **`FirstSegmentID`**: References the first segment in the Segments table to begin the story chain.
- **`CreatedAt`**: Timestamp for version tracking and sorting.
- **`Version`**: Incremented when story content changes.

## Segments Table

| Field             | Type     | Description                                                 |
| ----------------- | -------- | ----------------------------------------------------------- |
| `StoryID`         | `STRING` | UUID of the parent story (partition key).                   |
| `SegmentID`       | `STRING` | UUID of the segment (sort key).                             |
| `SegmentType`     | `STRING` | Type: decision, narrative, or combat.                       |
| `ShortStatus`     | `STRING` | Brief status text shown during segment.                     |
| `Duration`        | `NUMBER` | Time in seconds for this segment.                           |
| `DecisionText`    | `STRING` | For decision segments: the choice presented.                |
| `DecisionOptions` | `MAP`    | For decision segments: map of option ID to next segment ID. |
| `NextSegmentID`   | `STRING` | For narrative/combat segments: UUID of the next segment.    |
| `DefaultDecision` | `STRING` | For decision segments: which option to auto-select.         |
| `Challenges`      | `LIST`   | For narrative segments: list of skill/attribute challenges. |
| `Combat`          | `MAP`    | For combat segments: combat configuration.                  |
| `Results`         | `MAP`    | For narrative/combat segments: outcomes mapped to updates.  |

- **`StoryID` + `SegmentID`**: Composite key for efficient segment lookups.
- **`SegmentType`**: Determines segment behavior - decision, narrative, or combat.
- **`DecisionOptions`**: Map like {"left-path": "segment-uuid-2", "right-path": "segment-uuid-3"}.
- **`NextSegmentID`**: For narrative/combat segments, the single next segment in the chain.
- **`Challenges`**: List of objects with:
  - `attribute`: Character attribute name (e.g., "Strength", "Agility")
  - `skill`: Character skill name (e.g., "Combat", "Stealth")
  - `difficulty`: Target number to beat (typically 7-10)
  - `attempts`: Number of times to roll
- **`Combat`**: For combat segments, contains:
  - `opponentId`: UUID reference to Opponents table
  - `maxRounds`: Maximum combat rounds before forced resolution
  - `environment`: Optional combat modifiers (lighting, terrain)
- **`Results`**: Map of outcome types (death, failure, minimal, normal, exceptional) to:
  - `narrative`: Text shown for this outcome
  - `effects`: Character updates (items, room changes)
  - Note: Damage is applied directly through MUD wound system during combat

## ActiveSegments Table

| Field              | Type     | Description                                               |
| ------------------ | -------- | --------------------------------------------------------- |
| `ActiveSegmentID`  | `STRING` | UUID for this active segment instance (partition key).    |
| `CharacterID`      | `STRING` | UUID of the character.                                    |
| `StoryID`          | `STRING` | UUID of the story being played.                           |
| `SegmentID`        | `STRING` | UUID of the current segment definition.                   |
| `StartTime`        | `NUMBER` | Unix timestamp when segment started.                      |
| `EndTime`          | `NUMBER` | Unix timestamp when segment will complete.                |
| `Status`           | `STRING` | Status: active or completed.                              |
| `Decision`         | `STRING` | For decision segments: choice made by player.             |
| `ChallengeResults` | `LIST`   | For narrative segments: results of each challenge roll.   |
| `CombatState`      | `MAP`    | For combat segments: tracks ongoing combat state.         |
| `Outcome`          | `STRING` | Final outcome (death/failure/minimal/normal/exceptional). |
| `TTL`              | `NUMBER` | Time-to-live for automatic cleanup.                       |

- **`ActiveSegmentID`**: Unique identifier for this runtime instance.
- **`CharacterID`**: Links to the character experiencing this segment.
- **`EndTime`**: Key field for polling - when this segment completes.
- **`ChallengeResults`**: Stores each dice roll result for narrative challenges.
- **`CombatState`**: For combat segments, tracks:
  - `round`: Current combat round number
  - `playerWounds`: List of wounds with type and healAt timestamps
  - `opponentHealth`: Current opponent health
- **`Outcome`**: Final result determined by challenge aggregation or combat resolution.

### Global Secondary Index: CompletionTimeIndex

| Field     | Type     | Description                                       |
| --------- | -------- | ------------------------------------------------- |
| `Status`  | `STRING` | Partition key - filters for active segments only. |
| `EndTime` | `NUMBER` | Sort key - enables time-based range queries.      |

- **Projection**: ALL - includes all attributes for efficient polling.
- **Purpose**: Enables the segment poller Lambda to efficiently query for segments ready to complete.

## History Table

| Field            | Type     | Description                                                          |
| ---------------- | -------- | -------------------------------------------------------------------- |
| `CharacterID`    | `STRING` | UUID of the character (partition key).                               |
| `StoryID`        | `STRING` | UUID of the story (sort key).                                        |
| `StoryTitle`     | `STRING` | Title of the story for display without additional lookup.            |
| `StartedAt`      | `STRING` | ISO timestamp when the story began.                                  |
| `FinishedAt`     | `STRING` | ISO timestamp when the story ended (completion or abandonment).      |
| `StoryType`      | `STRING` | Type of story (one-time, daily, or repeatable).                      |
| `SegmentHistory` | `LIST`   | Detailed record of each segment's progression and outcomes.          |
| `FinalOutcome`   | `STRING` | Overall story result (death, failure, minimal, normal, exceptional). |
| `TotalDuration`  | `NUMBER` | Total seconds from start to finish.                                  |
| `Rewards`        | `MAP`    | Aggregated rewards earned (experience, items, gold, room changes).   |
| `AbandonedCount` | `NUMBER` | Number of times this story was abandoned before completion.          |

- **`CharacterID` + `StoryID`**: Composite primary key enabling efficient queries by character and specific story lookups.
- **`StoryTitle`**: Cached story title to avoid additional Story table lookup when displaying history.
- **`StartedAt`/`FinishedAt`**: Timestamps for duration tracking and analytics. Both are always populated.
- **`SegmentHistory`**: List containing detailed records for each segment:
  - `SegmentID`: UUID of the segment
  - `SegmentType`: decision, narrative, or combat
  - `Comment`: Brief description of what happened in this segment (e.g., "Chose the left path through the forest")
  - `Decision`: Player's choice text (for decision segments, e.g., "Take the left path")
  - `Outcome`: Result (for narrative/combat segments)
  - `ResultText`: Narrative text shown to player for this outcome (e.g., "You navigate successfully through the moonlit path...")
  - `ChallengeResults`: List of skill check results (for narrative segments)
  - `FinalCombatState`: Combat statistics (for combat segments)
  - `CompletedAt`: When this segment finished
- **`Data Lifecycle`**: Persists until character deletion process removes all associated history records.
- **`Query Patterns`**: Primary access by CharacterID to get all story history or by composite key for specific story run.

---

## Opponents Table

| Field           | Type     | Description                                       |
| --------------- | -------- | ------------------------------------------------- |
| `OpponentID`    | `STRING` | UUID of the opponent (UUIDv4) - primary key.      |
| `Name`          | `STRING` | Display name of the opponent.                     |
| `Description`   | `STRING` | Narrative description of the opponent.            |
| `CombatRating`  | `NUMBER` | Combined attack skill (Agility + Melee).          |
| `DefenseRating` | `NUMBER` | Combined defense skill (Agility + Dodge).         |
| `DamageRating`  | `NUMBER` | Combined damage potential (Strength + Weapon).    |
| `Toughness`     | `NUMBER` | Base endurance for damage resistance.             |
| `ArmorRating`   | `NUMBER` | Armor protection value.                           |
| `Health`        | `NUMBER` | Maximum health levels.                            |
| `WeaponType`    | `STRING` | Type of damage dealt (bashing/lethal/aggravated). |
| `WeaponDamage`  | `NUMBER` | Bonus damage from weapon.                         |
| `LootTable`     | `LIST`   | Items and drop chances upon defeat.               |
| `Tags`          | `LIST`   | Categories for filtering and searching.           |
| `CreatedAt`     | `STRING` | ISO timestamp of creation.                        |

- **`OpponentID`**: Unique identifier allowing reuse across multiple stories.
- **`Name`**: The opponent's display name shown in combat narratives.
- **`Description`**: Detailed description for story context.
- **`CombatRating`**: Pre-calculated attack value combining Agility and weapon skill.
- **`DefenseRating`**: Pre-calculated defense value for hit avoidance.
- **`DamageRating`**: Base damage potential before weapon bonus.
- **`Toughness`**: Endurance value used to resist damage.
- **`ArmorRating`**: Reduces incoming damage sigma values.
- **`Health`**: Total health levels the opponent can sustain.
- **`WeaponType`**: Determines wound type inflicted (uses MUD damage system).
- **`WeaponDamage`**: Additional damage bonus from equipped weapon.
- **`LootTable`**: List of objects with `itemId` and `chance` (0.0-1.0) for random drops.
- **`Tags`**: Enables filtering opponents by type, difficulty, or story theme.
- **`CreatedAt`**: Timestamp for version tracking and sorting.

---

**Notes:**

- All tables are designed for use with Amazon DynamoDB and are shared between MUD and Incremental game modes.
- The GameMode field on characters ensures a character cannot be active in both modes simultaneously.
- Primary keys are specified for each table to ensure data integrity.
- Data types correspond to DynamoDB data types (e.g., `STRING`, `NUMBER`, `MAP`, `LIST`, `BOOLEAN`).
- Maps (`MAP`) and lists (`LIST`) are used to store complex data structures.
- UUIDs are stored as strings to maintain consistency and readability.
- Ensure that any secondary indexes needed for queries are properly configured in DynamoDB.
- Field names in code (e.g., struct tags) should match the attribute names in DynamoDB for seamless data mapping.

---
