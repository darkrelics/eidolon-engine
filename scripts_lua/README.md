# Eidolon Engine Lua Scripts

This directory contains Lua scripts for the Eidolon Engine.

## Naming Convention

Scripts are organized by type:

- `room_*.lua` - Room scripts that handle room-specific commands and events
- `item_*.lua` - Item scripts (future)
- `exit_*.lua` - Exit scripts (future)

## Script Structure

All scripts must include a `SCRIPT_INFO` table that declares:

- `commands` - Array of command verbs the script handles
- `events` - Array of events the script responds to
- `periodic` - Boolean indicating if the script has an `onTick` function

Example:

```lua
SCRIPT_INFO = {
    commands = { "order", "ring" },
    events = { "onRoomStart", "onCharacterEnter" },
    periodic = true
}
```

## Deployment

Scripts are deployed to S3 using the deployment script:

```bash
cd deployment
./deploy_scripts.py <bucket-name>
```

Additional options:

- `--dry-run` - Show what would be uploaded without doing it
- `--profile <name>` - Use a specific AWS profile
- `list` - List deployed scripts
- `delete <script>` - Delete a specific script

## Room Scripts

Room scripts are loaded when a room starts if the room has a `scriptID` field set.

### Available Room Scripts

- `room_tavern` - Interactive tavern with drink ordering
- `room_puzzle` - Puzzle room with lever mechanism

### Room API Functions

Scripts have access to the `eidolon` global table with these APIs:

**Room functions:**

- `eidolon.room.sendMessage(message)` - Send message to all in room
- `eidolon.room.sendToCharacter(name, message)` - Send to specific character
- `eidolon.room.getCharacters()` - Get list of characters in room
- `eidolon.room.getItems()` - Get list of items in room
- `eidolon.room.addItem(name, description)` - Add item to room
- `eidolon.room.removeItem(name)` - Remove item from room
- `eidolon.room.setDescription(description)` - Change room description
- `eidolon.room.getExits()` - Get list of exits

**Logging functions:**

- `eidolon.log.info(message)`
- `eidolon.log.debug(message)`
- `eidolon.log.error(message)`

### Command Handlers

Command handlers follow the naming pattern `onCommand<Verb>` and receive:

- `character` - Table with character info (name, id)
- `args` - Array of command arguments

Example:

```lua
function onCommandOrder(character, args)
    local drinkName = args[2]  -- args[1] is "order"
    -- Handle order command
    return true  -- Return true if command was handled
end
```

### Event Handlers

- `onRoomStart()` - Called when room initializes
- `onCharacterEnter(character)` - Called when character enters
- `onTick()` - Called periodically if `periodic = true`
