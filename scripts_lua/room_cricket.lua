-- Cricket Room Script
-- Plays cricket chirps when there is exactly one character in the room
-- Crickets go quiet when someone speaks or when multiple people are present
-- Resume after 1 minute of silence

SCRIPT_INFO = {
    commands = {"say"},  -- Only handle say command for now
    events = {"onCharacterEnter", "onCharacterLeave", "onTick"},
    periodic = true
}

-- State variables
local lastActivityTime = 0
local isChirping = false
local lastChirpTime = 0
local isSilent = false

-- Constants
local CHIRP_INTERVAL = 20  -- seconds between chirps
local SILENCE_DURATION = 60  -- seconds of silence before chirping resumes

-- Initialize the script when room starts
function onRoomStart()
    lastActivityTime = os.time()
    isChirping = false
    lastChirpTime = 0
    isSilent = false
    eidolon.log.info("Cricket room script loaded")
end

-- Handle character entering the room
function onCharacterEnter(character)
    eidolon.log.debug("Character entered cricket room: " .. (character.name or "unknown"))
    
    local characters = eidolon.room.getCharacters()
    local characterCount = #characters
    
    if characterCount == 1 then
        -- First character enters empty room - start chirping immediately
        eidolon.log.debug("First character entered, starting cricket chirps")
        isSilent = false
        isChirping = true
        lastChirpTime = os.time()
        lastActivityTime = os.time()
        -- Play first chirp shortly after entry
        playChirp()
    else
        -- Multiple characters now - crickets go silent
        eidolon.log.debug("Multiple characters present, crickets go silent")
        isSilent = true
        isChirping = false
        lastActivityTime = os.time()
    end
end

-- Handle character leaving the room
function onCharacterLeave(character)
    eidolon.log.debug("Character left cricket room: " .. (character.name or "unknown"))
    lastActivityTime = os.time()
    
    local characters = eidolon.room.getCharacters()
    local characterCount = #characters
    
    if characterCount == 0 then
        -- Room is empty - stop everything
        eidolon.log.debug("Room empty, stopping cricket activity")
        isChirping = false
        isSilent = true
    elseif characterCount == 1 then
        -- Back to one character - will need to wait for silence period
        eidolon.log.debug("Room now has one character, crickets will resume after silence period")
        isChirping = false
        isSilent = true
    end
end

-- Handle say command
function onCommandSay(character, args)
    eidolon.log.debug("Character spoke in cricket room, crickets go silent")
    
    isSilent = true
    isChirping = false
    lastActivityTime = os.time()
    
    -- Let the command continue to be processed normally
    return false
end

-- Periodic tick function
function onTick()
    local characters = eidolon.room.getCharacters()
    local characterCount = #characters
    
    -- Don't run if room is empty
    if characterCount == 0 then
        isChirping = false
        isSilent = true
        return
    end
    
    -- Only proceed if there's exactly one character
    if characterCount ~= 1 then
        if isChirping then
            eidolon.log.debug("Stopping cricket chirps - multiple characters present")
        end
        isChirping = false
        isSilent = true
        return
    end
    
    local currentTime = os.time()
    local timeSinceActivity = currentTime - lastActivityTime
    
    -- Check if enough time has passed since last activity to resume chirping
    if isSilent and timeSinceActivity >= SILENCE_DURATION then
        eidolon.log.debug("Silence period ended, crickets resume chirping")
        isSilent = false
        isChirping = true
        lastChirpTime = currentTime
        playChirp()
    end
    
    -- If chirping and enough time since last chirp, play another chirp
    if isChirping and (currentTime - lastChirpTime) >= CHIRP_INTERVAL then
        lastChirpTime = currentTime
        playChirp()
    end
end

-- Play a cricket chirp sound
function playChirp()
    local messages = {
        "A cricket chirps softly in the distance.",
        "The gentle chirping of crickets fills the air.",
        "A lone cricket's song echoes quietly.",
        "You hear the rhythmic chirping of a cricket.",
        "A cricket's melodic chirp breaks the silence."
    }
    
    -- Pick a random message
    local message = messages[math.random(#messages)]
    eidolon.room.sendMessage(message)
    eidolon.log.debug("Cricket chirp played")
end

-- Note: onRoomStart will be called automatically when the room starts