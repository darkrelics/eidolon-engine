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

	// Register movement commands
	g.commands["north"] = CommandInfo{
		timed:       true,
		handler:     nil, // Handled by room level
		description: "Move north",
		usage:       "north",
	}

	g.commands["south"] = CommandInfo{
		timed:       true,
		handler:     nil, // Handled by room level
		description: "Move south",
		usage:       "south",
	}

	g.commands["east"] = CommandInfo{
		timed:       true,
		handler:     nil, // Handled by room level
		description: "Move east",
		usage:       "east",
	}

	g.commands["west"] = CommandInfo{
		timed:       true,
		handler:     nil, // Handled by room level
		description: "Move west",
		usage:       "west",
	}

	g.commands["up"] = CommandInfo{
		timed:       true,
		handler:     nil, // Handled by room level
		description: "Move up",
		usage:       "up",
	}

	g.commands["down"] = CommandInfo{
		timed:       true,
		handler:     nil, // Handled by room level
		description: "Move down",
		usage:       "down",
	}

	// Register shorthand movement commands
	g.commands["n"] = CommandInfo{
		timed:       true,
		handler:     nil, // Handled by room level
		description: "Move north (shorthand)",
		usage:       "n",
	}

	g.commands["s"] = CommandInfo{
		timed:       true,
		handler:     nil, // Handled by room level
		description: "Move south (shorthand)",
		usage:       "s",
	}

	g.commands["e"] = CommandInfo{
		timed:       true,
		handler:     nil, // Handled by room level
		description: "Move east (shorthand)",
		usage:       "e",
	}

	g.commands["w"] = CommandInfo{
		timed:       true,
		handler:     nil, // Handled by room level
		description: "Move west (shorthand)",
		usage:       "w",
	}

	g.commands["u"] = CommandInfo{
		timed:       true,
		handler:     nil, // Handled by room level
		description: "Move up (shorthand)",
		usage:       "u",
	}

	g.commands["d"] = CommandInfo{
		timed:       true,
		handler:     nil, // Handled by room level
		description: "Move down (shorthand)",
		usage:       "d",
	}

	// Register explicit movement commands
	g.commands["go"] = CommandInfo{
		timed:       true,
		handler:     nil, // Handled by room level
		description: "Move in the specified direction",
		usage:       "go <direction>",
	}

	g.commands["move"] = CommandInfo{
		timed:       true,
		handler:     nil, // Handled by room level
		description: "Move in the specified direction",
		usage:       "move <direction>",
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
		start := time.Now()

		err := cmdInfo.handler(character, tokens)

		elapsed := time.Since(start)
		if elapsed > 100*time.Millisecond {
			Logger.Warn("Slow command execution", "verb", verb, "duration", elapsed, "character", character.name)
		}

		return false, err
	} else {
		// For timed commands, determine the tier and route accordingly
		var tier CommandTier

		// Determine tier based on command properties
		switch verb {
		case "say", "look", "emote", "whisper":
			// Commands that only affect the local room
			tier = RoomTier
		case "shout", "weather", "time", "global":
			// Commands that affect multiple rooms or the entire game
			tier = GameTier
		case "north", "south", "east", "west", "up", "down",
			"n", "s", "e", "w", "u", "d", "go", "move":
			// Movement commands are processed at room level
			tier = RoomTier
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
		case character.player.commandOut <- "\n\rSaving character state...\n\r":
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

	character.player.commandOut <- helpMsg.String()
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
		character.player.commandOut <- fmt.Sprintf("\n\rNo help available for '%s'. Command not found.\n\r", cmdName)
		return nil
	}

	var msg strings.Builder
	msg.WriteString(fmt.Sprintf("\n\rCommand: %s\n\r", cmdName))
	msg.WriteString(fmt.Sprintf("Description: %s\n\r", cmdInfo.description))
	msg.WriteString(fmt.Sprintf("Usage: %s\n\r", cmdInfo.usage))

	character.player.commandOut <- msg.String()
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
		character.player.commandOut <- desc
		return nil
	}

	// Look at room
	room := character.room
	if room == nil {
		character.player.commandOut <- "\n\rYou are floating in the void.\n\r"
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

	character.player.commandOut <- roomInfo.String()
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

// executeWhoCommand handles the who command, displaying all online characters
func executeWhoCommand(character *Character, tokens []string) error {
	if character == nil || character.player == nil || character.game == nil {
		return errors.New("invalid character state")
	}

	Logger.Debug("Player checking who is online", "characterName", character.name)

	// Get all active characters from the game
	character.game.mutex.RLock()
	var characterNames []string
	for _, c := range character.game.characters {
		if c != nil && c.name != "" {
			characterNames = append(characterNames, c.name)
		}
	}
	character.game.mutex.RUnlock()

	// Sort names alphabetically
	sort.Strings(characterNames)

	// Check if there are any other characters online
	if len(characterNames) == 0 {
		character.player.commandOut <- whoEmpty
		return nil
	}

	// Build message with character list
	var msg strings.Builder
	msg.WriteString(whoHeader)
	msg.WriteString("----------------\n\r")

	// Determine column count based on console width and character count
	consoleWidth := 80 // Default
	if character.player.consoleWidth > 0 {
		consoleWidth = character.player.consoleWidth
	}

	// Column width is 16 characters (as specified)
	const colWidth = 16
	maxCols := consoleWidth / colWidth

	// If fewer than 20 characters, use single column layout as specified
	if len(characterNames) < 20 {
		// Single column layout
		for _, name := range characterNames {
			msg.WriteString(fmt.Sprintf("%-16s\n\r", name))
		}
	} else {
		// Multi-column layout
		cols := maxCols
		if cols < 1 {
			cols = 1 // Ensure at least one column
		}

		// Calculate rows needed
		rows := (len(characterNames) + cols - 1) / cols // Ceiling division

		// Display characters in column-first order
		for r := 0; r < rows; r++ {
			for c := 0; c < cols; c++ {
				idx := c*rows + r
				if idx < len(characterNames) {
					msg.WriteString(fmt.Sprintf("%-16s", characterNames[idx]))
				}
			}
			msg.WriteString("\n\r")
		}
	}

	msg.WriteString("\n\r")
	msg.WriteString(fmt.Sprintf("Total Characters Online: %d\n\r", len(characterNames)))

	character.player.commandOut <- msg.String()
	return nil
}

// executeInfoCommand displays information about the character
func executeInfoCommand(character *Character, tokens []string) error {
	if character == nil || character.player == nil {
		return errors.New("invalid character state")
	}

	Logger.Debug("Player requesting character information", "characterName", character.name)

	character.mutex.RLock()
	defer character.mutex.RUnlock()

	var info strings.Builder
	info.WriteString(fmt.Sprintf("\n\r%s\n\r", ApplyColor("bright_white", character.name)))
	info.WriteString("----------------\n\r")

	// Basic character information
	info.WriteString(fmt.Sprintf("Health: %d\n\r", int(character.health)))
	info.WriteString(fmt.Sprintf("Essence: %d\n\r", int(character.essence)))

	// Attributes
	if len(character.attributes) > 0 {
		info.WriteString("\n\rAttributes:\n\r")
		for attr, value := range character.attributes {
			info.WriteString(fmt.Sprintf("  %-12s: %d\n\r", attr, int(value)))
		}
	}

	// Abilities - only show those above zero
	var abilitiesAboveZero []string
	for ability, value := range character.abilities {
		if value > 0 {
			abilitiesAboveZero = append(abilitiesAboveZero, ability)
		}
	}

	if len(abilitiesAboveZero) > 0 {
		info.WriteString("\n\rAbilities:\n\r")
		// Sort abilities for consistent display
		sort.Strings(abilitiesAboveZero)

		// Display each ability with value > 0
		for _, ability := range abilitiesAboveZero {
			value := character.abilities[ability]
			info.WriteString(fmt.Sprintf("  %-12s: %d\n\r", ability, int(value)))
		}
	}

	// Inventory information
	if len(character.inventory) > 0 {
		info.WriteString("\n\rInventory:\n\r")
		for _, item := range character.inventory {
			if item != nil {
				if item.isWorn {
					info.WriteString(fmt.Sprintf("  %s (worn on %s)\n\r", item.name, strings.Join(item.wornOn, ", ")))
				} else {
					info.WriteString(fmt.Sprintf("  %s\n\r", item.name))
				}
			}
		}
	} else {
		info.WriteString("\n\rYou are not carrying anything.\n\r")
	}

	// Current location
	if character.room != nil {
		info.WriteString(fmt.Sprintf("\n\rCurrently in: %s\n\r", character.room.title))
	}

	character.player.commandOut <- info.String()
	return nil
}

// executeSkillCommand displays only the character's abilities
func executeSkillCommand(character *Character, tokens []string) error {
	if character == nil || character.player == nil {
		return errors.New("invalid character state")
	}

	Logger.Debug("Player requesting skill information", "characterName", character.name)

	character.mutex.RLock()
	defer character.mutex.RUnlock()

	var skillInfo strings.Builder
	skillInfo.WriteString(fmt.Sprintf("\n\r%s's Abilities\n\r", ApplyColor("bright_cyan", character.name)))
	skillInfo.WriteString("----------------\n\r")

	// Abilities - only show those above zero
	var abilitiesAboveZero []string
	for ability, value := range character.abilities {
		if value > 0 {
			abilitiesAboveZero = append(abilitiesAboveZero, ability)
		}
	}

	if len(abilitiesAboveZero) > 0 {
		// Sort abilities for consistent display
		sort.Strings(abilitiesAboveZero)

		// Display each ability with value > 0
		for _, ability := range abilitiesAboveZero {
			value := character.abilities[ability]
			skillInfo.WriteString(fmt.Sprintf("  %-15s: %d\n\r", ability, int(value)))
		}
	} else {
		skillInfo.WriteString("  You have not developed any abilities yet.\n\r")
	}

	character.player.commandOut <- skillInfo.String()
	return nil
}
