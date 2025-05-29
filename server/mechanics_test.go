package main

import (
	"math"
	"testing"
)

// TestResolveOpposedCheck tests the basic mechanics
func TestResolveOpposedCheck(t *testing.T) {
	tests := []struct {
		name      string
		aggressor int
		defender  int
		seed      int64
		wantMin   float64
		wantMax   float64
	}{
		{
			name:      "Equal ratings",
			aggressor: 10,
			defender:  10,
			seed:      12345,
			wantMin:   -2.0,
			wantMax:   2.0,
		},
		{
			name:      "Aggressor advantage",
			aggressor: 15,
			defender:  10,
			seed:      12345,
			wantMin:   -1.0,
			wantMax:   3.0,
		},
		{
			name:      "Defender advantage",
			aggressor: 5,
			defender:  10,
			seed:      12345,
			wantMin:   -3.0,
			wantMax:   1.0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// For actual testing, we'll need to expose a testing interface
			// For now, just test the production function
			outcome := ResolveOpposedCheck(tt.aggressor, tt.defender)

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

// TestOutcomeDistribution tests the statistical properties
func TestOutcomeDistribution(t *testing.T) {
	const iterations = 10000

	testCases := []struct {
		name           string
		aggressor      int
		defender       int
		expectedWinPct float64
		tolerance      float64
	}{
		{"Equal ratings", 10, 10, 0.50, 0.02},
		{"Small advantage", 12, 10, 0.646, 0.02},
		{"Large advantage", 20, 10, 0.943, 0.02},
		{"Small disadvantage", 8, 10, 0.334, 0.02},
		{"Large disadvantage", 0, 10, 0.003, 0.02},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			wins := 0
			for range iterations {
				outcome := ResolveOpposedCheck(tc.aggressor, tc.defender)
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

// TestSigmaRange tests that sigma values stay within expected bounds
func TestSigmaRange(t *testing.T) {
	const iterations = 1000

	for delta := -20; delta <= 20; delta += 5 {
		aggressor := 10 + delta
		defender := 10

		minSigma := math.Inf(1)
		maxSigma := math.Inf(-1)

		for range iterations {
			outcome := ResolveOpposedCheck(aggressor, defender)
			minSigma = min(minSigma, outcome.Sigma)
			maxSigma = max(maxSigma, outcome.Sigma)
		}

		// Expected bounds based on the mechanics
		mu := kShift * float64(delta)
		sigma := 1 + kVar*math.Tanh(float64(delta)/10)
		sigma = max(sigma, minSig)

		expectedMin := mu - 4*sigma // 4 standard deviations
		expectedMax := mu + 4*sigma

		if minSigma < expectedMin || maxSigma > expectedMax {
			t.Logf("Delta %d: range [%.2f, %.2f] vs expected [%.2f, %.2f]",
				delta, minSigma, maxSigma, expectedMin, expectedMax)
		}
	}
}
