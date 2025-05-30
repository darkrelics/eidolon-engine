package main

import (
	"math"
	"testing"
)

// TestResolveStaticCheck tests the static check mechanics
func TestResolveStaticCheck(t *testing.T) {
	tests := []struct {
		name       string
		aggressor  int
		difficulty int
	}{
		{
			name:       "Equal to difficulty",
			aggressor:  10,
			difficulty: 10,
		},
		{
			name:       "Above difficulty",
			aggressor:  15,
			difficulty: 10,
		},
		{
			name:       "Below difficulty",
			aggressor:  5,
			difficulty: 10,
		},
		{
			name:       "Zero difficulty",
			aggressor:  10,
			difficulty: 0,
		},
		{
			name:       "High difficulty",
			aggressor:  10,
			difficulty: 20,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			outcome := ResolveStaticCheck(tt.aggressor, tt.difficulty)

			// Basic sanity checks
			if math.IsNaN(outcome.Sigma) {
				t.Errorf("Sigma is NaN")
			}
			if outcome.Success != (outcome.Sigma >= 0) {
				t.Errorf("Success flag doesn't match Sigma sign")
			}
		})
	}
}

// TestResolveStaticCheckDistribution tests the statistical properties of static checks
func TestResolveStaticCheckDistribution(t *testing.T) {
	const iterations = 10000

	testCases := []struct {
		name           string
		aggressor      int
		difficulty     int
		expectedWinPct float64
		tolerance      float64
	}{
		{"Equal to difficulty", 10, 10, 0.50, 0.02},
		{"Small advantage", 12, 10, 0.646, 0.02},
		{"Large advantage", 20, 10, 0.943, 0.02},
		{"Small disadvantage", 8, 10, 0.334, 0.02},
		{"Large disadvantage", 0, 10, 0.003, 0.02},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			wins := 0
			for i := 0; i < iterations; i++ {
				outcome := ResolveStaticCheck(tc.aggressor, tc.difficulty)
				if outcome.Success {
					wins++
				}
			}

			actualWinPct := float64(wins) / float64(iterations)
			if math.Abs(actualWinPct-tc.expectedWinPct) > tc.tolerance {
				t.Errorf("Win percentage %.3f outside expected range %.3f±%.3f",
					actualWinPct, tc.expectedWinPct, tc.tolerance)
			}
		})
	}
}

// TestResolveStaticCheckWithXP tests the static check with XP mechanics
func TestResolveStaticCheckWithXP(t *testing.T) {
	tests := []struct {
		name       string
		skill      string
		attr       string
		skillVal   float64
		attrVal    float64
		difficulty int
	}{
		{
			name:       "Basic check with XP",
			skill:      "stealth",
			attr:       "dexterity",
			skillVal:   5.0,
			attrVal:    5.0,
			difficulty: 10,
		},
		{
			name:       "High skill check",
			skill:      "perception",
			attr:       "wisdom",
			skillVal:   8.0,
			attrVal:    5.0,
			difficulty: 10,
		},
		{
			name:       "Low skill check",
			skill:      "athletics",
			attr:       "strength",
			skillVal:   2.0,
			attrVal:    3.0,
			difficulty: 10,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Create a test character
			character := &Character{
				name:       "TestChar",
				skills:     make(map[string]float64),
				attributes: make(map[string]float64),
			}
			character.skills[tt.skill] = tt.skillVal
			character.attributes[tt.attr] = tt.attrVal

			// Store initial values
			initialSkill := character.GetSkill(tt.skill)
			initialAttr := character.GetAttribute(tt.attr)

			// Perform the check
			outcome := ResolveStaticCheckWithXP(character, tt.skill, tt.attr, tt.difficulty)

			// Verify outcome structure
			if math.IsNaN(outcome.Sigma) {
				t.Errorf("Sigma is NaN")
			}
			if outcome.Success != (outcome.Sigma >= 0) {
				t.Errorf("Success flag doesn't match Sigma sign")
			}

			// Verify XP was awarded (skill should increase)
			finalSkill := character.GetSkill(tt.skill)
			finalAttr := character.GetAttribute(tt.attr)

			if finalSkill <= initialSkill {
				t.Errorf("Skill XP not awarded: initial=%.3f, final=%.3f", initialSkill, finalSkill)
			}
			if finalAttr <= initialAttr {
				t.Errorf("Attribute XP not awarded: initial=%.3f, final=%.3f", initialAttr, finalAttr)
			}
		})
	}
}

// TestResolveStaticCheckWithXPNilCharacter tests handling of nil character
func TestResolveStaticCheckWithXPNilCharacter(t *testing.T) {
	// This should not panic
	defer func() {
		if r := recover(); r != nil {
			t.Errorf("ResolveStaticCheckWithXP panicked with nil character: %v", r)
		}
	}()

	outcome := ResolveStaticCheckWithXP(nil, "stealth", "dexterity", 10)
	// Should still return a valid outcome even with nil character
	if outcome.Success && outcome.Sigma < 0 {
		t.Errorf("Invalid outcome returned for nil character")
	}
}
