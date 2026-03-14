/*
Eidolon Engine - Container Commands (Put/Take)

Copyright 2024-2026 Jason E. Robinson

*/

package main

import (
	"fmt"
	"strings"
	"time"
)

// handlePutCommand processes the "put [item] in [container]" command
func handlePutCommand(cmd *CommandRequest) *CommandResponse {
	if len(cmd.Args) < 4 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("put what in what?"),
			Timestamp: time.Now(),
		}
	}

	// Find "in" keyword position
	inIndex := -1
	for i, arg := range cmd.Args {
		if strings.ToLower(arg) == "in" {
			inIndex = i
			break
		}
	}

	if inIndex < 2 || inIndex >= len(cmd.Args)-1 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("usage: put [item] in [container]"),
			Timestamp: time.Now(),
		}
	}

	// Extract item and container names
	itemName := strings.ToLower(strings.Join(cmd.Args[1:inIndex], " "))
	containerName := strings.ToLower(strings.Join(cmd.Args[inIndex+1:], " "))

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

	// Find matching items in character's inventory and hands
	character.mutex.Lock()
	var matchingItems []struct {
		item     *Item
		slot     string
		isInHand bool
	}

	// Check hands first
	if character.rightHand != nil && MatchesTarget(character.rightHand.name, itemBaseName) {
		matchingItems = append(matchingItems, struct {
			item     *Item
			slot     string
			isInHand bool
		}{character.rightHand, "right_hand", true})
	}
	if character.leftHand != nil && MatchesTarget(character.leftHand.name, itemBaseName) {
		matchingItems = append(matchingItems, struct {
			item     *Item
			slot     string
			isInHand bool
		}{character.leftHand, "left_hand", true})
	}

	// Then check inventory
	for slot, item := range character.inventory {
		if item != nil && MatchesTarget(item.name, itemBaseName) {
			matchingItems = append(matchingItems, struct {
				item     *Item
				slot     string
				isInHand bool
			}{item, slot, false})
		}
	}

	// Check if we found any matches
	if len(matchingItems) == 0 {
		character.mutex.Unlock()
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you don't have that"),
			Timestamp: time.Now(),
		}
	}

	// If multiple matches and no ordinal specified, inform the player
	if len(matchingItems) > 1 && !itemHasOrdinal {
		character.mutex.Unlock()
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error: fmt.Errorf("which %s? You have %d. Try 'put first %s in %s'",
				itemBaseName, len(matchingItems), itemBaseName, containerName),
			Timestamp: time.Now(),
		}
	}

	// Check if position is valid
	if itemPosition > len(matchingItems) {
		character.mutex.Unlock()
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you don't have that many %ss", itemBaseName),
			Timestamp: time.Now(),
		}
	}

	// Get the specific item
	targetMatch := matchingItems[itemPosition-1]
	itemToPut := targetMatch.item
	itemSlot := targetMatch.slot

	// Check if worn (with proper mutex protection)
	itemToPut.mutex.RLock()
	isWorn := itemToPut.isWorn
	itemToPut.mutex.RUnlock()

	if isWorn {
		character.mutex.Unlock()
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you need to remove that first"),
			Timestamp: time.Now(),
		}
	}

	// Remove item from inventory or hand before unlocking
	if targetMatch.isInHand {
		switch targetMatch.slot {
		case "right_hand":
			character.rightHand = nil
		case "left_hand":
			character.leftHand = nil
		}
	} else {
		delete(character.inventory, itemSlot)
	}
	character.mutex.Unlock()

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
			// Put the item back where it was
			restoreItemToOriginalLocation(character, itemToPut, targetMatch.slot, targetMatch.isInHand)

			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error:     fmt.Errorf("you don't have a '%s'", containerName),
				Timestamp: time.Now(),
			}
		}

		// If multiple matches and no ordinal specified, inform the player
		if len(matchingContainers) > 1 && !containerHasOrdinal {
			// Put the item back where it was
			restoreItemToOriginalLocation(character, itemToPut, targetMatch.slot, targetMatch.isInHand)

			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error: fmt.Errorf("which %s? You have %d. Try 'put %s in first %s'",
					containerBaseName, len(matchingContainers), itemName, containerBaseName),
				Timestamp: time.Now(),
			}
		}

		// Check if position is valid
		if containerPosition > len(matchingContainers) {
			// Put the item back where it was
			restoreItemToOriginalLocation(character, itemToPut, targetMatch.slot, targetMatch.isInHand)

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
			// Put the item back where it was
			restoreItemToOriginalLocation(character, itemToPut, targetMatch.slot, targetMatch.isInHand)

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
			// Put the item back where it was
			restoreItemToOriginalLocation(character, itemToPut, targetMatch.slot, targetMatch.isInHand)

			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error:     fmt.Errorf("you don't see a '%s' here", containerName),
				Timestamp: time.Now(),
			}
		}

		// If multiple matches and no ordinal specified, inform the player
		if len(matchingContainers) > 1 && !containerHasOrdinal {
			// Put the item back where it was
			restoreItemToOriginalLocation(character, itemToPut, targetMatch.slot, targetMatch.isInHand)

			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error: fmt.Errorf("which %s? There are %d here. Try 'put %s in first %s'",
					containerBaseName, len(matchingContainers), itemName, containerBaseName),
				Timestamp: time.Now(),
			}
		}

		// Check if position is valid
		if containerPosition > len(matchingContainers) {
			// Put the item back where it was
			restoreItemToOriginalLocation(character, itemToPut, targetMatch.slot, targetMatch.isInHand)

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
		// Put the item back where it was
		restoreItemToOriginalLocation(character, itemToPut, targetMatch.slot, targetMatch.isInHand)

		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("the %s is not a container", container.name),
			Timestamp: time.Now(),
		}
	}

	// Add item to container
	err := container.AddItemToContainer(itemToPut)
	if err != nil {
		// Put the item back where it was
		restoreItemToOriginalLocation(character, itemToPut, targetMatch.slot, targetMatch.isInHand)

		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     err,
			Timestamp: time.Now(),
		}
	}

	// Success message
	message := fmt.Sprintf("\n\rYou put %s in %s.\n\r", itemToPut.name, container.name)

	// Notify room
	if character.room != nil {
		SendRoomMessage(character.room,
			fmt.Sprintf("\n\r%s puts %s in %s.\n\r", character.name, itemToPut.name, container.name),
			character)
	}

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   message,
		Timestamp: time.Now(),
	}
}
