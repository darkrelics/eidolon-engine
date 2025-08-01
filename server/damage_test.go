/*
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

*/

package main

import (
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gofrs/uuid/v5"
)

func TestDamageTypes(t *testing.T) {
	tests := []struct {
		damageType       string
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
	if char.GetHealth() != 7 {
		t.Errorf("Expected health 7, got %d", char.GetHealth())
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
	if char.GetHealth() != 5 {
		t.Errorf("Expected health 5, got %d", char.GetHealth())
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

	// Calculate healing
	char.CalculateCurrentHealth()

	// Should have healed 2 wounds
	if len(char.wounds) != 1 {
		t.Errorf("Expected 1 wound remaining, got %d", len(char.wounds))
	}

	// Check health restored
	if char.GetHealth() != 9 {
		t.Errorf("Expected health 9, got %d", char.GetHealth())
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
		maxHealth:        10,
		wounds:           []Wound{},
		mutex:            sync.RWMutex{},
		charState:        CharStateStanding,
		playerCommandOut: make(chan string, 10),
	}

	// Take fatal damage (all lethal)
	char.TakeDamage(DamageTypeLethal, 10)

	// Check death state
	if char.charState != CharStateDead {
		t.Errorf("Expected dead state, got %s", char.charState)
	}

	// Check health
	if char.GetHealth() != 0 {
		t.Errorf("Expected health 0, got %d", char.GetHealth())
	}

	// Drain messages
	<-char.playerCommandOut // Damage message
	<-char.playerCommandOut // Death message
}

func TestUnconscious(t *testing.T) {
	char := &Character{
		id:               uuid.Must(uuid.NewV4()),
		name:             "TestChar",
		maxHealth:        10,
		wounds:           []Wound{},
		mutex:            sync.RWMutex{},
		charState:        CharStateStanding,
		playerCommandOut: make(chan string, 10),
	}

	// Take damage that includes bashing
	char.TakeDamage(DamageTypeBashing, 5)
	char.TakeDamage(DamageTypeLethal, 5)

	// Should be unconscious, not dead
	if char.charState != CharStateUnconscious {
		t.Errorf("Expected unconscious state, got %s", char.charState)
	}

	// Drain messages
	<-char.playerCommandOut // Bashing damage
	<-char.playerCommandOut // Lethal damage
	<-char.playerCommandOut // Unconscious message
}

func TestDamageConversionWhileUnconscious(t *testing.T) {
	char := &Character{
		id:               uuid.Must(uuid.NewV4()),
		name:             "TestChar",
		maxHealth:        10,
		wounds:           make([]Wound, 10),
		mutex:            sync.RWMutex{},
		charState:        CharStateUnconscious,
		playerCommandOut: make(chan string, 10),
	}

	// Fill with bashing wounds
	for i := 0; i < 10; i++ {
		char.wounds[i] = Wound{DamageType: DamageTypeBashing, HealAt: time.Now().Add(1 * time.Hour)}
	}

	// Test bashing converts to lethal when unconscious
	char.TakeDamage(DamageTypeBashing, 2)

	// Check that we still have 10 wounds
	if len(char.wounds) != 12 {
		t.Errorf("Expected 12 wounds, got %d", len(char.wounds))
	}

	// Count wound types
	counts := char.GetWoundsByType()
	if counts[DamageTypeLethal] != 2 {
		t.Errorf("Expected 2 lethal wounds from converted bashing, got %d", counts[DamageTypeLethal])
	}

	// Test lethal replaces bashing
	char.TakeDamage(DamageTypeLethal, 3)

	// We had 12 wounds (10 bashing + 2 lethal from conversion)
	// 3 bashing replaced with lethal, no new wounds can be added since already over max
	// So still 12 wounds total: 7 bashing + 5 lethal
	if len(char.wounds) != 12 {
		t.Errorf("Expected 12 wounds after replacement, got %d", len(char.wounds))
	}

	counts = char.GetWoundsByType()
	if counts[DamageTypeBashing] != 7 {
		t.Errorf("Expected 7 bashing wounds remaining, got %d", counts[DamageTypeBashing])
	}
	if counts[DamageTypeLethal] != 5 {
		t.Errorf("Expected 5 lethal wounds total, got %d", counts[DamageTypeLethal])
	}

	// Drain messages
	for i := 0; i < 2; i++ {
		<-char.playerCommandOut
	}
}

func TestHealingFromUnconscious(t *testing.T) {
	char := &Character{
		id:               uuid.Must(uuid.NewV4()),
		name:             "TestChar",
		maxHealth:        3,
		wounds:           []Wound{},
		mutex:            sync.RWMutex{},
		charState:        CharStateUnconscious,
		playerCommandOut: make(chan string, 10),
		player:           &Player{},
	}

	// Add wounds that will heal
	now := time.Now()
	char.wounds = []Wound{
		{DamageType: DamageTypeBashing, HealAt: now.Add(-1 * time.Minute)}, // Will heal
		{DamageType: DamageTypeBashing, HealAt: now.Add(1 * time.Hour)},
		{DamageType: DamageTypeLethal, HealAt: now.Add(1 * time.Hour)},
	}

	// Calculate healing
	char.CalculateCurrentHealth()

	// Should regain consciousness
	if char.charState != CharStateStanding {
		t.Errorf("Expected standing state after healing, got %s", char.charState)
	}

	// Health should be 1
	if char.GetHealth() != 1 {
		t.Errorf("Expected health 1, got %d", char.GetHealth())
	}

	// Check messages
	foundConsciousness := false
	for i := 0; i < 2; i++ {
		msg := <-char.playerCommandOut
		if strings.Contains(msg, "consciousness") {
			foundConsciousness = true
		}
	}

	if !foundConsciousness {
		t.Error("Expected consciousness message")
	}
}

func TestDeadCharacterNoHealing(t *testing.T) {
	char := &Character{
		id:               uuid.Must(uuid.NewV4()),
		name:             "TestChar",
		maxHealth:        10,
		wounds:           []Wound{},
		mutex:            sync.RWMutex{},
		charState:        CharStateDead,
		playerCommandOut: make(chan string, 10),
		player:           &Player{},
	}

	// Add wounds that would normally heal
	now := time.Now()
	char.wounds = []Wound{
		{DamageType: DamageTypeBashing, HealAt: now.Add(-1 * time.Hour)},
		{DamageType: DamageTypeLethal, HealAt: now.Add(-1 * time.Hour)},
	}

	// Try to calculate healing
	char.CalculateCurrentHealth()

	// Should still have 2 wounds (no healing for dead characters)
	if len(char.wounds) != 2 {
		t.Errorf("Expected 2 wounds (no healing), got %d", len(char.wounds))
	}

	// Health should remain 0
	if char.GetHealth() != 0 {
		t.Errorf("Expected health 0, got %d", char.GetHealth())
	}

	// State should remain dead
	if char.charState != CharStateDead {
		t.Errorf("Expected dead state, got %s", char.charState)
	}
}

func TestOfflineHealing(t *testing.T) {
	char := &Character{
		id:               uuid.Must(uuid.NewV4()),
		name:             "TestChar",
		maxHealth:        10,
		wounds:           []Wound{},
		mutex:            sync.RWMutex{},
		charState:        CharStateStanding,
		playerCommandOut: make(chan string, 10),
		player:           &Player{},
	}

	// Add wounds with different heal times
	now := time.Now()
	char.wounds = []Wound{
		{DamageType: DamageTypeBashing, HealAt: now.Add(-1 * time.Hour)}, // Should heal
		{DamageType: DamageTypeLethal, HealAt: now.Add(1 * time.Hour)},   // Should remain
	}

	// Calculate offline healing
	char.CalculateCurrentHealth()

	// Should have 1 wound remaining
	if len(char.wounds) != 1 {
		t.Errorf("Expected 1 wound after offline healing, got %d", len(char.wounds))
	}

	// Health should be updated
	if char.GetHealth() != 9 {
		t.Errorf("Expected health 9 after offline healing, got %d", char.GetHealth())
	}

	// Check healing message was sent
	select {
	case msg := <-char.playerCommandOut:
		if !strings.Contains(msg, "heal") {
			t.Error("Expected healing message")
		}
	default:
		t.Error("No healing message received")
	}
}
