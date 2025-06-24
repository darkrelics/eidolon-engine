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
	info.WriteString(fmt.Sprintf("Health: %d/%d\n\r", c.health, c.maxHealth))
	
	// Show wound breakdown if injured
	if len(c.wounds) > 0 {
		woundCounts := c.GetWoundsByType()
		info.WriteString("Wounds: ")
		first := true
		for damageType, count := range woundCounts {
			if !first {
				info.WriteString(", ")
			}
			info.WriteString(fmt.Sprintf("%d %s", count, damageType))
			first = false
		}
		info.WriteString("\n\r")
	}
	
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
