/*
Eidolon Engine - Movement Commands

Copyright 2024-2025 Jason Robinson

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package main

import (
	"fmt"
	"strings"
	"time"
)

// handleMovementCommand processes movement commands (go/move)
func handleMovementCommand(cmd *CommandRequest, game *Game) *CommandResponse {
	character := cmd.Character

	if character == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid character"),
			Timestamp: time.Now(),
		}
	}

	// If this is not a sneak command and character is hidden, reveal them
	if cmd.Verb != "sneak" && character.IsHidden() {
		character.SetHidden(false)
		character.DisplayMessage("You reveal yourself as you move.")

		if character.room != nil {
			SendRoomMessage(character.room,
				fmt.Sprintf("\n\r%s suddenly appears!\n\r", character.name),
				character,
			)
		}
	}

	room := character.room
	if room == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid room state"),
			Timestamp: time.Now(),
		}
	}

	// Check if character state allows movement
	if character.charState != "standing" {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you must be standing to move. You are currently %s", character.charState),
			Timestamp: time.Now(),
		}
	}

	// Check if a direction was provided
	if len(cmd.Args) < 2 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("which direction do you want to go?"),
			Timestamp: time.Now(),
		}
	}

	// Get the direction from the command
	direction := strings.ToLower(strings.Join(cmd.Args[1:], " "))
	Logger.Debug("Player attempting to move", "characterName", character.name, "direction", direction)

	// Parse ordinal from direction
	position, exitName, hasOrdinal := ParseTargetWithOrdinal(direction)

	// Look for matching exits
	room.mutex.RLock()
	var matchingExits []*Exit

	for _, exit := range room.exits {
		if exit != nil && MatchesTarget(exit.direction, exitName) {
			matchingExits = append(matchingExits, exit)
		}
	}
	room.mutex.RUnlock()

	// Check if we found any matches
	if len(matchingExits) == 0 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you cannot go that way"),
			Timestamp: time.Now(),
		}
	}

	// If multiple matches and no ordinal specified, inform the player
	if len(matchingExits) > 1 && !hasOrdinal {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error: fmt.Errorf("which way? There are %d exits %s. Try 'go first %s' or 'go second %s'",
				len(matchingExits), exitName, exitName, exitName),
			Timestamp: time.Now(),
		}
	}

	// Check if position is valid
	if position > len(matchingExits) {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("there aren't that many exits %s", exitName),
			Timestamp: time.Now(),
		}
	}

	// Get the specific exit (position is 1-based)
	targetExit := matchingExits[position-1]

	// Check if target room exists and load it if necessary
	targetRoom := targetExit.targetRoom

	// Check if we have a room reference but it's not running (stale reference)
	if targetRoom != nil && !targetRoom.running {
		Logger.Debug("Exit has stale room reference, clearing it",
			"exitID", targetExit.exitID,
			"targetRoomID", targetExit.targetRoomID)
		targetRoom = nil
		targetExit.targetRoom = nil
	}

	if targetRoom == nil {
		// Try to load the room using the target room ID
		loadedRoom, err := game.LoadRoom(targetExit.targetRoomID)
		if err != nil {
			Logger.Warn("Could not load target room for movement",
				"targetRoomID", targetExit.targetRoomID,
				"direction", direction,
				"characterName", character.name,
				"error", err)
			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error:     fmt.Errorf("the way is barred"),
				Timestamp: time.Now(),
			}
		}
		targetRoom = loadedRoom
		// Update the exit's room reference for future use
		targetExit.targetRoom = targetRoom
	}

	// Ensure target room is running
	if !targetRoom.running {
		targetRoom.Start(game)
		targetRoom.WaitReady()
	}

	// Get references before the move
	oldRoom := room
	newRoom := targetRoom

	Logger.Info("Character moving between rooms",
		"characterName", character.name,
		"fromRoom", oldRoom.roomID,
		"toRoom", newRoom.roomID,
		"direction", direction)

	// Prepare departure message - only if visible
	var departureMsg string
	if !character.IsHidden() {
		departureMsg = fmt.Sprintf("%s leaves %s.", character.name, direction)
	}

	// Perform room transitions atomically to prevent deadlocks
	// Lock in consistent order: oldRoom, newRoom, then character
	Logger.Debug("Acquiring room locks for movement", "oldRoomID", oldRoom.roomID, "newRoomID", newRoom.roomID)
	if oldRoom.roomID < newRoom.roomID {
		oldRoom.mutex.Lock()
		newRoom.mutex.Lock()
	} else if oldRoom.roomID > newRoom.roomID {
		newRoom.mutex.Lock()
		oldRoom.mutex.Lock()
	} else {
		// Same room (shouldn't happen, but handle gracefully)
		oldRoom.mutex.Lock()
	}
	Logger.Debug("Room locks acquired", "oldRoomID", oldRoom.roomID, "newRoomID", newRoom.roomID)

	// Remove from old room
	delete(oldRoom.characters, character.id)
	oldRoom.lastActive = time.Now()

	// Add to new room
	newRoom.characters[character.id] = character
	newRoom.lastActive = time.Now()
	newRoom.idleCounter = 0

	// If room has a script ID, activate scripts
	if newRoom.persistent && newRoom.scriptID != "" && !newRoom.scriptActive {
		newRoom.scriptActive = true
		Logger.Info("Activating scripts for persistent room with character entry", "roomID", newRoom.roomID)
	}

	// Store script execution info before unlocking
	oldRoomHasScript := oldRoom.scriptID != "" && oldRoom.scriptActive && ScriptMgr != nil
	newRoomHasScript := newRoom.scriptID != "" && newRoom.scriptActive && ScriptMgr != nil

	// Unlock rooms before executing scripts to avoid deadlock
	if oldRoom.roomID != newRoom.roomID {
		oldRoom.mutex.Unlock()
		newRoom.mutex.Unlock()
	} else {
		oldRoom.mutex.Unlock()
	}
	Logger.Debug("Room locks released", "oldRoomID", oldRoom.roomID, "newRoomID", newRoom.roomID)

	// Now execute scripts without holding locks
	// Trigger onCharacterLeave event for old room scripts
	if oldRoomHasScript {
		Logger.Debug("Executing onCharacterLeave event", "roomID", oldRoom.roomID, "character", character.name)
		if err := ScriptMgr.ExecuteRoomEvent(oldRoom, "onCharacterLeave", character); err != nil {
			Logger.Error("Error executing onCharacterLeave", "roomID", oldRoom.roomID, "error", err)
		}
		Logger.Debug("Completed onCharacterLeave event", "roomID", oldRoom.roomID, "character", character.name)
	}

	// Send departure message to remaining characters (only if visible)
	if departureMsg != "" {
		SendRoomMessage(oldRoom, departureMsg, character)
	}

	// Update character's room reference and clear facing
	character.mutex.Lock()
	character.room = newRoom
	character.facing = nil // Clear facing when changing rooms
	character.mutex.Unlock()

	// Clear facing for any characters in the old room that were facing the departing character
	// Also clean up combat ranges involving the departing character
	oldRoom.mutex.Lock()
	for _, char := range oldRoom.characters {
		if char != nil && char != character {
			char.mutex.Lock()
			if char.facing == character {
				char.facing = nil
			}
			char.mutex.Unlock()
		}
	}

	// Remove combat ranges involving the departing character
	oldRoom.removeCharacterFromCombat(character)
	oldRoom.mutex.Unlock()

	// Send arrival message using the exit's arrival text (only if visible)
	if !character.IsHidden() {
		arrivalMsg := fmt.Sprintf("%s %s.", character.name, targetExit.arrivalText)
		SendRoomMessage(newRoom, arrivalMsg, character)
	}

	// Get the room description for the character
	description := newRoom.GetDescription(character)

	// Trigger onCharacterEnter event for new room scripts AFTER description is prepared
	// We'll send it asynchronously after a brief delay to ensure the room description reaches the player first
	if newRoomHasScript {
		go func() {
			// Brief delay to ensure room description is processed first
			time.Sleep(100 * time.Millisecond)
			Logger.Debug("Executing onCharacterEnter event", "roomID", newRoom.roomID, "character", character.name)
			if err := ScriptMgr.ExecuteRoomEvent(newRoom, "onCharacterEnter", character); err != nil {
				Logger.Error("Error executing onCharacterEnter during movement", "roomID", newRoom.roomID, "error", err)
			}
			Logger.Debug("Completed onCharacterEnter event", "roomID", newRoom.roomID, "character", character.name)
		}()
	}

	Logger.Debug("Movement command completed successfully",
		"characterName", character.name,
		"fromRoom", oldRoom.roomID,
		"toRoom", newRoom.roomID)

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   description,
		Timestamp: time.Now(),
	}
}
