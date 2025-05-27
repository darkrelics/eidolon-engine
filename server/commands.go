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

	fuzzy "github.com/paul-mannino/go-fuzzywuzzy"
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

	// Movement commands (escalate to room tier)
	g.commands["go"] = CommandInfo{
		timed:       true,
		handler:     nil, // Escalates to room goroutine
		description: "Move in a direction or through an exit",
		usage:       "go <direction|exit>",
	}

	g.commands["move"] = CommandInfo{
		timed:       true,
		handler:     nil, // Escalates to room goroutine
		description: "Move in a direction or through an exit",
		usage:       "move <direction|exit>",
	}

	g.commands["inventory"] = CommandInfo{
		timed:       false,
		handler:     executeInventoryCommand,
		description: "Show your inventory",
		usage:       "inventory",
	}

	g.commands["equipment"] = CommandInfo{
		timed:       false,
		handler:     executeEquipmentCommand,
		description: "Show your equipped items",
		usage:       "equipment",
	}

	// Communication commands (escalate to room tier)
	g.commands["say"] = CommandInfo{
		timed:       false,
		handler:     nil, // Escalates to room goroutine
		description: "Say something to everyone in the room",
		usage:       "say <message>",
	}

	// Item commands (escalate to room tier)
	g.commands["get"] = CommandInfo{
		timed:       true,
		handler:     nil, // Escalates to room goroutine
		description: "Pick up an item from the room",
		usage:       "get <item>",
	}

	g.commands["take"] = CommandInfo{
		timed:       true,
		handler:     nil, // Escalates to room goroutine
		description: "Pick up an item from the room or container",
		usage:       "take <item> [from <container>]",
	}

	g.commands["drop"] = CommandInfo{
		timed:       true,
		handler:     nil, // Escalates to room goroutine
		description: "Drop an item from your inventory",
		usage:       "drop <item>",
	}

	g.commands["put"] = CommandInfo{
		timed:       true,
		handler:     nil, // Escalates to room goroutine
		description: "Put an item in a container",
		usage:       "put <item> in <container>",
	}

	g.commands["wear"] = CommandInfo{
		timed:       true,
		handler:     nil, // Escalates to room goroutine
		description: "Wear an item",
		usage:       "wear <item>",
	}

	g.commands["wield"] = CommandInfo{
		timed:       true,
		handler:     nil, // Escalates to room goroutine
		description: "Wield a weapon",
		usage:       "wield <weapon>",
	}

	g.commands["equip"] = CommandInfo{
		timed:       true,
		handler:     nil, // Escalates to room goroutine
		description: "Equip an item",
		usage:       "equip <item>",
	}

	g.commands["remove"] = CommandInfo{
		timed:       true,
		handler:     nil, // Escalates to room goroutine
		description: "Remove a worn item",
		usage:       "remove <item>",
	}

	g.commands["unwear"] = CommandInfo{
		timed:       true,
		handler:     nil, // Escalates to room goroutine
		description: "Remove a worn item",
		usage:       "unwear <item>",
	}

	g.commands["unequip"] = CommandInfo{
		timed:       true,
		handler:     nil, // Escalates to room goroutine
		description: "Remove an equipped item",
		usage:       "unequip <item>",
	}

	// Game-level environmental commands
	g.commands["weather"] = CommandInfo{
		timed:       false,
		handler:     nil, // Escalates to game tier
		description: "Check the current weather",
		usage:       "weather",
	}

	g.commands["time"] = CommandInfo{
		timed:       false,
		handler:     nil, // Escalates to game tier
		description: "Check the current game time",
		usage:       "time",
	}

	g.commands["shout"] = CommandInfo{
		timed:       false,
		handler:     nil, // Escalates to game tier
		description: "Shout a message to all players",
		usage:       "shout <message>",
	}

	g.commands["announce"] = CommandInfo{
		timed:       false,
		handler:     nil, // Escalates to game tier
		description: "Make a global announcement",
		usage:       "announce <message>",
	}

}

// commandIndex holds all command names for fuzzy matching
var commandIndex []string

// buildCommandIndex builds the command index for fuzzy matching
// This should be called after all commands are registered
func (g *Game) buildCommandIndex() {
	commandIndex = g.getCommandList()
	Logger.Info("Built command fuzzy index", "commands", len(commandIndex))
}

// findBestCommand uses fuzzy matching to find the best matching command
// Assumes commandIndex has been built during game initialization
func (g *Game) findBestCommand(input string) (string, int) {
	var bestMatch string
	var bestScore int

	// Use pre-built command index for efficiency
	for _, command := range commandIndex {
		score := fuzzy.Ratio(input, command)
		if score > bestScore {
			bestScore = score
			bestMatch = command
		}
	}

	return bestMatch, bestScore
}

// getCommandList returns a slice of all available command names
func (g *Game) getCommandList() []string {
	g.mutex.RLock()
	defer g.mutex.RUnlock()

	commands := make([]string, 0, len(g.commands))
	for command := range g.commands {
		commands = append(commands, command)
	}
	return commands
}

// ValidateCommand checks if a command is valid and returns its verb and tokens
func ValidateCommand(character *Character, input string) (string, []string, error) {
	if len(input) == 0 {
		return "", nil, errors.New("\n\rNo command entered.\n\r")
	}

	// Limit input to 240 characters
	if len(input) > 240 {
		return "", nil, errors.New("\n\rCommand too long. Maximum 240 characters allowed.\n\r")
	}

	tokens := tokenizeInput(input)

	if len(tokens) == 0 {
		return "", nil, errors.New("\n\rNo command entered.\n\r")
	}

	verb := strings.ToLower(tokens[0])
	if character == nil || character.game == nil {
		return "", nil, errors.New("\n\rInvalid character state.\n\r")
	}

	// First check for exact match
	character.game.mutex.RLock()
	_, exactMatch := character.game.commands[verb]
	character.game.mutex.RUnlock()

	if exactMatch {
		return verb, tokens, nil
	}

	// No exact match, try fuzzy matching
	bestMatch, score := character.game.findBestCommand(verb)

	// If confidence is 80% or higher, automatically execute the command
	if score >= 80 {
		Logger.Debug("Fuzzy match found", "input", verb, "match", bestMatch, "score", score)
		tokens[0] = bestMatch // Replace the verb with the matched command
		return bestMatch, tokens, nil
	}

	// If confidence is between 50% and 80%, ask if they meant the command
	if score >= 50 {
		return "", nil, fmt.Errorf("\n\rCommand '%s' not understood. Did you mean '%s'?\n\r", verb, bestMatch)
	}

	// No good match found
	return "", nil, fmt.Errorf("\n\rCommand '%s' not understood.\n\r", verb)
}

// tokenizeInput breaks the input into individual tokens
func tokenizeInput(input string) []string {
	// Sanitize input first
	input = strings.TrimSpace(input)

	// Remove any control characters (except tab which is handled in tokenization)
	input = strings.Map(func(r rune) rune {
		if r < 32 && r != '\t' {
			return -1
		}
		return r
	}, input)

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

// Ordinal words mapping for command parsing
var ordinalWords = map[string]int{
	"first":       1,
	"second":      2,
	"third":       3,
	"fourth":      4,
	"fifth":       5,
	"sixth":       6,
	"seventh":     7,
	"eighth":      8,
	"ninth":       9,
	"tenth":       10,
	"eleventh":    11,
	"twelfth":     12,
	"thirteenth":  13,
	"fourteenth":  14,
	"fifteenth":   15,
	"sixteenth":   16,
	"seventeenth": 17,
	"eighteenth":  18,
	"nineteenth":  19,
	"twentieth":   20,
}

// ordinalIndex holds all ordinal words for fuzzy matching
var ordinalIndex []string

// buildOrdinalIndex builds the ordinal index for fuzzy matching
// This should be called once during game initialization
func buildOrdinalIndex() {
	ordinalIndex = make([]string, 0, len(ordinalWords))
	for ordinal := range ordinalWords {
		ordinalIndex = append(ordinalIndex, ordinal)
	}
	Logger.Info("Built ordinal fuzzy index", "ordinals", len(ordinalIndex))
}

// fuzzyMatchOrdinal attempts to fuzzy match an input string to an ordinal word
// Returns the matched ordinal, its position value, and whether a match was found
// Assumes ordinalIndex has been built during game initialization
func fuzzyMatchOrdinal(input string) (string, int, bool) {
	input = strings.ToLower(strings.TrimSpace(input))

	// First check for exact match
	if position, exists := ordinalWords[input]; exists {
		return input, position, true
	}

	// Try fuzzy matching using pre-built index
	var bestMatch string
	var bestScore int

	for _, ordinal := range ordinalIndex {
		score := fuzzy.Ratio(input, ordinal)
		if score > bestScore {
			bestScore = score
			bestMatch = ordinal
		}
	}

	// Use standard 80% threshold
	if bestScore >= 80 {
		return bestMatch, ordinalWords[bestMatch], true
	}

	return "", 0, false
}

// ParseTargetWithOrdinal parses a target string and extracts ordinal position and item name
// Returns: ordinal position (1-based), item name, and whether an ordinal was found
// Examples:
//
//	"sword" -> 1, "sword", false (default to first)
//	"second sword" -> 2, "sword", true
//	"third goblin" -> 3, "goblin", true
func ParseTargetWithOrdinal(target string) (int, string, bool) {
	target = strings.ToLower(strings.TrimSpace(target))
	parts := strings.SplitN(target, " ", 2)

	// If only one word, return it as the item name with position 1
	if len(parts) == 1 {
		return 1, target, false
	}

	// Check if first word is an ordinal (with fuzzy matching)
	if _, position, isOrdinal := fuzzyMatchOrdinal(parts[0]); isOrdinal {
		return position, parts[1], true
	}

	// No ordinal found, return full target as item name
	return 1, target, false
}

// ExtractBaseNoun extracts the base noun from an item or exit name
// This helps match "red door", "blue door", "green door" all as "door"
// Returns the last word as the base noun
// Examples:
//
//	"red door" -> "door"
//	"silver sword" -> "sword"
//	"door" -> "door"
func ExtractBaseNoun(name string) string {
	words := strings.Fields(strings.ToLower(name))
	if len(words) == 0 {
		return ""
	}
	return words[len(words)-1]
}

// MatchesTarget checks if an item/exit name matches the target string
// Supports both full name matching and base noun matching
// Examples:
//
//	MatchesTarget("red door", "door") -> true
//	MatchesTarget("red door", "red door") -> true
//	MatchesTarget("red door", "blue door") -> false
func MatchesTarget(itemName, target string) bool {
	itemNameLower := strings.ToLower(itemName)
	targetLower := strings.ToLower(target)

	// First check if the full name contains the target
	if strings.Contains(itemNameLower, targetLower) {
		return true
	}

	// Then check if the base noun matches
	itemBaseNoun := ExtractBaseNoun(itemName)
	targetBaseNoun := ExtractBaseNoun(target)

	return itemBaseNoun == targetBaseNoun
}

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
