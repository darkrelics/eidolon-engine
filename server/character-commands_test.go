/*
Eidolon Engine

Copyright 2024-2025 Jason Robinson

*/

package main

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"strings"
	"sync"
	"testing"

	"github.com/gofrs/uuid/v5"
)

func init() {
	Logger = slog.New(slog.NewTextHandler(io.Discard, &slog.HandlerOptions{
		Level: slog.LevelError,
	}))
}

// Helper function to create a test game for character commands
func createTestGameForCharacterCommands() *Game {
	return &Game{
		ctx:        context.Background(),
		mutex:      sync.RWMutex{},
		characters: make(map[uuid.UUID]*Character),
		rooms:      make(map[int64]*Room),
	}
}

// Helper function to create a test room
func createTestRoom(id int64) *Room {
	return &Room{
		roomID:      id,
		title:       "Test Room",
		description: "A simple test room",
		mutex:       sync.RWMutex{},
		characters:  make(map[uuid.UUID]*Character),
		items:       make(map[uuid.UUID]*Item),
		exits:       make(map[uuid.UUID]*Exit),
	}
}

// Helper function to create a test character
func createTestCharacterForCommands(name string, game *Game, room *Room) *Character {
	player := &Player{
		commandOut: make(chan string, 10),
	}

	char := &Character{
		id:         uuid.Must(uuid.NewV4()),
		name:       name,
		game:       game,
		player:     player,
		room:       room,
		mutex:      sync.RWMutex{},
		health:     100,
		maxHealth:  100,
		essence:    50,
		attributes: make(map[string]float64),
		skills:     make(map[string]float64),
		inventory:  make(map[string]*Item),
	}

	return char
}

// Helper function to create a test item
func createTestItem(name, description string) *Item {
	return &Item{
		id:          uuid.Must(uuid.NewV4()),
		name:        name,
		description: description,
		mutex:       sync.RWMutex{},
		container:   false,
		isWorn:      false,
	}
}

// TestExecuteQuitCommand tests the quit command execution
func TestExecuteQuitCommand(t *testing.T) {
	tests := []struct {
		name        string
		character   *Character
		tokens      []string
		expectError bool
	}{
		{
			name:        "Nil character",
			character:   nil,
			tokens:      []string{"quit"},
			expectError: true,
		},
		// Skip test with valid character as it requires database setup
		// and would call character.Stop() which saves to database
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := executeQuitCommand(tt.character, tt.tokens)
			if tt.expectError && err == nil {
				t.Error("Expected error but got none")
			}
			if !tt.expectError && err != nil {
				t.Errorf("Unexpected error: %v", err)
			}
		})
	}
}

// TestExecuteHelpCommand tests the help command execution
func TestExecuteHelpCommand(t *testing.T) {
	game := createTestGameForCharacterCommands()
	room := createTestRoom(0)

	tests := []struct {
		name        string
		character   *Character
		tokens      []string
		expectError bool
	}{
		{
			name:        "Nil character",
			character:   nil,
			tokens:      []string{"help"},
			expectError: true,
		},
		{
			name: "Character with nil player",
			character: &Character{
				name: "TestChar",
				game: game,
			},
			tokens:      []string{"help"},
			expectError: true,
		},
		{
			name: "Character with nil game",
			character: &Character{
				name:   "TestChar",
				player: &Player{commandOut: make(chan string, 10)},
			},
			tokens:      []string{"help"},
			expectError: true,
		},
		{
			name:        "Valid help command - general",
			character:   createTestCharacterForCommands("TestChar", game, room),
			tokens:      []string{"help"},
			expectError: false,
		},
		{
			name:        "Valid help command - specific",
			character:   createTestCharacterForCommands("TestChar", game, room),
			tokens:      []string{"help", "look"},
			expectError: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := executeHelpCommand(tt.character, tt.tokens)
			if tt.expectError && err == nil {
				t.Error("Expected error but got none")
			}
			if !tt.expectError && err != nil {
				t.Errorf("Unexpected error: %v", err)
			}
		})
	}
}

// TestExecuteLookCommand tests the look command execution
func TestExecuteLookCommand(t *testing.T) {
	game := createTestGameForCharacterCommands()
	room := createTestRoom(0)
	game.rooms[0] = room

	tests := []struct {
		name        string
		character   *Character
		tokens      []string
		expectError bool
	}{
		{
			name:        "Nil character",
			character:   nil,
			tokens:      []string{"look"},
			expectError: true,
		},
		{
			name:        "Valid look command - room",
			character:   createTestCharacterForCommands("TestChar", game, room),
			tokens:      []string{"look"},
			expectError: false,
		},
		{
			name:        "Valid look command - target",
			character:   createTestCharacterForCommands("TestChar", game, room),
			tokens:      []string{"look", "sword"},
			expectError: false,
		},
		{
			name: "Character with nil room",
			character: &Character{
				name:   "TestChar",
				game:   game,
				player: &Player{commandOut: make(chan string, 10)},
				mutex:  sync.RWMutex{},
			},
			tokens:      []string{"look"},
			expectError: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := executeLookCommand(tt.character, tt.tokens)
			if tt.expectError && err == nil {
				t.Error("Expected error but got none")
			}
			if !tt.expectError && err != nil {
				t.Errorf("Unexpected error: %v", err)
			}
		})
	}
}

// TestExecuteWhoCommand tests the who command execution
func TestExecuteWhoCommand(t *testing.T) {
	game := createTestGameForCharacterCommands()
	room := createTestRoom(0)

	tests := []struct {
		name        string
		character   *Character
		tokens      []string
		setupFunc   func()
		expectError bool
	}{
		{
			name:        "Nil character",
			character:   nil,
			tokens:      []string{"who"},
			expectError: true,
		},
		{
			name: "Character with nil player",
			character: &Character{
				name: "TestChar",
				game: game,
			},
			tokens:      []string{"who"},
			expectError: true,
		},
		{
			name: "Character with nil game",
			character: &Character{
				name:   "TestChar",
				player: &Player{commandOut: make(chan string, 10)},
			},
			tokens:      []string{"who"},
			expectError: true,
		},
		{
			name:        "Valid who command - no other characters",
			character:   createTestCharacterForCommands("TestChar", game, room),
			tokens:      []string{"who"},
			expectError: false,
		},
		{
			name:      "Valid who command - with other characters",
			character: createTestCharacterForCommands("TestChar", game, room),
			tokens:    []string{"who"},
			setupFunc: func() {
				char1 := createTestCharacterForCommands("Alice", game, room)
				char2 := createTestCharacterForCommands("Bob", game, room)
				game.characters[char1.id] = char1
				game.characters[char2.id] = char2
			},
			expectError: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if tt.setupFunc != nil {
				tt.setupFunc()
			}

			err := executeWhoCommand(tt.character, tt.tokens)
			if tt.expectError && err == nil {
				t.Error("Expected error but got none")
			}
			if !tt.expectError && err != nil {
				t.Errorf("Unexpected error: %v", err)
			}

			// Clean up characters for next test
			game.characters = make(map[uuid.UUID]*Character)
		})
	}
}

// TestExecuteInfoCommand tests the info command execution
func TestExecuteInfoCommand(t *testing.T) {
	game := createTestGameForCharacterCommands()
	room := createTestRoom(0)

	tests := []struct {
		name        string
		character   *Character
		tokens      []string
		expectError bool
	}{
		{
			name:        "Nil character",
			character:   nil,
			tokens:      []string{"info"},
			expectError: true,
		},
		{
			name: "Character with nil player",
			character: &Character{
				name: "TestChar",
			},
			tokens:      []string{"info"},
			expectError: true,
		},
		{
			name:        "Valid info command",
			character:   createTestCharacterForCommands("TestChar", game, room),
			tokens:      []string{"info"},
			expectError: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := executeInfoCommand(tt.character, tt.tokens)
			if tt.expectError && err == nil {
				t.Error("Expected error but got none")
			}
			if !tt.expectError && err != nil {
				t.Errorf("Unexpected error: %v", err)
			}
		})
	}
}

// TestExecuteSkillCommand tests the skill command execution
func TestExecuteSkillCommand(t *testing.T) {
	game := createTestGameForCharacterCommands()
	room := createTestRoom(0)

	tests := []struct {
		name        string
		character   *Character
		tokens      []string
		expectError bool
	}{
		{
			name:        "Nil character",
			character:   nil,
			tokens:      []string{"skill"},
			expectError: true,
		},
		{
			name: "Character with nil player",
			character: &Character{
				name: "TestChar",
			},
			tokens:      []string{"skill"},
			expectError: true,
		},
		{
			name:        "Valid skill command",
			character:   createTestCharacterForCommands("TestChar", game, room),
			tokens:      []string{"skill"},
			expectError: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := executeSkillCommand(tt.character, tt.tokens)
			if tt.expectError && err == nil {
				t.Error("Expected error but got none")
			}
			if !tt.expectError && err != nil {
				t.Errorf("Unexpected error: %v", err)
			}
		})
	}
}

// TestExecuteInventoryCommand tests the inventory command execution
func TestExecuteInventoryCommand(t *testing.T) {
	game := createTestGameForCharacterCommands()
	room := createTestRoom(0)

	tests := []struct {
		name        string
		character   *Character
		tokens      []string
		setupFunc   func(*Character)
		expectError bool
	}{
		{
			name:        "Nil character",
			character:   nil,
			tokens:      []string{"inventory"},
			expectError: true,
		},
		{
			name: "Character with nil player",
			character: &Character{
				name: "TestChar",
			},
			tokens:      []string{"inventory"},
			expectError: true,
		},
		{
			name:        "Valid inventory command - empty",
			character:   createTestCharacterForCommands("TestChar", game, room),
			tokens:      []string{"inventory"},
			expectError: false,
		},
		{
			name:      "Valid inventory command - with items",
			character: createTestCharacterForCommands("TestChar", game, room),
			tokens:    []string{"inventory"},
			setupFunc: func(char *Character) {
				sword := createTestItem("Iron Sword", "A sharp iron sword")
				armor := createTestItem("Leather Armor", "Basic leather armor")
				armor.isWorn = true

				char.inventory["sword"] = sword
				char.inventory["armor"] = armor
				char.rightHand = sword
			},
			expectError: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if tt.setupFunc != nil && tt.character != nil {
				tt.setupFunc(tt.character)
			}

			err := executeInventoryCommand(tt.character, tt.tokens)
			if tt.expectError && err == nil {
				t.Error("Expected error but got none")
			}
			if !tt.expectError && err != nil {
				t.Errorf("Unexpected error: %v", err)
			}
		})
	}
}

// TestGetCharacterInfo tests the character info display method
func TestGetCharacterInfo(t *testing.T) {
	char := createTestCharacterForCommands("TestChar", createTestGameForCharacterCommands(), createTestRoom(0))

	// Add some attributes and skills
	char.attributes["strength"] = 15
	char.attributes["intelligence"] = 12
	char.skills["swordsmanship"] = 8
	char.skills["magic"] = 0 // Should not be displayed

	info := char.GetCharacterInfo()

	// Check that info contains character name (allowing for color codes)
	if !strings.Contains(info, "TestChar") {
		t.Errorf("Character info should contain character name, got: %q", info)
	}

	// Check that health and essence are displayed
	if !strings.Contains(info, "Health: 100") {
		t.Error("Character info should contain health")
	}
	if !strings.Contains(info, "Essence: 50") {
		t.Error("Character info should contain essence")
	}

	// Check that attributes are displayed
	if !strings.Contains(info, "strength") {
		t.Error("Character info should contain strength attribute")
	}
	if !strings.Contains(info, "intelligence") {
		t.Error("Character info should contain intelligence attribute")
	}

	// Check that skills with value > 0 are displayed
	if !strings.Contains(info, "swordsmanship") {
		t.Error("Character info should contain swordsmanship skill")
	}

	// Check that skills with value 0 are not displayed
	if strings.Contains(info, "magic") {
		t.Error("Character info should not contain magic skill with 0 value")
	}
}

// TestGetSkillInfo tests the skill info display method
func TestGetSkillInfo(t *testing.T) {
	char := createTestCharacterForCommands("TestChar", createTestGameForCharacterCommands(), createTestRoom(0))

	// Add some skills
	char.skills["swordsmanship"] = 8
	char.skills["magic"] = 5
	char.skills["stealth"] = 0 // Should not be displayed

	skillInfo := char.GetSkillInfo()

	// Check that skill info contains character name (allowing for color codes)
	if !strings.Contains(skillInfo, "TestChar") || !strings.Contains(skillInfo, "'s Skills") {
		t.Errorf("Skill info should contain character name, got: %q", skillInfo)
	}

	// Check that skills with value > 0 are displayed
	if !strings.Contains(skillInfo, "swordsmanship") {
		t.Error("Skill info should contain swordsmanship skill")
	}
	if !strings.Contains(skillInfo, "magic") {
		t.Error("Skill info should contain magic skill")
	}

	// Check that skills with value 0 are not displayed
	if strings.Contains(skillInfo, "stealth") {
		t.Error("Skill info should not contain stealth skill with 0 value")
	}
}

// TestGetSkillInfo_NoSkills tests skill display with no developed skills
func TestGetSkillInfo_NoSkills(t *testing.T) {
	char := createTestCharacterForCommands("TestChar", createTestGameForCharacterCommands(), createTestRoom(0))

	skillInfo := char.GetSkillInfo()

	if !strings.Contains(skillInfo, "You have not developed any skills yet") {
		t.Error("Should display message when no skills are developed")
	}
}

// TestLookAtTarget tests the look at target functionality
func TestLookAtTarget(t *testing.T) {
	game := createTestGameForCharacterCommands()
	room := createTestRoom(0)
	char := createTestCharacterForCommands("TestChar", game, room)

	// Add an item to the room
	sword := createTestItem("iron sword", "A sharp iron blade")
	swordID := uuid.Must(uuid.NewV4())
	sword.id = swordID
	room.items[swordID] = sword

	// Add another character to the room
	otherChar := createTestCharacterForCommands("OtherChar", game, room)
	room.characters[otherChar.id] = otherChar

	tests := []struct {
		name   string
		target string
	}{
		{
			name:   "Look at item in room",
			target: "sword",
		},
		{
			name:   "Look at character in room",
			target: "other",
		},
		{
			name:   "Look at non-existent target",
			target: "nonexistent",
		},
		{
			name:   "Look in container",
			target: "in bag",
		},
		{
			name:   "Look in my container",
			target: "in my bag",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := char.LookAtTarget(tt.target)
			if err != nil {
				t.Errorf("LookAtTarget should not return error, got: %v", err)
			}
		})
	}
}

// TestLookAtRoomTarget tests looking at targets in the room
func TestLookAtRoomTarget(t *testing.T) {
	game := createTestGameForCharacterCommands()
	room := createTestRoom(0)
	char := createTestCharacterForCommands("TestChar", game, room)

	// Add an item to the room
	sword := createTestItem("iron sword", "A sharp iron blade")
	swordID := uuid.Must(uuid.NewV4())
	sword.id = swordID
	room.items[swordID] = sword

	// Add an exit
	exitID := uuid.Must(uuid.NewV4())
	room.exits[exitID] = &Exit{
		direction:   "north",
		description: "A path leading north",
		visible:     true,
	}

	tests := []struct {
		name     string
		target   string
		expected string
	}{
		{
			name:     "Look at existing item",
			target:   "sword",
			expected: "A sharp iron blade",
		},
		{
			name:     "Look at non-existent item",
			target:   "shield",
			expected: "You don't see 'shield' here",
		},
		{
			name:     "Look at exit",
			target:   "north",
			expected: "A path leading north",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := char.LookAtRoomTarget(tt.target)
			if !strings.Contains(result, tt.expected) {
				t.Errorf("Expected result to contain %q, got %q", tt.expected, result)
			}
		})
	}
}

// TestLookAtInventoryItem tests looking at items in inventory
func TestLookAtInventoryItem(t *testing.T) {
	char := createTestCharacterForCommands("TestChar", createTestGameForCharacterCommands(), createTestRoom(0))

	// Add an item to inventory
	sword := createTestItem("iron sword", "A sharp iron blade")
	char.inventory["sword"] = sword

	tests := []struct {
		name     string
		target   string
		expected string
	}{
		{
			name:     "Look at item in inventory",
			target:   "sword",
			expected: "A sharp iron blade",
		},
		{
			name:     "Look at non-existent item",
			target:   "shield",
			expected: "You don't see 'shield' here",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := char.LookAtInventoryItem(tt.target)
			if !strings.Contains(result, tt.expected) {
				t.Errorf("Expected result to contain %q, got %q", tt.expected, result)
			}
		})
	}
}

// TestLookInContainer tests looking inside containers
func TestLookInContainer(t *testing.T) {
	char := createTestCharacterForCommands("TestChar", createTestGameForCharacterCommands(), createTestRoom(0))

	// Add a container to inventory
	bag := createTestItem("leather bag", "A sturdy leather bag")
	bag.container = true
	char.inventory["bag"] = bag

	// Add a non-container item
	sword := createTestItem("iron sword", "A sharp iron blade")
	char.inventory["sword"] = sword

	tests := []struct {
		name          string
		containerName string
		isMyContainer bool
		expectContain string
	}{
		{
			name:          "Look in my container",
			containerName: "bag",
			isMyContainer: true,
			expectContain: "", // Container contents (would be implemented in Item.GetContainerContents())
		},
		{
			name:          "Look in my non-container",
			containerName: "sword",
			isMyContainer: true,
			expectContain: "is not a container",
		},
		{
			name:          "Look in non-existent my container",
			containerName: "chest",
			isMyContainer: true,
			expectContain: "You don't have a 'chest'",
		},
		{
			name:          "Look in room container (no room setup)",
			containerName: "chest",
			isMyContainer: false,
			expectContain: "You don't see a 'chest' here",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := char.LookInContainer(tt.containerName, tt.isMyContainer)
			if tt.expectContain != "" && !strings.Contains(result, tt.expectContain) {
				t.Errorf("Expected result to contain %q, got %q", tt.expectContain, result)
			}
		})
	}
}

// TestConcurrentCharacterAccess tests concurrent access to character methods
func TestConcurrentCharacterAccess(t *testing.T) {
	char := createTestCharacterForCommands("TestChar", createTestGameForCharacterCommands(), createTestRoom(0))

	// Add some data to the character
	char.attributes["strength"] = 15
	char.skills["swordsmanship"] = 8

	var wg sync.WaitGroup
	errors := make([]error, 10)

	// Run concurrent operations
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func(index int) {
			defer wg.Done()

			// Test concurrent access to character info
			info := char.GetCharacterInfo()
			if !strings.Contains(info, "TestChar") {
				errors[index] = fmt.Errorf("character info missing name")
			}

			// Test concurrent access to skill info
			skillInfo := char.GetSkillInfo()
			if !strings.Contains(skillInfo, "TestChar") {
				errors[index] = fmt.Errorf("skill info missing name")
			}
		}(i)
	}

	wg.Wait()

	// Check for any errors
	for i, err := range errors {
		if err != nil {
			t.Errorf("Goroutine %d encountered error: %v", i, err)
		}
	}
}
