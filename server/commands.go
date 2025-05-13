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
	"errors"
	"fmt"
	"strings"
	"time"
)

// CommandInfo stores metadata about each command
type CommandInfo struct {
	timed       bool                                      // Whether the command is timed (true) or untimed (false)
	handler     func(c *Character, tokens []string) error // Function to execute the command
	description string                                    // Description for help text
	usage       string                                    // Usage information
}

// Initialize commands
func (g *Game) initCommands() {

	// Register basic commands
	g.commands["quit"] = CommandInfo{
		timed:       false,
		handler:     executeQuitCommand,
		description: "Exit the game",
		usage:       "quit",
	}

	g.commands["look"] = CommandInfo{
		timed:       false,
		handler:     executeLookCommand,
		description: "Look around or examine something",
		usage:       "look [target]",
	}

	g.commands["help"] = CommandInfo{
		timed:       false,
		handler:     executeHelpCommand,
		description: "Display available commands",
		usage:       "help",
	}

	g.commands["who"] = CommandInfo{
		timed:       false,
		handler:     executeWhoCommand,
		description: "Display currently online characters",
		usage:       "who",
	}

	g.commands["info"] = CommandInfo{
		timed:       false,
		handler:     executeInfoCommand,
		description: "Display information about your character",
		usage:       "info",
	}

	g.commands["skill"] = CommandInfo{
		timed:       false,
		handler:     executeSkillCommand,
		description: "Display your character's abilities",
		usage:       "skill",
	}

	// Movement commands
	g.commands["go"] = CommandInfo{
		timed:       true,
		handler:     executeGoCommand,
		description: "Move in a direction or through an exit",
		usage:       "go <direction|exit>",
	}

	g.commands["move"] = CommandInfo{
		timed:       true,
		handler:     executeGoCommand, // Alias to go
		description: "Move in a direction or through an exit",
		usage:       "move <direction|exit>",
	}

	// Speech commands
	g.commands["say"] = CommandInfo{
		timed:       true,
		handler:     nil, // Handled by room level
		description: "Say something to everyone in the room",
		usage:       "say <message>",
	}

	g.commands["emote"] = CommandInfo{
		timed:       true,
		handler:     nil, // Handled by room level
		description: "Express an action or emotion in the room",
		usage:       "emote <action>",
	}

	// Item commands
	g.commands["get"] = CommandInfo{
		timed:       true,
		handler:     nil, // Handled by room level
		description: "Pick up an item",
		usage:       "get <item>",
	}

	g.commands["take"] = CommandInfo{
		timed:       true,
		handler:     nil, // Handled by room level
		description: "Pick up an item",
		usage:       "take <item>",
	}

	g.commands["drop"] = CommandInfo{
		timed:       true,
		handler:     nil, // Handled by room level
		description: "Drop an item from your inventory",
		usage:       "drop <item>",
	}
}

// ValidateCommand checks if a command is valid and returns its verb and tokens
func ValidateCommand(character *Character, input string) (string, []string, error) {
	if len(input) == 0 {
		return "", nil, errors.New("\n\rNo command entered.\n\r")
	}

	tokens := tokenizeInput(input)

	if len(tokens) == 0 {
		return "", nil, errors.New("\n\rNo command entered.\n\r")
	}

	verb := strings.ToLower(tokens[0])
	if character == nil || character.game == nil {
		return "", nil, errors.New("\n\rInvalid character state.\n\r")
	}

	character.game.mutex.RLock()
	_, exists := character.game.commands[verb]
	character.game.mutex.RUnlock()

	if !exists {
		return "", nil, fmt.Errorf("\n\rCommand '%s' not understood.\n\r", verb)
	}

	return verb, tokens, nil
}

// tokenizeInput breaks the input into individual tokens
func tokenizeInput(input string) []string {
	var tokens []string
	var current strings.Builder
	inQuotes := false

	for i := 0; i < len(input); i++ {
		switch input[i] {
		case '"':
			inQuotes = !inQuotes
		case ' ', '\t':
			if !inQuotes && current.Len() > 0 {
				tokens = append(tokens, current.String())
				current.Reset()
			} else if inQuotes {
				current.WriteByte(input[i])
			}
		default:
			current.WriteByte(input[i])
		}
	}

	if current.Len() > 0 {
		tokens = append(tokens, current.String())
	}

	return tokens
}

// ProcessCommand determines command tier and routes it appropriately
func ProcessCommand(character *Character, input string) (bool, error) {
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

	// Process based on command tier
	if !cmdInfo.timed {
		// Execute untimed commands immediately at character level
		Logger.Debug("Executing character-tier command", "verb", verb, "character", character.name)
		return false, cmdInfo.handler(character, tokens)
	} else {
		// For timed commands, determine the tier and route accordingly
		var tier CommandTier

		// Determine tier based on command properties
		switch verb {
		case "say", "emote", "whisper", "get", "take", "drop":
			// Commands that only affect the local room
			tier = RoomTier
		case "shout", "weather", "time", "global":
			// Commands that affect multiple rooms or the entire game
			tier = GameTier
		default:
			// Default to room tier for most commands
			tier = RoomTier
		}

		// Create command request
		cmdReq := &CommandRequest{
			ID:        GenerateUUIDv7(),
			Character: character,
			Verb:      verb,
			Args:      tokens,
			Tier:      tier,
			State:     CommandPending,
			Timestamp: time.Now(),
			Response:  make(chan *CommandResponse, 1),
		}

		// Route command based on tier
		switch tier {
		case RoomTier:
			// Ensure room is running
			if !character.room.running {
				character.room.Start(character.game)
			}

			// Send command to the room
			Logger.Debug("Routing command to room", "verb", verb, "character", character.name, "roomID", character.room.roomID)
			select {
			case character.room.commandIn <- cmdReq:
				// Command sent successfully to room
			default:
				return false, fmt.Errorf("\n\rroom command buffer is full, try again later\n\r")
			}

		case GameTier:
			// Send command to the game
			Logger.Debug("Routing command to game", "verb", verb, "character", character.name)
			select {
			case character.gameCommandOut <- cmdReq:
				// Command sent successfully to game
			default:
				return false, fmt.Errorf("\n\rgame command buffer is full, try again later\n\r")
			}

		default:
			return false, fmt.Errorf("\n\rinvalid command tier\n\r")
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
		}
	}
}
