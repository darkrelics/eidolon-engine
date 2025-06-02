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

// Stealth system constants
const (
	hideBaseDifficulty = 4                // Base difficulty for hide attempts
	hideActionTime     = 3 * time.Second  // Time blocked after hide attempt
	hideRateLimit      = 10 * time.Second // Cooldown between hide attempts
	sneakActionTime    = 5 * time.Second  // Time blocked after sneak attempt
	searchActionTime   = 3 * time.Second  // Time blocked after search attempt
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

	// Try script commands first if room has an active script
	Logger.Info("Room script state check", "roomID", r.roomID, "scriptID", r.scriptID, "scriptActive", r.scriptActive, "scriptMgrNil", ScriptMgr == nil)

	if r.scriptID != "" && r.scriptActive && ScriptMgr != nil {
		Logger.Info("Attempting script command execution", "roomID", r.roomID, "scriptID", r.scriptID, "command", cmd.Verb)
		handled, err := ScriptMgr.ExecuteRoomCommand(r, cmd)
		if err != nil {
			Logger.Error("Script command execution error", "error", err, "roomID", r.roomID, "command", cmd.Verb)
		}
		Logger.Info("Script command result", "roomID", r.roomID, "command", cmd.Verb, "handled", handled)
		if handled {
			response.Success = true
			return response
		}
	} else {
		Logger.Info("Script conditions not met for command", "roomID", r.roomID, "command", cmd.Verb)
	}

	// Try to handle common room commands
	verb := strings.ToLower(cmd.Verb)

	// Movement commands
	if verb == "go" || verb == "move" {
		return handleMovementCommand(cmd, game)
	}

	// Item commands
	if verb == "get" || verb == "take" || verb == "drop" || verb == "put" || verb == "wear" || verb == "equip" || verb == "remove" || verb == "switch" {
		return handleItemCommand(cmd)
	}

	// Communication commands
	if verb == "say" || verb == "\"" || verb == "'" {
		return handleSayCommand(cmd)
	}

	// Stealth commands
	if verb == "hide" {
		return handleHideCommand(cmd, r)
	}
	if verb == "sneak" {
		return handleSneakCommand(cmd, game)
	}
	if verb == "search" {
		return handleSearchCommand(cmd, r)
	}
	if verb == "point" {
		return handlePointCommand(cmd, r)
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
			Success:   true,
			Message:   "\n\rWhat do you want to say?\n\r",
			Timestamp: time.Now(),
		}
	}

	// Join all arguments after the command to form the message
	message := strings.Join(cmd.Args[1:], " ")

	// Message for the speaker
	speakerMessage := fmt.Sprintf("\n\rYou say '%s'\n\r", message)

	// Message for others in the room - depends on whether speaker is hidden
	var roomMessage string
	if character.IsHidden() {
		roomMessage = fmt.Sprintf("\n\rYou hear a voice say '%s'\n\r", message)
	} else {
		roomMessage = fmt.Sprintf("\n\r%s says '%s'\n\r", character.name, message)
	}

	// Send message to everyone else in the room
	SendRoomMessage(character.room, roomMessage, character)

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
			Success:   true,
			Message:   fmt.Sprintf("\n\rWhat do you want to %s?\n\r", cmd.Verb),
			Timestamp: time.Now(),
		}
	}

	// Reveal character if hidden - item actions break stealth
	character := cmd.Character
	if character != nil && character.IsHidden() {
		character.SetHidden(false)
		character.playerCommandOut <- "\n\rYou reveal yourself as you interact with items.\n\r"

		if character.room != nil {
			SendRoomMessage(character.room,
				fmt.Sprintf("\n\r%s suddenly appears!\n\r", character.name),
				character,
			)
		}
	}

	targetName := strings.ToLower(strings.Join(cmd.Args[1:], " "))

	// Strip common articles and possessives
	targetName = stripArticles(targetName)

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
	case "wear":
		return handleWearCommand(cmd, targetName)
	case "remove":
		return handleRemoveCommand(cmd, targetName)
	case "switch":
		return handleSwitchCommand(cmd, targetName)
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
		if targetMatch.slot == "right_hand" {
			character.rightHand = nil
		} else if targetMatch.slot == "left_hand" {
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
		if targetMatch.slot == "right_hand" {
			character.rightHand = nil
		} else if targetMatch.slot == "left_hand" {
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

// restoreItemToOriginalLocation restores an item to its original location (hand or inventory)
func restoreItemToOriginalLocation(character *Character, item *Item, slot string, isInHand bool) {
	character.mutex.Lock()
	defer character.mutex.Unlock()

	if isInHand {
		if slot == "right_hand" {
			character.rightHand = item
		} else if slot == "left_hand" {
			character.leftHand = item
		}
	} else {
		character.inventory[slot] = item
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

	// If this is not a sneak command and character is hidden, reveal them
	if cmd.Verb != "sneak" && character.IsHidden() {
		character.SetHidden(false)
		character.playerCommandOut <- "\n\rYou reveal yourself as you move.\n\r"

		if character.room != nil {
			SendRoomMessage(character.room,
				fmt.Sprintf("\n\r%s suddenly appears!\n\r", character.name),
				character,
			)
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
	direction := strings.ToLower(strings.Join(cmd.Args[1:], " "))
	Logger.Debug("Player attempting to move", "characterName", character.name, "direction", direction)

	// Parse ordinal from direction
	position, exitName, hasOrdinal := ParseTargetWithOrdinal(direction)

	// Look for matching exits
	room.mutex.RLock()
	var matchingExits []*Exit

	for _, exit := range room.exits {
		if exit != nil && MatchesTarget(exit.direction, exitName) {
			matchingExits = append(matchingExits, exit)
		}
	}
	room.mutex.RUnlock()

	// Check if we found any matches
	if len(matchingExits) == 0 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you cannot go that way"),
			Timestamp: time.Now(),
		}
	}

	// If multiple matches and no ordinal specified, inform the player
	if len(matchingExits) > 1 && !hasOrdinal {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error: fmt.Errorf("which way? There are %d exits %s. Try 'go first %s' or 'go second %s'",
				len(matchingExits), exitName, exitName, exitName),
			Timestamp: time.Now(),
		}
	}

	// Check if position is valid
	if position > len(matchingExits) {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("there aren't that many exits %s", exitName),
			Timestamp: time.Now(),
		}
	}

	// Get the specific exit (position is 1-based)
	targetExit := matchingExits[position-1]

	// Check if target room exists and load it if necessary
	targetRoom := targetExit.targetRoom

	// Check if we have a room reference but it's not running (stale reference)
	if targetRoom != nil && !targetRoom.running {
		Logger.Debug("Exit has stale room reference, clearing it",
			"exitID", targetExit.exitID,
			"targetRoomID", targetExit.targetRoomID)
		targetRoom = nil
		targetExit.targetRoom = nil
	}

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
		targetRoom.WaitReady()
	}

	// Get references before the move
	oldRoom := room
	newRoom := targetRoom

	Logger.Info("Character moving between rooms",
		"characterName", character.name,
		"fromRoom", oldRoom.roomID,
		"toRoom", newRoom.roomID,
		"direction", direction)

	// Prepare departure message - only if visible
	var departureMsg string
	if !character.IsHidden() {
		departureMsg = fmt.Sprintf("%s leaves %s.", character.name, direction)
	}

	// Perform room transitions atomically to prevent deadlocks
	// Lock in consistent order: oldRoom, newRoom, then character
	Logger.Debug("Acquiring room locks for movement", "oldRoomID", oldRoom.roomID, "newRoomID", newRoom.roomID)
	if oldRoom.roomID < newRoom.roomID {
		oldRoom.mutex.Lock()
		newRoom.mutex.Lock()
	} else if oldRoom.roomID > newRoom.roomID {
		newRoom.mutex.Lock()
		oldRoom.mutex.Lock()
	} else {
		// Same room (shouldn't happen, but handle gracefully)
		oldRoom.mutex.Lock()
	}
	Logger.Debug("Room locks acquired", "oldRoomID", oldRoom.roomID, "newRoomID", newRoom.roomID)

	// Remove from old room
	delete(oldRoom.characters, character.id)
	oldRoom.lastActive = time.Now()

	// Add to new room
	newRoom.characters[character.id] = character
	newRoom.lastActive = time.Now()
	newRoom.idleCounter = 0

	// If room has a script ID, activate scripts
	if newRoom.persistent && newRoom.scriptID != "" && !newRoom.scriptActive {
		newRoom.scriptActive = true
		Logger.Info("Activating scripts for persistent room with character entry", "roomID", newRoom.roomID)
	}

	// Store script execution info before unlocking
	oldRoomHasScript := oldRoom.scriptID != "" && oldRoom.scriptActive && ScriptMgr != nil
	newRoomHasScript := newRoom.scriptID != "" && newRoom.scriptActive && ScriptMgr != nil

	// Unlock rooms before executing scripts to avoid deadlock
	if oldRoom.roomID != newRoom.roomID {
		oldRoom.mutex.Unlock()
		newRoom.mutex.Unlock()
	} else {
		oldRoom.mutex.Unlock()
	}
	Logger.Debug("Room locks released", "oldRoomID", oldRoom.roomID, "newRoomID", newRoom.roomID)

	// Now execute scripts without holding locks
	// Trigger onCharacterLeave event for old room scripts
	if oldRoomHasScript {
		Logger.Debug("Executing onCharacterLeave event", "roomID", oldRoom.roomID, "character", character.name)
		if err := ScriptMgr.ExecuteRoomEvent(oldRoom, "onCharacterLeave", character); err != nil {
			Logger.Error("Error executing onCharacterLeave", "roomID", oldRoom.roomID, "error", err)
		}
		Logger.Debug("Completed onCharacterLeave event", "roomID", oldRoom.roomID, "character", character.name)
	}

	// Send departure message to remaining characters (only if visible)
	if departureMsg != "" {
		SendRoomMessage(oldRoom, departureMsg, character)
	}

	// Update character's room reference
	character.mutex.Lock()
	character.room = newRoom
	character.mutex.Unlock()

	// Send arrival message using the exit's arrival text (only if visible)
	if !character.IsHidden() {
		arrivalMsg := fmt.Sprintf("%s %s.", character.name, targetExit.arrivalText)
		SendRoomMessage(newRoom, arrivalMsg, character)
	}

	// Get the room description for the character
	description := newRoom.GetDescription(character)

	// Trigger onCharacterEnter event for new room scripts AFTER description is prepared
	// We'll send it asynchronously after a brief delay to ensure the room description reaches the player first
	if newRoomHasScript {
		go func() {
			// Brief delay to ensure room description is processed first
			time.Sleep(100 * time.Millisecond)
			Logger.Debug("Executing onCharacterEnter event", "roomID", newRoom.roomID, "character", character.name)
			if err := ScriptMgr.ExecuteRoomEvent(newRoom, "onCharacterEnter", character); err != nil {
				Logger.Error("Error executing onCharacterEnter during movement", "roomID", newRoom.roomID, "error", err)
			}
			Logger.Debug("Completed onCharacterEnter event", "roomID", newRoom.roomID, "character", character.name)
		}()
	}

	Logger.Debug("Movement command completed successfully",
		"characterName", character.name,
		"fromRoom", oldRoom.roomID,
		"toRoom", newRoom.roomID)

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   description,
		Timestamp: time.Now(),
	}
}

// stripArticles removes common articles and possessives from the beginning of a string
func stripArticles(input string) string {
	// List of common articles and possessives to strip
	prefixes := []string{"the ", "a ", "an ", "my ", "your ", "his ", "her ", "its ", "their ", "our "}

	// Check each prefix and remove it if found
	for _, prefix := range prefixes {
		if strings.HasPrefix(input, prefix) {
			return strings.TrimPrefix(input, prefix)
		}
	}

	return input
}

// handleHideCommand processes the hide command
func handleHideCommand(cmd *CommandRequest, room *Room) *CommandResponse {
	character := cmd.Character
	if character == nil || room == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid character or room state"),
			Timestamp: time.Now(),
		}
	}

	// Verify character is actually in this room
	if character.room != room {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("character room mismatch"),
			Timestamp: time.Now(),
		}
	}

	// Rate limiting: 10-second cooldown prevents hide spam
	character.mutex.RLock()
	timeSinceLastHide := time.Since(character.lastHideAttempt)
	character.mutex.RUnlock()

	if timeSinceLastHide < hideRateLimit {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you must wait before attempting to hide again"),
			Timestamp: time.Now(),
		}
	}

	character.SetCommandWaitTime(hideActionTime)

	character.mutex.Lock()
	character.lastHideAttempt = time.Now()
	character.mutex.Unlock()

	if character.IsHidden() {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you are already hidden"),
			Timestamp: time.Now(),
		}
	}

	outcome := ResolveStaticCheckWithXP(character, "stealth", "agility", hideBaseDifficulty)

	if !outcome.Success {
		message := "\n\rYou attempt to hide but fail to find adequate concealment.\n\r"

		SendRoomMessage(room,
			fmt.Sprintf("\n\r%s attempts to hide but remains visible.\n\r", character.name),
			character,
		)

		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   true, // Command executed successfully, even if hiding failed
			Message:   message,
			Timestamp: time.Now(),
		}
	}

	character.SetHidden(true)
	message := "\n\rYou slip into the shadows and hide.\n\r"

	// Detection phase: observers immediately attempt to spot the hiding character
	room.mutex.RLock()
	observers := make([]*Character, 0, len(room.characters))
	for _, observer := range room.characters {
		if observer != nil && observer != character {
			observers = append(observers, observer)
		}
	}
	room.mutex.RUnlock()

	// Check if each observer detects the hidden character
	// Use atomic detection to prevent race conditions
	var detectedBy []*Character
	var detectionMessages []string

	for _, observer := range observers {
		if observer == nil || observer.player == nil {
			continue // Skip invalid observers
		}

		// Re-verify character is still hidden before each check
		if !character.IsHidden() {
			break // Character already revealed by previous detection
		}

		// Perception & Investigation vs Stealth & Agility
		detectOutcome := ResolveOpposedCheckWithXP(
			observer, character,
			"investigation", "perception",
			"stealth", "agility",
		)

		if detectOutcome.Success {
			detectedBy = append(detectedBy, observer)
			detectionMessages = append(detectionMessages,
				fmt.Sprintf("\n\rYou notice %s trying to hide.\n\r", character.name))
		}
	}

	// If detected by anyone, reveal immediately with proper coordination
	if len(detectedBy) > 0 && character.IsHidden() {
		character.SetHidden(false)
		message = "\n\rYou attempt to hide but are spotted!\n\r"

		// Send detection messages only to those who detected
		for i, detector := range detectedBy {
			if i < len(detectionMessages) && detector.player != nil {
				SafeSendString(detector.player.commandOut, detectionMessages[i], detector.name)
			}
		}

		// Notify others that someone was discovered (without details)
		for _, observer := range observers {
			if observer == nil || observer.player == nil {
				continue
			}
			wasDetector := false
			for _, detector := range detectedBy {
				if observer == detector {
					wasDetector = true
					break
				}
			}
			if !wasDetector {
				SafeSendString(observer.player.commandOut, "\n\rSomeone notices movement in the shadows.\n\r", observer.name)
			}
		}
	}

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   message,
		Timestamp: time.Now(),
	}
}

// handleSneakCommand processes the sneak command for hidden movement
func handleSneakCommand(cmd *CommandRequest, game *Game) *CommandResponse {
	character := cmd.Character
	if character == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid character state"),
			Timestamp: time.Now(),
		}
	}

	if !character.IsHidden() {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   true,
			Message:   "\n\rYou must be hidden to sneak.\n\r",
			Timestamp: time.Now(),
		}
	}

	outcome := ResolveStaticCheckWithXP(character, "stealth", "agility", hideBaseDifficulty)

	if !outcome.Success {
		character.SetHidden(false)
		character.SetCommandWaitTime(hideActionTime)

		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   true,
			Message:   "\n\rYou stumble and reveal yourself.\n\r",
			Timestamp: time.Now(),
		}
	}

	// Store original verb and use movement handler
	originalVerb := cmd.Verb
	cmd.Verb = "sneak" // Keep as sneak so movement handler knows not to reveal
	moveResponse := handleMovementCommand(cmd, game)
	cmd.Verb = originalVerb // Restore original verb

	if !moveResponse.Success {
		// Movement failed, remain hidden
		return moveResponse
	}

	// Movement succeeded, character remains hidden
	// Perform detection checks in the new room
	newRoom := character.room
	newRoom.mutex.RLock()
	observers := make([]*Character, 0, len(newRoom.characters))
	for _, observer := range newRoom.characters {
		if observer != nil && observer != character {
			observers = append(observers, observer)
		}
	}
	newRoom.mutex.RUnlock()

	// Check if each observer detects the hidden character
	for _, observer := range observers {
		// Perception & Investigation vs Stealth & Agility
		detectOutcome := ResolveOpposedCheckWithXP(
			observer, character,
			"investigation", "perception",
			"stealth", "agility",
		)

		if detectOutcome.Success {
			character.SetHidden(false)
			SafeSendString(observer.player.commandOut, fmt.Sprintf("\n\rYou spot %s sneaking in!\n\r", character.name), observer.name)

			// Notify others
			SendRoomMessage(newRoom,
				fmt.Sprintf("\n\r%s points out %s who was sneaking in.\n\r", observer.name, character.name),
				observer,
			)
			break
		}
	}

	character.SetCommandWaitTime(sneakActionTime)

	return moveResponse
}

// handleSearchCommand processes the search command to find hidden characters
func handleSearchCommand(cmd *CommandRequest, room *Room) *CommandResponse {
	character := cmd.Character
	if character == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid character state"),
			Timestamp: time.Now(),
		}
	}

	character.SetCommandWaitTime(hideActionTime)

	// Find all hidden characters in the room
	room.mutex.RLock()
	var hiddenCharacters []*Character
	for _, other := range room.characters {
		if other != nil && other != character && other.IsHidden() {
			hiddenCharacters = append(hiddenCharacters, other)
		}
	}
	room.mutex.RUnlock()

	if len(hiddenCharacters) == 0 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   true,
			Message:   "\n\rYou search carefully but find no one hiding.\n\r",
			Timestamp: time.Now(),
		}
	}

	// Announce the search
	SafeSendString(character.player.commandOut, "\n\rYou begin searching for hidden characters...\n\r", character.name)
	SendRoomMessage(room,
		fmt.Sprintf("\n\r%s begins searching the area carefully.\n\r", character.name),
		character,
	)

	// Check against each hidden character - find only one per search
	var foundAny bool
	var foundCharacter *Character

	for _, hidden := range hiddenCharacters {
		if hidden == nil || hidden.player == nil {
			continue
		}

		// Perception & Investigation vs Stealth & Agility
		detectOutcome := ResolveOpposedCheckWithXP(
			character, hidden,
			"investigation", "perception",
			"stealth", "agility",
		)

		if detectOutcome.Success {
			foundAny = true
			foundCharacter = hidden
			break // Only find one character per search attempt
		}
	}

	// Process the discovery if any character was found
	if foundAny && foundCharacter != nil {
		foundCharacter.SetHidden(false)

		SafeSendString(character.player.commandOut, fmt.Sprintf("\n\rYou discover %s hiding!\n\r", foundCharacter.name), character.name)
		SafeSendString(foundCharacter.player.commandOut, fmt.Sprintf("\n\r%s discovers your hiding place!\n\r", character.name), foundCharacter.name)

		// Notify others
		SendRoomMessage(room,
			fmt.Sprintf("\n\r%s discovers %s hiding!\n\r", character.name, foundCharacter.name),
			character,
		)
	}

	if !foundAny {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   true,
			Message:   "\n\rYour search reveals nothing.\n\r",
			Timestamp: time.Now(),
		}
	}

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   "", // Messages already sent
		Timestamp: time.Now(),
	}
}

// handlePointCommand processes the point command to reveal a hidden character
func handlePointCommand(cmd *CommandRequest, room *Room) *CommandResponse {
	character := cmd.Character
	if character == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid character state"),
			Timestamp: time.Now(),
		}
	}

	// Check if target was specified
	if len(cmd.Args) < 2 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("point at whom?"),
			Timestamp: time.Now(),
		}
	}

	targetName := strings.ToLower(strings.Join(cmd.Args[1:], " "))

	// Find the target character
	room.mutex.RLock()
	var target *Character
	for _, other := range room.characters {
		if other != nil && other != character && MatchesTarget(other.name, targetName) {
			target = other
			break
		}
	}
	room.mutex.RUnlock()

	if target == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you don't see anyone by that name here"),
			Timestamp: time.Now(),
		}
	}

	// Check if the character can see the target
	if target.IsHidden() && !character.IsHidden() {
		// Perform detection check first
		detectOutcome := ResolveOpposedCheckWithXP(
			character, target,
			"investigation", "perception",
			"stealth", "agility",
		)

		if !detectOutcome.Success {
			return &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error:     fmt.Errorf("you don't see anyone by that name here"),
				Timestamp: time.Now(),
			}
		}
	}

	// If target is hidden, reveal them
	if target.IsHidden() {
		target.SetHidden(false)

		SafeSendString(character.player.commandOut, fmt.Sprintf("\n\rYou point at %s, revealing their location!\n\r", target.name), character.name)
		SafeSendString(target.player.commandOut, fmt.Sprintf("\n\r%s points at you, revealing your location!\n\r", character.name), target.name)

		SendRoomMessage(room,
			fmt.Sprintf("\n\r%s points at %s, revealing their location!\n\r", character.name, target.name),
			character,
		)
	} else {
		// Target is not hidden, just point normally
		SafeSendString(character.player.commandOut, fmt.Sprintf("\n\rYou point at %s.\n\r", target.name), character.name)
		SafeSendString(target.player.commandOut, fmt.Sprintf("\n\r%s points at you.\n\r", character.name), target.name)

		SendRoomMessage(room,
			fmt.Sprintf("\n\r%s points at %s.\n\r", character.name, target.name),
			character,
		)
	}

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   "", // Messages already sent
		Timestamp: time.Now(),
	}
}
