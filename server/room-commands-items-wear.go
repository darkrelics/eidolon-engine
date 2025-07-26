/*
Eidolon Engine - Wear/Remove/Switch Commands

Copyright 2024-2025 Jason E. Robinson

*/

package main

import (
	"fmt"
	"strings"
	"time"
)

// handleWearCommand processes the wear/equip command
func handleWearCommand(cmd *CommandRequest, targetName string) *CommandResponse {
	// Check if cmd is valid
	if cmd == nil {
		return &CommandResponse{
			Success:   false,
			Error:     fmt.Errorf("invalid command request"),
			Timestamp: time.Now(),
		}
	}

	character := cmd.Character

	// Check if character is valid
	if character == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid character state"),
			Timestamp: time.Now(),
		}
	}

	// Find the item in the character's inventory or hands
	var itemToWear *Item
	var fromHand string // Track which hand the item came from

	// Lock only for inventory and hand search
	character.mutex.Lock()

	// First check inventory
	for _, item := range character.inventory {
		if item != nil && MatchesTarget(item.name, targetName) {
			itemToWear = item
			break
		}
	}

	// If not found in inventory, check hands
	if itemToWear == nil {
		if character.rightHand != nil && MatchesTarget(character.rightHand.name, targetName) {
			itemToWear = character.rightHand
			fromHand = "right"
		} else if character.leftHand != nil && MatchesTarget(character.leftHand.name, targetName) {
			itemToWear = character.leftHand
			fromHand = "left"
		}
	}
	character.mutex.Unlock()

	// Check if item exists
	if itemToWear == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you don't have that"),
			Timestamp: time.Now(),
		}
	}

	// Check if item is already worn (with proper mutex protection)
	itemToWear.mutex.RLock()
	isWorn := itemToWear.isWorn
	itemToWear.mutex.RUnlock()

	if isWorn {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you're already wearing that"),
			Timestamp: time.Now(),
		}
	}

	// Check if item is wearable
	if !itemToWear.wearable || len(itemToWear.wornOn) == 0 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you can't wear that"),
			Timestamp: time.Now(),
		}
	}

	// Validate that the wear locations are valid
	for _, location := range itemToWear.wornOn {
		if !WearLocations[location] {
			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error:     fmt.Errorf("invalid wear location: %s", location),
				Timestamp: time.Now(),
			}
		}
	}

	// Check if wear locations are already occupied
	// Build a map of worn locations (with proper mutex protection)
	wornLocations := make(map[string]bool)

	// Lock character briefly to check worn items
	character.mutex.Lock()
	for _, item := range character.inventory {
		if item == nil {
			continue
		}

		item.mutex.RLock()
		isWorn := item.isWorn
		wornOn := make([]string, len(item.wornOn))
		copy(wornOn, item.wornOn)
		item.mutex.RUnlock()

		if isWorn {
			for _, loc := range wornOn {
				wornLocations[loc] = true
			}
		}
	}
	character.mutex.Unlock()

	// Special handling for finger and wrist items - map to specific left/right locations
	var finalWearLocations []string
	for _, location := range itemToWear.wornOn {
		switch location {
		case "finger":
			// Check left finger first, then right finger
			if !wornLocations["left_finger"] {
				finalWearLocations = append(finalWearLocations, "left_finger")
			} else if !wornLocations["right_finger"] {
				finalWearLocations = append(finalWearLocations, "right_finger")
			} else {
				return &CommandResponse{
					RequestID: cmd.ID,
					Success:   false,
					Error:     fmt.Errorf("both your fingers are already occupied"),
					Timestamp: time.Now(),
				}
			}
		case "wrist":
			// Check left wrist first, then right wrist
			if !wornLocations["left_wrist"] {
				finalWearLocations = append(finalWearLocations, "left_wrist")
			} else if !wornLocations["right_wrist"] {
				finalWearLocations = append(finalWearLocations, "right_wrist")
			} else {
				return &CommandResponse{
					RequestID: cmd.ID,
					Success:   false,
					Error:     fmt.Errorf("both your wrists are already occupied"),
					Timestamp: time.Now(),
				}
			}
		default:
			// For all other locations, check for conflicts normally
			if wornLocations[location] {
				return &CommandResponse{
					RequestID: cmd.ID,
					Success:   false,
					Error:     fmt.Errorf("you're already wearing something on your %s", location),
					Timestamp: time.Now(),
				}
			}
			finalWearLocations = append(finalWearLocations, location)
		}
	}

	// If item is from a hand, remove it from that hand and add to inventory
	if fromHand != "" {
		character.mutex.Lock()

		// Check if the inventory slot is already occupied
		slotKey := itemToWear.id.String()
		if existingItem, exists := character.inventory[slotKey]; exists && existingItem != nil {
			character.mutex.Unlock()
			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error:     fmt.Errorf("this item is already in your inventory"),
				Timestamp: time.Now(),
			}
		}

		// Safe to proceed - remove from hand and add to inventory
		if fromHand == "right" {
			character.rightHand = nil
		} else {
			character.leftHand = nil
		}

		// Add to inventory using the item's ID as the slot
		character.inventory[slotKey] = itemToWear
		character.mutex.Unlock()
	}

	// Update the item's state with proper mutex protection
	itemToWear.mutex.Lock()
	itemToWear.wornOn = finalWearLocations
	itemToWear.isWorn = true

	// Create success message while we still have the lock
	wearLocations := strings.Join(itemToWear.wornOn, " and ")
	message := fmt.Sprintf("\n\rYou wear %s on your %s.\n\r", itemToWear.name, wearLocations)

	itemToWear.mutex.Unlock()

	// Notify the room
	if character.room != nil {
		SendRoomMessage(character.room,
			fmt.Sprintf("\n\r%s wears %s.\n\r", character.name, itemToWear.name),
			character)
	}

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   message,
		Timestamp: time.Now(),
	}
}

// handleRemoveCommand processes the remove/unwear command
func handleRemoveCommand(cmd *CommandRequest, targetName string) *CommandResponse {
	if cmd == nil {
		return &CommandResponse{
			Success:   false,
			Error:     fmt.Errorf("invalid command request"),
			Timestamp: time.Now(),
		}
	}

	character := cmd.Character
	if character == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid character state"),
			Timestamp: time.Now(),
		}
	}

	character.mutex.Lock()
	var itemToRemove *Item

	if character.inventory != nil {
		for _, item := range character.inventory {
			if item == nil {
				continue
			}

			// Safely check item state with mutex
			item.mutex.RLock()
			isWorn := item.isWorn
			name := item.name
			item.mutex.RUnlock()

			if isWorn && MatchesTarget(name, targetName) {
				itemToRemove = item
				break
			}
		}
	}

	// Check if item exists
	if itemToRemove == nil {
		character.mutex.Unlock()
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you're not wearing that"),
			Timestamp: time.Now(),
		}
	}

	// Check if we have a free hand to put the item in
	var targetHand string
	if character.rightHand == nil {
		targetHand = "right"
	} else if character.leftHand == nil {
		targetHand = "left"
	} else {
		// Both hands are full, cannot remove
		character.mutex.Unlock()
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("your hands are full"),
			Timestamp: time.Now(),
		}
	}

	// Find which slot the item is in
	var itemSlot string
	for slot, item := range character.inventory {
		if item == itemToRemove {
			itemSlot = slot
			break
		}
	}

	// Move item to hand
	if targetHand == "right" {
		character.rightHand = itemToRemove
	} else {
		character.leftHand = itemToRemove
	}

	// Remove from inventory slot
	if itemSlot != "" {
		delete(character.inventory, itemSlot)
	}

	// Mark item as not worn (with proper mutex protection)
	itemToRemove.mutex.Lock()
	itemToRemove.isWorn = false
	itemName := itemToRemove.name
	itemToRemove.mutex.Unlock()

	// Unlock character before trait modifications
	character.mutex.Unlock()

	// Create success message
	handName := "right hand"
	if targetHand == "left" {
		handName = "left hand"
	}
	message := fmt.Sprintf("\n\rYou remove %s and hold it in your %s.\n\r", itemName, handName)

	// Notify the room
	if character.room != nil {
		SendRoomMessage(character.room,
			fmt.Sprintf("\n\r%s removes %s.\n\r", character.name, itemToRemove.name),
			character)
	}

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   message,
		Timestamp: time.Now(),
	}
}

// handleSwitchCommand processes the switch hands command
func handleSwitchCommand(cmd *CommandRequest, targetName string) *CommandResponse {
	if cmd == nil {
		return &CommandResponse{
			Success:   false,
			Error:     fmt.Errorf("invalid command request"),
			Timestamp: time.Now(),
		}
	}

	character := cmd.Character
	if character == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid character state"),
			Timestamp: time.Now(),
		}
	}

	// Check if the user provided an argument
	if targetName != "" {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("usage: switch (no arguments needed)"),
			Timestamp: time.Now(),
		}
	}

	// Lock the character to check and modify hand contents
	character.mutex.Lock()

	// Check if both hands are empty
	if character.rightHand == nil && character.leftHand == nil {
		character.mutex.Unlock()
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("your hands are empty"),
			Timestamp: time.Now(),
		}
	}

	// Get references to items before switching
	rightItem := character.rightHand
	leftItem := character.leftHand

	// Perform the switch
	character.rightHand = leftItem
	character.leftHand = rightItem

	character.mutex.Unlock()

	// Create appropriate success message based on what was switched
	var message string
	if rightItem != nil && leftItem != nil {
		// Both hands had items
		message = fmt.Sprintf("\n\rYou switch %s to your right hand and %s to your left hand.\n\r",
			leftItem.name, rightItem.name)
	} else if rightItem != nil {
		// Only right hand had an item
		message = fmt.Sprintf("\n\rYou switch %s to your left hand.\n\r", rightItem.name)
	} else {
		// Only left hand had an item
		message = fmt.Sprintf("\n\rYou switch %s to your right hand.\n\r", leftItem.name)
	}

	// Notify the room
	if character.room != nil {
		SendRoomMessage(character.room,
			fmt.Sprintf("\n\r%s switches the items in their hands.\n\r", character.name),
			character)
	}

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   message,
		Timestamp: time.Now(),
	}
}
