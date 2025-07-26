/*
Eidolon Engine - Item Get/Drop Commands

Copyright 2024-2025 Jason Robinson

*/

package main

import (
	"fmt"
	"time"

	"github.com/gofrs/uuid/v5"
)

// handleGetCommand processes the get/take command
func handleGetCommand(cmd *CommandRequest, targetName string) *CommandResponse {
	character := cmd.Character
	room := character.room

	// Check if room or character is valid
	if room == nil || character == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid room or character state"),
			Timestamp: time.Now(),
		}
	}

	// Parse ordinal from target
	position, itemName, hasOrdinal := ParseTargetWithOrdinal(targetName)

	// Find all matching items first
	var matchingItems []struct {
		item *Item
		id   uuid.UUID
	}

	// Lock room briefly to search for items
	room.mutex.Lock()
	for id, item := range room.items {
		if item != nil && MatchesTarget(item.name, itemName) {
			matchingItems = append(matchingItems, struct {
				item *Item
				id   uuid.UUID
			}{item, id})
		}
	}
	room.mutex.Unlock()

	// Check if we found any matches
	if len(matchingItems) == 0 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you don't see that here"),
			Timestamp: time.Now(),
		}
	}

	// If multiple matches and no ordinal specified, inform the player
	if len(matchingItems) > 1 && !hasOrdinal {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error: fmt.Errorf("which %s? There are %d here. Try 'get first %s' or 'get second %s'",
				itemName, len(matchingItems), itemName, itemName),
			Timestamp: time.Now(),
		}
	}

	// Check if position is valid
	if position > len(matchingItems) {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("there aren't that many %ss here", itemName),
			Timestamp: time.Now(),
		}
	}

	// Get the specific item (position is 1-based)
	targetMatch := matchingItems[position-1]
	targetItem := targetMatch.item
	targetItemID := targetMatch.id

	// Check if item can be picked up
	if !targetItem.canPickUp {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you cannot pick that up"),
			Timestamp: time.Now(),
		}
	}

	// Try to put item in a hand
	character.mutex.Lock()
	var placedInHand bool
	var handUsed string

	// Try right hand first (dominant hand)
	if character.rightHand == nil {
		character.rightHand = targetItem
		placedInHand = true
		handUsed = "right hand"
	} else if character.leftHand == nil {
		// Try left hand if right is full
		character.leftHand = targetItem
		placedInHand = true
		handUsed = "left hand"
	}
	character.mutex.Unlock()

	// If both hands are full, cannot pick up the item
	if !placedInHand {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("your hands are full"),
			Timestamp: time.Now(),
		}
	}

	// Remove from room after character operation
	room.mutex.Lock()
	delete(room.items, targetItemID)
	room.mutex.Unlock()

	// Create success message
	message := fmt.Sprintf("\n\rYou pick up %s in your %s.\n\r", targetItem.name, handUsed)

	// Notify the room
	SendRoomMessage(room, fmt.Sprintf("\n\r%s picks up %s.\n\r", character.name, targetItem.name), character)

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   message,
		Timestamp: time.Now(),
	}
}

// handleDropCommand processes the drop command
func handleDropCommand(cmd *CommandRequest, targetName string) *CommandResponse {
	character := cmd.Character
	room := character.room

	// Check if room or character is valid
	if room == nil || character == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid room or character state"),
			Timestamp: time.Now(),
		}
	}

	// Parse ordinal from target
	position, itemName, hasOrdinal := ParseTargetWithOrdinal(targetName)

	// Find matching items in the character's inventory and hands
	character.mutex.Lock()
	var matchingItems []struct {
		item     *Item
		slot     string
		isInHand bool
	}

	// Check hands first
	if character.rightHand != nil && MatchesTarget(character.rightHand.name, itemName) {
		matchingItems = append(matchingItems, struct {
			item     *Item
			slot     string
			isInHand bool
		}{character.rightHand, "right_hand", true})
	}
	if character.leftHand != nil && MatchesTarget(character.leftHand.name, itemName) {
		matchingItems = append(matchingItems, struct {
			item     *Item
			slot     string
			isInHand bool
		}{character.leftHand, "left_hand", true})
	}

	// Then check inventory
	for slot, item := range character.inventory {
		if item != nil && MatchesTarget(item.name, itemName) {
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
	if len(matchingItems) > 1 && !hasOrdinal {
		character.mutex.Unlock()
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error: fmt.Errorf("which %s? You have %d. Try 'drop first %s' or 'drop second %s'",
				itemName, len(matchingItems), itemName, itemName),
			Timestamp: time.Now(),
		}
	}

	// Check if position is valid
	if position > len(matchingItems) {
		character.mutex.Unlock()
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you don't have that many %ss", itemName),
			Timestamp: time.Now(),
		}
	}

	// Get the specific item (position is 1-based)
	targetMatch := matchingItems[position-1]
	itemToRemove := targetMatch.item
	slotToRemove := targetMatch.slot

	// Check if worn (with proper mutex protection)
	itemToRemove.mutex.RLock()
	isWorn := itemToRemove.isWorn
	itemToRemove.mutex.RUnlock()

	if isWorn {
		character.mutex.Unlock()
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you need to remove that first"),
			Timestamp: time.Now(),
		}
	}

	// Remove from inventory or hand
	if targetMatch.isInHand {
		switch targetMatch.slot {
		case "right_hand":
			character.rightHand = nil
		case "left_hand":
			character.leftHand = nil
		}
	} else {
		delete(character.inventory, slotToRemove)
	}
	character.mutex.Unlock()

	// Add to room
	room.mutex.Lock()
	room.items[itemToRemove.id] = itemToRemove
	room.mutex.Unlock()

	// Create success message
	message := fmt.Sprintf("\n\rYou drop %s.\n\r", itemToRemove.name)

	// Notify the room
	SendRoomMessage(room, fmt.Sprintf("\n\r%s drops %s.\n\r", character.name, itemToRemove.name), character)

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   message,
		Timestamp: time.Now(),
	}
}

// restoreItemToOriginalLocation restores an item to its original location (hand or inventory)
func restoreItemToOriginalLocation(character *Character, item *Item, slot string, isInHand bool) {
	character.mutex.Lock()
	defer character.mutex.Unlock()

	if isInHand {
		switch slot {
		case "right_hand":
			character.rightHand = item
		case "left_hand":
			character.leftHand = item
		}
	} else {
		character.inventory[slot] = item
	}
}
