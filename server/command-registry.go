/*
Eidolon Engine

Copyright 2024-2025 Jason Robinson

*/

package main

import (
	fuzzy "github.com/paul-mannino/go-fuzzywuzzy"
)

// CommandInfo stores metadata about each command
type CommandInfo struct {
	roundTime   int                                       // Round time in seconds (-1 = doesn't care, 0 = blocked by RT, >0 = generates RT)
	handler     func(c *Character, tokens []string) error // Function to execute the command
	description string                                    // Description for help text
	usage       string                                    // Usage information
}

// commandIndex holds all command names for fuzzy matching
var commandIndex []string

func (g *Game) initCommands() {

	g.commands["quit"] = CommandInfo{
		roundTime:   -1,
		handler:     executeQuitCommand,
		description: "Exit the game",
		usage:       "quit",
	}

	g.commands["look"] = CommandInfo{
		roundTime:   -1,
		handler:     executeLookCommand,
		description: "Look around or examine something",
		usage:       "look [target]",
	}

	g.commands["help"] = CommandInfo{
		roundTime:   -1,
		handler:     executeHelpCommand,
		description: "Display available commands",
		usage:       "help",
	}

	g.commands["who"] = CommandInfo{
		roundTime:   -1,
		handler:     executeWhoCommand,
		description: "Display currently online characters",
		usage:       "who",
	}

	g.commands["info"] = CommandInfo{
		roundTime:   -1,
		handler:     executeInfoCommand,
		description: "Display information about your character",
		usage:       "info",
	}

	g.commands["skill"] = CommandInfo{
		roundTime:   -1,
		handler:     executeSkillCommand,
		description: "Display your character's skills",
		usage:       "skill",
	}

	// Movement commands (escalate to room tier)
	g.commands["go"] = CommandInfo{
		roundTime:   0,
		handler:     nil,
		description: "Move in a direction or through an exit",
		usage:       "go <direction|exit>",
	}

	g.commands["move"] = CommandInfo{
		roundTime:   0,
		handler:     nil,
		description: "Move in a direction or through an exit",
		usage:       "move <direction|exit>",
	}

	g.commands["inventory"] = CommandInfo{
		roundTime:   -1,
		handler:     executeInventoryCommand,
		description: "Show your inventory",
		usage:       "inventory",
	}

	g.commands["say"] = CommandInfo{
		roundTime:   -1,
		handler:     nil,
		description: "Say something to everyone in the room",
		usage:       "say <message>",
	}

	// Item commands (escalate to room tier)
	g.commands["get"] = CommandInfo{
		roundTime:   0,
		handler:     nil,
		description: "Pick up an item from the room",
		usage:       "get <item>",
	}

	g.commands["take"] = CommandInfo{
		roundTime:   0,
		handler:     nil,
		description: "Pick up an item from the room or container",
		usage:       "take <item> [from <container>]",
	}

	g.commands["drop"] = CommandInfo{
		roundTime:   0,
		handler:     nil,
		description: "Drop an item from your inventory",
		usage:       "drop <item>",
	}

	g.commands["put"] = CommandInfo{
		roundTime:   0,
		handler:     nil,
		description: "Put an item in a container",
		usage:       "put <item> in <container>",
	}

	g.commands["wear"] = CommandInfo{
		roundTime:   0,
		handler:     nil,
		description: "Wear an item",
		usage:       "wear <item>",
	}

	g.commands["remove"] = CommandInfo{
		roundTime:   0,
		handler:     nil,
		description: "Remove a worn item",
		usage:       "remove <item>",
	}

	g.commands["switch"] = CommandInfo{
		roundTime:   -1,
		handler:     nil,
		description: "Switch items between your hands",
		usage:       "switch hands",
	}

	g.commands["hide"] = CommandInfo{
		roundTime:   4,
		handler:     nil,
		description: "Attempt to hide from others in the room",
		usage:       "hide",
	}

	g.commands["unhide"] = CommandInfo{
		roundTime:   -1,
		handler:     executeUnhideCommand,
		description: "Reveal yourself if hidden",
		usage:       "unhide",
	}

	g.commands["sneak"] = CommandInfo{
		roundTime:   3,
		handler:     nil,
		description: "Move stealthily while hidden",
		usage:       "sneak <direction|exit>",
	}

	g.commands["search"] = CommandInfo{
		roundTime:   0,
		handler:     nil,
		description: "Search for hidden characters in the room",
		usage:       "search",
	}

	g.commands["point"] = CommandInfo{
		roundTime:   0,
		handler:     nil,
		description: "Point at a hidden character to reveal them",
		usage:       "point <character>",
	}

	// Combat commands are handled at the room level, not character level
	g.commands["face"] = CommandInfo{
		roundTime:   0,
		handler:     nil, // Room-level handler in room-commands.go
		description: "Face a character for combat",
		usage:       "face <character>",
	}

	g.commands["assess"] = CommandInfo{
		roundTime:   -1,
		handler:     nil, // Room-level handler in room-commands.go
		description: "Check your current combat status",
		usage:       "assess",
	}

	g.commands["advance"] = CommandInfo{
		roundTime:   0,
		handler:     nil, // Room-level handler in room-commands.go
		description: "Advance on a target in combat",
		usage:       "advance [target] [range]",
	}

	g.commands["retreat"] = CommandInfo{
		roundTime:   0,
		handler:     nil, // Room-level handler in room-commands.go
		description: "Retreat from combat opponents",
		usage:       "retreat [range]",
	}

	g.commands["flee"] = CommandInfo{
		roundTime:   0,
		handler:     nil, // Room-level handler in room-commands.go
		description: "Flee from combat",
		usage:       "flee [direction]",
	}

	g.commands["depart"] = CommandInfo{
		roundTime:   -1,
		handler:     executeDepartCommand,
		description: "Depart as a ghost when dead",
		usage:       "depart",
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
