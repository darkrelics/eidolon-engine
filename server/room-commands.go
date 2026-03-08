/*
Eidolon Engine

Copyright 2024-2026 Jason E. Robinson

*/

package main

import (
	"fmt"
	"strings"
	"time"

	"github.com/gofrs/uuid/v5"
	"github.com/robinje/eidolon-engine/events"
)

// Room command messages
const (
	msgNoExits     = "There are no visible exits."
	msgNoDirection = "Which direction do you want to go?"
	msgCantEscape  = "You can't escape!"
	msgInvalidDir  = "You cannot go that way."
	msgPathNowhere = "The path leads nowhere."
)

// Stealth system constants
const (
	hideBaseDifficulty = 4                // Base difficulty for hide attempts
	hideActionTime     = 3 * time.Second  // Time blocked after hide attempt
	hideRateLimit      = 10 * time.Second // Cooldown between hide attempts
	sneakActionTime    = 5 * time.Second  // Time blocked after sneak attempt
	searchActionTime   = 3 * time.Second  // Time blocked after search attempt
)

// Combat range constants
const (
	combatRangeClose   = 0.0  // Close combat range
	combatRangeMelee   = 3.0  // Melee weapon range
	combatRangePole    = 10.0 // Pole weapon range
	combatRangeDefault = 30.0 // Default starting combat range
)

// processRoomCommand handles commands at the room level
func (r *Room) ProcessRoomCommand(cmd *CommandRequest, game *Game) *CommandResponse {
	if cmd == nil {
		return &CommandResponse{
			Success:   false,
			Error:     fmt.Errorf("invalid command"),
			Timestamp: time.Now(),
		}
	}

	// Create default response
	response := &CommandResponse{
		RequestID: cmd.ID,
		Success:   false,
		Timestamp: time.Now(),
	}

	// Try script commands first if room has an active script
	if r.scriptID != "" && r.scriptActive && ScriptMgr != nil {
		handled, err := ScriptMgr.ExecuteRoomCommand(r, cmd)
		if err != nil {
			Logger.Error("Script command execution error", "error", err, "roomID", r.roomID, "command", cmd.Verb)
		}
		if handled {
			response.Success = true
			return response
		}
	}

	// Try to handle common room commands
	verb := strings.ToLower(cmd.Verb)

	// Movement commands
	if verb == "go" || verb == "move" {
		return handleMovementCommand(cmd, game)
	}

	// Item commands
	if verb == "get" || verb == "take" || verb == "drop" || verb == "put" || verb == "wear" || verb == "equip" || verb == "remove" || verb == "switch" {
		return handleItemCommand(cmd)
	}

	// Communication commands
	if verb == "say" || verb == "\"" || verb == "'" {
		return handleSayCommand(cmd, game)
	}

	// Stealth commands
	if verb == "hide" {
		return handleHideCommand(cmd, r)
	}
	if verb == "sneak" {
		return handleSneakCommand(cmd, game)
	}
	if verb == "search" {
		return handleSearchCommand(cmd, r)
	}
	if verb == "point" {
		return handlePointCommand(cmd, r)
	}

	// Look command (room-level effects)
	if verb == "look" || verb == "l" {
		// This is typically handled at the character level, but might have room-level effects
		response.Success = true
		return response
	}

	// Combat commands
	if verb == "face" {
		return handleFaceCommand(cmd, r)
	}
	if verb == "advance" {
		return handleAdvanceCommand(cmd, r)
	}
	if verb == "retreat" {
		return handleRetreatCommand(cmd, r)
	}
	if verb == "assess" {
		return handleAssessCommand(cmd)
	}
	if verb == "flee" {
		return handleFleeCommand(cmd, r)
	}

	// Unknown command at room level
	Logger.Debug("Room cannot handle command, will escalate", "verb", cmd.Verb, "roomID", r.roomID)
	response.Error = fmt.Errorf("unknown room command: %s", cmd.Verb)
	return response
}

func handleSayCommand(cmd *CommandRequest, game *Game) *CommandResponse {
	character := cmd.Character

	if character == nil || character.room == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid character or room state"),
			Timestamp: time.Now(),
		}
	}

	// Check if there's text to say
	if len(cmd.Args) < 2 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   true,
			Message:   "\n\rWhat do you want to say?\n\r",
			Timestamp: time.Now(),
		}
	}

	// Join all arguments after the command to form the message
	message := strings.Join(cmd.Args[1:], " ")

	// Check if character is dead or a ghost
	if character.charState == CharStateDead || character.charState == CharStateGhost {
		// Dead/ghost trying to speak
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   true,
			Message:   ApplyColor("cyan", "\n\rYour voice cannot cross the veil of death.\n\r"),
			Timestamp: time.Now(),
		}
	}

	// Create Event
	event := events.NewChatEvent(character.id, message, character.room.roomID, character.name)

	// Save Event
	if game.eventStore != nil {
		if err := game.eventStore.Save(event); err != nil {
			Logger.Error("Failed to save chat event", "error", err)
		}
	}

	// Apply Event (this handles the broadcasting)
	character.ApplyEvent(event)

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   "", // Message handled by ApplyEvent
		Timestamp: time.Now(),
	}
}

// handleItemCommand processes item-related commands like get, take, drop, etc.
func handleItemCommand(cmd *CommandRequest) *CommandResponse {
	if len(cmd.Args) < 2 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   true,
			Message:   fmt.Sprintf("\n\rWhat do you want to %s?\n\r", cmd.Verb),
			Timestamp: time.Now(),
		}
	}

	// Reveal character if hidden - item actions break stealth
	character := cmd.Character
	if character != nil && character.IsHidden() {
		character.SetHidden(false)
		character.DisplayMessage("You reveal yourself as you interact with items.")

		if character.room != nil {
			SendRoomMessage(character.room,
				fmt.Sprintf("\n\r%s suddenly appears!\n\r", character.name),
				character,
			)
		}
	}

	targetName := strings.ToLower(strings.Join(cmd.Args[1:], " "))

	// Strip common articles and possessives
	targetName = stripArticles(targetName)

	switch cmd.Verb {
	case "get", "take":
		// Special handling for "take from" command
		if len(cmd.Args) >= 4 && strings.ToLower(cmd.Args[2]) == "from" {
			return handleTakeFromCommand(cmd)
		}
		return handleGetCommand(cmd, targetName)
	case "drop":
		return handleDropCommand(cmd, targetName)
	case "put":
		return handlePutCommand(cmd)
	case "wear":
		return handleWearCommand(cmd, targetName)
	case "remove":
		return handleRemoveCommand(cmd, targetName)
	case "switch":
		return handleSwitchCommand(cmd, targetName)
	default:
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid item command: %s", cmd.Verb),
			Timestamp: time.Now(),
		}
	}
}

// stripArticles removes common articles and possessives from the beginning of a string
func stripArticles(input string) string {
	// List of common articles and possessives to strip
	prefixes := []string{"the ", "a ", "an ", "my ", "your ", "his ", "her ", "its ", "their ", "our "}

	// Check each prefix and remove it if found
	for _, prefix := range prefixes {
		if strings.HasPrefix(input, prefix) {
			return strings.TrimPrefix(input, prefix)
		}
	}

	return input
}

// handleFaceCommand processes the FACE command to target a character for combat
func handleFaceCommand(cmd *CommandRequest, r *Room) *CommandResponse {
	character := cmd.Character
	if character == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid character"),
			Timestamp: time.Now(),
		}
	}

	// Check if a target was provided
	if len(cmd.Args) < 2 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   true,
			Message:   "\n\rWho do you want to face?\n\r",
			Timestamp: time.Now(),
		}
	}

	// Get the target name
	targetName := strings.ToLower(strings.Join(cmd.Args[1:], " "))
	targetName = stripArticles(targetName)

	// Look for the target in the room
	r.mutex.RLock()
	var target *Character
	for _, char := range r.characters {
		if char != nil && char != character && strings.Contains(strings.ToLower(char.name), targetName) {
			target = char
			break
		}
	}
	r.mutex.RUnlock()

	if target == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   true,
			Message:   "\n\rYou don't see anyone here by that name.\n\r",
			Timestamp: time.Now(),
		}
	}

	// Clear any existing facing targets that are no longer in the same room
	character.mutex.Lock()
	if character.facing != nil && character.facing.room != character.room {
		character.facing = nil
	}
	character.facing = target
	character.mutex.Unlock()

	// Clear the target's facing if they were facing someone not in the room
	target.mutex.Lock()
	if target.facing != nil && target.facing.room != target.room {
		target.facing = nil
	}
	target.mutex.Unlock()

	// Initialize combat ranges with default combatRangeDefault if no existing range
	r.mutex.Lock()
	if r.combatRanges[character.id] == nil {
		r.combatRanges[character.id] = make(map[uuid.UUID]float64)
	}
	if r.combatRanges[target.id] == nil {
		r.combatRanges[target.id] = make(map[uuid.UUID]float64)
	}

	// Only set default range if no existing range between these characters
	if _, exists := r.combatRanges[character.id][target.id]; !exists {
		r.combatRanges[character.id][target.id] = combatRangeDefault
		r.combatRanges[target.id][character.id] = combatRangeDefault
	}
	r.mutex.Unlock()

	// Send messages
	character.DisplayMessage(fmt.Sprintf("\n\rYou turn to face %s.\n\r", target.name))
	target.DisplayMessage(fmt.Sprintf("\n\r%s turns to face you!\n\r", character.name))
	SendRoomMessage(r, fmt.Sprintf("\n\r%s turns to face %s.\n\r", character.name, target.name), character, target)

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Timestamp: time.Now(),
	}
}

// handleAssessCommand shows the room's current combat situation
func handleAssessCommand(cmd *CommandRequest) *CommandResponse {
	character := cmd.Character
	if character == nil || character.room == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid character or room"),
			Timestamp: time.Now(),
		}
	}

	room := character.room
	var message strings.Builder

	// Check personal facing status
	character.mutex.RLock()
	facing := character.facing
	character.mutex.RUnlock()

	if facing != nil && facing.room == character.room {
		message.WriteString(fmt.Sprintf("\n\rYou are facing %s.\n\r", facing.name))
	} else {
		// Clear stale facing if target is no longer in the same room
		if facing != nil {
			character.mutex.Lock()
			character.facing = nil
			character.mutex.Unlock()
		}
		message.WriteString("\n\rYou are not currently facing anyone.\n\r")
	}

	// Show room combat situation
	room.mutex.RLock()
	hasAnyCombat := false

	// Check if this character is in combat with others
	if ranges, exists := room.combatRanges[character.id]; exists && len(ranges) > 0 {
		hasAnyCombat = true
		message.WriteString("\n\rYou are in combat with:\n\r")
		for targetID, distance := range ranges {
			if target, found := room.characters[targetID]; found {
				rangeDesc := getRangeDescription(distance)
				message.WriteString(fmt.Sprintf("  %s (%s)\n\r", target.name, rangeDesc))
			}
		}
	}

	// Show other combat pairs in the room (excluding those involving this character)
	otherCombatPairs := make(map[string]bool) // Track pairs to avoid duplicates
	for attackerID, targets := range room.combatRanges {
		if attackerID == character.id {
			continue // Skip this character's combat ranges
		}

		if attacker, found := room.characters[attackerID]; found {
			for targetID, distance := range targets {
				if targetID == character.id {
					continue // Skip combat involving this character
				}

				if target, found := room.characters[targetID]; found {
					// Create a normalized pair key to avoid duplicates
					var pairKey string
					if attackerID.String() < targetID.String() {
						pairKey = fmt.Sprintf("%s-%s", attackerID.String(), targetID.String())
					} else {
						pairKey = fmt.Sprintf("%s-%s", targetID.String(), attackerID.String())
					}

					if !otherCombatPairs[pairKey] {
						if !hasAnyCombat {
							message.WriteString("\n\rOther combat in the room:\n\r")
							hasAnyCombat = true
						}
						rangeDesc := getRangeDescription(distance)
						message.WriteString(fmt.Sprintf("  %s vs %s (%s)\n\r", attacker.name, target.name, rangeDesc))
						otherCombatPairs[pairKey] = true
					}
				}
			}
		}
	}
	room.mutex.RUnlock()

	if !hasAnyCombat {
		message.WriteString("\n\rNo combat is currently taking place in this room.\n\r")
	}

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   message.String(),
		Timestamp: time.Now(),
	}
}

// getRangeDescription returns the range category based on distance
func getRangeDescription(distance float64) string {
	if distance < 5.0 {
		return "melee"
	} else if distance <= 15.0 {
		return "pole"
	} else {
		return "far"
	}
}

// initiateCombat sets up combat ranges between two characters at the specified distance
func (r *Room) initiateCombat(char1, char2 *Character, distance float64) {
	r.mutex.Lock()
	defer r.mutex.Unlock()

	if r.combatRanges[char1.id] == nil {
		r.combatRanges[char1.id] = make(map[uuid.UUID]float64)
	}
	if r.combatRanges[char2.id] == nil {
		r.combatRanges[char2.id] = make(map[uuid.UUID]float64)
	}

	r.combatRanges[char1.id][char2.id] = distance
	r.combatRanges[char2.id][char1.id] = distance
}

// removeCharacterFromCombat removes all combat ranges for a specific character
func (r *Room) removeCharacterFromCombat(character *Character) {
	r.mutex.Lock()
	defer r.mutex.Unlock()

	// Remove the character's outgoing combat ranges
	delete(r.combatRanges, character.id)

	// Remove the character from other characters' combat ranges
	for _, targets := range r.combatRanges {
		if targets != nil {
			delete(targets, character.id)
		}
	}
}

// getCombatRange returns the combat range between two characters, or -1 if not in combat
func (r *Room) getCombatRange(char1, char2 *Character) float64 {
	r.mutex.RLock()
	defer r.mutex.RUnlock()

	if ranges, exists := r.combatRanges[char1.id]; exists {
		if distance, found := ranges[char2.id]; found {
			return distance
		}
	}
	return -1
}

// setCombatRange updates the combat range between two characters
func (r *Room) setCombatRange(char1, char2 *Character, distance float64) {
	r.mutex.Lock()
	defer r.mutex.Unlock()

	if r.combatRanges[char1.id] != nil {
		r.combatRanges[char1.id][char2.id] = distance
	}
	if r.combatRanges[char2.id] != nil {
		r.combatRanges[char2.id][char1.id] = distance
	}
}

// handleAdvanceCommand processes the ADVANCE command
func handleAdvanceCommand(cmd *CommandRequest, r *Room) *CommandResponse {
	character := cmd.Character
	if character == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid character"),
			Timestamp: time.Now(),
		}
	}

	// Check round time
	if time.Now().Before(character.waitUntil) {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Message:   "\n\rYou are still recovering from your last action.\n\r",
			Timestamp: time.Now(),
		}
	}

	// Parse arguments: ADVANCE [target] [range]
	var targetName string
	var rangeType string

	if len(cmd.Args) > 1 {
		targetName = strings.ToLower(strings.Join(cmd.Args[1:], " "))
		// Check if last argument is a range type
		lastArg := strings.ToLower(cmd.Args[len(cmd.Args)-1])
		if lastArg == "pole" || lastArg == "melee" {
			rangeType = lastArg
			// Reconstruct target name without range
			if len(cmd.Args) > 2 {
				targetName = strings.ToLower(strings.Join(cmd.Args[1:len(cmd.Args)-1], " "))
			} else {
				targetName = ""
			}
		}
	}

	// Strip articles from target name
	if targetName != "" {
		targetName = stripArticles(targetName)
	}

	// Determine target range based on range type
	var targetRange float64
	switch rangeType {
	case "pole":
		targetRange = combatRangePole
	case "melee":
		targetRange = combatRangeMelee
	case "":
		targetRange = combatRangeClose
	default:
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Message:   "\n\rValid range options are: melee, pole, or omit for close combat.\n\r",
			Timestamp: time.Now(),
		}
	}

	// If target specified, execute face command first
	if targetName != "" {
		// Find target in room
		r.mutex.RLock()
		var target *Character
		for _, c := range r.characters {
			if c != nil && c != character && strings.Contains(strings.ToLower(c.name), targetName) {
				target = c
				break
			}
		}
		r.mutex.RUnlock()

		if target == nil {
			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Message:   "\n\rYou don't see anyone here by that name.\n\r",
				Timestamp: time.Now(),
			}
		}

		// Update facing - only lock for the actual update
		character.mutex.Lock()
		if character.facing != nil && character.facing.room != character.room {
			character.facing = nil
		}
		character.facing = target
		targetName := target.name
		character.mutex.Unlock()

		// Initialize combat if needed
		r.initiateCombat(character, target, combatRangeDefault)

		// Send facing messages with advance context
		character.DisplayMessage(fmt.Sprintf("\n\rYou advance on %s.\n\r", targetName))
		target.DisplayMessage(fmt.Sprintf("\n\r%s advances on you!\n\r", character.name))
		SendRoomMessage(r, fmt.Sprintf("\n\r%s advances on %s.\n\r", character.name, targetName), character, target)
	} else {
		// No target specified - check if already facing someone or in combat
		character.mutex.RLock()
		currentFacing := character.facing
		character.mutex.RUnlock()

		if currentFacing == nil {
			// Check if character is in combat ranges
			r.mutex.RLock()
			var potentialTarget *Character
			if ranges, exists := r.combatRanges[character.id]; exists && len(ranges) > 0 {
				// Find first character facing this character
				for targetID := range ranges {
					for _, c := range r.characters {
						if c != nil && c.id == targetID {
							c.mutex.RLock()
							if c.facing == character {
								potentialTarget = c
							}
							c.mutex.RUnlock()
							if potentialTarget != nil {
								break
							}
						}
					}
					if potentialTarget != nil {
						break
					}
				}
			}
			r.mutex.RUnlock()

			if potentialTarget == nil {
				return &CommandResponse{
					RequestID: cmd.ID,
					Success:   false,
					Message:   "\n\rThere isn't anybody to advance on.\n\r",
					Timestamp: time.Now(),
				}
			}

			// Update facing - only lock for the actual update
			character.mutex.Lock()
			character.facing = potentialTarget
			character.mutex.Unlock()
		}
	}

	// Check if we have a valid facing target
	character.mutex.RLock()
	facingTarget := character.facing
	character.mutex.RUnlock()

	if facingTarget != nil {
		// Set combat movement - only lock for the actual update
		character.mutex.Lock()
		character.combatMovement = &CombatMovement{
			mode:        "advance",
			targetID:    facingTarget.id,
			targetRange: targetRange,
		}
		character.mutex.Unlock()

		// Add to movement list
		r.AddCharacterToMove(character)

		var rangeName string
		switch targetRange {
		case combatRangeMelee:
			rangeName = "melee range"
		case combatRangePole:
			rangeName = "pole range"
		default:
			rangeName = "close combat"
		}

		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   true,
			Message:   fmt.Sprintf("\n\rYou begin advancing to %s.\n\r", rangeName),
			Timestamp: time.Now(),
		}
	} else {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Message:   "\n\rThere isn't anybody to advance on.\n\r",
			Timestamp: time.Now(),
		}
	}
}

// handleRetreatCommand processes the RETREAT command
func handleRetreatCommand(cmd *CommandRequest, r *Room) *CommandResponse {
	character := cmd.Character
	if character == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid character"),
			Timestamp: time.Now(),
		}
	}

	// Check round time
	if time.Now().Before(character.waitUntil) {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Message:   "\n\rYou are still recovering from your last action.\n\r",
			Timestamp: time.Now(),
		}
	}

	// Parse range argument
	var targetRange = 45.0

	if len(cmd.Args) > 1 {
		rangeType := strings.ToLower(cmd.Args[1])
		switch rangeType {
		case "melee":
			targetRange = 5.0
		case "pole":
			targetRange = combatRangePole
		case "far":
			targetRange = 30.0
		default:
			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Message:   "\n\rValid range options are: melee, pole, far, or omit for maximum distance.\n\r",
				Timestamp: time.Now(),
			}
		}
	}

	// Check if in combat
	r.mutex.RLock()
	ranges, exists := r.combatRanges[character.id]
	inCombat := exists && len(ranges) > 0
	r.mutex.RUnlock()

	if !inCombat {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Message:   "\n\rYou are not in combat.\n\r",
			Timestamp: time.Now(),
		}
	}

	// Set combat movement - only lock for the actual update
	character.mutex.Lock()
	character.combatMovement = &CombatMovement{
		mode:        "retreat",
		targetRange: targetRange,
	}
	character.mutex.Unlock()

	// Add to movement list
	r.AddCharacterToMove(character)

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   "\n\rYou begin retreating.\n\r",
		Timestamp: time.Now(),
	}
}

// handleFleeCommand processes the FLEE command
func handleFleeCommand(cmd *CommandRequest, r *Room) *CommandResponse {
	character := cmd.Character
	if character == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid character"),
			Timestamp: time.Now(),
		}
	}

	// FLEE has no round time requirement

	// Parse optional exit argument
	var exitDirection string
	if len(cmd.Args) >= 2 {
		exitDirection = strings.ToLower(cmd.Args[1])

		// Verify exit exists if direction specified
		r.mutex.RLock()
		var targetExit *Exit
		for _, exit := range r.exits {
			if exit != nil && strings.EqualFold(exit.direction, exitDirection) {
				targetExit = exit
				break
			}
		}
		r.mutex.RUnlock()

		if targetExit == nil {
			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Message:   "\n\rThere is no exit in that direction.\n\r",
				Timestamp: time.Now(),
			}
		}
	}

	// Get current facing target
	character.mutex.Lock()
	oldFacing := character.facing
	character.facing = nil
	hadCombatMovement := character.combatMovement != nil
	if hadCombatMovement {
		character.combatMovement = nil
	}
	// Set flee state
	character.fleeTarget = &FleeState{
		exitDirection: exitDirection,
		startTime:     time.Now(),
		hasDirection:  exitDirection != "",
	}
	character.mutex.Unlock()

	// Clear reciprocal facing if needed
	if oldFacing != nil {
		oldFacing.mutex.Lock()
		if oldFacing.facing == character {
			oldFacing.facing = nil
		}
		oldFacing.mutex.Unlock()
	}

	// Update room lists
	r.AddCharacterToFlee(character)
	if hadCombatMovement {
		r.RemoveCharacterToMove(character)
	}

	// Send messages
	if exitDirection != "" {
		character.DisplayMessage(fmt.Sprintf("\n\rYou attempt to flee %s!\n\r", exitDirection))
	} else {
		character.DisplayMessage("\n\rYou attempt to flee from combat!\n\r")
	}
	SendRoomMessage(r, fmt.Sprintf("\n\r%s attempts to flee!\n\r", character.name), character)

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Timestamp: time.Now(),
	}
}
