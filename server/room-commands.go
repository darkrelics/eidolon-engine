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
)

// Room command messages
const (
	msgNoExits     = "There are no visible exits."
	msgNoDirection = "Which direction do you want to go?"
	msgCantEscape  = "You can't escape!"
	msgInvalidDir  = "You cannot go that way."
	msgPathNowhere = "The path leads nowhere."
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
		character.DisplayMessage("You reveal yourself as you interact with items.")

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
