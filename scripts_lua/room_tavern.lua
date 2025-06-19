-- Example Lua script for a tavern room
-- This script demonstrates various room scripting capabilities

-- Script metadata - tells the engine what this script handles
SCRIPT_INFO = {
    commands = { "order", "ring" },  -- Commands this script handles
    events = { "onRoomStart", "onCharacterEnter" },  -- Events this script responds to
    periodic = true  -- This script has a periodic onTick function
}

-- Called when the room starts up
function onRoomStart()
    eidolon.log.info("Tavern script initialized")
    
    -- Add some ambient items to the room
    eidolon.room.addItem("wooden bar", "A long wooden bar with a polished surface, showing years of use.")
    eidolon.room.addItem("fireplace", "A large stone fireplace with a crackling fire that warms the room.")
    eidolon.room.addItem("menu board", "A chalkboard menu listing today's specials.")
end

-- Called when a character enters the room
function onCharacterEnter(character)
    local name = character.name
    eidolon.log.debug("Character " .. name .. " entered the tavern")
    
    -- Send a personalized greeting
    eidolon.room.sendToCharacter(name, "\n\rThe bartender looks up and nods at you. 'Welcome to the Wanderer's Rest!'\n\r")
    
    -- Announce to others
    eidolon.room.sendMessage("\n\rThe door chimes softly as someone enters.\n\r")
end

-- Called periodically (could be used for ambient messages)
function onTick()
    -- Random chance for ambient message
    if math.random(1, 100) <= 5 then  -- 5% chance per tick
        local messages = {
            "\n\rThe fire crackles softly in the fireplace.\n\r",
            "\n\rSomeone laughs heartily at the bar.\n\r",
            "\n\rThe bartender polishes a glass while humming an old tune.\n\r",
            "\n\rA gust of wind rattles the windows.\n\r"
        }
        local msg = messages[math.random(1, #messages)]
        eidolon.room.sendMessage(msg)
    end
end

-- Command handler for "order" command
function onCommandOrder(character, args)
    local name = character.name
    local drinkName = args[2]  -- args[1] is "order", args[2] is the drink name
    
    if drinkName == nil or drinkName == "" then
        eidolon.room.sendToCharacter(name, "\n\rThe bartender asks, 'What would you like to drink?'\n\r")
        return true  -- Command was handled
    end
    
    -- Simple drink menu
    local drinks = {
        ale = "A foamy mug of ale",
        wine = "A glass of red wine",
        mead = "A horn of honey mead",
        water = "A glass of clear water"
    }
    
    local drink = drinks[drinkName:lower()]
    if drink then
        eidolon.room.sendToCharacter(name, "\n\rThe bartender serves you " .. drink .. ".\n\r")
        eidolon.room.sendMessage("\n\rThe bartender serves " .. name .. " a drink.\n\r")
    else
        eidolon.room.sendToCharacter(name, "\n\rThe bartender says, 'Sorry, we don't have that. We serve ale, wine, mead, and water.'\n\r")
    end
    
    return true  -- Command was handled
end

-- Command handler for "ring" command (ring the bell for service)
function onCommandRing(character, args)
    local name = character.name
    
    eidolon.room.sendToCharacter(name, "\n\rYou ring the small brass bell on the bar.\n\r")
    eidolon.room.sendMessage("\n\r*DING* Someone rings the service bell.\n\r")
    eidolon.room.sendMessage("\n\rThe bartender hurries over, 'How may I help you?'\n\r")
    
    return true  -- Command was handled
end