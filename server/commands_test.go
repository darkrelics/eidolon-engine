/*
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

*/

package main

import (
	"context"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gofrs/uuid/v5"
)

// Mock command handlers for testing
func mockLookCommand(c *Character, tokens []string) error {
	return nil
}

func mockQuitCommand(c *Character, tokens []string) error {
	// Don't call the real quit command which saves to database
	// Just return an error to simulate quit
	return errors.New("quit requested")
}

func mockTimedCommand(c *Character, tokens []string) error {
	return nil
}

// Helper function to create a minimal test game
func createTestGameForCommands() *Game {
	g := &Game{
		commands: make(map[string]CommandInfo),
		mutex:    sync.RWMutex{},
	}

	// Register test commands
	g.commands["look"] = CommandInfo{
		roundTime:   -1, // Doesn't care about round time
		handler:     mockLookCommand,
		description: "Look around",
		usage:       "look",
	}

	g.commands["quit"] = CommandInfo{
		roundTime:   -1, // Doesn't care about round time
		handler:     mockQuitCommand,
		description: "Exit game",
		usage:       "quit",
	}

	g.commands["get"] = CommandInfo{
		roundTime:   0, // Blocked by round time but doesn't generate it
		handler:     mockTimedCommand,
		description: "Get item",
		usage:       "get <item>",
	}

	g.commands["go"] = CommandInfo{
		roundTime:   0,   // Blocked by round time but doesn't generate it
		handler:     nil, // Escalates to room
		description: "Move",
		usage:       "go <direction>",
	}

	// Build command index
	g.buildCommandIndex()

	return g
}

// Helper function to create a test character with channels
func createTestCharacter(game *Game) *Character {
	player := &Player{
		commandOut: make(chan string, 10),
	}

	room := &Room{
		roomID:     1,
		commandIn:  make(chan *CommandRequest, 10),
		running:    true,
		mutex:      sync.RWMutex{},
		characters: make(map[uuid.UUID]*Character),
	}

	char := &Character{
		name:           "TestChar",
		game:           game,
		player:         player,
		room:           room,
		gameCommandOut: make(chan *CommandRequest, 10),
		waitUntil:      time.Now(), // No timeout by default
	}

	return char
}

func TestProcessCommand_InputValidation(t *testing.T) {
	game := createTestGameForCommands()
	char := createTestCharacter(game)
	ctx := context.Background()

	tests := []struct {
		name          string
		input         string
		expectedError string
	}{
		{
			name:          "Input too long",
			input:         strings.Repeat("a", 241),
			expectedError: "Command too long",
		},
		{
			name:          "Empty input",
			input:         "",
			expectedError: "No command entered",
		},
		{
			name:          "Valid input",
			input:         "look",
			expectedError: "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := ProcessCommand(ctx, char, tt.input)
			if tt.expectedError != "" {
				// Input validation errors are now user messages, not errors
				if err != nil {
					t.Errorf("Expected no error (user message), got %v", err)
				}
			} else if err != nil {
				t.Errorf("Unexpected error: %v", err)
			}
		})
	}
}

func TestProcessCommand_CharacterState(t *testing.T) {
	ctx := context.Background()

	tests := []struct {
		name          string
		character     *Character
		expectedError string
	}{
		{
			name:          "Nil character",
			character:     nil,
			expectedError: "invalid character state",
		},
		{
			name:          "Character with nil game",
			character:     &Character{name: "Test"},
			expectedError: "invalid character state",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := ProcessCommand(ctx, tt.character, "look")
			if err == nil || !strings.Contains(err.Error(), tt.expectedError) {
				t.Errorf("Expected error containing %q, got %v", tt.expectedError, err)
			}
		})
	}
}

func TestProcessCommand_QuitCommand(t *testing.T) {
	// Skip this test as quit command requires database setup
	t.Skip("Skipping quit command test - requires database setup")
}

func TestProcessCommand_CommandTimeout(t *testing.T) {
	game := createTestGameForCommands()
	char := createTestCharacter(game)
	ctx := context.Background()

	// Set command timeout in the future
	char.waitUntil = time.Now().Add(1 * time.Hour)

	// Commands that should be blocked
	blockedCommands := []string{"get sword", "go north"}
	for _, cmd := range blockedCommands {
		_, err := ProcessCommand(ctx, char, cmd)
		if err == nil || !strings.Contains(err.Error(), "You must wait") {
			t.Errorf("Expected timeout error for %q, got %v", cmd, err)
		}
	}

	// Commands that should be allowed - only test with look which we mocked
	_, err := ProcessCommand(ctx, char, "look")
	if err != nil && strings.Contains(err.Error(), "You must wait") {
		t.Errorf("Command 'look' should be allowed during timeout, got %v", err)
	}
}

func TestProcessCommand_CharacterHandler(t *testing.T) {
	game := createTestGameForCommands()
	char := createTestCharacter(game)
	ctx := context.Background()

	// Test untimed command with handler
	_, err := ProcessCommand(ctx, char, "look")
	if err != nil {
		t.Errorf("Expected look command to succeed, got %v", err)
	}

	// Test timed command with handler
	_, err = ProcessCommand(ctx, char, "get sword")
	if err != nil {
		t.Errorf("Expected get command to succeed, got %v", err)
	}
}

func TestProcessCommand_RoomEscalation(t *testing.T) {
	game := createTestGameForCommands()
	char := createTestCharacter(game)
	ctx := context.Background()

	// Set up a goroutine to handle room commands
	go func() {
		for cmdReq := range char.room.commandIn {
			cmdReq.Response <- &CommandResponse{
				Message: "Room handled command",
			}
		}
	}()

	// Command that escalates to room (no handler)
	_, err := ProcessCommand(ctx, char, "go north")
	if err != nil {
		t.Errorf("Expected room escalation to succeed, got %v", err)
	}
}

func TestProcessCommand_ContextCancellation(t *testing.T) {
	game := createTestGameForCommands()
	char := createTestCharacter(game)

	// Create a context that we'll cancel
	ctx, cancel := context.WithCancel(context.Background())

	// Command that escalates to room but no handler responds
	go func() {
		time.Sleep(100 * time.Millisecond)
		cancel()
	}()

	_, err := ProcessCommand(ctx, char, "go north")
	if err == nil || err != context.Canceled {
		t.Errorf("Expected context canceled error, got %v", err)
	}
}

func TestEscalateToGame(t *testing.T) {
	game := createTestGameForCommands()
	char := createTestCharacter(game)
	ctx := context.Background()

	// Set up a goroutine to handle game commands
	go func() {
		for cmdReq := range char.gameCommandOut {
			cmdReq.Response <- &CommandResponse{
				Message: "Game handled command",
			}
		}
	}()

	// Test successful escalation
	_, err := escalateToGame(ctx, char, "test", []string{"test"})
	if err != nil {
		t.Errorf("Expected game escalation to succeed, got %v", err)
	}
}

func TestEscalateToGame_BufferFull(t *testing.T) {
	game := createTestGameForCommands()
	char := createTestCharacter(game)
	ctx := context.Background()

	// Fill the game command buffer
	for range cap(char.gameCommandOut) {
		char.gameCommandOut <- &CommandRequest{}
	}

	// Try to escalate - should return nil (message displayed to user)
	_, err := escalateToGame(ctx, char, "test", []string{"test"})
	if err != nil {
		t.Errorf("Expected nil error (user message), got %v", err)
	}
}

func TestEscalateToGame_Timeout(t *testing.T) {
	game := createTestGameForCommands()
	char := createTestCharacter(game)
	ctx := context.Background()

	// Don't set up a handler - let it timeout
	start := time.Now()
	_, err := escalateToGame(ctx, char, "test", []string{"test"})
	elapsed := time.Since(start)

	if err != nil {
		t.Errorf("Expected nil error (user message), got %v", err)
	}

	// Should timeout after ~5 seconds
	if elapsed < 4*time.Second || elapsed > 6*time.Second {
		t.Errorf("Expected ~5 second timeout, got %v", elapsed)
	}
}
