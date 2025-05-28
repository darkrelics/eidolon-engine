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
	"testing"
)

func TestTokenizeInput(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected []string
	}{
		{
			name:     "Simple command",
			input:    "look around",
			expected: []string{"look", "around"},
		},
		{
			name:     "Command with multiple spaces",
			input:    "go    north",
			expected: []string{"go", "north"},
		},
		{
			name:     "Command with tabs",
			input:    "get\tsword",
			expected: []string{"get", "sword"},
		},
		{
			name:     "Command with quotes",
			input:    `say "hello world"`,
			expected: []string{"say", "hello world"},
		},
		{
			name:     "Command with quotes and spaces",
			input:    `say "hello   world"`,
			expected: []string{"say", "hello   world"},
		},
		{
			name:     "Command with leading/trailing spaces",
			input:    "  look  ",
			expected: []string{"look"},
		},
		{
			name:     "Empty input",
			input:    "",
			expected: []string{},
		},
		{
			name:     "Only spaces",
			input:    "   ",
			expected: []string{},
		},
		{
			name:     "Control characters filtered",
			input:    "look\x00\x01around",
			expected: []string{"lookaround"},
		},
		{
			name:     "Unclosed quote",
			input:    `say "hello world`,
			expected: []string{"say", "hello world"},
		},
		{
			name:     "Multiple quoted sections",
			input:    `put "red sword" in "blue chest"`,
			expected: []string{"put", "red sword", "in", "blue chest"},
		},
		{
			name:     "Empty quotes",
			input:    `say ""`,
			expected: []string{"say"},
		},
		{
			name:     "Single word",
			input:    "quit",
			expected: []string{"quit"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := tokenizeInput(tt.input)
			if len(result) != len(tt.expected) {
				t.Errorf("tokenizeInput() returned %d tokens, expected %d", len(result), len(tt.expected))
				t.Errorf("Got: %v", result)
				t.Errorf("Expected: %v", tt.expected)
				return
			}
			for i, token := range result {
				if token != tt.expected[i] {
					t.Errorf("tokenizeInput() token[%d] = %q, expected %q", i, token, tt.expected[i])
				}
			}
		})
	}
}

func TestFuzzyMatchOrdinal(t *testing.T) {
	// Initialize ordinal index for testing
	buildOrdinalIndex()

	tests := []struct {
		name          string
		input         string
		expectedWord  string
		expectedPos   int
		expectedFound bool
	}{
		{
			name:          "Exact match first",
			input:         "first",
			expectedWord:  "first",
			expectedPos:   1,
			expectedFound: true,
		},
		{
			name:          "Exact match tenth",
			input:         "tenth",
			expectedWord:  "tenth",
			expectedPos:   10,
			expectedFound: true,
		},
		{
			name:          "Case insensitive",
			input:         "SECOND",
			expectedWord:  "second",
			expectedPos:   2,
			expectedFound: true,
		},
		{
			name:          "With spaces",
			input:         "  third  ",
			expectedWord:  "third",
			expectedPos:   3,
			expectedFound: true,
		},
		{
			name:          "Close match - typo",
			input:         "frist",
			expectedWord:  "first",
			expectedPos:   1,
			expectedFound: true,
		},
		{
			name:          "Close match - missing letter",
			input:         "secon",
			expectedWord:  "second",
			expectedPos:   2,
			expectedFound: true,
		},
		{
			name:          "Not an ordinal",
			input:         "sword",
			expectedWord:  "",
			expectedPos:   0,
			expectedFound: false,
		},
		{
			name:          "Empty input",
			input:         "",
			expectedWord:  "",
			expectedPos:   0,
			expectedFound: false,
		},
		{
			name:          "Too different",
			input:         "xyz",
			expectedWord:  "",
			expectedPos:   0,
			expectedFound: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			word, pos, found := fuzzyMatchOrdinal(tt.input)
			if found != tt.expectedFound {
				t.Errorf("fuzzyMatchOrdinal() found = %v, expected %v", found, tt.expectedFound)
			}
			if word != tt.expectedWord {
				t.Errorf("fuzzyMatchOrdinal() word = %q, expected %q", word, tt.expectedWord)
			}
			if pos != tt.expectedPos {
				t.Errorf("fuzzyMatchOrdinal() position = %d, expected %d", pos, tt.expectedPos)
			}
		})
	}
}

func TestParseTargetWithOrdinal(t *testing.T) {
	// Initialize ordinal index for testing
	buildOrdinalIndex()

	tests := []struct {
		name             string
		input            string
		expectedPosition int
		expectedItem     string
		expectedHasOrd   bool
	}{
		{
			name:             "Single word",
			input:            "sword",
			expectedPosition: 1,
			expectedItem:     "sword",
			expectedHasOrd:   false,
		},
		{
			name:             "Ordinal with item",
			input:            "second sword",
			expectedPosition: 2,
			expectedItem:     "sword",
			expectedHasOrd:   true,
		},
		{
			name:             "Third item",
			input:            "third goblin",
			expectedPosition: 3,
			expectedItem:     "goblin",
			expectedHasOrd:   true,
		},
		{
			name:             "Multiple words without ordinal",
			input:            "red sword",
			expectedPosition: 1,
			expectedItem:     "red sword",
			expectedHasOrd:   false,
		},
		{
			name:             "Ordinal with multi-word item",
			input:            "first red sword",
			expectedPosition: 1,
			expectedItem:     "red sword",
			expectedHasOrd:   true,
		},
		{
			name:             "Case insensitive ordinal",
			input:            "SECOND door",
			expectedPosition: 2,
			expectedItem:     "door",
			expectedHasOrd:   true,
		},
		{
			name:             "Fuzzy matched ordinal",
			input:            "frist sword",
			expectedPosition: 1,
			expectedItem:     "sword",
			expectedHasOrd:   true,
		},
		{
			name:             "Empty input",
			input:            "",
			expectedPosition: 1,
			expectedItem:     "",
			expectedHasOrd:   false,
		},
		{
			name:             "Only spaces",
			input:            "   ",
			expectedPosition: 1,
			expectedItem:     "",
			expectedHasOrd:   false,
		},
		{
			name:             "Twentieth item",
			input:            "twentieth potion",
			expectedPosition: 20,
			expectedItem:     "potion",
			expectedHasOrd:   true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			pos, item, hasOrd := ParseTargetWithOrdinal(tt.input)
			if pos != tt.expectedPosition {
				t.Errorf("ParseTargetWithOrdinal() position = %d, expected %d", pos, tt.expectedPosition)
			}
			if item != tt.expectedItem {
				t.Errorf("ParseTargetWithOrdinal() item = %q, expected %q", item, tt.expectedItem)
			}
			if hasOrd != tt.expectedHasOrd {
				t.Errorf("ParseTargetWithOrdinal() hasOrdinal = %v, expected %v", hasOrd, tt.expectedHasOrd)
			}
		})
	}
}

func TestExtractBaseNoun(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected string
	}{
		{
			name:     "Single word",
			input:    "door",
			expected: "door",
		},
		{
			name:     "Two words",
			input:    "red door",
			expected: "door",
		},
		{
			name:     "Three words",
			input:    "big red door",
			expected: "door",
		},
		{
			name:     "Mixed case",
			input:    "Silver Sword",
			expected: "sword",
		},
		{
			name:     "Empty string",
			input:    "",
			expected: "",
		},
		{
			name:     "Only spaces",
			input:    "   ",
			expected: "",
		},
		{
			name:     "Extra spaces",
			input:    "red   door",
			expected: "door",
		},
		{
			name:     "Leading/trailing spaces",
			input:    "  blue chest  ",
			expected: "chest",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := ExtractBaseNoun(tt.input)
			if result != tt.expected {
				t.Errorf("ExtractBaseNoun(%q) = %q, expected %q", tt.input, result, tt.expected)
			}
		})
	}
}

func TestMatchesTarget(t *testing.T) {
	tests := []struct {
		name     string
		itemName string
		target   string
		expected bool
	}{
		{
			name:     "Exact match",
			itemName: "red door",
			target:   "red door",
			expected: true,
		},
		{
			name:     "Partial match - base noun",
			itemName: "red door",
			target:   "door",
			expected: true,
		},
		{
			name:     "Different adjective same noun",
			itemName: "red door",
			target:   "blue door",
			expected: true, // Actually matches because both have "door" as base noun
		},
		{
			name:     "Contains match",
			itemName: "a shiny silver sword",
			target:   "silver sword",
			expected: true,
		},
		{
			name:     "Case insensitive",
			itemName: "Red Door",
			target:   "red door",
			expected: true,
		},
		{
			name:     "Base noun case insensitive",
			itemName: "Red Door",
			target:   "DOOR",
			expected: true,
		},
		{
			name:     "No match",
			itemName: "sword",
			target:   "shield",
			expected: false,
		},
		{
			name:     "Empty target",
			itemName: "sword",
			target:   "",
			expected: true, // strings.Contains returns true for empty substring
		},
		{
			name:     "Empty item name",
			itemName: "",
			target:   "sword",
			expected: false,
		},
		{
			name:     "Partial word match",
			itemName: "golden sword",
			target:   "gold",
			expected: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := MatchesTarget(tt.itemName, tt.target)
			if result != tt.expected {
				t.Errorf("MatchesTarget(%q, %q) = %v, expected %v", tt.itemName, tt.target, result, tt.expected)
			}
		})
	}
}

func TestValidateCommand(t *testing.T) {
	// Create a mock game for testing
	mockGame := &Game{
		commands: make(map[string]CommandInfo),
	}
	
	// Add some test commands
	mockGame.commands["look"] = CommandInfo{}
	mockGame.commands["go"] = CommandInfo{}
	mockGame.commands["get"] = CommandInfo{}
	mockGame.commands["inventory"] = CommandInfo{}
	
	// Build command index
	mockGame.buildCommandIndex()
	
	// Create a mock character
	mockChar := &Character{
		name: "TestChar",
		game: mockGame,
	}

	tests := []struct {
		name          string
		character     *Character
		input         string
		expectedVerb  string
		expectedError string
		expectTokens  bool
	}{
		{
			name:         "Valid command exact match",
			character:    mockChar,
			input:        "look around",
			expectedVerb: "look",
			expectTokens: true,
		},
		{
			name:         "Valid command case insensitive",
			character:    mockChar,
			input:        "LOOK",
			expectedVerb: "look",
			expectTokens: true,
		},
		{
			name:          "Empty input",
			character:     mockChar,
			input:         "",
			expectedError: "\n\rNo command entered.\n\r",
		},
		{
			name:          "Only spaces",
			character:     mockChar,
			input:         "   ",
			expectedError: "\n\rNo command entered.\n\r",
		},
		{
			name:          "Input too long",
			character:     mockChar,
			input:         strings.Repeat("a", 241),
			expectedError: "\n\rCommand too long. Maximum 240 characters allowed.\n\r",
		},
		{
			name:          "Nil character",
			character:     nil,
			input:         "look",
			expectedError: "\n\rInvalid character state.\n\r",
		},
		{
			name:          "Character with nil game",
			character:     &Character{name: "Test"},
			input:         "look",
			expectedError: "\n\rInvalid character state.\n\r",
		},
		{
			name:         "Fuzzy match high confidence",
			character:    mockChar,
			input:        "lok", // Close to "look"
			expectedVerb: "look",
			expectTokens: true,
		},
		{
			name:         "Fuzzy match medium confidence",
			character:    mockChar,
			input:        "invntry", // Close to "inventory" - may actually match with >80%
			expectedVerb: "inventory", // Fuzzy matching might accept this
			expectTokens: true,
		},
		{
			name:          "No match",
			character:     mockChar,
			input:         "xyz",
			expectedError: "\n\rCommand 'xyz' not understood.\n\r",
		},
		{
			name:         "Command with arguments",
			character:    mockChar,
			input:        "go north",
			expectedVerb: "go",
			expectTokens: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			verb, tokens, err := ValidateCommand(tt.character, tt.input)
			
			if tt.expectedError != "" {
				if err == nil {
					t.Errorf("ValidateCommand() expected error %q, got nil", tt.expectedError)
				} else if err.Error() != tt.expectedError {
					t.Errorf("ValidateCommand() error = %q, expected %q", err.Error(), tt.expectedError)
				}
				return
			}
			
			if err != nil {
				t.Errorf("ValidateCommand() unexpected error: %v", err)
				return
			}
			
			if verb != tt.expectedVerb {
				t.Errorf("ValidateCommand() verb = %q, expected %q", verb, tt.expectedVerb)
			}
			
			if tt.expectTokens && len(tokens) == 0 {
				t.Errorf("ValidateCommand() returned no tokens, expected some")
			}
		})
	}
}

func TestBuildOrdinalIndex(t *testing.T) {
	// Clear the index first
	ordinalIndex = nil
	
	// Build the index
	buildOrdinalIndex()
	
	// Check that index was built
	if len(ordinalIndex) != len(ordinalWords) {
		t.Errorf("buildOrdinalIndex() created index with %d entries, expected %d", len(ordinalIndex), len(ordinalWords))
	}
	
	// Check that all ordinals are in the index
	indexMap := make(map[string]bool)
	for _, ord := range ordinalIndex {
		indexMap[ord] = true
	}
	
	for ord := range ordinalWords {
		if !indexMap[ord] {
			t.Errorf("buildOrdinalIndex() missing ordinal %q in index", ord)
		}
	}
}