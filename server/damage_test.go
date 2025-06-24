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
	"sync"
	"testing"
	"time"

	"github.com/gofrs/uuid/v5"
)

func TestDamageTypes(t *testing.T) {
	tests := []struct {
		damageType     string
		expectedDuration time.Duration
	}{
		{DamageTypeBashing, BashingHealTime},
		{DamageTypeLethal, LethalHealTime},
		{DamageTypeAggravated, AggravatedHealTime},
		{"unknown", BashingHealTime}, // Default case
	}

	for _, tt := range tests {
		t.Run(tt.damageType, func(t *testing.T) {
			duration := GetHealingDuration(tt.damageType)
			if duration != tt.expectedDuration {
				t.Errorf("GetHealingDuration(%s) = %v, want %v", tt.damageType, duration, tt.expectedDuration)
			}
		})
	}
}

func TestTakeDamage(t *testing.T) {
	// Create test character
	char := &Character{
		id:               uuid.Must(uuid.NewV4()),
		name:             "TestChar",
		health:           10,
		maxHealth:        10,
		wounds:           []Wound{},
		mutex:            sync.RWMutex{},
		playerCommandOut: make(chan string, 10),
	}

	// Test taking damage
	char.TakeDamage(DamageTypeBashing, 3)

	// Check wounds
	if len(char.wounds) != 3 {
		t.Errorf("Expected 3 wounds, got %d", len(char.wounds))
	}

	// Check health
	if char.health != 7 {
		t.Errorf("Expected health 7, got %d", char.health)
	}

	// Check damage type
	for _, wound := range char.wounds {
		if wound.DamageType != DamageTypeBashing {
			t.Errorf("Expected bashing damage, got %s", wound.DamageType)
		}
	}

	// Drain message channel
	<-char.playerCommandOut
}

func TestMixedDamage(t *testing.T) {
	char := &Character{
		id:               uuid.Must(uuid.NewV4()),
		name:             "TestChar",
		health:           10,
		maxHealth:        10,
		wounds:           []Wound{},
		mutex:            sync.RWMutex{},
		playerCommandOut: make(chan string, 10),
	}

	// Apply different damage types
	char.TakeDamage(DamageTypeBashing, 2)
	char.TakeDamage(DamageTypeLethal, 2)
	char.TakeDamage(DamageTypeAggravated, 1)

	// Check total wounds
	if len(char.wounds) != 5 {
		t.Errorf("Expected 5 wounds, got %d", len(char.wounds))
	}

	// Check health
	if char.health != 5 {
		t.Errorf("Expected health 5, got %d", char.health)
	}

	// Check wound counts by type
	counts := char.GetWoundsByType()
	if counts[DamageTypeBashing] != 2 {
		t.Errorf("Expected 2 bashing wounds, got %d", counts[DamageTypeBashing])
	}
	if counts[DamageTypeLethal] != 2 {
		t.Errorf("Expected 2 lethal wounds, got %d", counts[DamageTypeLethal])
	}
	if counts[DamageTypeAggravated] != 1 {
		t.Errorf("Expected 1 aggravated wound, got %d", counts[DamageTypeAggravated])
	}

	// Drain message channels
	for i := 0; i < 3; i++ {
		<-char.playerCommandOut
	}
}

func TestHealing(t *testing.T) {
	char := &Character{
		id:               uuid.Must(uuid.NewV4()),
		name:             "TestChar",
		health:           10,
		maxHealth:        10,
		wounds:           []Wound{},
		mutex:            sync.RWMutex{},
		playerCommandOut: make(chan string, 10),
		player:           &Player{}, // Need non-nil player for healing messages
	}

	// Add wounds that will heal immediately
	now := time.Now()
	char.wounds = []Wound{
		{DamageType: DamageTypeBashing, HealAt: now.Add(-1 * time.Minute)},
		{DamageType: DamageTypeBashing, HealAt: now.Add(5 * time.Minute)},
		{DamageType: DamageTypeLethal, HealAt: now.Add(-1 * time.Hour)},
	}
	char.health = 7

	// Calculate healing
	char.CalculateCurrentHealth()

	// Should have healed 2 wounds
	if len(char.wounds) != 1 {
		t.Errorf("Expected 1 wound remaining, got %d", len(char.wounds))
	}

	// Check health restored
	if char.health != 9 {
		t.Errorf("Expected health 9, got %d", char.health)
	}

	// Check healing message
	select {
	case msg := <-char.playerCommandOut:
		if msg == "" {
			t.Error("Expected healing message")
		}
	default:
		t.Error("No healing message received")
	}
}

func TestDeath(t *testing.T) {
	char := &Character{
		id:               uuid.Must(uuid.NewV4()),
		name:             "TestChar",
		health:           10,
		maxHealth:        10,
		wounds:           []Wound{},
		mutex:            sync.RWMutex{},
		charState:        "standing",
		playerCommandOut: make(chan string, 10),
	}

	// Take fatal damage
	char.TakeDamage(DamageTypeLethal, 10)

	// Check death state
	if char.charState != "dead" {
		t.Errorf("Expected dead state, got %s", char.charState)
	}

	// Check health
	if char.health != 0 {
		t.Errorf("Expected health 0, got %d", char.health)
	}

	// Drain messages
	<-char.playerCommandOut // Damage message
	<-char.playerCommandOut // Death message
}

func TestOfflineHealing(t *testing.T) {
	game := &Game{
		ctx:        context.Background(),
		mutex:      sync.RWMutex{},
		rooms:      map[int64]*Room{0: {roomID: 0}},
		characters: make(map[uuid.UUID]*Character),
	}

	player := &Player{
		id: uuid.Must(uuid.NewV4()),
		server: &Server{game: game},
	}

	// Create character data with old wounds
	now := time.Now()
	cd := &CharacterData{
		CharacterID: uuid.Must(uuid.NewV4()).String(),
		PlayerID:    player.id.String(),
		CharacterName: "TestChar",
		Health:      5,
		MaxHealth:   10,
		Wounds: []Wound{
			{DamageType: DamageTypeBashing, HealAt: now.Add(-1 * time.Hour)}, // Should heal
			{DamageType: DamageTypeLethal, HealAt: now.Add(1 * time.Hour)},   // Should remain
		},
		RoomID: 0,
		Attributes: make(map[string]float64),
		Skills:     make(map[string]float64),
		Inventory:  make(map[string]string),
	}

	// Load character (which triggers offline healing)
	char, err := LoadCharacter(player, uuid.Must(uuid.FromString(cd.CharacterID)))
	if err == nil {
		t.Error("Expected error loading non-existent character")
	}

	// Instead, test by creating character manually
	char = &Character{
		game:             game,
		player:           player,
		mutex:            sync.RWMutex{},
		playerCommandOut: make(chan string, 10),
		attributes:       make(map[string]float64),
		skills:           make(map[string]float64),
		inventory:        make(map[string]*Item),
	}

	// Manually set data
	char.id = uuid.Must(uuid.FromString(cd.CharacterID))
	char.name = cd.CharacterName
	char.health = cd.Health
	char.maxHealth = cd.MaxHealth
	char.wounds = cd.Wounds

	// Calculate offline healing
	char.CalculateCurrentHealth()

	// Should have 1 wound remaining
	if len(char.wounds) != 1 {
		t.Errorf("Expected 1 wound after offline healing, got %d", len(char.wounds))
	}

	// Health should be updated
	if char.health != 9 {
		t.Errorf("Expected health 9 after offline healing, got %d", char.health)
	}
}