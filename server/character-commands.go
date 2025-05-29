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
	character.Stop()
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
	SafeSendString(character.player.commandOut, description, character.name)

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
		SafeSendString(character.player.commandOut, whoEmpty, character.name)
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

	SafeSendString(character.player.commandOut, msg.String(), character.name)
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
	SafeSendString(character.player.commandOut, info, character.name)
	return nil
}

// executeSkillCommand displays only the character's skills
func executeSkillCommand(character *Character, tokens []string) error {
	if character == nil || character.player == nil {
		return errors.New("invalid character state")
	}

	Logger.Debug("Player requesting skill information", "characterName", character.name)

	// Get skill display from character method
	skillInfo := character.GetSkillInfo()
	SafeSendString(character.player.commandOut, skillInfo, character.name)
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

	// Display what's in hands first
	if character.leftHand != nil || character.rightHand != nil {
		invDisplay.WriteString("\n\rYou are holding:\n\r")
		if character.leftHand != nil {
			invDisplay.WriteString(fmt.Sprintf("  Left hand:  %s\n\r", character.leftHand.name))
		}
		if character.rightHand != nil {
			invDisplay.WriteString(fmt.Sprintf("  Right hand: %s\n\r", character.rightHand.name))
		}
	}

	if len(character.inventory) == 0 {
		if character.leftHand == nil && character.rightHand == nil {
			invDisplay.WriteString("You are not carrying anything.\n\r")
		}
	} else {
		// Display items using detailed formatting with proper mutex protection
		var wornItems, carriedItems []*Item

		for _, item := range character.inventory {
			if item == nil {
				continue
			}

			// Safely check item state with mutex
			item.mutex.RLock()
			isWorn := item.isWorn
			item.mutex.RUnlock()

			if isWorn {
				wornItems = append(wornItems, item)
			} else {
				carriedItems = append(carriedItems, item)
			}
		}

		// Display worn items with detailed formatting
		if len(wornItems) > 0 {
			invDisplay.WriteString("\n\rYou are wearing:\n\r")
			for _, item := range wornItems {
				invDisplay.WriteString(formatWornItem(item))
			}
		}

		// Display carried items with detailed formatting
		if len(carriedItems) > 0 {
			invDisplay.WriteString("\n\rYou are carrying:\n\r")
			for _, item := range carriedItems {
				invDisplay.WriteString(formatCarriedItem(item))
			}
		}
	}

	SafeSendString(character.player.commandOut, invDisplay.String(), character.name)
	return nil
}

// GetCharacterInfo returns a formatted string with character information
func (c *Character) GetCharacterInfo() string {
	c.mutex.RLock()
	defer c.mutex.RUnlock()

	var info strings.Builder
	info.WriteString(fmt.Sprintf("\n\r%s\n\r", ApplyColor("bright_white", c.name)))
	info.WriteString("----------------\n\r")

	// Basic character information
	info.WriteString(fmt.Sprintf("Health: %d\n\r", int(c.health)))
	info.WriteString(fmt.Sprintf("Essence: %d\n\r", int(c.essence)))

	// Attributes
	if len(c.attributes) > 0 {
		info.WriteString("\n\rAttributes:\n\r")
		for attr, value := range c.attributes {
			info.WriteString(fmt.Sprintf("  %-12s: %d\n\r", attr, int(value)))
		}
	}

	// Skills - only show those above zero
	var skillsAboveZero []string
	for skill, value := range c.skills {
		if value > 0 {
			skillsAboveZero = append(skillsAboveZero, skill)
		}
	}

	if len(skillsAboveZero) > 0 {
		info.WriteString("\n\rSkills:\n\r")
		// Sort skills for consistent display
		sort.Strings(skillsAboveZero)

		// Display each skill with value > 0
		for _, skill := range skillsAboveZero {
			value := c.skills[skill]
			info.WriteString(fmt.Sprintf("  %-12s: %d\n\r", skill, int(value)))
		}
	}

	// Display hand contents
	if c.leftHand != nil || c.rightHand != nil {
		var handItems []string
		if c.rightHand != nil {
			handItems = append(handItems, c.rightHand.name)
		}
		if c.leftHand != nil {
			handItems = append(handItems, c.leftHand.name)
		}
		info.WriteString("\n\rYou are holding ")
		info.WriteString(formatItemListWithOxfordComma(handItems))
		info.WriteString(".\n\r")
	}

	// Inventory information
	if len(c.inventory) > 0 {
		// Separate worn and carried items
		var wornItems, carriedItems []string

		for _, item := range c.inventory {
			if item != nil {
				if item.isWorn {
					wornItems = append(wornItems, item.name)
				} else {
					carriedItems = append(carriedItems, item.name)
				}
			}
		}

		// Display worn items
		if len(wornItems) > 0 {
			info.WriteString("\n\rYou are wearing ")
			info.WriteString(formatItemListWithOxfordComma(wornItems))
			info.WriteString(".\n\r")
		}

		// Display carried items
		if len(carriedItems) > 0 {
			info.WriteString("\n\rYou are carrying ")
			info.WriteString(formatItemListWithOxfordComma(carriedItems))
			info.WriteString(".\n\r")
		}
	} else if c.leftHand == nil && c.rightHand == nil {
		// Only show "not carrying anything" if hands are also empty
		info.WriteString("\n\rYou are not carrying anything.\n\r")
	}

	return info.String()
}

// GetSkillInfo returns a formatted string with character skills
func (c *Character) GetSkillInfo() string {
	c.mutex.RLock()
	defer c.mutex.RUnlock()

	var skillInfo strings.Builder
	skillInfo.WriteString(fmt.Sprintf("\n\r%s's Skills\n\r", ApplyColor("bright_cyan", c.name)))
	skillInfo.WriteString("----------------\n\r")

	// Skills - only show those above zero
	var skillsAboveZero []string
	for skill, value := range c.skills {
		if value > 0 {
			skillsAboveZero = append(skillsAboveZero, skill)
		}
	}

	if len(skillsAboveZero) > 0 {
		// Sort skills for consistent display
		sort.Strings(skillsAboveZero)

		// Display each skill with value > 0
		for _, skill := range skillsAboveZero {
			value := c.skills[skill]
			skillInfo.WriteString(fmt.Sprintf("  %-15s: %.2f\n\r", skill, value))
		}
	} else {
		skillInfo.WriteString("  You have not developed any skills yet.\n\r")
	}

	return skillInfo.String()
}

// LookAtTarget handles examining specific targets
func (c *Character) LookAtTarget(target string) error {
	// Check if this is a "look in" command
	if strings.HasPrefix(target, "in ") {
		// Extract container name and check for "my" prefix
		containerPart := strings.TrimPrefix(target, "in ")
		isMyContainer := false

		if strings.HasPrefix(containerPart, "my ") {
			isMyContainer = true
			containerPart = strings.TrimPrefix(containerPart, "my ")
		}

		desc := c.LookInContainer(containerPart, isMyContainer)
		SafeSendString(c.player.commandOut, desc, c.name)
		return nil
	}

	// First check if target is in the room
	desc := c.LookAtRoomTarget(target)
	if desc != fmt.Sprintf("\n\rYou don't see '%s' here.\n\r", target) {
		SafeSendString(c.player.commandOut, desc, c.name)
		return nil
	}

	// Then check if it's in inventory
	desc = c.LookAtInventoryItem(target)
	if desc != fmt.Sprintf("\n\rYou don't see '%s' here.\n\r", target) {
		SafeSendString(c.player.commandOut, desc, c.name)
		return nil
	}

	// Not found anywhere
	SafeSendString(c.player.commandOut, fmt.Sprintf("\n\rYou don't see '%s' here.\n\r", target), c.name)
	return nil
}

// LookAtRoomTarget looks for a target in the room (character or item)
func (c *Character) LookAtRoomTarget(target string) string {
	// Check if looking at a character in the room
	if c.room != nil {
		c.room.mutex.RLock()
		for _, char := range c.room.characters {
			if char != nil && strings.Contains(strings.ToLower(char.name), target) {
				c.room.mutex.RUnlock()
				return FormatCharacterDescription(char, c)
			}
		}

		// Check if looking at an item in the room
		for _, item := range c.room.items {
			if item != nil && MatchesTarget(item.name, target) {
				c.room.mutex.RUnlock()
				return formatItemDescription(item)
			}
		}

		// Check for directions/exits
		for direction, exit := range c.room.exits {
			if strings.Contains(exit.direction, target) && exit != nil && exit.visible {
				c.room.mutex.RUnlock()
				if exit.description != "" {
					return fmt.Sprintf("\n\r%s\n\r", exit.description)
				}
				return fmt.Sprintf("\n\rYou see an exit leading %s.\n\r", direction)
			}
		}
		c.room.mutex.RUnlock()
	}

	return fmt.Sprintf("\n\rYou don't see '%s' here.\n\r", target)
}

// LookAtInventoryItem looks for an item in the character's inventory
func (c *Character) LookAtInventoryItem(target string) string {
	c.mutex.RLock()
	defer c.mutex.RUnlock()

	for _, item := range c.inventory {
		if item != nil && MatchesTarget(item.name, target) {
			return formatItemDescription(item)
		}
	}

	return fmt.Sprintf("\n\rYou don't see '%s' here.\n\r", target)
}

// LookInContainer handles looking inside a container
func (c *Character) LookInContainer(containerName string, isMyContainer bool) string {
	if isMyContainer {
		// Look in character's inventory for the container
		c.mutex.RLock()
		var container *Item
		for _, item := range c.inventory {
			if item != nil && MatchesTarget(item.name, containerName) {
				container = item
				break
			}
		}
		c.mutex.RUnlock()

		if container == nil {
			return fmt.Sprintf("\n\rYou don't have a '%s'.\n\r", containerName)
		}

		if !container.container {
			return fmt.Sprintf("\n\rThe %s is not a container.\n\r", container.name)
		}

		return "\n\r" + container.GetContainerContents()
	} else {
		// Look in room for the container
		if c.room == nil {
			return "\n\rYou're not in a valid room.\n\r"
		}

		c.room.mutex.RLock()
		var container *Item
		for _, item := range c.room.items {
			if item != nil && MatchesTarget(item.name, containerName) {
				container = item
				break
			}
		}
		c.room.mutex.RUnlock()

		if container == nil {
			return fmt.Sprintf("\n\rYou don't see a '%s' here.\n\r", containerName)
		}

		if !container.container {
			return fmt.Sprintf("\n\rThe %s is not a container.\n\r", container.name)
		}

		return "\n\r" + container.GetContainerContents()
	}
}
