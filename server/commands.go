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
	// Limit input to 240 characters
	if len(input) > 240 {
		return false, errors.New("\n\rCommand too long. Maximum 240 characters allowed.\n\r")
	}

	// Parse and validate the command
	verb, tokens, err := ValidateCommand(character, input)
	if err != nil {
		return false, err
	}

	if character == nil || character.game == nil {
		return false, errors.New("\n\rInvalid character state.\n\r")
	}

	// Check if the character is waiting for a command timeout
	canExecute, reason := character.CanExecuteCommand()
	if !canExecute {
		// Allow certain commands even when waiting
		if verb != "look" && verb != "help" && verb != "who" && verb != "quit" {
			return false, fmt.Errorf("\n\r%s\n\r", reason)
		}
		// These commands are allowed during wait time
	}

	// Retrieve the command info
	character.game.mutex.RLock()
	cmdInfo, exists := character.game.commands[verb]
	character.game.mutex.RUnlock()

	if !exists {
		return false, fmt.Errorf("command '%s' not understood", verb)
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
		if cmdInfo.timed {
			// For timed character commands, still respect timing but execute directly
			err := cmdInfo.handler(character, tokens)
			return false, err
		} else {
			// Execute untimed commands immediately
			return false, cmdInfo.handler(character, tokens)
		}
	}

	// Step 2: Character doesn't handle this command, escalate to room
	Logger.Debug("Escalating command to room", "verb", verb, "character", character.name)

	// Create command request for room processing
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

	select {
	case character.room.commandIn <- cmdReq:
		// Command sent successfully to room
	case <-retryTimer.C:
		// Brief retry after 50ms
		select {
		case character.room.commandIn <- cmdReq:
			// Command sent successfully on retry
		default:
			Logger.Warn("Room command buffer full after retry",
				"roomID", character.room.roomID,
				"characterName", character.name,
				"verb", verb)
			return false, fmt.Errorf("\n\rThe room is processing too many commands. Please wait a moment and try again.\n\r")
		}
	}

	// Wait for response or timeout
	select {
	case resp := <-cmdReq.Response:
		if resp.Error != nil {
			// If room doesn't handle it, escalate to game
			if strings.Contains(resp.Error.Error(), "unknown room command") {
				Logger.Debug("Escalating command to game", "verb", verb, "character", character.name)
				return escalateToGame(ctx, character, verb, tokens)
			}
			return false, resp.Error
		}
		if resp.Message != "" {
			character.player.commandOut <- resp.Message
		}
		return false, nil
	case <-time.After(5 * time.Second):
		return false, fmt.Errorf("\n\rcommand timed out\n\r")
	case <-ctx.Done():
		return false, ctx.Err()
	}
}

// escalateToGame handles commands that neither character nor room can process
func escalateToGame(ctx context.Context, character *Character, verb string, tokens []string) (bool, error) {
	// Create command request for game processing
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

	// Send command to the game
	select {
	case character.gameCommandOut <- cmdReq:
		// Command sent successfully to game
	default:
		Logger.Warn("Game command buffer full",
			"characterName", character.name,
			"verb", verb)
		return false, fmt.Errorf("\n\rThe game is processing too many commands. Please wait a moment and try again.\n\r")
	}

	// Wait for response or timeout
	select {
	case resp := <-cmdReq.Response:
		if resp.Error != nil {
			return false, resp.Error
		}
		if resp.Message != "" {
			character.player.commandOut <- resp.Message
		}
		return false, nil
	case <-time.After(5 * time.Second):
		return false, fmt.Errorf("\n\rcommand timed out\n\r")
	case <-ctx.Done():
		return false, ctx.Err()
	}
}
