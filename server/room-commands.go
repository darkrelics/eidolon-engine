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

	// Try to handle common room commands
	verb := strings.ToLower(cmd.Verb)

	// Movement commands
	if verb == "go" || verb == "move" {
		return handleMovementCommand(cmd, game)
	}

	// Item commands
	if verb == "get" || verb == "take" || verb == "drop" || verb == "put" || verb == "wear" || verb == "wield" || verb == "equip" || verb == "remove" || verb == "unwear" || verb == "unequip" {
		return handleItemCommand(cmd)
	}

	// Communication commands
	if verb == "say" || verb == "\"" || verb == "'" {
		return handleSayCommand(cmd)
	}

	// Look command (room-level effects)
	if verb == "look" || verb == "l" {
		// This is typically handled at the character level, but might have room-level effects
		response.Success = true
		return response
	}

	// Unknown command at room level
	Logger.Debug("Room cannot handle command, will escalate", "verb", cmd.Verb, "roomID", r.roomID)
	response.Error = fmt.Errorf("unknown room command: %s", cmd.Verb)
	return response
}

// handleSayCommand processes say/talk commands
func handleSayCommand(cmd *CommandRequest) *CommandResponse {
	character := cmd.Character

	if character == nil || character.room == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid character or room state"),
			Timestamp: time.Now(),
		}
	}

	// Check if there's text to say
	if len(cmd.Args) < 2 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("what do you want to say?"),
			Timestamp: time.Now(),
		}
	}

	// Join all arguments after the command to form the message
	message := strings.Join(cmd.Args[1:], " ")

	// Message for the speaker
	speakerMessage := fmt.Sprintf("\n\rYou say '%s'\n\r", message)

	// Message for others in the room
	roomMessage := fmt.Sprintf("\n\r%s says '%s'\n\r", character.name, message)

	// Send message to everyone else in the room
	SendRoomMessageExcept(character.room, roomMessage, character)

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   speakerMessage,
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
		// Special handling for "take from" command
		if len(cmd.Args) >= 4 && strings.ToLower(cmd.Args[2]) == "from" {
			return handleTakeFromCommand(cmd)
		}
		return handleGetCommand(cmd, targetName)
	case "drop":
		return handleDropCommand(cmd, targetName)
	case "put":
		return handlePutCommand(cmd)
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

	character := cmd.Character
	if character == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid character state"),
			Timestamp: time.Now(),
		}
	}

	// Find the item in character's inventory
	character.mutex.Lock()
	var itemToPut *Item
	var itemSlot string
	
	for slot, item := range character.inventory {
		if item != nil && strings.Contains(strings.ToLower(item.name), itemName) {
			if item.isWorn {
				character.mutex.Unlock()
				return &CommandResponse{
					RequestID: cmd.ID,
					Success:   false,
					Error:     fmt.Errorf("you need to remove that first"),
					Timestamp: time.Now(),
				}
			}
			itemToPut = item
			itemSlot = slot
			break
		}
	}
	
	if itemToPut == nil {
		character.mutex.Unlock()
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you don't have that"),
			Timestamp: time.Now(),
		}
	}
	
	// Remove item from inventory before unlocking
	delete(character.inventory, itemSlot)
	character.mutex.Unlock()

	// Find the container
	var container *Item
	
	if isMyContainer {
		// Look in character's inventory
		character.mutex.RLock()
		for _, item := range character.inventory {
			if item != nil && strings.Contains(strings.ToLower(item.name), containerName) {
				container = item
				break
			}
		}
		character.mutex.RUnlock()
		
		if container == nil {
			// Put the item back in inventory
			character.mutex.Lock()
			character.inventory[itemSlot] = itemToPut
			character.mutex.Unlock()
			
			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error:     fmt.Errorf("you don't have a '%s'", containerName),
				Timestamp: time.Now(),
			}
		}
	} else {
		// Look in room
		if character.room == nil {
			// Put the item back in inventory
			character.mutex.Lock()
			character.inventory[itemSlot] = itemToPut
			character.mutex.Unlock()
			
			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error:     fmt.Errorf("invalid room state"),
				Timestamp: time.Now(),
			}
		}
		
		character.room.mutex.RLock()
		for _, item := range character.room.items {
			if item != nil && strings.Contains(strings.ToLower(item.name), containerName) {
				container = item
				break
			}
		}
		character.room.mutex.RUnlock()
		
		if container == nil {
			// Put the item back in inventory
			character.mutex.Lock()
			character.inventory[itemSlot] = itemToPut
			character.mutex.Unlock()
			
			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error:     fmt.Errorf("you don't see a '%s' here", containerName),
				Timestamp: time.Now(),
			}
		}
	}

	// Add item to container
	err := container.AddItemToContainer(itemToPut)
	if err != nil {
		// Put the item back in inventory
		character.mutex.Lock()
		character.inventory[itemSlot] = itemToPut
		character.mutex.Unlock()
		
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
		SendRoomMessageExcept(character.room,
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
	
	if isMyContainer {
		// Look in character's inventory
		character.mutex.RLock()
		for _, item := range character.inventory {
			if item != nil && strings.Contains(strings.ToLower(item.name), containerName) {
				container = item
				break
			}
		}
		character.mutex.RUnlock()
		
		if container == nil {
			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error:     fmt.Errorf("you don't have a '%s'", containerName),
				Timestamp: time.Now(),
			}
		}
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
			if item != nil && strings.Contains(strings.ToLower(item.name), containerName) {
				container = item
				break
			}
		}
		character.room.mutex.RUnlock()
		
		if container == nil {
			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error:     fmt.Errorf("you don't see a '%s' here", containerName),
				Timestamp: time.Now(),
			}
		}
	}

	// Find item in container
	itemToTake := container.FindItemInContainer(itemName)
	if itemToTake == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("there's no '%s' in the %s", itemName, container.name),
			Timestamp: time.Now(),
		}
	}

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

	// Add to character's inventory
	character.mutex.Lock()
	slotName := removedItem.name
	character.inventory[slotName] = removedItem
	character.mutex.Unlock()

	// Success message
	message := fmt.Sprintf("\n\rYou take %s from %s.\n\r", removedItem.name, container.name)
	
	// Notify room
	if character.room != nil {
		SendRoomMessageExcept(character.room,
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

	// Special handling for finger and wrist items - map to specific left/right locations
	var finalWearLocations []string
	for _, location := range itemToWear.wornOn {
		if location == "finger" {
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
		} else if location == "wrist" {
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
		} else {
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

	// Update the item's worn locations to the specific locations
	itemToWear.wornOn = finalWearLocations

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
			if item != nil && item.isWorn && strings.Contains(strings.ToLower(item.name), targetName) {
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

	// Mark item as not worn
	itemToRemove.isWorn = false

	// Remove trait modifications
	if len(itemToRemove.traitMods) > 0 {
		character.RemoveItemTraitMods(itemToRemove)
	}

	// Create success message
	message := fmt.Sprintf("\n\rYou remove %s.\n\r", itemToRemove.name)
	character.mutex.Unlock()

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

// handleMovementCommand processes movement commands (go/move)
func handleMovementCommand(cmd *CommandRequest, game *Game) *CommandResponse {
	character := cmd.Character

	if character == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid character"),
			Timestamp: time.Now(),
		}
	}

	room := character.room
	if room == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid room state"),
			Timestamp: time.Now(),
		}
	}

	// Check if character state allows movement
	if character.charState != "standing" {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you must be standing to move. You are currently %s", character.charState),
			Timestamp: time.Now(),
		}
	}

	// Check if a direction was provided
	if len(cmd.Args) < 2 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("which direction do you want to go?"),
			Timestamp: time.Now(),
		}
	}

	// Get the direction from the command
	direction := strings.ToLower(cmd.Args[1])
	Logger.Debug("Player attempting to move", "characterName", character.name, "direction", direction)

	// Look for matching exit
	room.mutex.RLock()
	var targetExit *Exit

	for _, exit := range room.exits {
		if exit != nil && strings.ToLower(exit.direction) == direction {
			targetExit = exit
			break
		}
	}
	room.mutex.RUnlock()

	// Check if exit exists
	if targetExit == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you cannot go that way"),
			Timestamp: time.Now(),
		}
	}

	// Check if target room exists and load it if necessary
	targetRoom := targetExit.targetRoom
	if targetRoom == nil {
		// Try to load the room using the target room ID
		loadedRoom, err := game.LoadRoom(targetExit.targetRoomID)
		if err != nil {
			Logger.Warn("Could not load target room for movement",
				"targetRoomID", targetExit.targetRoomID,
				"direction", direction,
				"characterName", character.name,
				"error", err)
			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error:     fmt.Errorf("the way is barred"),
				Timestamp: time.Now(),
			}
		}
		targetRoom = loadedRoom
		// Update the exit's room reference for future use
		targetExit.targetRoom = targetRoom
	}

	// Ensure target room is running
	if !targetRoom.running {
		targetRoom.Start(game)
	}

	// Get references before the move
	oldRoom := room
	newRoom := targetRoom

	Logger.Info("Character moving between rooms",
		"characterName", character.name,
		"fromRoom", oldRoom.roomID,
		"toRoom", newRoom.roomID,
		"direction", direction)

	// Prepare departure message
	departureMsg := fmt.Sprintf("%s leaves %s.", character.name, direction)

	// Remove character from current room and send departure message
	oldRoom.mutex.Lock()
	delete(oldRoom.characters, character.id)
	oldRoom.lastActive = time.Now()
	oldRoom.mutex.Unlock()

	// Send departure message to remaining characters
	SendRoomMessageExcept(oldRoom, departureMsg, character)

	// Update character's room reference
	character.mutex.Lock()
	character.room = newRoom
	character.mutex.Unlock()

	// Add character to new room and send arrival message
	newRoom.mutex.Lock()
	newRoom.characters[character.id] = character
	newRoom.lastActive = time.Now()
	newRoom.idleCounter = 0

	// If room has a script ID, activate scripts
	if newRoom.persistent && newRoom.scriptID != "" && !newRoom.scriptActive {
		newRoom.scriptActive = true
		Logger.Info("Activating scripts for persistent room with character entry", "roomID", newRoom.roomID)
	}
	newRoom.mutex.Unlock()

	// Send arrival message using the exit's arrival text
	arrivalMsg := fmt.Sprintf("%s %s.", character.name, targetExit.arrivalText)
	SendRoomMessageExcept(newRoom, arrivalMsg, character)

	// Get the room description for the character
	description := newRoom.GetDescription(character)

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   description,
		Timestamp: time.Now(),
	}
}
