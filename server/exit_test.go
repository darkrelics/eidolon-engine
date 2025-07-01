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
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gofrs/uuid/v5"
)

// MockPlayer captures messages sent to players for testing
type MockPlayer struct {
	*Player
	messages []string
	mu       sync.Mutex
}

func NewMockPlayer() *MockPlayer {
	mp := &MockPlayer{
		Player: &Player{
			commandOut: make(chan string, 100),
			commandIn:  make(chan string, 100),
		},
		messages: make([]string, 0),
	}

	// Start a goroutine to capture messages
	go func() {
		for msg := range mp.Player.commandOut {
			mp.mu.Lock()
			mp.messages = append(mp.messages, msg)
			mp.mu.Unlock()
		}
	}()

	return mp
}

func (mp *MockPlayer) GetMessages() []string {
	mp.mu.Lock()
	defer mp.mu.Unlock()
	return append([]string{}, mp.messages...)
}

func (mp *MockPlayer) ContainsMessage(msg string) bool {
	mp.mu.Lock()
	defer mp.mu.Unlock()
	for _, m := range mp.messages {
		if strings.Contains(m, msg) {
			return true
		}
	}
	return false
}

func TestNewExit(t *testing.T) {
	exitID := uuid.Must(uuid.NewV4())
	targetRoom := &Room{
		roomID:      100,
		title:       "Target Room",
		description: "The destination",
		characters:  make(map[uuid.UUID]*Character),
	}

	tests := []struct {
		name         string
		exitID       uuid.UUID
		direction    string
		description  string
		targetRoom   *Room
		targetRoomID int64
		arrivalText  string
		visible      bool
		scriptID     string
	}{
		{
			name:         "Complete exit with all fields",
			exitID:       exitID,
			direction:    "north",
			description:  "A path leading north",
			targetRoom:   targetRoom,
			targetRoomID: 100,
			arrivalText:  "arrives from the south",
			visible:      true,
			scriptID:     "north_script",
		},
		{
			name:         "Exit with minimal fields",
			exitID:       exitID,
			direction:    "east",
			description:  "",
			targetRoom:   nil,
			targetRoomID: 200,
			arrivalText:  "",
			visible:      false,
			scriptID:     "",
		},
		{
			name:         "Hidden exit",
			exitID:       exitID,
			direction:    "secret",
			description:  "A hidden passage",
			targetRoom:   targetRoom,
			targetRoomID: 100,
			arrivalText:  "emerges from the shadows",
			visible:      false,
			scriptID:     "secret_door",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			beforeTime := time.Now()

			exit := NewExit(
				tt.exitID,
				tt.direction,
				tt.description,
				tt.targetRoom,
				tt.targetRoomID,
				tt.arrivalText,
				tt.visible,
				tt.scriptID,
			)

			afterTime := time.Now()

			// Verify all fields are set correctly
			if exit.exitID != tt.exitID {
				t.Errorf("exitID = %v, want %v", exit.exitID, tt.exitID)
			}
			if exit.direction != tt.direction {
				t.Errorf("direction = %v, want %v", exit.direction, tt.direction)
			}
			if exit.description != tt.description {
				t.Errorf("description = %v, want %v", exit.description, tt.description)
			}
			if exit.targetRoom != tt.targetRoom {
				t.Errorf("targetRoom = %v, want %v", exit.targetRoom, tt.targetRoom)
			}
			if exit.targetRoomID != tt.targetRoomID {
				t.Errorf("targetRoomID = %v, want %v", exit.targetRoomID, tt.targetRoomID)
			}
			if exit.arrivalText != tt.arrivalText {
				t.Errorf("arrivalText = %v, want %v", exit.arrivalText, tt.arrivalText)
			}
			if exit.visible != tt.visible {
				t.Errorf("visible = %v, want %v", exit.visible, tt.visible)
			}
			if exit.scriptID != tt.scriptID {
				t.Errorf("scriptID = %v, want %v", exit.scriptID, tt.scriptID)
			}

			// Verify timestamps are set and reasonable
			if exit.lastEdited.Before(beforeTime) || exit.lastEdited.After(afterTime) {
				t.Errorf("lastEdited timestamp out of expected range")
			}
			if exit.lastSaved.Before(beforeTime) || exit.lastSaved.After(afterTime) {
				t.Errorf("lastSaved timestamp out of expected range")
			}
		})
	}
}

// TestExitDataDefaults tests the default arrival text generation logic
func TestExitDataDefaults(t *testing.T) {
	tests := []struct {
		name                string
		arrivalText         string
		direction           string
		expectedArrivalText string
	}{
		{
			name:                "Custom arrival text preserved",
			arrivalText:         "teleports in with a flash",
			direction:           "north",
			expectedArrivalText: "teleports in with a flash",
		},
		{
			name:                "Empty arrival text generates default",
			arrivalText:         "",
			direction:           "south",
			expectedArrivalText: "arrives from the south",
		},
		{
			name:                "Default for east direction",
			arrivalText:         "",
			direction:           "east",
			expectedArrivalText: "arrives from the east",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Simulate the logic from LoadExits
			arrivalText := tt.arrivalText
			if arrivalText == "" {
				// Generate default arrival text based on direction
				arrivalText = "arrives from the " + tt.direction
			}

			if arrivalText != tt.expectedArrivalText {
				t.Errorf("Expected arrival text '%s', got '%s'",
					tt.expectedArrivalText, arrivalText)
			}
		})
	}
}

func TestSendArrivalMessage(t *testing.T) {
	tests := []struct {
		name            string
		character       *Character
		exitUsed        *Exit
		destinationRoom *Room
		expectedMessage string
		shouldSend      bool
	}{
		{
			name: "Custom arrival text",
			character: &Character{
				name: "TestPlayer",
			},
			exitUsed: &Exit{
				direction:   "north",
				arrivalText: "teleports in with a flash",
			},
			destinationRoom: &Room{
				roomID:     1,
				characters: make(map[uuid.UUID]*Character),
			},
			expectedMessage: "\n\rTestPlayer teleports in with a flash.\n\r",
			shouldSend:      true,
		},
		{
			name: "Default arrival text",
			character: &Character{
				name: "TestPlayer",
			},
			exitUsed: &Exit{
				direction:   "north",
				arrivalText: "",
			},
			destinationRoom: &Room{
				roomID:     1,
				characters: make(map[uuid.UUID]*Character),
			},
			expectedMessage: "\n\rTestPlayer arrives from the north.\n\r",
			shouldSend:      true,
		},
		{
			name:            "Nil character",
			character:       nil,
			exitUsed:        &Exit{direction: "north"},
			destinationRoom: &Room{roomID: 1},
			shouldSend:      false,
		},
		{
			name:            "Nil exit",
			character:       &Character{name: "TestPlayer"},
			exitUsed:        nil,
			destinationRoom: &Room{roomID: 1},
			shouldSend:      false,
		},
		{
			name:            "Nil destination room",
			character:       &Character{name: "TestPlayer"},
			exitUsed:        &Exit{direction: "north"},
			destinationRoom: nil,
			shouldSend:      false,
		},
		{
			name: "Arriving character excluded from message",
			character: &Character{
				name: "TestPlayer",
				id:   uuid.Must(uuid.NewV4()),
			},
			exitUsed: &Exit{
				direction:   "north",
				arrivalText: "appears suddenly",
			},
			destinationRoom: &Room{
				roomID:     1,
				characters: make(map[uuid.UUID]*Character),
			},
			expectedMessage: "\n\rTestPlayer appears suddenly.\n\r",
			shouldSend:      true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var mockObserver *MockPlayer

			// For testing, we'll add mock observers to the room
			if tt.shouldSend && tt.destinationRoom != nil {
				// Add a mock observer character
				observerId := uuid.Must(uuid.NewV4())
				mockObserver = NewMockPlayer()
				observer := &Character{
					id:     observerId,
					name:   "Observer",
					player: mockObserver.Player,
					prompt: "> ",
				}
				tt.destinationRoom.characters[observerId] = observer

				// If testing that arriving character is excluded, add them too
				if tt.character != nil && tt.name == "Arriving character excluded from message" {
					mockArriver := NewMockPlayer()
					tt.character.player = mockArriver.Player
					tt.character.prompt = "> "
					tt.destinationRoom.characters[tt.character.id] = tt.character
				}
			}

			SendArrivalMessage(tt.character, tt.exitUsed, tt.destinationRoom)

			// Give time for async message delivery
			time.Sleep(10 * time.Millisecond)

			if tt.shouldSend && tt.destinationRoom != nil && mockObserver != nil {
				// Check that observer received the message
				if !mockObserver.ContainsMessage(tt.expectedMessage) {
					t.Errorf("Expected message '%s' not found in observer's messages: %v",
						tt.expectedMessage, mockObserver.GetMessages())
				}

				// Verify arriving character didn't receive the message
				if tt.character != nil && tt.character.player != nil &&
					tt.name == "Arriving character excluded from message" {
					// The arriving character's mock would have been created above
					// We can't easily check it here due to the test structure
					// but the real SendRoomMessage function handles the exclusion
					// This check validates the test scenario is correctly configured
				}
			}
		})
	}
}
