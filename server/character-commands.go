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
		select {
		case character.player.commandOut <- "\n\rSaving character state...\n\r":
		default:
			Logger.Warn("Failed to notify player: ToPlayer channel is full or closed", "characterName", character.name)
		}
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

// executeLookCommand handles the look command
func executeLookCommand(character *Character, tokens []string) error {
	if character == nil {
		Logger.Error("Attempted to look with nil character")
		return errors.New("invalid character state")
	}

	Logger.Debug("Player is looking", "characterName", character.name)

	// Target examination provides detailed object descriptions
	if len(tokens) > 1 {
		target := strings.ToLower(strings.Join(tokens[1:], " "))
		return character.LookAtTarget(target)
	}

	// Room examination is the default when no target specified
	// The Run method should have placed the character in room 0 if room was nil
	if character.room == nil {
		Logger.Warn("Character has no room assigned, placing in room 0", "characterName", character.name)
		character.room = character.game.rooms[0]
	}

	// Room description includes exits, occupants, and items
	description := character.room.GetDescription(character)
	SafeSendString(character.player.commandOut, description, character.name)
	return nil
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

// executeInfoCommand displays information about the character
func executeInfoCommand(character *Character, tokens []string) error {
	if character == nil || character.player == nil {
		return errors.New("invalid character state")
	}

	Logger.Debug("Player requesting character information", "characterName", character.name)

	// Character info includes stats, skills, and status
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

	// Skill display shows only skills with non-zero values
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

	// Inventory locking prevents race conditions during display
	character.mutex.RLock()
	defer character.mutex.RUnlock()

	var invDisplay strings.Builder
	invDisplay.WriteString("\n\rInventory:\n\r")
	invDisplay.WriteString("----------------\n\r")

	// Hand items shown first for combat readiness visibility
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
		// Detailed formatting shows quantity for stackable items
		var wornItems, carriedItems []*Item

		for _, item := range character.inventory {
			if item == nil {
				continue
			}

			// Mutex protection prevents crashes from concurrent modifications
			item.mutex.RLock()
			isWorn := item.isWorn
			item.mutex.RUnlock()

			if isWorn {
				wornItems = append(wornItems, item)
			} else {
				carriedItems = append(carriedItems, item)
			}
		}

		// Worn items indicate character's current equipment
		if len(wornItems) > 0 {
			invDisplay.WriteString("\n\rYou are wearing:\n\r")
			for _, item := range wornItems {
				invDisplay.WriteString(formatWornItem(item))
			}
		}

		// Carried items represent inventory not currently equipped
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
	info.WriteString(fmt.Sprintf("\n\r%s\n\r", ApplyColor("bright_cyan", c.name+"'s Info")))
	info.WriteString("----------------\n\r")

	// Core stats provide combat and survival metrics
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
		// Consistent ordering improves skill comparison
		sort.Strings(skillsAboveZero)

		// Zero-value skills hidden to reduce UI clutter
		for _, skill := range skillsAboveZero {
			value := c.skills[skill]
			info.WriteString(fmt.Sprintf("  %-12s: %d\n\r", skill, int(value)))
		}
	}

	// Hand contents affect combat capabilities
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

	// Inventory capacity and organization details
	if len(c.inventory) > 0 {
		// Separation clarifies equipment vs stored items
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

		// Worn equipment provides active bonuses
		if len(wornItems) > 0 {
			info.WriteString("\n\rYou are wearing ")
			info.WriteString(formatItemListWithOxfordComma(wornItems))
			info.WriteString(".\n\r")
		}

		// Carried items available for use or trade
		if len(carriedItems) > 0 {
			info.WriteString("\n\rYou are carrying ")
			info.WriteString(formatItemListWithOxfordComma(carriedItems))
			info.WriteString(".\n\r")
		}
	} else if c.leftHand == nil && c.rightHand == nil {
		// Empty message only when truly nothing held
		info.WriteString("\n\rYou are not carrying anything.\n\r")
	}

	return info.String()
}

// GetSkillInfo returns a formatted string with character skills
func (c *Character) GetSkillInfo() string {
	c.mutex.RLock()
	defer c.mutex.RUnlock()

	var skillInfo strings.Builder
	skillInfo.WriteString(fmt.Sprintf("\n\r%s\n\r", ApplyColor("bright_cyan", c.name+"'s Skills")))
	skillInfo.WriteString("----------------\n\r")

	// Skills - only show those above zero
	var skillsAboveZero []string
	for skill, value := range c.skills {
		if value > 0 {
			skillsAboveZero = append(skillsAboveZero, skill)
		}
	}

	if len(skillsAboveZero) > 0 {
		// Consistent ordering improves skill comparison
		sort.Strings(skillsAboveZero)

		// Zero-value skills hidden to reduce UI clutter
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
	// "Look in" command examines container contents
	if strings.HasPrefix(target, "in ") {
		// "My" prefix directs search to personal inventory
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

	// Room search takes precedence over inventory
	desc := c.LookAtRoomTarget(target)
	if desc != fmt.Sprintf("\n\rYou don't see '%s' here.\n\r", target) {
		SafeSendString(c.player.commandOut, desc, c.name)
		return nil
	}

	// Inventory search fallback for personal items
	desc = c.LookAtInventoryItem(target)
	if desc != fmt.Sprintf("\n\rYou don't see '%s' here.\n\r", target) {
		SafeSendString(c.player.commandOut, desc, c.name)
		return nil
	}

	// Target doesn't exist in accessible locations
	SafeSendString(c.player.commandOut, fmt.Sprintf("\n\rYou don't see '%s' here.\n\r", target), c.name)
	return nil
}

// LookAtRoomTarget looks for a target in the room (character or item)
func (c *Character) LookAtRoomTarget(target string) string {
	// Character examination shows their description
	if c.room != nil {
		c.room.mutex.RLock()
		for _, char := range c.room.characters {
			if char != nil && strings.Contains(strings.ToLower(char.name), target) && char.IsVisibleTo(c) {
				c.room.mutex.RUnlock()
				return FormatCharacterDescription(char, c)
			}
		}

		// Item examination reveals detailed properties
		for _, item := range c.room.items {
			if item != nil && MatchesTarget(item.name, target) {
				c.room.mutex.RUnlock()
				return formatItemDescription(item)
			}
		}

		// Exit examination describes connected areas
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
		// Personal inventory containers need ownership check
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
		// Room containers accessible to all present
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
