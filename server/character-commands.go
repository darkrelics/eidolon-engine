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
)

// Character command messages
const (
	msgAlone    = "You are alone.\n\r"
	msgAlsoHere = "Also here: "
	msgItems    = "Items in the room:\n\r"
	whoHeader   = "\n\rOnline Characters\n\r"
	whoEmpty    = "\n\rNo other players online.\n\r"
)

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
		return character.LookAtTarget(target)
	}

	// Look at room - character should always be in a room
	// The Run method should have placed the character in room 0 if room was nil
	if character.room == nil {
		Logger.Warn("Character has no room assigned, placing in room 0", "characterName", character.name)
		character.room = character.game.rooms[0]
	}

	// Get room description
	description := character.room.GetDescription(character)
	character.player.commandOut <- description
	return nil
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

	// Display characters in simple list format
	for _, name := range characterNames {
		msg.WriteString(fmt.Sprintf("%s\n\r", name))
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

	// Get character info display from character method
	info := character.GetCharacterInfo()
	character.player.commandOut <- info
	return nil
}

// executeSkillCommand displays only the character's abilities
func executeSkillCommand(character *Character, tokens []string) error {
	if character == nil || character.player == nil {
		return errors.New("invalid character state")
	}

	Logger.Debug("Player requesting skill information", "characterName", character.name)

	// Get skill display from character method
	skillInfo := character.GetSkillInfo()
	character.player.commandOut <- skillInfo
	return nil
}
