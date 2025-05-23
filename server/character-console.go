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
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/gofrs/uuid/v5"
)

// RunConsole is the main loop that handles character console input/output
func (c *Character) RunConsole(done chan bool) {
	if c == nil || c.player == nil {
		Logger.Error("Invalid character or player in RunConsole method")
		done <- true
		return
	}

	// Ensure character is properly stopped when the function exits
	defer c.Stop(done)

	Logger.Debug("Starting character console", "characterName", c.name)

	// If the room is nil, move the character to room 0
	if c.room == nil {
		Logger.Warn("Character room is nil, defaulting to room ID 0", "characterName", c.name)
		c.room = c.game.rooms[0]
	}

	// Add character to game's active characters
	c.game.mutex.Lock()
	c.game.characters[c.id] = c
	c.game.mutex.Unlock()

	// Add character to the room
	c.room.mutex.Lock()
	if c.room.characters == nil {
		c.room.characters = make(map[uuid.UUID]*Character)
	}
	c.room.characters[c.id] = c
	// Update room activity timestamp
	c.room.lastActive = time.Now()
	c.room.mutex.Unlock()

	// Call HandleCharacterEntry to reset idle counter and activate scripts
	c.room.HandleCharacterEntry()

	// Notify room of arrival (without holding locks)
	SendRoomMessageExcept(c.room, fmt.Sprintf("\n\r%s has arrived.\n\r", c.name), c)

	// Show initial room description
	if err := executeLookCommand(c, []string{"look"}); err != nil {
		Logger.Warn("Failed to show initial room", "characterName", c.name, "error", err)
	}

	const idleTimeout = 30 * time.Second
	timer := time.NewTimer(idleTimeout)
	defer timer.Stop()

	// Channel to track when a command is processing
	commandProcessing := make(chan struct{}, 1)

	for {
		timer.Reset(idleTimeout)

		select {
		case inputLine, ok := <-c.playerCommandIn:
			if !ok {
				Logger.Info("Player input channel closed", "characterName", c.name)
				return
			}

			// Signal that a command is processing
			select {
			case commandProcessing <- struct{}{}:
			default:
				// Channel already has a value, which is fine
			}

			// Process the command
			isQuit, err := ProcessCommand(c.game.ctx, c, strings.TrimSpace(inputLine))
			if err != nil {
				// Send error message to player
				c.player.commandOut <- err.Error() + "\n\r"
			} else {
				// Command processed successfully
				Logger.Debug("Command processed", "characterName", c.name, "command", inputLine)
			}

			// If the quit command was processed, exit the loop
			if isQuit {
				Logger.Info("Quit command processed, exiting character loop", "characterName", c.name)
				return
			}

			// Clear the processing signal
			select {
			case <-commandProcessing:
			default:
				// Channel already empty, which is fine
			}

			// Always send prompt after processing a command
			c.player.commandOut <- c.prompt

		case _, ok := <-c.end:
			if !ok {
				Logger.Info("Character end channel closed", "characterName", c.name)
			} else {
				Logger.Info("Character end signaled", "characterName", c.name)
			}
			return

		case <-timer.C:
			if c.player == nil {
				Logger.Warn("Player connection lost", "characterName", c.name)
				return
			}
		}
	}
}

// DisplayHelp shows help information to the character
func (c *Character) DisplayHelp(specific string) error {
	if c == nil || c.player == nil || c.game == nil {
		return fmt.Errorf("invalid character state")
	}

	var helpMsg strings.Builder

	// If a specific command was requested
	if specific != "" {
		c.game.mutex.RLock()
		cmdInfo, exists := c.game.commands[specific]
		c.game.mutex.RUnlock()

		if !exists {
			c.player.commandOut <- fmt.Sprintf("\n\rNo help available for '%s'. Command not found.\n\r", specific)
			return nil
		}

		helpMsg.WriteString(fmt.Sprintf("\n\rCommand: %s\n\r", specific))
		helpMsg.WriteString(fmt.Sprintf("Description: %s\n\r", cmdInfo.description))
		helpMsg.WriteString(fmt.Sprintf("Usage: %s\n\r", cmdInfo.usage))

		c.player.commandOut <- helpMsg.String()
		return nil
	}

	// Otherwise, show all available commands
	c.game.mutex.RLock()

	var commandNames []string
	for name := range c.game.commands {
		commandNames = append(commandNames, name)
	}

	c.game.mutex.RUnlock()

	// Sort commands alphabetically
	sort.Strings(commandNames)

	helpMsg.WriteString("\n\rAvailable Commands:\n\r\n\r")

	c.game.mutex.RLock()

	for _, cmd := range commandNames {
		info := c.game.commands[cmd]
		helpMsg.WriteString(fmt.Sprintf("  %-12s - %s\n\r", cmd, info.description))
	}

	c.game.mutex.RUnlock()

	helpMsg.WriteString("\n\rType 'help <command>' for more information on a specific command.\n\r")

	c.player.commandOut <- helpMsg.String()
	return nil
}

// SendPrompt sends a prompt to the player
func (c *Character) SendPrompt() {
	if c == nil || c.player == nil {
		return
	}

	c.player.commandOut <- c.prompt
}

// SetPrompt changes the character's prompt
func (c *Character) SetPrompt(newPrompt string) {
	if c == nil {
		return
	}

	c.mutex.Lock()
	defer c.mutex.Unlock()

	if newPrompt == "" {
		c.prompt = "> "
	} else {
		c.prompt = newPrompt
	}
}

// DisplayMessage displays a message to the character
func (c *Character) DisplayMessage(message string) {
	if c == nil || c.player == nil {
		return
	}

	c.player.commandOut <- message
}
