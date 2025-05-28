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
	fuzzy "github.com/paul-mannino/go-fuzzywuzzy"
)

// CommandInfo stores metadata about each command
type CommandInfo struct {
	timed       bool                                      // Whether the command is timed (true) or untimed (false)
	handler     func(c *Character, tokens []string) error // Function to execute the command
	description string                                    // Description for help text
	usage       string                                    // Usage information
}

// commandIndex holds all command names for fuzzy matching
var commandIndex []string

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


	g.commands["remove"] = CommandInfo{
		timed:       true,
		handler:     nil, // Escalates to room goroutine
		description: "Remove a worn item",
		usage:       "remove <item>",
	}

	g.commands["switch"] = CommandInfo{
		timed:       false,
		handler:     nil, // Escalates to room goroutine
		description: "Switch items between your hands",
		usage:       "switch hands",
	}

}

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