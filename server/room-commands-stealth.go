/*
Eidolon Engine - Stealth Commands (Hide/Sneak/Search/Point)

Copyright 2024-2026 Jason E. Robinson

*/

package main

import (
	"fmt"
	"strings"
	"time"
)

// handleHideCommand processes the hide command
func handleHideCommand(cmd *CommandRequest, room *Room) *CommandResponse {
	character := cmd.Character
	if character == nil || room == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid character or room state"),
			Timestamp: time.Now(),
		}
	}

	// Verify character is actually in this room
	if character.room != room {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("character room mismatch"),
			Timestamp: time.Now(),
		}
	}

	// Rate limiting: 10-second cooldown prevents hide spam
	character.mutex.RLock()
	timeSinceLastHide := time.Since(character.lastHideAttempt)
	character.mutex.RUnlock()

	if timeSinceLastHide < hideRateLimit {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you must wait before attempting to hide again"),
			Timestamp: time.Now(),
		}
	}

	character.SetCommandWaitTime(hideActionTime)

	character.mutex.Lock()
	character.lastHideAttempt = time.Now()
	character.mutex.Unlock()

	if character.IsHidden() {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you are already hidden"),
			Timestamp: time.Now(),
		}
	}

	outcome := ResolveStaticCheckWithXP(character, "stealth", "agility", hideBaseDifficulty)

	if !outcome.Success {
		// Set 4-second round time for failed hide attempts
		character.SetCommandWaitTime(4 * time.Second)

		message := "\n\rYou attempt to hide but fail to find adequate concealment.\n\r"

		SendRoomMessage(room,
			fmt.Sprintf("\n\r%s attempts to hide but remains visible.\n\r", character.name),
			character,
		)

		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   true, // Command executed successfully, even if hiding failed
			Message:   message,
			Timestamp: time.Now(),
		}
	}

	character.SetHidden(true)
	message := "\n\rYou slip into the shadows and hide.\n\r"

	// Detection phase: observers immediately attempt to spot the hiding character
	room.mutex.RLock()
	observers := make([]*Character, 0, len(room.characters))
	for _, observer := range room.characters {
		if observer != nil && observer != character {
			observers = append(observers, observer)
		}
	}
	room.mutex.RUnlock()

	// Check if each observer detects the hidden character
	// Use atomic detection to prevent race conditions
	var detectedBy []*Character
	var detectionMessages []string

	for _, observer := range observers {
		if observer == nil || observer.player == nil {
			continue // Skip invalid observers
		}

		// Re-verify character is still hidden before each check
		if !character.IsHidden() {
			break // Character already revealed by previous detection
		}

		// Perception & Investigation vs Stealth & Agility
		detectOutcome := ResolveOpposedCheckWithXP(
			observer, character,
			"investigation", "perception",
			"stealth", "agility",
		)

		if detectOutcome.Success {
			detectedBy = append(detectedBy, observer)
			detectionMessages = append(detectionMessages,
				fmt.Sprintf("\n\rYou notice %s trying to hide.\n\r", character.name))
		}
	}

	// If detected by anyone, reveal immediately with proper coordination
	if len(detectedBy) > 0 && character.IsHidden() {
		character.SetHidden(false)
		message = "\n\rYou attempt to hide but are spotted!\n\r"

		// Send detection messages only to those who detected
		for i, detector := range detectedBy {
			if i < len(detectionMessages) && detector.player != nil {
				SafeSendString(detector.player.commandOut, detectionMessages[i], detector.name)
			}
		}

		// Notify others that someone was discovered (without details)
		for _, observer := range observers {
			if observer == nil || observer.player == nil {
				continue
			}
			wasDetector := false
			for _, detector := range detectedBy {
				if observer == detector {
					wasDetector = true
					break
				}
			}
			if !wasDetector {
				SafeSendString(observer.player.commandOut, "\n\rSomeone notices movement in the shadows.\n\r", observer.name)
			}
		}
	}

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   message,
		Timestamp: time.Now(),
	}
}

// handleSneakCommand processes the sneak command for hidden movement
func handleSneakCommand(cmd *CommandRequest, game *Game) *CommandResponse {
	character := cmd.Character
	if character == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid character state"),
			Timestamp: time.Now(),
		}
	}

	if !character.IsHidden() {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   true,
			Message:   "\n\rYou must be hidden to sneak.\n\r",
			Timestamp: time.Now(),
		}
	}

	outcome := ResolveStaticCheckWithXP(character, "stealth", "agility", hideBaseDifficulty)

	if !outcome.Success {
		character.SetHidden(false)
		character.SetCommandWaitTime(hideActionTime)

		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   true,
			Message:   "\n\rYou stumble and reveal yourself.\n\r",
			Timestamp: time.Now(),
		}
	}

	// Store original verb and use movement handler
	originalVerb := cmd.Verb
	cmd.Verb = "sneak" // Keep as sneak so movement handler knows not to reveal
	moveResponse := handleMovementCommand(cmd, game)
	cmd.Verb = originalVerb // Restore original verb

	if !moveResponse.Success {
		// Movement failed, remain hidden
		return moveResponse
	}

	// Movement succeeded, character remains hidden
	// Perform detection checks in the new room
	newRoom := character.room
	newRoom.mutex.RLock()
	observers := make([]*Character, 0, len(newRoom.characters))
	for _, observer := range newRoom.characters {
		if observer != nil && observer != character {
			observers = append(observers, observer)
		}
	}
	newRoom.mutex.RUnlock()

	// Check if each observer detects the hidden character
	for _, observer := range observers {
		// Perception & Investigation vs Stealth & Agility
		detectOutcome := ResolveOpposedCheckWithXP(
			observer, character,
			"investigation", "perception",
			"stealth", "agility",
		)

		if detectOutcome.Success {
			character.SetHidden(false)
			SafeSendString(observer.player.commandOut, fmt.Sprintf("\n\rYou spot %s sneaking in!\n\r", character.name), observer.name)

			// Notify others
			SendRoomMessage(newRoom,
				fmt.Sprintf("\n\r%s points out %s who was sneaking in.\n\r", observer.name, character.name),
				observer,
			)
			break
		}
	}

	character.SetCommandWaitTime(sneakActionTime)

	return moveResponse
}

// handleSearchCommand processes the search command to find hidden characters
func handleSearchCommand(cmd *CommandRequest, room *Room) *CommandResponse {
	character := cmd.Character
	if character == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid character state"),
			Timestamp: time.Now(),
		}
	}

	character.SetCommandWaitTime(hideActionTime)

	// Find all hidden characters in the room
	room.mutex.RLock()
	var hiddenCharacters []*Character
	for _, other := range room.characters {
		if other != nil && other != character && other.IsHidden() {
			hiddenCharacters = append(hiddenCharacters, other)
		}
	}
	room.mutex.RUnlock()

	if len(hiddenCharacters) == 0 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   true,
			Message:   "\n\rYou search carefully but find no one hiding.\n\r",
			Timestamp: time.Now(),
		}
	}

	// Announce the search
	SafeSendString(character.player.commandOut, "\n\rYou begin searching for hidden characters...\n\r", character.name)
	SendRoomMessage(room,
		fmt.Sprintf("\n\r%s begins searching the area carefully.\n\r", character.name),
		character,
	)

	// Check against each hidden character - find only one per search
	var foundAny bool
	var foundCharacter *Character

	for _, hidden := range hiddenCharacters {
		if hidden == nil || hidden.player == nil {
			continue
		}

		// Perception & Investigation vs Stealth & Agility
		detectOutcome := ResolveOpposedCheckWithXP(
			character, hidden,
			"investigation", "perception",
			"stealth", "agility",
		)

		if detectOutcome.Success {
			foundAny = true
			foundCharacter = hidden
			break // Only find one character per search attempt
		}
	}

	// Process the discovery if any character was found
	if foundAny && foundCharacter != nil {
		foundCharacter.SetHidden(false)

		SafeSendString(character.player.commandOut, fmt.Sprintf("\n\rYou discover %s hiding!\n\r", foundCharacter.name), character.name)
		SafeSendString(foundCharacter.player.commandOut, fmt.Sprintf("\n\r%s discovers your hiding place!\n\r", character.name), foundCharacter.name)

		// Notify others
		SendRoomMessage(room,
			fmt.Sprintf("\n\r%s discovers %s hiding!\n\r", character.name, foundCharacter.name),
			character,
		)
	}

	if !foundAny {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   true,
			Message:   "\n\rYour search reveals nothing.\n\r",
			Timestamp: time.Now(),
		}
	}

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   "", // Messages already sent
		Timestamp: time.Now(),
	}
}

// handlePointCommand processes the point command to reveal a hidden character
func handlePointCommand(cmd *CommandRequest, room *Room) *CommandResponse {
	character := cmd.Character
	if character == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid character state"),
			Timestamp: time.Now(),
		}
	}

	// Check if target was specified
	if len(cmd.Args) < 2 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("point at whom?"),
			Timestamp: time.Now(),
		}
	}

	targetName := strings.ToLower(strings.Join(cmd.Args[1:], " "))

	// Find the target character
	room.mutex.RLock()
	var target *Character
	for _, other := range room.characters {
		if other != nil && other != character && MatchesTarget(other.name, targetName) {
			target = other
			break
		}
	}
	room.mutex.RUnlock()

	if target == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you don't see anyone by that name here"),
			Timestamp: time.Now(),
		}
	}

	// Check if the character can see the target
	if target.IsHidden() && !character.IsHidden() {
		// Perform detection check first
		detectOutcome := ResolveOpposedCheckWithXP(
			character, target,
			"investigation", "perception",
			"stealth", "agility",
		)

		if !detectOutcome.Success {
			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error:     fmt.Errorf("you don't see anyone by that name here"),
				Timestamp: time.Now(),
			}
		}
	}

	// If target is hidden, reveal them
	if target.IsHidden() {
		target.SetHidden(false)

		SafeSendString(character.player.commandOut, fmt.Sprintf("\n\rYou point at %s, revealing their location!\n\r", target.name), character.name)
		SafeSendString(target.player.commandOut, fmt.Sprintf("\n\r%s points at you, revealing your location!\n\r", character.name), target.name)

		SendRoomMessage(room,
			fmt.Sprintf("\n\r%s points at %s, revealing their location!\n\r", character.name, target.name),
			character,
		)
	} else {
		// Target is not hidden, just point normally
		SafeSendString(character.player.commandOut, fmt.Sprintf("\n\rYou point at %s.\n\r", target.name), character.name)
		SafeSendString(target.player.commandOut, fmt.Sprintf("\n\r%s points at you.\n\r", character.name), target.name)

		SendRoomMessage(room,
			fmt.Sprintf("\n\r%s points at %s.\n\r", character.name, target.name),
			character,
		)
	}

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   "", // Messages already sent
		Timestamp: time.Now(),
	}
}
