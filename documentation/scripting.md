# Eidolon Engine Lua Scripting System

The Eidolon Engine incorporates a powerful Lua scripting system that allows developers and game operators to create dynamic, interactive content for rooms, items, and other game elements. Scripts are stored in Amazon S3 and loaded on demand by the game server.

## Architecture Overview

The scripting system consists of two main components:

- **ScriptManager** (`server/scripting.go`): Manages script loading, caching, and execution
- **Script API** (`server/scripting-api.go`): Provides Lua functions for interacting with game objects

Scripts are automatically loaded when referenced and cached for performance. The system supports concurrent execution using Lua coroutines to prevent blocking the main game loop.

## Script Storage and Deployment

Scripts are stored in Amazon S3 with the following structure:

```
s3://your-bucket/scripts/
├── room_tavern.lua
├── room_cricket.lua
├── room_puzzle.lua
└── ...
```

### Deployment

Use the deployment script to upload scripts:

```bash
cd deployment
./deploy_scripts.py <bucket-name>
```

Options:

- `--dry-run`: Preview what would be uploaded
- `--profile <name>`: Use specific AWS profile
- `list`: List deployed scripts
- `delete <script>`: Remove a script

## Script Structure

All Lua scripts must include a `SCRIPT_INFO` table that declares the script's capabilities:

```lua
SCRIPT_INFO = {
    commands = { "order", "ring", "say" },  -- Commands this script handles
    events = { "onRoomStart", "onCharacterEnter" },  -- Events this script responds to
    periodic = true  -- Whether script has onTick function
}
```

### Script Metadata

- **commands**: Array of command verbs the script can handle (e.g., "pull", "push", "order")
- **events**: Array of game events the script responds to
- **periodic**: Boolean indicating if the script has an `onTick` function for periodic execution

## Available APIs

Scripts have access to the global `eidolon` table with the following APIs:

### Room Functions (`eidolon.room`)

| Function                         | Parameters                        | Description                            |
| -------------------------------- | --------------------------------- | -------------------------------------- |
| `sendMessage(message)`           | message: string                   | Send message to all characters in room |
| `sendToCharacter(name, message)` | name: string, message: string     | Send message to specific character     |
| `getCharacters()`                | none                              | Get array of character tables in room  |
| `getItems()`                     | none                              | Get array of item tables in room       |
| `addItem(name, description)`     | name: string, description: string | Add new item to room                   |
| `removeItem(name)`               | name: string                      | Remove item from room by name          |
| `setDescription(description)`    | description: string               | Change room description                |
| `getExits()`                     | none                              | Get array of exit tables               |

### Logging Functions (`eidolon.log`)

| Function         | Parameters      | Description               |
| ---------------- | --------------- | ------------------------- |
| `info(message)`  | message: string | Log informational message |
| `debug(message)` | message: string | Log debug message         |
| `error(message)` | message: string | Log error message         |

## Event Handlers

Scripts can implement event handlers by defining functions with specific names:

### Standard Events

- `onRoomStart()`: Called when room initializes
- `onCharacterEnter(character)`: Called when character enters room
- `onCharacterLeave(character)`: Called when character leaves room
- `onTick()`: Called periodically if `periodic = true` in SCRIPT_INFO

### Event Parameters

**Character table structure:**

```lua
{
    name = "PlayerName",
    id = "uuid-string",
    state = "playing",
    hidden = false
}
```

## Command Handlers

Command handlers follow the naming pattern `onCommand<Verb>` where `<Verb>` is the capitalized command verb.

### Function Signature

```lua
function onCommandVerb(character, args)
    -- character: table with character info
    -- args: array of command arguments (args[1] is the verb)

    -- Perform command logic

    return true  -- Return true if command was handled, false otherwise
end
```

### Example Command Handler

```lua
function onCommandOrder(character, args)
    local name = character.name
    local item = args[2]  -- args[1] is "order"

    if item == "ale" then
        eidolon.room.sendToCharacter(name, "The bartender serves you a foamy ale.")
        return true
    end

    return false  -- Command not handled
end
```

## Script Examples

### Basic Room Script

```lua
SCRIPT_INFO = {
    commands = { "examine" },
    events = { "onRoomStart", "onCharacterEnter" },
    periodic = false
}

function onRoomStart()
    eidolon.log.info("Room script initialized")
    eidolon.room.addItem("sign", "A weathered wooden sign.")
end

function onCharacterEnter(character)
    eidolon.room.sendToCharacter(character.name, "Welcome to this special room!")
end

function onCommandExamine(character, args)
    local target = args[2]
    if target == "sign" then
        eidolon.room.sendToCharacter(character.name, "The sign reads: 'Welcome, traveler!'")
        return true
    end
    return false
end
```

### Periodic Script with State

```lua
SCRIPT_INFO = {
    commands = {},
    events = { "onRoomStart" },
    periodic = true
}

local tickCount = 0

function onRoomStart()
    tickCount = 0
    eidolon.log.info("Periodic script started")
end

function onTick()
    tickCount = tickCount + 1

    -- Send ambient message every 10 ticks
    if tickCount % 10 == 0 then
        eidolon.room.sendMessage("The room hums with mysterious energy.")
    end
end
```

## Script Types

### Room Scripts (`room_*.lua`)

Room scripts handle room-specific interactions and are loaded when a room has a `scriptID` field set. They can:

- Handle custom commands within the room
- Respond to character movement events
- Provide periodic ambient effects
- Modify room state dynamically

**Configuration**:

- Set `scriptID` field in room data to script name (without .lua extension)
- Scripts can be enabled/disabled at runtime using the `scriptActive` flag
- When `scriptActive` is false, the script won't handle commands or events

### Future Script Types

- **Item Scripts** (`item_*.lua`): Handle item-specific interactions
- **Exit Scripts** (`exit_*.lua`): Handle exit-specific behaviors
- **Global Scripts**: Server-wide functionality

## Performance Considerations

### Script Caching

- Scripts are cached in memory after first load
- Cache entries include content and metadata
- Automatic cache cleanup removes old unused scripts
- Use `ClearCache()` to manually manage cache size

### Concurrency

- Each room gets its own isolated Lua state to prevent cross-contamination
- Scripts cannot block the main game loop
- Room-specific states ensure scripts in different rooms don't interfere
- Thread-safe operations are enforced through mutex protection

### Resource Management

- Scripts are automatically unloaded when not in use
- Memory usage is monitored through cache statistics
- S3 requests are minimized through intelligent caching

## Configuration

Add script configuration to your `config.yml`:

```yaml
Game:
  ScriptsS3Bucket: "eidolon-scripts"
  ScriptsS3Prefix: "scripts/" # Optional, defaults to "scripts/"
```

## Best Practices

### Script Design

1. **Keep scripts focused**: Each script should handle a specific set of related functionality
2. **Use appropriate events**: Only declare events your script actually uses
3. **Handle errors gracefully**: Use logging for debugging and error reporting
4. **Minimize state**: Keep script state simple and well-documented

### Performance

1. **Efficient command checking**: Use SCRIPT_INFO metadata for command filtering
2. **Limit periodic operations**: Use `periodic = true` sparingly
3. **Cache expensive operations**: Store results of complex calculations
4. **Minimize S3 requests**: Scripts are cached automatically

### Security

1. **Input validation**: Always validate command arguments and user input
2. **Safe operations**: Use provided APIs rather than attempting system calls
3. **Error boundaries**: Handle script errors without crashing the game

### Debugging

1. **Use logging**: Utilize `eidolon.log` functions for debugging
2. **Test incrementally**: Test scripts with simple functionality first
3. **Monitor logs**: Check server logs for script execution errors
4. **Validate metadata**: Ensure SCRIPT_INFO matches actual script capabilities

## Error Handling

The scripting system provides robust error handling:

- Script loading errors are logged and prevent script activation
- Runtime errors are caught and logged without crashing the server
- Failed commands return false, allowing fallback to default handlers
- Missing event handlers are silently ignored
- Panic recovery ensures script errors never crash the game server
- All script executions are protected to maintain server stability

## Troubleshooting

### Common Issues

1. **Script not loading**: Check S3 bucket configuration and script syntax
2. **Commands not working**: Verify command is listed in SCRIPT_INFO.commands
3. **Events not firing**: Ensure event names match exactly and are declared
4. **Performance issues**: Check for infinite loops in onTick functions

## Updating Scripts

When updating scripts:

1. Test changes in development environment
2. Deploy to S3 using deployment script
3. Reload scripts on running servers if needed
4. Monitor logs for any errors after deployment

The scripting system provides a powerful way to create dynamic, engaging content while maintaining performance and reliability in the Eidolon Engine.
