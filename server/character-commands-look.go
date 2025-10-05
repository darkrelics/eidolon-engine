/*
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

*/

package main

import (
	"errors"
	"fmt"
	"strings"
)

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
	character.DisplayMessage(description)
	return nil
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
