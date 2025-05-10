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
	// This is a placeholder. Real implementation would handle items
	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   false,
		Error:     fmt.Errorf("item commands are not implemented yet"),
		Timestamp: time.Now(),
	}
}
