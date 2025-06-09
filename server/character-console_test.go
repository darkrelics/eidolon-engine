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
	"context"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gofrs/uuid/v5"
)

// mockPlayer provides a test double for Player
type mockPlayer struct {
	commandOut     chan string
	commandIn      chan string
	closed         bool
	mutex          sync.Mutex
	receivedOutput []string
}

func newMockPlayer() *mockPlayer {
	return &mockPlayer{
		commandOut:     make(chan string, 100),
		commandIn:      make(chan string, 10),
		receivedOutput: make([]string, 0),
	}
}

func (mp *mockPlayer) close() {
	mp.mutex.Lock()
	defer mp.mutex.Unlock()
	if !mp.closed {
		close(mp.commandOut)
		close(mp.commandIn)
		mp.closed = true
	}
}

func (mp *mockPlayer) captureOutput() {
	defer func() {
		if r := recover(); r != nil {
			// Ignore panics from closed channels during test cleanup
		}
	}()
	for msg := range mp.commandOut {
		mp.mutex.Lock()
		mp.receivedOutput = append(mp.receivedOutput, msg)
		mp.mutex.Unlock()
	}
}

func (mp *mockPlayer) getOutput() []string {
	mp.mutex.Lock()
	defer mp.mutex.Unlock()
	result := make([]string, len(mp.receivedOutput))
	copy(result, mp.receivedOutput)
	return result
}

// setupTestCharacterConsole creates a test character with console dependencies
func setupTestCharacterConsole(_ *testing.T) (*Character, *Game, *mockPlayer, chan bool) {
	ctx := context.Background()
	config := &Configuration{
		Game: struct {
			Balance                  float64 `yaml:"Balance"`
			StartingEssence          uint16  `yaml:"StartingEssence"`
			StartingHealth           uint16  `yaml:"StartingHealth"`
			AutoSave                 uint16  `yaml:"AutoSave"`
			NamesPath                string  `yaml:"NamesPath"`
			ObscenityPath            string  `yaml:"ObscenityPath"`
			ScriptsS3Bucket          string  `yaml:"ScriptsS3Bucket"`
			ScriptsS3Prefix          string  `yaml:"ScriptsS3Prefix"`
			TickIntervalSeconds      int     `yaml:"TickIntervalSeconds"`
			RoomItemCleanupSeconds   int     `yaml:"RoomItemCleanupSeconds"`
			RoomUnloadSeconds        int     `yaml:"RoomUnloadSeconds"`
			CommandTimeoutSeconds    int     `yaml:"CommandTimeoutSeconds"`
			PlayerIdleTimeoutSeconds int     `yaml:"PlayerIdleTimeoutSeconds"`
		}{
			StartingHealth:  100,
			StartingEssence: 50,
			Balance:         1.0,
		},
	}

	game := &Game{
		ctx:              ctx,
		config:           config,
		rooms:            make(map[int64]*Room),
		characters:       make(map[uuid.UUID]*Character),
		commands:         make(map[string]CommandInfo),
		archetypes:       make(map[string]*Archetype),
		prototypes:       make(map[uuid.UUID]*Prototype),
		items:            make(map[uuid.UUID]*Item),
		exits:            make(map[uuid.UUID]*Exit),
		mutex:            sync.RWMutex{},
		startingHealth:   100,
		startingEssence:  50,
		balance:          1.0,
		autoSaveInterval: 5,
		database:         &KeyPair{}, // Mock database - minimal instance
	}

	// Initialize commands for help testing
	game.commands["look"] = CommandInfo{
		handler:     executeLookCommand,
		description: "Look around or examine something",
		usage:       "look [target]",
	}
	game.commands["quit"] = CommandInfo{
		handler:     executeQuitCommand,
		description: "Exit the game",
		usage:       "quit",
	}
	game.commands["help"] = CommandInfo{
		handler:     executeHelpCommand,
		description: "Display available commands",
		usage:       "help [command]",
	}

	// Create default room
	defaultRoom := NewRoom(ctx, 0, "void", "The Void", "A dark void.", true, "")
	defaultRoom.running = true
	defaultRoom.isReady = true
	game.rooms[0] = defaultRoom

	// Create test room
	testRoom := NewRoom(ctx, 1, "test", "Test Room", "A test room.", true, "")
	testRoom.running = true
	testRoom.isReady = true
	game.rooms[1] = testRoom

	// Create mock player
	mockPlayer := newMockPlayer()

	// Create character
	charID, _ := uuid.NewV4()
	character := &Character{
		id:               charID,
		name:             "TestChar",
		game:             game,
		room:             testRoom,
		player:           &Player{commandOut: mockPlayer.commandOut},
		playerCommandIn:  mockPlayer.commandIn,
		roomCommandOut:   make(chan *CommandRequest, 10),
		roomCommandIn:    make(chan *CommandResponse, 10),
		gameCommandOut:   make(chan *CommandRequest, 10),
		gameCommandIn:    make(chan *CommandResponse, 10),
		playerCommandOut: make(chan string, 10),
		end:              make(chan bool, 1),
		prompt:           "> ",
		mutex:            sync.RWMutex{},
		health:           100,
		essence:          50,
		skills:           make(map[string]float64),
		attributes:       make(map[string]float64),
		inventory:        make(map[string]*Item),
		lastSaved:        time.Now(),
		lastEdited:       time.Now(),
	}

	done := make(chan bool, 1)

	// Start output capture with cleanup
	go func() {
		defer func() {
			mockPlayer.close()
		}()
		mockPlayer.captureOutput()
	}()

	return character, game, mockPlayer, done
}

func TestRunConsole_BasicInitialization(t *testing.T) {
	character, _, mockPlayer, done := setupTestCharacterConsole(t)

	// Test that character gets registered properly
	go func() {
		character.RunConsole(done)
	}()

	// Allow minimal initialization time
	time.Sleep(50 * time.Millisecond)

	// Verify character was added to game
	character.game.mutex.RLock()
	_, exists := character.game.characters[character.id]
	character.game.mutex.RUnlock()
	if !exists {
		t.Error("Character was not registered in game")
	}

	// Exit cleanly by closing input
	close(mockPlayer.commandIn)

	// Give it time to exit
	select {
	case <-done:
		// Success
	case <-time.After(1 * time.Second):
		// Console may still be running, that's okay for this test
	}
}

func TestRunConsole_NilRoom(t *testing.T) {
	character, game, mockPlayer, done := setupTestCharacterConsole(t)
	character.room = nil

	// Ensure default room exists
	if _, exists := game.rooms[0]; !exists {
		t.Fatal("Default room 0 must exist for test")
	}

	// Start console
	go character.RunConsole(done)

	// Allow console to initialize
	time.Sleep(100 * time.Millisecond)

	// Verify character was assigned to default room
	character.mutex.RLock()
	roomAssigned := character.room != nil && character.room.roomID == 0
	character.mutex.RUnlock()
	if !roomAssigned {
		t.Error("Character was not assigned to default room when starting with nil room")
	}

	// Clean shutdown
	close(mockPlayer.commandIn)
	select {
	case <-done:
	case <-time.After(1 * time.Second):
		t.Error("RunConsole did not exit after channel closure")
	}
}

func TestRunConsole_RoomNotRunning(t *testing.T) {
	character, _, mockPlayer, done := setupTestCharacterConsole(t)

	// Create a non-running room
	nonRunningRoom := NewRoom(character.game.ctx, 99, "test", "Non-Running Room", "A stopped room.", false, "")
	nonRunningRoom.running = false
	character.game.rooms[99] = nonRunningRoom
	character.room = nonRunningRoom

	// Start console
	go character.RunConsole(done)

	// Allow time for room startup
	time.Sleep(200 * time.Millisecond)

	// Verify room was started
	nonRunningRoom.mutex.RLock()
	running := nonRunningRoom.running
	nonRunningRoom.mutex.RUnlock()

	if !running {
		t.Error("Room should have been started when character entered")
	}

	// Clean shutdown
	close(mockPlayer.commandIn)
	select {
	case <-done:
	case <-time.After(1 * time.Second):
		t.Error("RunConsole did not exit after channel closure")
	}
}

func TestRunConsole_ChannelClosure(t *testing.T) {
	character, _, mockPlayer, done := setupTestCharacterConsole(t)

	// Start console
	go character.RunConsole(done)

	// Allow console to initialize
	time.Sleep(100 * time.Millisecond)

	// Close input channel to simulate disconnection
	close(mockPlayer.commandIn)

	// Wait for done signal
	select {
	case <-done:
		// Success - console detected closed channel and exited
	case <-time.After(1 * time.Second):
		t.Error("RunConsole did not exit after input channel closure")
	}
}

func TestRunConsole_EndSignal(t *testing.T) {
	character, _, _, done := setupTestCharacterConsole(t)

	// Start console
	go character.RunConsole(done)

	// Allow console to initialize
	time.Sleep(100 * time.Millisecond)

	// Send end signal
	character.end <- true

	// Wait for done signal
	select {
	case <-done:
		// Success - console responded to end signal
	case <-time.After(1 * time.Second):
		t.Error("RunConsole did not exit after end signal")
	}
}

func TestDisplayHelp_AllCommands(t *testing.T) {
	character, _, mockPlayer, _ := setupTestCharacterConsole(t)

	err := character.DisplayHelp("")
	if err != nil {
		t.Errorf("DisplayHelp returned error: %v", err)
	}

	// Give output capture time to process
	time.Sleep(50 * time.Millisecond)

	output := mockPlayer.getOutput()
	if len(output) == 0 {
		t.Error("No help output received")
		return
	}

	helpText := strings.Join(output, "")

	// Verify help contains expected commands
	expectedCommands := []string{"look", "quit", "help"}
	for _, cmd := range expectedCommands {
		if !strings.Contains(helpText, cmd) {
			t.Errorf("Help output missing command: %s", cmd)
		}
	}

	if !strings.Contains(helpText, "Available Commands:") {
		t.Error("Help output missing header")
	}
}

func TestDisplayHelp_SpecificCommand(t *testing.T) {
	character, _, mockPlayer, _ := setupTestCharacterConsole(t)

	err := character.DisplayHelp("look")
	if err != nil {
		t.Errorf("DisplayHelp returned error: %v", err)
	}

	// Give output capture time to process
	time.Sleep(50 * time.Millisecond)

	output := mockPlayer.getOutput()
	if len(output) == 0 {
		t.Error("No help output received")
		return
	}

	helpText := strings.Join(output, "")

	// Verify specific command help
	if !strings.Contains(helpText, "Command: look") {
		t.Error("Help output missing command name")
	}
	if !strings.Contains(helpText, "Description: Look around or examine something") {
		t.Error("Help output missing description")
	}
	if !strings.Contains(helpText, "Usage: look [target]") {
		t.Error("Help output missing usage")
	}
}

func TestDisplayHelp_InvalidCommand(t *testing.T) {
	character, _, mockPlayer, _ := setupTestCharacterConsole(t)

	err := character.DisplayHelp("nonexistent")
	if err != nil {
		t.Errorf("DisplayHelp returned error: %v", err)
	}

	// Give output capture time to process
	time.Sleep(50 * time.Millisecond)

	output := mockPlayer.getOutput()
	if len(output) == 0 {
		t.Error("No help output received")
		return
	}

	helpText := strings.Join(output, "")

	if !strings.Contains(helpText, "No help available for 'nonexistent'") {
		t.Error("Help output missing error message for invalid command")
	}
}

func TestDisplayHelp_InvalidState(t *testing.T) {
	character, _, _, _ := setupTestCharacterConsole(t)

	// Test with nil player
	character.player = nil
	err := character.DisplayHelp("")
	if err == nil {
		t.Error("DisplayHelp should return error with nil player")
	}

	// Test with nil game
	character.player = &Player{}
	character.game = nil
	err = character.DisplayHelp("")
	if err == nil {
		t.Error("DisplayHelp should return error with nil game")
	}
}

func TestSendPrompt(t *testing.T) {
	character, _, mockPlayer, _ := setupTestCharacterConsole(t)

	character.SendPrompt()

	// Give output capture time to process
	time.Sleep(50 * time.Millisecond)

	output := mockPlayer.getOutput()
	if len(output) == 0 {
		t.Error("No prompt received")
		return
	}

	if output[len(output)-1] != "> " {
		t.Errorf("Expected prompt '> ', got '%s'", output[len(output)-1])
	}
}

func TestSetPrompt(t *testing.T) {
	character, _, mockPlayer, _ := setupTestCharacterConsole(t)

	// Test custom prompt
	character.SetPrompt("custom> ")
	character.SendPrompt()

	time.Sleep(50 * time.Millisecond)
	output := mockPlayer.getOutput()

	if len(output) > 0 && output[len(output)-1] != "custom> " {
		t.Errorf("Expected prompt 'custom> ', got '%s'", output[len(output)-1])
	}

	// Test empty prompt (should default to "> ")
	character.SetPrompt("")
	character.SendPrompt()

	time.Sleep(50 * time.Millisecond)
	output = mockPlayer.getOutput()

	// Find the last prompt in output
	var lastPrompt string
	for i := len(output) - 1; i >= 0; i-- {
		if strings.HasSuffix(output[i], "> ") {
			lastPrompt = output[i]
			break
		}
	}

	if lastPrompt != "> " {
		t.Errorf("Expected default prompt '> ', got '%s'", lastPrompt)
	}
}

func TestDisplayMessage(t *testing.T) {
	character, _, mockPlayer, _ := setupTestCharacterConsole(t)

	testMessage := "Test message for display"
	character.DisplayMessage(testMessage)

	time.Sleep(50 * time.Millisecond)
	output := mockPlayer.getOutput()

	found := false
	expectedMessage := "\n\r" + testMessage + "\n\r" + character.prompt
	for _, msg := range output {
		if msg == expectedMessage {
			found = true
			break
		}
	}

	if !found {
		t.Errorf("Message '%s' not found in output (looking for '%s')", testMessage, expectedMessage)
	}
}

func TestSafeExecuteLookCommand(t *testing.T) {
	character, _, _, _ := setupTestCharacterConsole(t)

	// This should not panic even if look command fails
	character.safeExecuteLookCommand()

	// Test with nil room to trigger potential panic
	character.room = nil
	character.safeExecuteLookCommand() // Should recover from panic

	// If we get here, panic recovery worked
}

func TestCleanupAndSignalDone(t *testing.T) {
	character, _, _, done := setupTestCharacterConsole(t)

	// Add character to room
	character.room.mutex.Lock()
	character.room.characters[character.id] = character
	character.room.mutex.Unlock()

	// Call cleanup
	character.cleanupAndSignalDone(done)

	// Wait for done signal
	select {
	case <-done:
		// Success
	case <-time.After(1 * time.Second):
		t.Error("Done channel not signaled")
	}

	// Verify character was removed from room
	character.room.mutex.RLock()
	_, exists := character.room.characters[character.id]
	character.room.mutex.RUnlock()

	if exists {
		t.Error("Character was not removed from room during cleanup")
	}
}

func TestRunConsole_CommandProcessing(t *testing.T) {
	character, _, mockPlayer, done := setupTestCharacterConsole(t)

	// Start console
	go character.RunConsole(done)

	// Allow console to initialize
	time.Sleep(100 * time.Millisecond)

	// Send multiple commands rapidly
	commands := []string{"look", "help", "look"}
	for _, cmd := range commands {
		mockPlayer.commandIn <- cmd
		time.Sleep(50 * time.Millisecond) // Small delay between commands
	}

	// Allow processing time
	time.Sleep(200 * time.Millisecond)

	// Close input to exit cleanly
	close(mockPlayer.commandIn)

	select {
	case <-done:
		// Success
	case <-time.After(2 * time.Second):
		t.Error("RunConsole did not exit after commands")
	}

	// Verify we got output for commands
	output := mockPlayer.getOutput()
	if len(output) < len(commands) {
		t.Errorf("Expected at least %d outputs, got %d", len(commands), len(output))
	}
}

func TestRunConsole_IdleTimeout(t *testing.T) {
	character, _, mockPlayer, done := setupTestCharacterConsole(t)

	// Set player to nil to simulate lost connection during idle
	go func() {
		time.Sleep(500 * time.Millisecond)
		character.mutex.Lock()
		character.player = nil
		character.mutex.Unlock()
	}()

	// Start console
	go character.RunConsole(done)

	// Don't send any commands - let it idle
	// The timer in RunConsole will fire and check player connection

	// Wait for console to exit due to nil player
	select {
	case <-done:
		// Success - console detected nil player during idle check
	case <-time.After(35 * time.Second): // Slightly more than idle timeout
		t.Error("RunConsole did not exit after player disconnection")
	}

	mockPlayer.close()
}
