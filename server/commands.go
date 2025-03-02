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
	"sort"
	"strings"
	"time"
)

// Command messages
const (
	msgNoExits     = "There are no visible exits.\n\r"
	msgAlone       = "You are alone.\n\r"
	msgAlsoHere    = "Also here: "
	msgItems       = "Items in the room:\n\r"
	msgNoDirection = "\n\rWhich direction do you want to go?\n\r"
	msgCantEscape  = "\n\rYou can't escape!\n\r"
	msgNoRoom      = "\n\rYou are not in any room to move from.\n\r"
	msgInvalidDir  = "\n\rYou cannot go that way.\n\r"
	msgPathNowhere = "\n\rThe path leads nowhere.\n\r"
	whoHeader      = "\n\rOnline Characters\n\r"
	whoEmpty       = "\n\rNo other players online.\n\r"
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
		usage:       "help [command]",
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

// ProcessCommand determines if a command is timed or untimed and handles it accordingly
func ProcessCommand(character *Character, input string) (bool, error) {
	// Parse and validate the command
	verb, tokens, err := ValidateCommand(character, input)
	if err != nil {
		return false, err
	}

	if character == nil || character.game == nil {
		return false, errors.New("\n\rInvalid character state.\n\r")
	}

	// Retrieve the command info
	character.game.mutex.RLock()
	cmdInfo, exists := character.game.commands[verb]
	character.game.mutex.RUnlock()

	if !exists {
		return false, fmt.Errorf("command '%s' not understood", verb)
	}

	// Process based on command type
	if !cmdInfo.timed {
		// Execute untimed commands immediately
		Logger.Debug("Executing untimed command", "verb", verb, "character", character.name)
		start := time.Now()

		err := cmdInfo.handler(character, tokens)

		elapsed := time.Since(start)
		if elapsed > 100*time.Millisecond {
			Logger.Warn("Slow command execution", "verb", verb, "duration", elapsed, "character", character.name)
		}

		return false, err
	} else {
		// For timed commands, send to the game loop for processing
		Logger.Debug("Queuing timed command for processing", "verb", verb, "character", character.name)

		// TODO: Implement timed commands via a command queue in the Game struct
		Logger.Error("Timed commands not implemented", "character", character.name, "command", verb)
		return false, errors.New("\n\rTimed commands are not yet implemented.\n\r")
	}
}

// executeQuitCommand handles the quit command
func executeQuitCommand(character *Character, tokens []string) error {
	if character == nil {
		Logger.Error("Attempted to quit with nil character")
		return errors.New("invalid character state")
	}

	Logger.Info("Player initiating quit", "characterName", character.name)

	// Notify the player
	if character.player != nil {
		select {
		case character.player.toPlayer <- "\n\rSaving character state...\n\r":
		default:
			Logger.Warn("Failed to notify player: ToPlayer channel is full or closed", "characterName", character.name)
		}
	}

	// Signal the end of character's lifecycle
	character.Stop(character.end)
	return nil
}

// executeHelpCommand handles the help command
func executeHelpCommand(character *Character, tokens []string) error {
	if character == nil || character.player == nil || character.game == nil {
		return errors.New("invalid character state")
	}

	Logger.Debug("Player requesting help", "characterName", character.name)

	// Check if help was requested for a specific command
	if len(tokens) > 1 {
		return showCommandHelp(character, tokens[1])
	}

	// Collect all commands
	character.game.mutex.RLock()

	var commandNames []string
	for name := range character.game.commands {
		commandNames = append(commandNames, name)
	}

	character.game.mutex.RUnlock()

	// Sort commands alphabetically
	sort.Strings(commandNames)

	// Build help message
	var helpMsg strings.Builder
	helpMsg.WriteString("\n\rAvailable Commands:\n\r\n\r")

	character.game.mutex.RLock()

	for _, cmd := range commandNames {
		info := character.game.commands[cmd]
		helpMsg.WriteString(fmt.Sprintf("  %-12s - %s\n\r", cmd, info.description))
	}

	character.game.mutex.RUnlock()

	helpMsg.WriteString("\n\rType 'help <command>' for more information on a specific command.\n\r")

	character.player.toPlayer <- helpMsg.String()
	return nil
}

// showCommandHelp displays help for a specific command
func showCommandHelp(character *Character, cmdName string) error {
	if character == nil || character.player == nil || character.game == nil {
		return errors.New("invalid character state")
	}

	cmdName = strings.ToLower(cmdName)

	character.game.mutex.RLock()
	cmdInfo, exists := character.game.commands[cmdName]
	character.game.mutex.RUnlock()

	if !exists {
		character.player.toPlayer <- fmt.Sprintf("\n\rNo help available for '%s'. Command not found.\n\r", cmdName)
		return nil
	}

	var msg strings.Builder
	msg.WriteString(fmt.Sprintf("\n\rCommand: %s\n\r", cmdName))
	msg.WriteString(fmt.Sprintf("Description: %s\n\r", cmdInfo.description))
	msg.WriteString(fmt.Sprintf("Usage: %s\n\r", cmdInfo.usage))

	character.player.toPlayer <- msg.String()
	return nil
}

// executeLookCommand handles the look command
func executeLookCommand(character *Character, tokens []string) error {
	if character == nil {
		Logger.Error("Attempted to look with nil character")
		return errors.New("invalid character state")
	}

	Logger.Debug("Player is looking", "characterName", character.name)

	// Handle looking at specific targets if provided
	if len(tokens) > 1 {
		target := strings.ToLower(strings.Join(tokens[1:], " "))
		desc := getLookTarget(character, target)
		character.player.toPlayer <- desc
		return nil
	}

	// Look at room
	room := character.room
	if room == nil {
		character.player.toPlayer <- "\n\rYou are floating in the void.\n\r"
		return nil
	}

	room.mutex.RLock()
	defer room.mutex.RUnlock()

	var roomInfo strings.Builder
	roomInfo.Grow(1024) // Pre-allocate reasonable buffer

	// Room Title and Description
	roomInfo.WriteString("\n\r[")
	roomInfo.WriteString(ApplyColor("bright_white", room.title))
	roomInfo.WriteString("]\n\r")
	roomInfo.WriteString(room.description)
	roomInfo.WriteString("\n\r")

	// Exits - collect while under lock
	exits := make([]string, 0, len(room.exits))
	for _, exit := range room.exits {
		if exit != nil && exit.visible {
			exits = append(exits, exit.direction)
		}
	}

	if len(exits) == 0 {
		roomInfo.WriteString(msgNoExits)
	} else {
		sort.Strings(exits)
		roomInfo.WriteString("Obvious exits: ")
		roomInfo.WriteString(strings.Join(exits, ", "))
		roomInfo.WriteString("\n\r")
	}

	// Characters - collect while under lock
	chars := make([]string, 0, len(room.characters))
	for _, c := range room.characters {
		if c != nil && c != character {
			chars = append(chars, c.name)
		}
	}

	if len(chars) == 0 {
		roomInfo.WriteString(msgAlone)
	} else {
		roomInfo.WriteString(msgAlsoHere)
		roomInfo.WriteString(strings.Join(chars, ", "))
		roomInfo.WriteString("\n\r")
	}

	// Items - collect while under lock
	items := make([]string, 0, len(room.items))
	for _, item := range room.items {
		if item != nil && item.canPickUp {
			items = append(items, item.name)
		}
	}

	if len(items) > 0 {
		roomInfo.WriteString(msgItems)
		for _, item := range items {
			roomInfo.WriteString("- ")
			roomInfo.WriteString(item)
			roomInfo.WriteString("\n\r")
		}
	}

	character.player.toPlayer <- roomInfo.String()
	return nil
}

// getLookTarget handles looking at specific targets (characters, items, etc.)
func getLookTarget(character *Character, target string) string {
	// Check if looking at a character in the room
	if character.room != nil {
		character.room.mutex.RLock()
		for _, c := range character.room.characters {
			if c != nil && strings.Contains(strings.ToLower(c.name), target) {
				character.room.mutex.RUnlock()
				return formatCharacterDescription(c, character)
			}
		}

		// Check if looking at an item in the room
		for _, item := range character.room.items {
			if item != nil && strings.Contains(strings.ToLower(item.name), target) {
				character.room.mutex.RUnlock()
				return formatItemDescription(item)
			}
		}
		character.room.mutex.RUnlock()
	}

	// Check if looking at an item in inventory
	character.mutex.RLock()
	defer character.mutex.RUnlock()

	for _, item := range character.inventory {
		if item != nil && strings.Contains(strings.ToLower(item.name), target) {
			return formatItemDescription(item)
		}
	}

	// Check for directions/exits
	if character.room != nil {
		character.room.mutex.RLock()
		defer character.room.mutex.RUnlock()

		for direction, exit := range character.room.exits {
			if strings.Contains(exit.direction, target) && exit != nil && exit.visible {
				if exit.description != "" {
					return fmt.Sprintf("\n\r%s\n\r", exit.description)
				}
				return fmt.Sprintf("\n\rYou see an exit leading %s.\n\r", direction)
			}
		}
	}

	return fmt.Sprintf("\n\rYou don't see '%s' here.\n\r", target)
}

// formatCharacterDescription creates a description of a character
func formatCharacterDescription(target *Character, observer *Character) string {
	target.mutex.RLock()
	defer target.mutex.RUnlock()

	var desc strings.Builder
	desc.WriteString(fmt.Sprintf("\n\r%s\n\r", target.name))

	// Basic appearance info
	desc.WriteString("You see a ")

	// Add more descriptive elements here based on character attributes, equipment, etc.
	// This is placeholder logic
	if target.health < float64(target.game.startingHealth)/2 {
		desc.WriteString("wounded ")
	}

	desc.WriteString("person.\n\r")

	// Equipment description
	var visibleItems []string
	for _, item := range target.inventory {
		if item != nil && item.isWorn {
			visibleItems = append(visibleItems, fmt.Sprintf("%s on %s", item.name, strings.Join(item.wornOn, " and ")))
		}
	}

	if len(visibleItems) > 0 {
		desc.WriteString("They are wearing ")
		desc.WriteString(strings.Join(visibleItems, ", "))
		desc.WriteString(".\n\r")
	}

	return desc.String()
}
