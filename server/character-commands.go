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

// Error messages and prompts for character commands
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

	// Player needs immediate feedback about quit action
	if character.player != nil {
		character.DisplayMessage("Saving character state...")
	}

	// Lifecycle termination triggers cleanup and save operations
	character.Stop()
	return nil
}

// executeHelpCommand handles the help command
func executeHelpCommand(character *Character, tokens []string) error {
	if character == nil || character.player == nil || character.game == nil {
		return errors.New("invalid character state")
	}

	Logger.Debug("Player requesting help", "characterName", character.name)

	// Specific command help provides detailed usage information
	if len(tokens) > 1 {
		return character.DisplayHelp(tokens[1])
	}

	return character.DisplayHelp("")
}

// executeWhoCommand handles the who command, displaying all online characters
func executeWhoCommand(character *Character, tokens []string) error {
	if character == nil || character.player == nil || character.game == nil {
		return errors.New("invalid character state")
	}

	Logger.Debug("Player checking who is online", "characterName", character.name)

	// Active character list shows who's currently online
	character.game.mutex.RLock()
	var characterNames []string
	for _, c := range character.game.characters {
		if c != nil && c.name != "" {
			characterNames = append(characterNames, c.name)
		}
	}
	character.game.mutex.RUnlock()

	// Alphabetical sorting improves readability of player lists
	sort.Strings(characterNames)

	// Empty player list means player is alone online
	if len(characterNames) == 0 {
		SafeSendString(character.player.commandOut, whoEmpty, character.name)
		return nil
	}

	// Character list formatting shows all online players
	var msg strings.Builder
	msg.WriteString(whoHeader)
	msg.WriteString("----------------\n\r")

	// Simple list format provides clean player roster
	for _, name := range characterNames {
		msg.WriteString(fmt.Sprintf("%s\n\r", name))
	}

	msg.WriteString("\n\r")
	msg.WriteString(fmt.Sprintf("Total Characters Online: %d\n\r", len(characterNames)))

	SafeSendString(character.player.commandOut, msg.String(), character.name)
	return nil
}

// executeUnhideCommand handles the unhide command
func executeUnhideCommand(character *Character, tokens []string) error {
	if character == nil {
		return errors.New("invalid character state")
	}

	if !character.IsHidden() {
		SafeSendString(character.player.commandOut, "\n\rYou are not hidden.\n\r", character.name)
		return nil
	}

	// Stealth state reset makes character visible
	character.SetHidden(false)
	SafeSendString(character.player.commandOut, "\n\rYou step out from hiding.\n\r", character.name)

	// Room notification alerts players to revealed presence
	SendRoomMessage(character.room,
		fmt.Sprintf("\n\r%s steps out from hiding.\n\r", character.name),
		character,
	)

	return nil
}

// executeDepartCommand handles the depart command for dead characters
func executeDepartCommand(character *Character, tokens []string) error {
	if character == nil {
		return errors.New("invalid character state")
	}

	// Only dead characters can depart
	if character.charState != CharStateDead {
		SafeSendString(character.player.commandOut, "\n\rYou can only depart when you are dead.\n\r", character.name)
		return nil
	}

	Logger.Info("Character departing as ghost", "characterName", character.name)

	// Drop all inventory items to the room
	if err := character.dropAllItems(); err != nil {
		Logger.Error("Failed to drop items during depart", "character", character.name, "error", err)
	}

	// Drop held items
	if err := character.dropHeldItems(); err != nil {
		Logger.Error("Failed to drop held items during depart", "character", character.name, "error", err)
	}

	// Transition to ghost state
	character.mutex.Lock()
	character.charState = CharStateGhost
	character.mutex.Unlock()

	// Notify the departing player
	SafeSendString(character.player.commandOut,
		ApplyColor("cyan", "\n\rYour spirit is released from your body, leaving your mortal possessions behind.\n\r"),
		character.name)

	// Notify others in the room
	SendRoomMessage(character.room,
		fmt.Sprintf("\n\r%s's body rots aways and returns to the earth.\n\r", character.name),
		character,
	)

	return nil
}
