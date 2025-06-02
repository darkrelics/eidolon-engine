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

	// Defer ensures cleanup even if panic occurs
	defer c.cleanupAndSignalDone(done)

	Logger.Debug("Starting character console", "characterName", c.name)

	// Room 0 serves as fallback void location
	c.mutex.Lock()
	if c.room == nil {
		Logger.Warn("Character room is nil, defaulting to room ID 0", "characterName", c.name)
		if defaultRoom, ok := c.game.rooms[0]; ok {
			c.room = defaultRoom
		} else {
			c.mutex.Unlock()
			Logger.Error("No default room available", "characterName", c.name)
			done <- true
			return
		}
	}
	c.mutex.Unlock()

	// Game registration enables global character tracking
	c.game.mutex.Lock()
	c.game.characters[c.id] = c
	c.game.mutex.Unlock()

	// Room must be running to process character events
	c.room.mutex.RLock()
	roomRunning := c.room.running
	c.room.mutex.RUnlock()

	if !roomRunning {
		Logger.Info("Starting room for character entry", "roomID", c.room.roomID, "characterName", c.name)
		c.room.Start(c.game)
		// Ready state indicates room can accept characters
		c.room.WaitReady()
	}

	// Room addition enables location-based interactions
	c.room.mutex.Lock()
	if c.room.characters == nil {
		c.room.characters = make(map[uuid.UUID]*Character)
	}
	c.room.characters[c.id] = c
	// Activity tracking prevents idle room cleanup
	c.room.lastActive = time.Now()
	c.room.mutex.Unlock()

	// Call HandleCharacterEntry to reset idle counter and activate scripts
	// Timing prevents race conditions with room scripts
	c.room.HandleCharacterEntry(c)

	// Script events provide dynamic room behaviors
	if c.room.scriptID != "" && c.room.scriptActive && ScriptMgr != nil {
		if err := ScriptMgr.ExecuteRoomEvent(c.room, "onCharacterEnter", c); err != nil {
			Logger.Error("Error executing onCharacterEnter", "roomID", c.room.roomID, "characterName", c.name, "error", err)
		}
	}

	// Arrival notification informs other players
	SendRoomMessage(c.room, fmt.Sprintf("\n\r%s has arrived.\n\r", c.name), c)

	// Initial view orients player to their location
	c.safeExecuteLookCommand()

	const idleTimeout = 30 * time.Second
	timer := time.NewTimer(idleTimeout)
	defer timer.Stop()

	// Processing signal prevents command overlap
	commandProcessing := make(chan struct{}, 1)

	for {
		timer.Reset(idleTimeout)

		select {
		case inputLine, ok := <-c.playerCommandIn:
			if !ok {
				Logger.Info("Player input channel closed", "characterName", c.name)
				return
			}

			// Non-blocking send prevents deadlock on full channel
			select {
			case commandProcessing <- struct{}{}:
			default:
				// Existing signal means command already processing
			}

			// Command processing may modify game state
			isQuit, err := ProcessCommand(c.game.ctx, c, strings.TrimSpace(inputLine))
			if err != nil {
				// Send error message to player - these are typically user-friendly messages
				c.DisplayMessage(err.Error())
				// Log at debug level since command errors (like typos) are normal gameplay
				Logger.Debug("Command not recognized", "characterName", c.name, "command", inputLine, "message", err.Error())
			} else {
				// Success path continues normal game flow
				Logger.Debug("Command processed", "characterName", c.name, "command", inputLine)
			}

			// Quit command triggers graceful session termination
			if isQuit {
				Logger.Info("Quit command processed, exiting character loop", "characterName", c.name)
				return
			}

			// Signal clearing allows next command to process
			select {
			case <-commandProcessing:
			default:
				// Empty channel expected during normal operation
			}

			// Prompt is now automatically restored by Player's SendMessageWithBuffer

		case _, ok := <-c.end:
			if !ok {
				Logger.Info("Character end channel closed", "characterName", c.name)
			} else {
				Logger.Info("Character end signaled", "characterName", c.name)
			}
			return

		case <-timer.C:
			c.mutex.RLock()
			player := c.player
			c.mutex.RUnlock()
			if player == nil {
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

	// Specific command help provides targeted assistance
	if specific != "" {
		c.game.mutex.RLock()
		cmdInfo, exists := c.game.commands[specific]
		c.game.mutex.RUnlock()

		if !exists {
			c.DisplayMessage(fmt.Sprintf("\n\rNo help available for '%s'. Command not found.\n\r", specific))
			return nil
		}

		helpMsg.WriteString(fmt.Sprintf("\n\rCommand: %s\n\r", specific))
		helpMsg.WriteString(fmt.Sprintf("Description: %s\n\r", cmdInfo.description))
		helpMsg.WriteString(fmt.Sprintf("Usage: %s\n\r", cmdInfo.usage))

		c.DisplayMessage(helpMsg.String())
		return nil
	}

	// Otherwise, show all available commands
	c.game.mutex.RLock()

	var commandNames []string
	for name := range c.game.commands {
		commandNames = append(commandNames, name)
	}

	c.game.mutex.RUnlock()

	// Alphabetical order improves command discovery
	sort.Strings(commandNames)

	helpMsg.WriteString("\n\rAvailable Commands:\n\r\n\r")

	c.game.mutex.RLock()

	for _, cmd := range commandNames {
		info := c.game.commands[cmd]
		helpMsg.WriteString(fmt.Sprintf("  %-12s - %s\n\r", cmd, info.description))
	}

	c.game.mutex.RUnlock()

	helpMsg.WriteString("\n\rType 'help <command>' for more information on a specific command.\n\r")

	c.DisplayMessage(helpMsg.String())
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

// DisplayMessage displays a message to the character with proper formatting and buffer preservation
func (c *Character) DisplayMessage(message string) {
	if c == nil {
		return
	}
	
	c.mutex.RLock()
	player := c.player
	c.mutex.RUnlock()
	
	if player == nil {
		return
	}

	// Get current buffer content to preserve what the user was typing
	bufferContent := ""
	if player.inputBuffer != nil {
		bufferContent = player.inputBuffer.String()
	}

	// Build the complete message with formatting
	var completeMessage string
	if len(bufferContent) > 0 && player.echo {
		// Clear current line, send message, prompt, and restore buffer
		completeMessage = "\r\033[K\n\r" + message + "\n\r" + c.prompt + bufferContent
	} else {
		// Just send message with prompt
		completeMessage = "\n\r" + message + "\n\r" + c.prompt
	}

	player.commandOut <- completeMessage
}

// safeExecuteLookCommand safely executes the initial look command with panic recovery
func (c *Character) safeExecuteLookCommand() {
	defer func() {
		if r := recover(); r != nil {
			Logger.Error("Panic during initial look command", "characterName", c.name, "roomID", c.room.roomID, "panic", r)
		}
	}()
	if err := executeLookCommand(c, []string{"look"}); err != nil {
		Logger.Warn("Failed to show initial room", "characterName", c.name, "error", err)
	}
}
