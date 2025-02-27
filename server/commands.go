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

// CommandType defines whether a command is timed or untimed
type CommandType int

const (
	CommandUntimed CommandType = iota // Commands that don't affect the game world and execute immediately
	CommandTimed                      // Commands that affect the game world and are processed with the game clock
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

// CommandHandler is the function signature for command handlers
type CommandHandler func(character *Character, tokens []string) error

// CommandInfo stores metadata about each command
type CommandInfo struct {
	Type        CommandType    // Whether the command is timed or untimed
	Handler     CommandHandler // Function to execute the command
	Description string         // Description for help text
	Usage       string         // Usage information
}

// Commands map stores all available commands and their handlers
var Commands = map[string]CommandInfo{
	"quit": {
		Type:        CommandUntimed,
		Handler:     executeQuitCommand,
		Description: "Exit the game",
		Usage:       "quit",
	},
	"look": {
		Type:        CommandUntimed,
		Handler:     executeLookCommand,
		Description: "Look around or examine something",
		Usage:       "look [target]",
	},
	"help": {
		Type:        CommandUntimed,
		Handler:     executeHelpCommand,
		Description: "Display available commands",
		Usage:       "help [command]",
	},
}

// commandLexer splits input into tokens while respecting quoted strings
type commandLexer struct {
	input string
	pos   int
}

// newCommandLexer creates a new lexer for parsing commands
func newCommandLexer(input string) *commandLexer {
	return &commandLexer{input: input}
}

// tokenize breaks the input into individual tokens
func (l *commandLexer) tokenize() []string {
	var tokens []string
	var current strings.Builder
	inQuotes := false

	for l.pos < len(l.input) {
		switch l.input[l.pos] {
		case '"':
			inQuotes = !inQuotes
		case ' ', '\t':
			if !inQuotes && current.Len() > 0 {
				tokens = append(tokens, current.String())
				current.Reset()
			} else if inQuotes {
				current.WriteByte(l.input[l.pos])
			}
		default:
			current.WriteByte(l.input[l.pos])
		}
		l.pos++
	}

	if current.Len() > 0 {
		tokens = append(tokens, current.String())
	}

	return tokens
}

// ValidateCommand checks if a command is valid and returns its verb and tokens
func ValidateCommand(input string) (string, []string, error) {
	if len(input) == 0 {
		return "", nil, errors.New("\n\rNo command entered.\n\r")
	}

	lexer := newCommandLexer(input)
	tokens := lexer.tokenize()

	if len(tokens) == 0 {
		return "", nil, errors.New("\n\rNo command entered.\n\r")
	}

	verb := strings.ToLower(tokens[0])
	if _, exists := Commands[verb]; !exists {
		return "", nil, fmt.Errorf("\n\rCommand '%s' not understood.\n\r", verb)
	}

	return verb, tokens, nil
}

// ProcessCommand determines if a command is timed or untimed and handles it accordingly
func ProcessCommand(character *Character, input string) (bool, error) {
	// Parse and validate the command
	verb, tokens, err := ValidateCommand(input)
	if err != nil {
		return false, err
	}

	// Retrieve the command info
	cmdInfo, exists := Commands[verb]
	if !exists {
		return false, fmt.Errorf("command '%s' not understood", verb)
	}

	// Process based on command type
	if cmdInfo.Type == CommandUntimed {
		// Execute untimed commands immediately
		Logger.Debug("Executing untimed command", "verb", verb, "character", character.Name)
		start := time.Now()

		err := cmdInfo.Handler(character, tokens)

		elapsed := time.Since(start)
		if elapsed > 100*time.Millisecond {
			Logger.Warn("Slow command execution", "verb", verb, "duration", elapsed, "character", character.Name)
		}

		// Return true if the command was "quit"
		return verb == "quit", err
	} else {
		// For timed commands, send to the game loop for processing
		Logger.Debug("Queuing timed command for processing", "verb", verb, "character", character.Name)

		// Create a command package to send to the game loop
		cmdPackage := &CommandPackage{
			Character: character,
			Verb:      verb,
			Tokens:    tokens,
			Timestamp: time.Now(),
		}

		// Send to game loop for processing
		select {
		case character.game.commandQueue <- cmdPackage:
			return false, nil
		default:
			return false, errors.New("\n\rServer is busy. Please try again in a moment.\n\r")
		}
	}
}

// CommandPackage represents a command to be processed by the game loop
type CommandPackage struct {
	Character *Character
	Verb      string
	Tokens    []string
	Timestamp time.Time
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
			Logger.Warn("Failed to notify player: ToPlayer channel is full or closed", "characterName", character.Name)
		}
	}

	// Signal the end of character's lifecycle
	select {
	case character.end <- true:
	default:
		Logger.Warn("End channel is full or closed", "characterName", character.name)
	}

	// Clean up and save character state
	if err := character.Stop(); err != nil {
		Logger.Error("Error stopping character", "characterName", character.name, "error", err)
		return fmt.Errorf("error during character logout: %w", err)
	}

	return nil
}

// executeHelpCommand handles the help command
func executeHelpCommand(character *Character, tokens []string) error {
	if character == nil || character.player == nil {
		return errors.New("invalid character state")
	}

	Logger.Debug("Player requesting help", "characterName", character.name)

	// Check if help was requested for a specific command
	if len(tokens) > 1 {
		return showCommandHelp(character, tokens[1])
	}

	// Show general help with all commands
	var untimedCommands, timedCommands []string
	for name, info := range Commands {
		if info.Type == CommandUntimed {
			untimedCommands = append(untimedCommands, name)
		} else {
			timedCommands = append(timedCommands, name)
		}
	}

	// Sort commands alphabetically
	sort.Strings(untimedCommands)
	sort.Strings(timedCommands)

	// Build help message
	var helpMsg strings.Builder
	helpMsg.WriteString("\n\rAvailable Commands:\n\r\n\r")

	helpMsg.WriteString("Untimed Commands (execute immediately):\n\r")
	for _, cmd := range untimedCommands {
		info := Commands[cmd]
		helpMsg.WriteString(fmt.Sprintf("  %-12s - %s\n\r", cmd, info.Description))
	}

	if len(timedCommands) > 0 {
		helpMsg.WriteString("\n\rTimed Commands (process with game clock):\n\r")
		for _, cmd := range timedCommands {
			info := Commands[cmd]
			helpMsg.WriteString(fmt.Sprintf("  %-12s - %s\n\r", cmd, info.Description))
		}
	}

	helpMsg.WriteString("\n\rType 'help <command>' for more information on a specific command.\n\r")

	character.player.toPlayer <- helpMsg.String()
	return nil
}

// showCommandHelp displays help for a specific command
func showCommandHelp(character *Character, cmdName string) error {
	cmdName = strings.ToLower(cmdName)
	cmdInfo, exists := Commands[cmdName]

	if !exists {
		character.player.toPlayer <- fmt.Sprintf("\n\rNo help available for '%s'. Command not found.\n\r", cmdName)
		return nil
	}

	var msg strings.Builder
	msg.WriteString(fmt.Sprintf("\n\rCommand: %s\n\r", cmdName))
	msg.WriteString(fmt.Sprintf("Description: %s\n\r", cmdInfo.Description))
	msg.WriteString(fmt.Sprintf("Usage: %s\n\r", cmdInfo.Usage))

	if cmdInfo.Type == CommandTimed {
		msg.WriteString("Note: This is a timed command and will be processed with the game clock.\n\r")
	} else {
		msg.WriteString("Note: This is an untimed command and will execute immediately.\n\r")
	}

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

// formatItemDescription creates a description of an item
func formatItemDescription(item *Item) string {
	var desc strings.Builder
	desc.WriteString(fmt.Sprintf("\n\r%s\n\r", item.name))
	desc.WriteString(item.description)
	desc.WriteString("\n\r")

	if item.wearable && len(item.wornOn) > 0 {
		desc.WriteString(fmt.Sprintf("It can be worn on: %s\n\r", strings.Join(item.wornOn, ", ")))
	}

	return desc.String()
}

// SendRoomMessageExcept sends a message to all characters in a room except one
func SendRoomMessageExcept(room *Room, message string, except *Character) {
	if room == nil {
		return
	}

	room.mutex.RLock()
	defer room.mutex.RUnlock()

	for _, c := range room.characters {
		if c != nil && c != except && c.player != nil {
			select {
			case c.player.toPlayer <- message:
				// Message sent successfully
			default:
				Logger.Warn("Failed to send room message to player",
					"recipient", c.name,
					"message", message)
			}
		}
	}
}

// formatHandSlot formats a hand slot for inventory display
func formatHandSlot(slotName string, item *Item) string {
	if item == nil {
		return fmt.Sprintf("  %s: empty\n\r", slotName)
	}

	description := fmt.Sprintf("  %s: %s", slotName, item.name)
	if item.stackable && item.quantity > 1 {
		description += fmt.Sprintf(" (x%d)", item.quantity)
	}
	description += "\n\r"

	return description
}

// formatWornItem formats a worn item for inventory display
func formatWornItem(item *Item) string {
	description := fmt.Sprintf("  %s", item.name)
	if len(item.wornOn) > 0 {
		description += fmt.Sprintf(" (worn on %s)", strings.Join(item.wornOn, ", "))
	}
	description += "\n\r"

	return description
}

// formatCarriedItem formats a carried item for inventory display
func formatCarriedItem(item *Item) string {
	description := fmt.Sprintf("  %s", item.name)
	if item.stackable && item.quantity > 1 {
		description += fmt.Sprintf(" (x%d)", item.quantity)
	}
	description += "\n\r"

	return description
}
