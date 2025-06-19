-- Example puzzle room script
-- Demonstrates state management and interactive elements

-- Script metadata
SCRIPT_INFO = {
    commands = { "pull", "push", "reset" },  -- Commands this script handles
    events = { "onRoomStart", "onCharacterEnter" },  -- Events this script responds to
    periodic = false  -- No periodic tick needed
}

-- Room state (persists for the life of the script)
local puzzleState = {
    leverPosition = "up",
    doorOpen = false,
    attempts = 0
}

function onRoomStart()
    eidolon.log.info("Puzzle room script initialized")
    
    -- Set initial room description
    eidolon.room.setDescription("A mysterious chamber with stone walls. A large lever protrudes from the eastern wall, and a heavy iron door blocks the northern exit.")
    
    -- Add puzzle elements
    eidolon.room.addItem("stone lever", "A sturdy stone lever that can be pulled. It's currently in the up position.")
    eidolon.room.addItem("iron door", "A massive iron door with no visible handle or keyhole.")
    eidolon.room.addItem("inscription", "Ancient runes that read: 'Pull when the shadow points north.'")
end

function onCharacterEnter(character)
    local name = character.name
    
    if puzzleState.doorOpen then
        eidolon.room.sendToCharacter(name, "\n\rYou enter the chamber. The iron door to the north stands open.\n\r")
    else
        eidolon.room.sendToCharacter(name, "\n\rYou enter a mysterious chamber. The iron door to the north is sealed shut.\n\r")
    end
end

-- Command handler for "pull" command
function onCommandPull(character, args)
    local name = character.name
    puzzleState.attempts = puzzleState.attempts + 1
    
    -- Check time to determine if puzzle should be solved
    local hour = tonumber(os.date("%H"))
    local minute = tonumber(os.date("%M"))
    
    -- The "shadow points north" at noon (12:00)
    local isNoon = (hour == 12 and minute >= 0 and minute <= 5)
    
    if puzzleState.leverPosition == "up" then
        puzzleState.leverPosition = "down"
        eidolon.room.sendToCharacter(name, "\n\rYou pull the lever down. It moves with a grinding sound.\n\r")
        eidolon.room.sendMessage("\n\r" .. name .. " pulls the stone lever.\n\r")
        
        if isNoon and not puzzleState.doorOpen then
            -- Puzzle solved!
            puzzleState.doorOpen = true
            eidolon.room.sendMessage("\n\rThe iron door rumbles and slowly swings open!\n\r")
            eidolon.room.setDescription("A mysterious chamber with stone walls. The lever is in the down position, and the iron door to the north stands open.")
            eidolon.log.info("Puzzle solved after " .. puzzleState.attempts .. " attempts")
        elseif puzzleState.doorOpen then
            eidolon.room.sendToCharacter(name, "\n\rNothing happens. The door remains open.\n\r")
        else
            eidolon.room.sendToCharacter(name, "\n\rNothing happens. The timing doesn't seem right.\n\r")
        end
    else
        puzzleState.leverPosition = "up"
        eidolon.room.sendToCharacter(name, "\n\rThe lever is already up.\n\r")
    end
    
    return true  -- Command was handled
end

-- Command handler for "push" command
function onCommandPush(character, args)
    local name = character.name
    
    if puzzleState.leverPosition == "down" then
        puzzleState.leverPosition = "up"
        eidolon.room.sendToCharacter(name, "\n\rYou push the lever back up.\n\r")
        eidolon.room.sendMessage("\n\r" .. name .. " pushes the stone lever back up.\n\r")
    else
        eidolon.room.sendToCharacter(name, "\n\rThe lever is already in the up position.\n\r")
    end
    
    return true  -- Command was handled
end

-- Command handler for "reset" command (could be admin only)
function onCommandReset(character, args)
    puzzleState.leverPosition = "up"
    puzzleState.doorOpen = false
    puzzleState.attempts = 0
    
    eidolon.room.setDescription("A mysterious chamber with stone walls. A large lever protrudes from the eastern wall, and a heavy iron door blocks the northern exit.")
    eidolon.room.sendMessage("\n\rThe iron door rumbles shut and the lever resets to its original position.\n\r")
    eidolon.log.info("Puzzle has been reset by " .. character.name)
    
    return true  -- Command was handled
end