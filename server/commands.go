/*
Eidolon Engine

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
	"context"
	"errors"
	"fmt"
	"strings"
	"time"
)

// ProcessCommand determines command tier and routes it appropriately
func ProcessCommand(ctx context.Context, character *Character, input string) (bool, error) {
	// Parse and validate the command
	verb, tokens, userMsg, err := ValidateCommand(character, input)
	if err != nil {
		return false, err
	}

	// If there's a user message, display it and return
	if userMsg != "" {
		character.DisplayMessage(userMsg)
		return false, nil
	}

	if character == nil || character.game == nil {
		return false, errors.New("invalid character state")
	}

	// Retrieve the command info
	character.game.mutex.RLock()
	cmdInfo, exists := character.game.commands[verb]
	character.game.mutex.RUnlock()

	if !exists {
		return false, fmt.Errorf("command '%s' not understood", verb)
	}

	// Check if the character is waiting for a command timeout
	// Only check for commands that care about round time (roundTime >= 0)
	if cmdInfo.roundTime >= 0 {
		canExecute, reason := character.CanExecuteCommand()
		if !canExecute {
			return false, fmt.Errorf("%s", reason)
		}
	}

	// Special case handling for "quit" command - always process immediately
	if verb == "quit" {
		err := executeQuitCommand(character, tokens)
		return true, err
	}

	// Try to execute command hierarchically: Character -> Room -> Game

	// Step 1: Try character-level handler first (both timed and untimed)
	if cmdInfo.handler != nil {
		Logger.Debug("Executing character-tier command", "verb", verb, "character", character.name)
		err := cmdInfo.handler(character, tokens)
		// Apply round time if command generates one (roundTime > 0)
		if cmdInfo.roundTime > 0 {
			character.SetCommandWaitTime(time.Duration(cmdInfo.roundTime) * time.Second)
		}
		return false, err
	}

	// Step 2: Character doesn't handle this command, escalate to room
	Logger.Debug("Escalating command to room", "verb", verb, "character", character.name)

	// Room-tier request enables location-based command handling
	cmdReq := &CommandRequest{
		ID:        GenerateUUIDv7(),
		Character: character,
		Verb:      verb,
		Args:      tokens,
		Tier:      RoomTier,
		State:     CommandPending,
		Timestamp: time.Now(),
		Response:  make(chan *CommandResponse, 1),
	}

	// Ensure room is running
	if !character.room.running {
		character.room.Start(character.game)
	}

	// Try to send command to the room with a brief retry
	retryTimer := time.NewTimer(50 * time.Millisecond)
	defer retryTimer.Stop()

	Logger.Debug("Sending command to room", "roomID", character.room.roomID, "verb", verb, "character", character.name)

	select {
	case character.room.commandIn <- cmdReq:
		Logger.Debug("Command sent successfully to room", "roomID", character.room.roomID, "verb", verb)
		// Command sent successfully to room
	case <-retryTimer.C:
		// Brief retry after 50ms
		select {
		case character.room.commandIn <- cmdReq:
			Logger.Debug("Command sent successfully to room on retry", "roomID", character.room.roomID, "verb", verb)
			// Command sent successfully on retry
		default:
			Logger.Warn("Room command buffer full after retry",
				"roomID", character.room.roomID,
				"characterName", character.name,
				"verb", verb)
			character.DisplayMessage("The room is processing too many commands. Please wait a moment and try again.")
			return false, nil
		}
	}

	// Wait for response or timeout
	Logger.Debug("Waiting for command response", "roomID", character.room.roomID, "verb", verb)

	select {
	case resp := <-cmdReq.Response:
		Logger.Debug("Got command response", "roomID", character.room.roomID, "verb", verb, "success", resp.Success)
		if resp.Error != nil {
			// If room doesn't handle it, escalate to game
			if strings.Contains(resp.Error.Error(), "unknown room command") {
				Logger.Debug("Escalating command to game", "verb", verb, "character", character.name)
				return escalateToGame(ctx, character, verb, tokens)
			}
			return false, resp.Error
		}
		if resp.Message != "" {
			character.DisplayMessage(resp.Message)
		}
		// Apply round time if command generates one (roundTime > 0)
		if cmdInfo.roundTime > 0 {
			character.SetCommandWaitTime(time.Duration(cmdInfo.roundTime) * time.Second)
		}
		return false, nil
	case <-time.After(5 * time.Second):
		Logger.Error("Command timed out waiting for response", "roomID", character.room.roomID, "verb", verb, "character", character.name)
		character.DisplayMessage("Command timed out. Please try again.")
		return false, nil
	case <-ctx.Done():
		return false, ctx.Err()
	}
}

// escalateToGame handles commands that neither character nor room can process
func escalateToGame(ctx context.Context, character *Character, verb string, tokens []string) (bool, error) {
	// Get command info for round time application
	character.game.mutex.RLock()
	cmdInfo := character.game.commands[verb]
	character.game.mutex.RUnlock()
	// Game-tier request handles global commands
	cmdReq := &CommandRequest{
		ID:        GenerateUUIDv7(),
		Character: character,
		Verb:      verb,
		Args:      tokens,
		Tier:      GameTier,
		State:     CommandPending,
		Timestamp: time.Now(),
		Response:  make(chan *CommandResponse, 1),
	}

	// Game submission routes to global handler
	select {
	case character.gameCommandOut <- cmdReq:
		// Command sent successfully to game
	default:
		Logger.Warn("Game command buffer full", "characterName", character.name, "verb", verb)
		character.DisplayMessage("The game is processing too many commands. Please wait a moment and try again.")
		return false, nil
	}

	// Wait for response or timeout
	select {
	case resp := <-cmdReq.Response:
		if resp.Error != nil {
			return false, resp.Error
		}
		if resp.Message != "" {
			character.DisplayMessage(resp.Message)
		}
		// Apply round time if command generates one (roundTime > 0)
		if cmdInfo.roundTime > 0 {
			character.SetCommandWaitTime(time.Duration(cmdInfo.roundTime) * time.Second)
		}
		return false, nil
	case <-time.After(5 * time.Second):
		character.DisplayMessage("Command timed out. Please try again.")
		return false, nil
	case <-ctx.Done():
		return false, ctx.Err()
	}
}
