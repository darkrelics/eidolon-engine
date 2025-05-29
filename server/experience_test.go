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
	"math"
	"sync"
	"testing"
	"time"

	"github.com/gofrs/uuid/v5"
)

func TestCalculateXPRequirement(t *testing.T) {
	tests := []struct {
		name     string
		score    float64
		expected float64
	}{
		{"Level 0", 0.0, 10.0},
		{"Level 1", 1.0, 35.0},
		{"Level 2", 2.0, 122.5},
		{"Level 3", 3.0, 428.75},
		{"Level 4", 4.0, 1500.625},
		{"Level 5", 5.0, 5252.1875},
		{"Level 6", 6.0, 18382.65625},
		{"Fractional", 2.5, 229.176515},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := CalculateXPRequirement(tt.score)
			if math.Abs(result-tt.expected) > 0.0001 {
				t.Errorf("CalculateXPRequirement(%f) = %f, want %f", tt.score, result, tt.expected)
			}
		})
	}
}

func TestCalculateVarianceModifier(t *testing.T) {
	tests := []struct {
		name               string
		myEffective        int
		opponentEffective  int
		expectedModifier   float64
	}{
		{"Even match", 10, 10, 1.0},
		{"Weaker opponent", 10, 5, 0.25},
		{"Stronger opponent", 5, 10, 0.25},
		{"Very weak opponent", 10, 2, 0.04},
		{"Very strong opponent", 2, 10, 0.04},
		{"Zero vs zero", 0, 0, 1.0},
		{"Zero vs non-zero", 0, 10, 0.0},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := CalculateVarianceModifier(tt.myEffective, tt.opponentEffective)
			if math.Abs(result-tt.expectedModifier) > 0.0001 {
				t.Errorf("CalculateVarianceModifier(%d, %d) = %f, want %f", 
					tt.myEffective, tt.opponentEffective, result, tt.expectedModifier)
			}
		})
	}
}

func TestCalculateFinalXP(t *testing.T) {
	tests := []struct {
		name             string
		baseXP           float64
		varianceModifier float64
		success          bool
		expectedXP       float64
	}{
		{"Success even match", 0.25, 1.0, true, 0.25},
		{"Failure even match", 0.25, 1.0, false, 0.125},
		{"Success weak opponent", 0.25, 0.25, true, 0.0625},
		{"Failure weak opponent", 0.25, 0.25, false, 0.03125},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := CalculateFinalXP(tt.baseXP, tt.varianceModifier, tt.success)
			if math.Abs(result-tt.expectedXP) > 0.0001 {
				t.Errorf("CalculateFinalXP(%f, %f, %v) = %f, want %f", 
					tt.baseXP, tt.varianceModifier, tt.success, result, tt.expectedXP)
			}
		})
	}
}

func TestCalculateScoreIncrement(t *testing.T) {
	tests := []struct {
		name          string
		xpGained      float64
		currentScore  float64
		expectedIncr  float64
	}{
		{"Small XP at level 0", 0.25, 0.0, 0.025},
		{"Large XP at level 0", 10.0, 0.0, 1.0},
		{"Small XP at level 5", 0.25, 5.0, 0.0000475839},
		{"At max score", 1.0, 10.0, 0.0},
		{"Near max score", 100.0, 9.99, 0.01},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := CalculateScoreIncrement(tt.xpGained, tt.currentScore)
			if math.Abs(result-tt.expectedIncr) > 0.0001 {
				t.Errorf("CalculateScoreIncrement(%f, %f) = %f, want %f", 
					tt.xpGained, tt.currentScore, result, tt.expectedIncr)
			}
		})
	}
}

func TestAwardSkillXP(t *testing.T) {
	character := &Character{
		id:         uuid.Must(uuid.NewV4()),
		name:       "TestChar",
		skills:     make(map[string]float64),
		attributes: make(map[string]float64),
		mutex:      sync.RWMutex{},
		lastEdited: time.Now(),
	}

	// Test awarding XP to a new skill
	character.AwardSkillXP("swordsmanship", 0.25)
	expectedValue := 0.025
	if math.Abs(character.skills["swordsmanship"]-expectedValue) > 0.0001 {
		t.Errorf("Expected swordsmanship skill to be %f, got %f", expectedValue, character.skills["swordsmanship"])
	}

	// Test awarding more XP to existing skill
	previousValue := character.skills["swordsmanship"]
	character.AwardSkillXP("swordsmanship", 0.25)
	// The increment will be slightly less than 0.025 due to the increased XP requirement
	if character.skills["swordsmanship"] <= previousValue {
		t.Errorf("Expected swordsmanship skill to increase from %f, got %f", previousValue, character.skills["swordsmanship"])
	}

	// Test zero XP award
	initialValue := character.skills["swordsmanship"]
	character.AwardSkillXP("swordsmanship", 0.0)
	if character.skills["swordsmanship"] != initialValue {
		t.Errorf("Expected swordsmanship skill to remain %f, got %f", initialValue, character.skills["swordsmanship"])
	}

	// Test max score cap
	character.skills["mastered"] = 9.99
	character.AwardSkillXP("mastered", 100.0)
	// Due to the calculation, it might not reach exactly 10.0
	if character.skills["mastered"] < 9.99 || character.skills["mastered"] > 10.0 {
		t.Errorf("Expected mastered skill to be capped near 10.0, got %f", character.skills["mastered"])
	}
}

func TestAwardAttributeXP(t *testing.T) {
	character := &Character{
		id:         uuid.Must(uuid.NewV4()),
		name:       "TestChar",
		skills:     make(map[string]float64),
		attributes: make(map[string]float64),
		mutex:      sync.RWMutex{},
		lastEdited: time.Now(),
	}

	// Test awarding XP to a new attribute
	character.AwardAttributeXP("strength", 0.025)
	expectedValue := 0.0025
	if math.Abs(character.attributes["strength"]-expectedValue) > 0.0001 {
		t.Errorf("Expected strength attribute to be %f, got %f", expectedValue, character.attributes["strength"])
	}

	// Test awarding more XP to existing attribute
	previousValue := character.attributes["strength"]
	character.AwardAttributeXP("strength", 0.025)
	// The increment will be slightly less due to increased XP requirement
	if character.attributes["strength"] <= previousValue {
		t.Errorf("Expected strength attribute to increase from %f, got %f", previousValue, character.attributes["strength"])
	}
}

func TestAwardExperience(t *testing.T) {
	// Create test characters
	aggressor := &Character{
		id:         uuid.Must(uuid.NewV4()),
		name:       "Aggressor",
		skills:     map[string]float64{"combat": 5.0},
		attributes: map[string]float64{"strength": 5.0},
		mutex:      sync.RWMutex{},
		lastEdited: time.Now(),
	}

	defender := &Character{
		id:         uuid.Must(uuid.NewV4()),
		name:       "Defender",
		skills:     map[string]float64{"defense": 3.0},
		attributes: map[string]float64{"agility": 3.0},
		mutex:      sync.RWMutex{},
		lastEdited: time.Now(),
	}

	context := ExperienceContext{
		AggressorSkill:     "combat",
		AggressorAttr:      "strength",
		DefenderSkill:      "defense",
		DefenderAttr:       "agility",
		AggressorSuccess:   true,
		DefenderSuccess:    false,
		AggressorEffective: 10,
		DefenderEffective:  6,
	}

	// Award experience
	AwardExperience(aggressor, defender, context)

	// Check aggressor gained XP (less because fighting weaker opponent)
	if aggressor.skills["combat"] <= 5.0 {
		t.Error("Expected aggressor combat skill to increase")
	}
	if aggressor.attributes["strength"] <= 5.0 {
		t.Error("Expected aggressor strength attribute to increase")
	}

	// Check defender gained XP (more because fighting stronger opponent)
	if defender.skills["defense"] <= 3.0 {
		t.Error("Expected defender defense skill to increase")
	}
	if defender.attributes["agility"] <= 3.0 {
		t.Error("Expected defender agility attribute to increase")
	}

	// Verify defender gains more XP than aggressor due to variance modifier
	aggressorSkillGain := aggressor.skills["combat"] - 5.0
	defenderSkillGain := defender.skills["defense"] - 3.0
	if defenderSkillGain <= aggressorSkillGain {
		t.Errorf("Expected defender to gain more XP than aggressor, but aggressor gained %f and defender gained %f",
			aggressorSkillGain, defenderSkillGain)
	}
}

func TestResolveOpposedCheckWithXP(t *testing.T) {
	// Create test characters
	char1 := &Character{
		id:         uuid.Must(uuid.NewV4()),
		name:       "Fighter1",
		skills:     map[string]float64{"combat": 5.0},
		attributes: map[string]float64{"strength": 5.0},
		mutex:      sync.RWMutex{},
		lastEdited: time.Now(),
	}

	char2 := &Character{
		id:         uuid.Must(uuid.NewV4()),
		name:       "Fighter2",
		skills:     map[string]float64{"combat": 3.0},
		attributes: map[string]float64{"strength": 3.0},
		mutex:      sync.RWMutex{},
		lastEdited: time.Now(),
	}

	// Store initial values
	char1InitialSkill := char1.skills["combat"]
	char2InitialSkill := char2.skills["combat"]

	// Perform check with XP
	outcome := ResolveOpposedCheckWithXP(char1, char2, "combat", "strength", "combat", "strength")

	// Verify outcome is valid
	if outcome.Sigma == 0 {
		t.Error("Expected non-zero Sigma value")
	}

	// Verify both characters gained XP
	if char1.skills["combat"] <= char1InitialSkill {
		t.Error("Expected char1 combat skill to increase")
	}
	if char2.skills["combat"] <= char2InitialSkill {
		t.Error("Expected char2 combat skill to increase")
	}
}

func TestExperienceProgressionCurve(t *testing.T) {
	character := &Character{
		id:         uuid.Must(uuid.NewV4()),
		name:       "TestChar",
		skills:     make(map[string]float64),
		attributes: make(map[string]float64),
		mutex:      sync.RWMutex{},
		lastEdited: time.Now(),
	}

	// Simulate progression from 0 to 1
	actionsTo1 := 0
	for character.skills["test"] < 1.0 {
		character.AwardSkillXP("test", 0.25)
		actionsTo1++
	}

	// Should take approximately 80 actions to reach level 1 (with 0.25 XP per action)
	if actionsTo1 < 70 || actionsTo1 > 90 {
		t.Errorf("Expected ~80 actions to reach level 1, got %d", actionsTo1)
	}

	// Reset to level 5 and test progression to 6
	character.skills["test"] = 5.0
	actionsTo6 := 0
	for character.skills["test"] < 6.0 {
		character.AwardSkillXP("test", 0.25)
		actionsTo6++
		if actionsTo6 > 50000 {
			break // Prevent infinite loop
		}
	}

	// Should take approximately 42000 actions to go from 5 to 6
	if actionsTo6 < 35000 || actionsTo6 > 50000 {
		t.Errorf("Expected ~42000 actions to go from level 5 to 6, got %d", actionsTo6)
	}
}