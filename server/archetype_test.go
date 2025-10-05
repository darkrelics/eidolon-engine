/*
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

*/

package main

import (
	"context"
	"io"
	"log/slog"
	"strings"
	"sync"
	"testing"

	"github.com/gofrs/uuid/v5"
)

func init() {
	// Initialize a test logger that discards output
	Logger = slog.New(slog.NewTextHandler(io.Discard, &slog.HandlerOptions{
		Level: slog.LevelError, // Only show errors in tests
	}))
}

// Helper function to create a test game instance
func createTestGame() *Game {
	return &Game{
		ctx:              context.Background(),
		mutex:            sync.RWMutex{},
		archetypes:       make(map[string]*Archetype),
		archetypeOptions: []string{},
		prototypes:       make(map[uuid.UUID]*Prototype),
		// database field is nil for unit tests that don't need database access
	}
}

// Helper function to create a valid archetype
func createValidArchetype(name string) *Archetype {
	return &Archetype{
		ArchetypeName: name,
		Description:   "Test archetype description",
		Attributes: map[string]float64{
			"strength":     10,
			"intelligence": 15,
			"agility":      12,
		},
		Skills: map[string]float64{
			"swordsmanship": 5,
			"magic":         10,
		},
		StartRoom:     1,
		StartingItems: []ArchetypeItem{},
		Health:        100,
		Essence:       50,
		Player:        true,
	}
}

func TestIsSlotCompatible(t *testing.T) {
	tests := []struct {
		name             string
		slot             string
		wearableLocation string
		expected         bool
	}{
		// Direct matches
		{"Direct match weapon", "weapon", "weapon", true},
		{"Direct match armor", "armor", "armor", true},
		{"Direct match back", "back", "back", true},

		// Semantic equivalents
		{"Weapon slot with waist location", "weapon", "waist", true},
		{"Weapon slot with hands location", "weapon", "hands", true},
		{"Armor slot with chest location", "armor", "chest", true},
		{"Armor slot with body location", "armor", "body", true},
		{"Back slot with shoulders location", "back", "shoulders", true},
		{"Finger slot with left_finger location", "finger", "left_finger", true},
		{"Finger slot with right_finger location", "finger", "right_finger", true},
		{"Wrist slot with left_wrist location", "wrist", "left_wrist", true},
		{"Wrist slot with right_wrist location", "wrist", "right_wrist", true},

		// Substring matching
		{"Substring match finger in ring_finger", "finger", "ring_finger", true},
		{"Substring match ring in rings", "ring", "rings", true},

		// Non-matches
		{"Weapon slot with head location", "weapon", "head", false},
		{"Armor slot with feet location", "armor", "feet", false},
		{"Back slot with waist location", "back", "waist", false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := isSlotCompatible(tt.slot, tt.wearableLocation)
			if result != tt.expected {
				t.Errorf("isSlotCompatible(%s, %s) = %v, want %v",
					tt.slot, tt.wearableLocation, result, tt.expected)
			}
		})
	}
}

func TestValidateArchetype(t *testing.T) {
	game := createTestGame()

	// Add a prototype for testing
	prototypeID := uuid.Must(uuid.NewV4())
	game.prototypes[prototypeID] = &Prototype{
		name:     "Test Sword",
		wearable: true,
		wornOn:   []string{"weapon", "waist"},
	}

	tests := []struct {
		name        string
		archetype   *Archetype
		setupFunc   func()
		expectError bool
		errorMsg    string
	}{
		{
			name:        "Nil archetype",
			archetype:   nil,
			expectError: true,
			errorMsg:    "archetype cannot be nil",
		},
		{
			name:        "Valid archetype",
			archetype:   createValidArchetype("Warrior"),
			expectError: false,
		},
		{
			name: "Empty archetype name",
			archetype: &Archetype{
				Description: "Test",
				Attributes:  map[string]float64{"str": 10},
				Skills:      map[string]float64{"skill": 5},
			},
			expectError: true,
			errorMsg:    "archetype name cannot be empty",
		},
		{
			name: "Empty description",
			archetype: &Archetype{
				ArchetypeName: "Warrior",
				Attributes:    map[string]float64{"str": 10},
				Skills:        map[string]float64{"skill": 5},
			},
			expectError: true,
			errorMsg:    "description cannot be empty",
		},
		{
			name: "No attributes",
			archetype: &Archetype{
				ArchetypeName: "Warrior",
				Description:   "Test",
				Skills:        map[string]float64{"skill": 5},
			},
			expectError: true,
			errorMsg:    "must have at least one attribute",
		},
		{
			name: "No skills",
			archetype: &Archetype{
				ArchetypeName: "Warrior",
				Description:   "Test",
				Attributes:    map[string]float64{"str": 10},
			},
			expectError: true,
			errorMsg:    "must have at least one skill",
		},
		{
			name: "Starting item with empty prototype ID",
			archetype: &Archetype{
				ArchetypeName: "Warrior",
				Description:   "Test",
				Attributes:    map[string]float64{"str": 10},
				Skills:        map[string]float64{"skill": 5},
				StartingItems: []ArchetypeItem{
					{PrototypeID: "", Slot: "weapon"},
				},
			},
			expectError: true,
			errorMsg:    "has empty prototype ID",
		},
		{
			name: "Starting item with empty slot",
			archetype: &Archetype{
				ArchetypeName: "Warrior",
				Description:   "Test",
				Attributes:    map[string]float64{"str": 10},
				Skills:        map[string]float64{"skill": 5},
				StartingItems: []ArchetypeItem{
					{PrototypeID: prototypeID.String(), Slot: ""},
				},
			},
			expectError: true,
			errorMsg:    "has empty slot",
		},
		{
			name: "Starting item with invalid UUID",
			archetype: &Archetype{
				ArchetypeName: "Warrior",
				Description:   "Test",
				Attributes:    map[string]float64{"str": 10},
				Skills:        map[string]float64{"skill": 5},
				StartingItems: []ArchetypeItem{
					{PrototypeID: "not-a-uuid", Slot: "weapon"},
				},
			},
			expectError: true,
			errorMsg:    "has invalid prototype ID",
		},
		{
			name: "Starting item with non-existent prototype",
			archetype: &Archetype{
				ArchetypeName: "Warrior",
				Description:   "Test",
				Attributes:    map[string]float64{"str": 10},
				Skills:        map[string]float64{"skill": 5},
				StartingItems: []ArchetypeItem{
					{PrototypeID: uuid.Must(uuid.NewV4()).String(), Slot: "weapon"},
				},
			},
			expectError: true,
			errorMsg:    "references non-existent prototype",
		},
		{
			name: "Valid starting item",
			archetype: &Archetype{
				ArchetypeName: "Warrior",
				Description:   "Test",
				Attributes:    map[string]float64{"str": 10},
				Skills:        map[string]float64{"skill": 5},
				StartingItems: []ArchetypeItem{
					{PrototypeID: prototypeID.String(), Slot: "weapon", IsWorn: true},
				},
			},
			expectError: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if tt.setupFunc != nil {
				tt.setupFunc()
			}

			err := game.ValidateArchetype(tt.archetype)

			if tt.expectError {
				if err == nil {
					t.Errorf("Expected error containing '%s', but got nil", tt.errorMsg)
				} else if !contains(err.Error(), tt.errorMsg) {
					t.Errorf("Expected error containing '%s', but got '%s'", tt.errorMsg, err.Error())
				}
			} else {
				if err != nil {
					t.Errorf("Expected no error, but got: %v", err)
				}
			}
		})
	}
}

// TestAttributeNormalization tests the case normalization logic
func TestAttributeNormalization(t *testing.T) {
	archetype := &Archetype{
		Attributes: map[string]float64{"STRENGTH": 10, "Intelligence": 15, "agility": 12},
		Skills:     map[string]float64{"SWORDSMANSHIP": 5, "Magic": 10, "stealth": 3},
	}

	// Normalize attributes
	for k, v := range archetype.Attributes {
		lowerKey := strings.ToLower(k)
		if lowerKey != k {
			archetype.Attributes[lowerKey] = v
			delete(archetype.Attributes, k)
		}
	}

	// Normalize skills
	for k, v := range archetype.Skills {
		lowerKey := strings.ToLower(k)
		if lowerKey != k {
			archetype.Skills[lowerKey] = v
			delete(archetype.Skills, k)
		}
	}

	// Check attributes
	expectedAttrs := map[string]float64{
		"strength":     10,
		"intelligence": 15,
		"agility":      12,
	}
	for key, expected := range expectedAttrs {
		if val, ok := archetype.Attributes[key]; !ok || val != expected {
			t.Errorf("Expected attribute %s=%f, got %f", key, expected, val)
		}
	}

	// Check skills
	expectedSkills := map[string]float64{
		"swordsmanship": 5,
		"magic":         10,
		"stealth":       3,
	}
	for key, expected := range expectedSkills {
		if val, ok := archetype.Skills[key]; !ok || val != expected {
			t.Errorf("Expected skill %s=%f, got %f", key, expected, val)
		}
	}
}

func TestBuildArchetypeOptions(t *testing.T) {
	game := createTestGame()

	// Add test archetypes - mix of player and NPC archetypes
	game.archetypes["Warrior"] = &Archetype{
		ArchetypeName: "Warrior",
		Description:   "A mighty fighter",
		Player:        true,
	}
	game.archetypes["Mage"] = &Archetype{
		ArchetypeName: "Mage",
		Description:   "A powerful spellcaster",
		Player:        true,
	}
	game.archetypes["Rogue"] = &Archetype{
		ArchetypeName: "Rogue",
		Description:   "A stealthy thief",
		Player:        true,
	}
	game.archetypes["Goblin"] = &Archetype{
		ArchetypeName: "Goblin",
		Description:   "A mischievous creature",
		Player:        false, // NPC archetype
	}
	game.archetypes["Guard"] = &Archetype{
		ArchetypeName: "Guard",
		Description:   "A castle guard",
		Player:        false, // NPC archetype
	}

	game.BuildArchetypeOptions()

	// Check that only player archetypes are included
	if len(game.archetypeOptions) != 3 {
		t.Errorf("Expected 3 player archetype options, got %d", len(game.archetypeOptions))
	}

	// Check that options are sorted and only contain player archetypes
	expectedOptions := []string{
		"Mage - A powerful spellcaster",
		"Rogue - A stealthy thief",
		"Warrior - A mighty fighter",
	}

	for i, expected := range expectedOptions {
		if i >= len(game.archetypeOptions) {
			t.Errorf("Missing option at index %d", i)
			continue
		}
		if game.archetypeOptions[i] != expected {
			t.Errorf("Option %d: expected '%s', got '%s'", i, expected, game.archetypeOptions[i])
		}
	}

	// Ensure NPC archetypes are not in the options
	for _, option := range game.archetypeOptions {
		if strings.Contains(option, "Goblin") || strings.Contains(option, "Guard") {
			t.Errorf("NPC archetype found in player options: %s", option)
		}
	}
}

func TestDisplayArchetypes(t *testing.T) {
	game := createTestGame()

	// Add test archetypes
	game.archetypes["Warrior"] = createValidArchetype("Warrior")
	game.archetypes["Mage"] = createValidArchetype("Mage")

	// This function only logs, so we just ensure it doesn't panic
	game.DisplayArchetypes()
}

// TestConcurrentAccess tests for race conditions
func TestConcurrentAccess(t *testing.T) {
	game := createTestGame()

	// Add a prototype
	prototypeID := uuid.Must(uuid.NewV4())
	game.prototypes[prototypeID] = &Prototype{
		name:     "Test Item",
		wearable: true,
		wornOn:   []string{"weapon"},
	}

	// Create a valid archetype
	archetype := &Archetype{
		ArchetypeName: "Warrior",
		Description:   "Test",
		Attributes:    map[string]float64{"str": 10},
		Skills:        map[string]float64{"skill": 5},
		StartingItems: []ArchetypeItem{
			{PrototypeID: prototypeID.String(), Slot: "weapon"},
		},
	}

	// Run concurrent operations
	var wg sync.WaitGroup
	errors := make([]error, 10)

	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func(index int) {
			defer wg.Done()
			errors[index] = game.ValidateArchetype(archetype)
		}(i)
	}

	wg.Wait()

	// Check that no errors occurred
	for i, err := range errors {
		if err != nil {
			t.Errorf("Goroutine %d encountered error: %v", i, err)
		}
	}
}

// Helper function
func contains(s, substr string) bool {
	return strings.Contains(s, substr)
}
