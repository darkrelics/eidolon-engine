**Schema Overview:**

This schema supports the Eidolon Engine, providing structures for players, characters, rooms, items, and game messages. It facilitates:

- Player management with associated characters and messages seen.
- Character progression with attributes, abilities, inventory, and location tracking.
- Room definitions with descriptions, items, and exits to other rooms.
- Item management including stacking, containment, and usage mechanics.
- Archetype templates for character creation.
- Storage of messages of the day for player engagement.

By adhering to this schema, developers can ensure data consistency and ease of access across the application, while leveraging DynamoDB's capabilities for scalability and performance.

## Player Table

| Field           | Type     | Description                                               |
| --------------- | -------- | --------------------------------------------------------- |
| `PlayerID`      | `STRING` | Email of the player.                                      |
| `CharacterList` | `MAP`    | Map of character names to their UUIDs.                    |
| `SeenMotD`      | `LIST`   | List of UUIDs of messages of the day the player has seen. |

- **`PlayerID`**: The email address of the player, serving as the primary key.
- **`CharacterList`**: A map where the key is the character's name and the value is the character's UUID as a string.
- **`SeenMotD`**: A list of UUIDs representing the messages of the day that the player has viewed.

---

## Character Table

| Field           | Type     | Description                                                 |
| --------------- | -------- | ----------------------------------------------------------- |
| `CharacterID`   | `STRING` | UUID of the character.                                      |
| `PlayerID`      | `STRING` | Email of the player who owns the character.                 |
| `CharacterName` | `STRING` | Name of the character.                                      |
| `RoomID`        | `NUMBER` | ID of the room the character is currently in.               |
| `Inventory`     | `MAP`    | Map of inventory slots to item UUIDs.                       |
| `Attributes`    | `MAP`    | Map of attribute names to their values (e.g., Strength: 4). |
| `Skills`        | `MAP`    | Map of skill names to their values (e.g., Stealth: 3).      |
| `Essence`       | `NUMBER` | The character's essence or magical energy.                  |
| `Health`        | `NUMBER` | The character's current health points.                      |
| `Hidden`        | `BOOL`   | Whether the character is currently hidden.                  |

- **`CharacterID`**: The UUID of the character, serving as the primary key.
- **`PlayerID`**: The email address of the player who owns this character.
- **`CharacterName`**: The name given to the character by the player.
- **`RoomID`**: The ID of the room where the character is located.
- **`Inventory`**: A map where keys represent inventory slots or item names, and values are item UUIDs.
- **`Attributes`**: A map of character attributes (e.g., Strength, Agility) to their numerical values.
- **`Skills`**: A map of character skills (e.g., Stealth, Archery) to their numerical values.
- **`Essence`**: Represents the character's magical energy or mana.
- **`Health`**: Indicates the character's current health status.
- **`Hidden`**: Boolean indicating whether the character is currently hidden from other players.

---

## Rooms Table

| Field           | Type      | Description                                     |
| --------------- | --------- | ----------------------------------------------- |
| `RoomID`        | `NUMBER`  | Unique identifier of the room.                  |
| `Area`          | `STRING`  | Name of the area or region the room belongs to. |
| `Title`         | `STRING`  | Title or name of the room.                      |
| `Description`   | `STRING`  | Text description of the room.                   |
| `ExitID`        | `LIST`    | Map of exit directions to exit UUIDs.           |
| `ScriptID`      | `STRING`  | ID of the Lua script associated with the room.  |
| `ScriptActive`  | `BOOLEAN` | Indicates if the room script is active.         |

- **`RoomID`**: Serves as the primary key for the room.
- **`Area`**: The broader area or zone where the room is located.
- **`Title`**: A short name or title for the room.
- **`Description`**: A detailed description that players see upon entering.
- **`ExitID`**: A list of UUIDs representing exits from the room.
- **`ScriptID`**: The filename (without .lua extension) of the Lua script associated with this room. Scripts are stored in S3.
- **`ScriptActive`**: Boolean flag indicating whether the room's script is currently active and should handle events/commands.

---

## Exits Table

| Field        | Type      | Description                                     |
| ------------ | --------- | ----------------------------------------------- |
| `ExitID`     | `STRING`  | UUID of the exit.                               |
| `Direction`  | `STRING`  | Direction of the exit (e.g., "north", "south"). |
| `TargetRoom` | `NUMBER`  | ID of the room the exit leads to.               |
| `Visible`    | `BOOLEAN` | Indicates if the exit is visible to players.    |

- **`ExitID`**: The UUID of the exit, serving as the primary key.
- **`Direction`**: The cardinal direction or named exit.
- **`TargetRoom`**: The `RoomID` of the destination room.
- **`Visible`**: A flag indicating whether the exit is visible to players.

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

| Field           | Type     | Description                                |
| --------------- | -------- | ------------------------------------------ |
| `ArchetypeName` | `STRING` | Name of the archetype.                     |
| `Description`   | `STRING` | Description of the archetype.              |
| `Attributes`    | `MAP`    | Default attributes for the archetype.      |
| `Abilities`     | `MAP`    | Default abilities for the archetype.       |
| `StartRoom`     | `NUMBER` | ID of the starting room for the archetype. |

- **`ArchetypeName`**: Primary key for the archetype.
- **`Description`**: Explains the archetype's role or characteristics.
- **`Attributes`**: Base attribute values assigned to the archetype.
- **`Abilities`**: Starting abilities associated with the archetype.

---

## MOTD Table (Messages of the Day)

| Field     | Type     | Description                                   |
| --------- | -------- | --------------------------------------------- |
| `MotdID`  | `STRING` | UUID of the message.                          |
| `Content` | `STRING` | The text content of the message.              |
| `Date`    | `STRING` | Date when the message was created or updated. |
| `Author`  | `STRING` | Author or creator of the message.             |

- **`MotdID`**: Primary key, uniquely identifies the message.
- **`Content`**: The actual message displayed to players.
- **`Date`**: Used to determine if players have seen the latest message.
- **`Author`**: Identifies who created or modified the message.

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

**Notes:**

- All tables are designed for use with Amazon DynamoDB.
- Primary keys are specified for each table to ensure data integrity.
- Data types correspond to DynamoDB data types (e.g., `STRING`, `NUMBER`, `MAP`, `LIST`, `BOOLEAN`).
- Maps (`MAP`) and lists (`LIST`) are used to store complex data structures.
- UUIDs are stored as strings to maintain consistency and readability.
- Ensure that any secondary indexes needed for queries are properly configured in DynamoDB.
- Field names in code (e.g., struct tags) should match the attribute names in DynamoDB for seamless data mapping.

---
