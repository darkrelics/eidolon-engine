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
		return character.DisplayHelp(tokens[1])
	}

	return character.DisplayHelp("")
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

	// Always send prompt after room description
	character.SendPrompt()
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

// executeInventoryCommand displays the character's inventory
func executeInventoryCommand(character *Character, tokens []string) error {
	if character == nil || character.player == nil {
		return errors.New("invalid character state")
	}

	Logger.Debug("Player checking inventory", "characterName", character.name)

	// Lock the character's inventory while we read it
	character.mutex.RLock()
	defer character.mutex.RUnlock()

	var invDisplay strings.Builder
	invDisplay.WriteString("\n\rInventory:\n\r")
	invDisplay.WriteString("----------------\n\r")

	if len(character.inventory) == 0 {
		invDisplay.WriteString("You are not carrying anything.\n\r")
	} else {
		// Separate worn and carried items
		var wornItems, carriedItems []*Item

		for _, item := range character.inventory {
			if item == nil {
				continue
			}

			if item.isWorn {
				wornItems = append(wornItems, item)
			} else {
				carriedItems = append(carriedItems, item)
			}
		}

		// Display worn items first
		if len(wornItems) > 0 {
			invDisplay.WriteString("\n\rYou are wearing:\n\r")
			for _, item := range wornItems {
				invDisplay.WriteString(formatWornItem(item))
			}
		}

		// Then display carried items
		if len(carriedItems) > 0 {
			invDisplay.WriteString("\n\rYou are carrying:\n\r")
			for _, item := range carriedItems {
				invDisplay.WriteString(formatCarriedItem(item))
			}
		}
	}

	character.player.commandOut <- invDisplay.String()
	return nil
}

// executeEquipmentCommand displays only the character's equipped items
func executeEquipmentCommand(character *Character, tokens []string) error {
	if character == nil || character.player == nil {
		return errors.New("invalid character state")
	}

	Logger.Debug("Player checking equipment", "characterName", character.name)

	// Lock the character's inventory while we read it
	character.mutex.RLock()
	defer character.mutex.RUnlock()

	var eqDisplay strings.Builder
	eqDisplay.WriteString("\n\rEquipment:\n\r")
	eqDisplay.WriteString("----------------\n\r")

	// Check if character has any equipment
	var wornItems []*Item
	for _, item := range character.inventory {
		if item != nil && item.isWorn {
			wornItems = append(wornItems, item)
		}
	}

	if len(wornItems) == 0 {
		eqDisplay.WriteString("You are not wearing anything.\n\r")
	} else {
		// Organize items by wear location
		wearSlots := make(map[string][]*Item)
		for _, item := range wornItems {
			for _, location := range item.wornOn {
				wearSlots[location] = append(wearSlots[location], item)
			}
		}

		// Display items by location
		var locations []string
		for location := range wearSlots {
			locations = append(locations, location)
		}
		sort.Strings(locations)

		for _, location := range locations {
			items := wearSlots[location]
			eqDisplay.WriteString(fmt.Sprintf("\n\r%s:\n\r", location))
			for _, item := range items {
				eqDisplay.WriteString(fmt.Sprintf("  %s\n\r", item.name))
			}
		}

		// Display trait modifications if any
		var totalMods = make(map[string]int8)
		for _, item := range wornItems {
			for trait, mod := range item.traitMods {
				totalMods[trait] += mod
			}
		}

		if len(totalMods) > 0 {
			eqDisplay.WriteString("\n\rAttribute Modifiers:\n\r")
			for trait, mod := range totalMods {
				sign := "+"
				if mod < 0 {
					sign = ""
				}
				eqDisplay.WriteString(fmt.Sprintf("  %s: %s%d\n\r", trait, sign, mod))
			}
		}
	}

	character.player.commandOut <- eqDisplay.String()
	return nil
}

// executeGoCommand handles movement between rooms
func executeGoCommand(character *Character, tokens []string) error {
	if character == nil || character.player == nil || character.room == nil {
		return errors.New("invalid character state")
	}

	// Check if character state allows movement
	if character.charState != "standing" {
		return fmt.Errorf("\n\rYou must be standing to move. You are currently %s.\n\r", character.charState)
	}

	// Check if a direction was provided
	if len(tokens) < 2 {
		return errors.New(msgNoDirection)
	}

	// Get the direction from the command
	direction := strings.ToLower(tokens[1])
	Logger.Debug("Player attempting to move", "characterName", character.name, "direction", direction)

	// Look for matching exit
	character.room.mutex.RLock()
	var targetExit *Exit

	for _, exit := range character.room.exits {
		if exit != nil && strings.ToLower(exit.direction) == direction && exit.visible {
			targetExit = exit
			break
		}
	}
	character.room.mutex.RUnlock()

	// Check if exit exists
	if targetExit == nil {
		return errors.New(msgInvalidDir)
	}

	// Check if target room exists
	if targetExit.targetRoom == nil {
		return errors.New(msgPathNowhere)
	}

	// Get references before the move
	oldRoom := character.room
	newRoom := targetExit.targetRoom

	Logger.Info("Character moving between rooms",
		"characterName", character.name,
		"fromRoom", oldRoom.roomID,
		"toRoom", newRoom.roomID,
		"direction", direction)

	// Prepare departure message before modifying room states
	departureMsg := fmt.Sprintf("\n\r%s leaves %s.\n\r", character.name, direction)

	// Remove character from current room and update room activity timestamp
	oldRoom.mutex.Lock()
	delete(oldRoom.characters, character.id)
	oldRoom.lastActive = time.Now() // Update activity timestamp directly

	// Send departure message while holding the lock - avoid separate lock in SendRoomMessageExcept
	for _, c := range oldRoom.characters {
		if c != nil && c != character && c.player != nil {
			select {
			case c.player.commandOut <- departureMsg:
				// After sending room message, send the prompt again to ensure consistent UI
				select {
				case c.player.commandOut <- c.prompt:
					// Prompt sent successfully
				default:
					Logger.Warn("Failed to send prompt after room message to player",
						"recipient", c.name)
				}
			default:
				Logger.Warn("Failed to send room message to player",
					"recipient", c.name,
					"message", departureMsg)
			}
		}
	}
	oldRoom.mutex.Unlock()

	// Update character's room reference
	character.mutex.Lock()
	character.room = newRoom
	// We rely on the game tick to limit movement (ProcessCommand will verify waitUntil)
	character.mutex.Unlock()

	// Add character to new room, update activity timestamp, and send arrival message
	newRoom.mutex.Lock()
	newRoom.characters[character.id] = character
	newRoom.lastActive = time.Now() // Update activity timestamp directly
	// Reset idle counter while holding the lock
	newRoom.idleCounter = 0

	// If room has a script ID, activate scripts while holding the lock
	if newRoom.persistent && newRoom.scriptID != "" && !newRoom.scriptActive {
		newRoom.scriptActive = true
		Logger.Info("Activating scripts for persistent room with character entry", "roomID", newRoom.roomID)
	}

	// Send arrival message while holding the lock
	var message string
	if targetExit.arrivalText != "" {
		// Use custom arrival text if provided
		message = fmt.Sprintf("\n\r%s %s.\n\r", character.name, targetExit.arrivalText)
	} else {
		// Use default arrival text with direction
		message = fmt.Sprintf("\n\r%s arrives from the %s.\n\r", character.name, targetExit.direction)
	}

	for _, c := range newRoom.characters {
		if c != nil && c != character && c.player != nil {
			select {
			case c.player.commandOut <- message:
				// After sending room message, send the prompt again to ensure consistent UI
				select {
				case c.player.commandOut <- c.prompt:
					// Prompt sent successfully
				default:
					Logger.Warn("Failed to send prompt after room message to player",
						"recipient", c.name)
				}
			default:
				Logger.Warn("Failed to send room message to player",
					"recipient", c.name,
					"message", message)
			}
		}
	}
	newRoom.mutex.Unlock()

	// Get the room description for the character
	// Note: GetDescription acquires its own mutex lock
	description := newRoom.GetDescription(character)
	character.player.commandOut <- description

	return nil
}
