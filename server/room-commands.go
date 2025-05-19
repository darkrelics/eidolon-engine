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
	"fmt"
	"strings"
	"time"

	"github.com/gofrs/uuid/v5"
)

// Room command messages
const (
	msgNoExits     = "There are no visible exits.\n\r"
	msgNoDirection = "\n\rWhich direction do you want to go?\n\r"
	msgCantEscape  = "\n\rYou can't escape!\n\r"
	msgInvalidDir  = "\n\rYou cannot go that way.\n\r"
	msgPathNowhere = "\n\rThe path leads nowhere.\n\r"
)

// processRoomCommand handles commands at the room level
func (r *Room) ProcessRoomCommand(cmd *CommandRequest, game *Game) *CommandResponse {
	if cmd == nil {
		Logger.Error("Received nil command in room", "roomID", r.roomID)
		return &CommandResponse{
			Success:   false,
			Error:     fmt.Errorf("invalid command"),
			Timestamp: time.Now(),
		}
	}

	Logger.Debug("Processing room command",
		"roomID", r.roomID,
		"verb", cmd.Verb,
		"character", cmd.Character.name)

	// Create default response
	response := &CommandResponse{
		RequestID: cmd.ID,
		Success:   false,
		Timestamp: time.Now(),
	}

	// Process command based on verb
	switch strings.ToLower(cmd.Verb) {
	case "say", "\"", "'": // Handle speech commands
		return handleSayCommand(cmd)

	case "look", "l": // Handle look command (additional room-based look processing)
		// This is typically handled at the character level, but might have room-level effects
		response.Success = true
		// No message/error for success since character handler already showed the room
		return response

	case "get", "take", "drop", "put": // Handle item commands
		return handleItemCommand(cmd)

	default:
		// Unknown command at room level
		Logger.Warn("Unhandled room command", "verb", cmd.Verb, "roomID", r.roomID)
		response.Error = fmt.Errorf("unknown room command: %s", cmd.Verb)
		return response
	}
}

// handleSayCommand processes say/talk commands
func handleSayCommand(cmd *CommandRequest) *CommandResponse {
	// This is a placeholder. Real implementation would handle speech
	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   false,
		Error:     fmt.Errorf("say command not implemented yet"),
		Timestamp: time.Now(),
	}
}

// handleItemCommand processes item-related commands like get, take, drop, etc.
func handleItemCommand(cmd *CommandRequest) *CommandResponse {
	if len(cmd.Args) < 2 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("what do you want to %s?", cmd.Verb),
			Timestamp: time.Now(),
		}
	}

	targetName := strings.ToLower(strings.Join(cmd.Args[1:], " "))

	switch cmd.Verb {
	case "get", "take":
		return handleGetCommand(cmd, targetName)
	case "drop":
		return handleDropCommand(cmd, targetName)
	case "wear", "wield", "equip":
		return handleWearCommand(cmd, targetName)
	case "remove", "unwear", "unequip":
		return handleRemoveCommand(cmd, targetName)
	default:
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid item command: %s", cmd.Verb),
			Timestamp: time.Now(),
		}
	}
}

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

	// Acquire room lock to search for the item
	room.mutex.Lock()
	defer room.mutex.Unlock()

	// Find the item in the room
	var targetItem *Item
	var targetItemID uuid.UUID

	for id, item := range room.items {
		if item != nil && strings.Contains(strings.ToLower(item.name), targetName) {
			if !item.canPickUp {
				return &CommandResponse{
					RequestID: cmd.ID,
					Success:   false,
					Error:     fmt.Errorf("you cannot pick that up"),
					Timestamp: time.Now(),
				}
			}
			targetItem = item
			targetItemID = id
			break
		}
	}

	if targetItem == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you don't see that here"),
			Timestamp: time.Now(),
		}
	}

	// Remove from room
	delete(room.items, targetItemID)

	// Add to character's inventory
	character.mutex.Lock()
	slotName := targetItem.name // Use the item name as the slot name
	character.inventory[slotName] = targetItem
	character.mutex.Unlock()

	// Create success message
	message := fmt.Sprintf("\n\rYou pick up %s.\n\r", targetItem.name)

	// Notify the room
	SendRoomMessageExcept(room, fmt.Sprintf("\n\r%s picks up %s.\n\r", character.name, targetItem.name), character)

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

	// Find the item in the character's inventory
	character.mutex.Lock()
	var itemToRemove *Item
	var slotToRemove string

	for slot, item := range character.inventory {
		if item != nil && strings.Contains(strings.ToLower(item.name), targetName) {
			if item.isWorn {
				character.mutex.Unlock()
				return &CommandResponse{
					RequestID: cmd.ID,
					Success:   false,
					Error:     fmt.Errorf("you need to remove that first"),
					Timestamp: time.Now(),
				}
			}
			itemToRemove = item
			slotToRemove = slot
			break
		}
	}

	if itemToRemove == nil {
		character.mutex.Unlock()
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you don't have that"),
			Timestamp: time.Now(),
		}
	}

	// Remove from inventory
	delete(character.inventory, slotToRemove)
	character.mutex.Unlock()

	// Add to room
	room.mutex.Lock()
	room.items[itemToRemove.id] = itemToRemove
	room.mutex.Unlock()

	// Create success message
	message := fmt.Sprintf("\n\rYou drop %s.\n\r", itemToRemove.name)

	// Notify the room
	SendRoomMessageExcept(room, fmt.Sprintf("\n\r%s drops %s.\n\r", character.name, itemToRemove.name), character)

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   message,
		Timestamp: time.Now(),
	}
}

// handleWearCommand processes the wear/equip command
func handleWearCommand(cmd *CommandRequest, targetName string) *CommandResponse {
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

	// Find the item in the character's inventory
	character.mutex.Lock()
	defer character.mutex.Unlock()

	var itemToWear *Item

	for _, item := range character.inventory {
		if item != nil && strings.Contains(strings.ToLower(item.name), targetName) {
			itemToWear = item
			break
		}
	}

	// Check if item exists
	if itemToWear == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you don't have that"),
			Timestamp: time.Now(),
		}
	}

	// Check if item is already worn
	if itemToWear.isWorn {
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
	// Build a map of worn locations
	wornLocations := make(map[string]bool)
	for _, item := range character.inventory {
		if item != nil && item.isWorn {
			for _, loc := range item.wornOn {
				wornLocations[loc] = true
			}
		}
	}

	// Check if any locations conflict
	for _, location := range itemToWear.wornOn {
		if wornLocations[location] {
			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error:     fmt.Errorf("you're already wearing something on your %s", location),
				Timestamp: time.Now(),
			}
		}
	}

	// Mark item as worn
	itemToWear.isWorn = true

	// Apply trait modifications
	if len(itemToWear.traitMods) > 0 {
		character.ApplyItemTraitMods(itemToWear)
	}

	// Create success message
	wearLocations := strings.Join(itemToWear.wornOn, " and ")
	message := fmt.Sprintf("\n\rYou wear %s on your %s.\n\r", itemToWear.name, wearLocations)

	// Notify the room
	if character.room != nil {
		SendRoomMessageExcept(character.room,
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

	// Find the item in the character's inventory
	character.mutex.Lock()
	defer character.mutex.Unlock()

	var itemToRemove *Item

	for _, item := range character.inventory {
		if item != nil && item.isWorn && strings.Contains(strings.ToLower(item.name), targetName) {
			itemToRemove = item
			break
		}
	}

	// Check if item exists
	if itemToRemove == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you're not wearing that"),
			Timestamp: time.Now(),
		}
	}

	// Mark item as not worn
	itemToRemove.isWorn = false

	// Remove trait modifications
	if len(itemToRemove.traitMods) > 0 {
		character.RemoveItemTraitMods(itemToRemove)
	}

	// Create success message
	message := fmt.Sprintf("\n\rYou remove %s.\n\r", itemToRemove.name)

	// Notify the room
	if character.room != nil {
		SendRoomMessageExcept(character.room,
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
