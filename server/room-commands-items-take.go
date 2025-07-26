/*
Eidolon Engine - Take From Container Command

Copyright 2024-2025 Jason E. Robinson

*/

package main

import (
	"fmt"
	"strings"
	"time"
)

// handleTakeFromCommand processes the "take [item] from [container]" command
func handleTakeFromCommand(cmd *CommandRequest) *CommandResponse {
	// Args format: ["take", "item", "from", "container"]
	if len(cmd.Args) < 4 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("take what from what?"),
			Timestamp: time.Now(),
		}
	}

	// Find "from" keyword position
	fromIndex := -1
	for i, arg := range cmd.Args {
		if strings.ToLower(arg) == "from" {
			fromIndex = i
			break
		}
	}

	if fromIndex < 2 || fromIndex >= len(cmd.Args)-1 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("usage: take [item] from [container]"),
			Timestamp: time.Now(),
		}
	}

	// Extract item and container names
	itemName := strings.ToLower(strings.Join(cmd.Args[1:fromIndex], " "))
	containerName := strings.ToLower(strings.Join(cmd.Args[fromIndex+1:], " "))

	// Check for "my" prefix on container
	isMyContainer := false
	if strings.HasPrefix(containerName, "my ") {
		isMyContainer = true
		containerName = strings.TrimPrefix(containerName, "my ")
	}

	// Parse ordinals for both item and container
	itemPosition, itemBaseName, itemHasOrdinal := ParseTargetWithOrdinal(itemName)
	containerPosition, containerBaseName, containerHasOrdinal := ParseTargetWithOrdinal(containerName)

	character := cmd.Character
	if character == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid character state"),
			Timestamp: time.Now(),
		}
	}

	// Find the container
	var container *Item
	var matchingContainers []*Item

	if isMyContainer {
		// Look in character's inventory
		character.mutex.RLock()
		for _, item := range character.inventory {
			if item != nil && MatchesTarget(item.name, containerBaseName) {
				matchingContainers = append(matchingContainers, item)
			}
		}
		character.mutex.RUnlock()

		if len(matchingContainers) == 0 {
			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error:     fmt.Errorf("you don't have a '%s'", containerName),
				Timestamp: time.Now(),
			}
		}

		// If multiple matches and no ordinal specified, inform the player
		if len(matchingContainers) > 1 && !containerHasOrdinal {
			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error: fmt.Errorf("which %s? You have %d. Try 'take %s from first %s'",
					containerBaseName, len(matchingContainers), itemName, containerBaseName),
				Timestamp: time.Now(),
			}
		}

		// Check if position is valid
		if containerPosition > len(matchingContainers) {
			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error:     fmt.Errorf("you don't have that many %ss", containerBaseName),
				Timestamp: time.Now(),
			}
		}

		container = matchingContainers[containerPosition-1]
	} else {
		// Look in room
		if character.room == nil {
			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error:     fmt.Errorf("invalid room state"),
				Timestamp: time.Now(),
			}
		}

		character.room.mutex.RLock()
		for _, item := range character.room.items {
			if item != nil && MatchesTarget(item.name, containerBaseName) {
				matchingContainers = append(matchingContainers, item)
			}
		}
		character.room.mutex.RUnlock()

		if len(matchingContainers) == 0 {
			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error:     fmt.Errorf("you don't see a '%s' here", containerName),
				Timestamp: time.Now(),
			}
		}

		// If multiple matches and no ordinal specified, inform the player
		if len(matchingContainers) > 1 && !containerHasOrdinal {
			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error: fmt.Errorf("which %s? There are %d here. Try 'take %s from first %s'",
					containerBaseName, len(matchingContainers), itemName, containerBaseName),
				Timestamp: time.Now(),
			}
		}

		// Check if position is valid
		if containerPosition > len(matchingContainers) {
			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error:     fmt.Errorf("there aren't that many %ss here", containerBaseName),
				Timestamp: time.Now(),
			}
		}

		container = matchingContainers[containerPosition-1]
	}

	// Check if container is actually a container
	if !container.container {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("the %s is not a container", container.name),
			Timestamp: time.Now(),
		}
	}

	// Find all matching items in container
	var matchingItems []*Item
	container.mutex.RLock()
	for _, item := range container.contents {
		if item != nil && MatchesTarget(item.name, itemBaseName) {
			matchingItems = append(matchingItems, item)
		}
	}
	container.mutex.RUnlock()

	if len(matchingItems) == 0 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("there's no '%s' in the %s", itemBaseName, container.name),
			Timestamp: time.Now(),
		}
	}

	// If multiple matches and no ordinal specified, inform the player
	if len(matchingItems) > 1 && !itemHasOrdinal {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error: fmt.Errorf("which %s? There are %d in the %s. Try 'take first %s from %s'",
				itemBaseName, len(matchingItems), container.name, itemBaseName, container.name),
			Timestamp: time.Now(),
		}
	}

	// Check if position is valid
	if itemPosition > len(matchingItems) {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("there aren't that many %ss in the %s", itemBaseName, container.name),
			Timestamp: time.Now(),
		}
	}

	itemToTake := matchingItems[itemPosition-1]

	// Remove from container
	removedItem, err := container.RemoveItemFromContainer(itemToTake.id)
	if err != nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     err,
			Timestamp: time.Now(),
		}
	}

	// Try to put item in a hand
	character.mutex.Lock()
	var placedInHand bool
	var handUsed string

	// Try right hand first (dominant hand)
	if character.rightHand == nil {
		character.rightHand = removedItem
		placedInHand = true
		handUsed = "right hand"
	} else if character.leftHand == nil {
		// Try left hand if right is full
		character.leftHand = removedItem
		placedInHand = true
		handUsed = "left hand"
	}
	character.mutex.Unlock()

	// If both hands are full, put the item back in the container
	if !placedInHand {
		// Put item back in container
		err := container.AddItemToContainer(removedItem)
		if err != nil {
			Logger.Error("Failed to return item to container after hands full", "error", err)
		}
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("your hands are full"),
			Timestamp: time.Now(),
		}
	}

	// Success message
	message := fmt.Sprintf("\n\rYou take %s from %s and hold it in your %s.\n\r", removedItem.name, container.name, handUsed)

	// Notify room
	if character.room != nil {
		SendRoomMessage(character.room,
			fmt.Sprintf("\n\r%s takes %s from %s.\n\r", character.name, removedItem.name, container.name),
			character)
	}

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   message,
		Timestamp: time.Now(),
	}
}
