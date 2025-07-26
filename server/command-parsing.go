/*
Eidolon Engine

Copyright 2024-2025 Jason Robinson

*/

package main

import (
	"errors"
	"fmt"
	"strings"

	fuzzy "github.com/paul-mannino/go-fuzzywuzzy"
)

// Ordinal words mapping for command parsing
var ordinalWords = map[string]int{
	"first":       1,
	"second":      2,
	"third":       3,
	"fourth":      4,
	"fifth":       5,
	"sixth":       6,
	"seventh":     7,
	"eighth":      8,
	"ninth":       9,
	"tenth":       10,
	"eleventh":    11,
	"twelfth":     12,
	"thirteenth":  13,
	"fourteenth":  14,
	"fifteenth":   15,
	"sixteenth":   16,
	"seventeenth": 17,
	"eighteenth":  18,
	"nineteenth":  19,
	"twentieth":   20,
}

// ordinalIndex holds all ordinal words for fuzzy matching
var ordinalIndex []string

// buildOrdinalIndex builds the ordinal index for fuzzy matching
// This should be called once during game initialization
func buildOrdinalIndex() {
	ordinalIndex = make([]string, 0, len(ordinalWords))
	for ordinal := range ordinalWords {
		ordinalIndex = append(ordinalIndex, ordinal)
	}
	Logger.Info("Built ordinal fuzzy index", "ordinals", len(ordinalIndex))
}

// ValidateCommand checks if a command is valid and returns its verb and tokens
func ValidateCommand(character *Character, input string) (string, []string, string, error) {
	if len(input) == 0 {
		return "", nil, "No command entered.", nil
	}

	// Limit input to 240 characters
	if len(input) > 240 {
		return "", nil, "Command too long. Maximum 240 characters allowed.", nil
	}

	tokens := tokenizeInput(input)

	if len(tokens) == 0 {
		return "", nil, "No command entered.", nil
	}

	verb := strings.ToLower(tokens[0])
	if character == nil || character.game == nil {
		return "", nil, "", errors.New("invalid character state")
	}

	// First check for exact match
	character.game.mutex.RLock()
	_, exactMatch := character.game.commands[verb]
	character.game.mutex.RUnlock()

	if exactMatch {
		return verb, tokens, "", nil
	}

	// No exact match, try fuzzy matching
	bestMatch, score := character.game.findBestCommand(verb)

	// If confidence is 80% or higher, automatically execute the command
	if score >= 80 {
		Logger.Debug("Fuzzy match found", "input", verb, "match", bestMatch, "score", score)
		tokens[0] = bestMatch // Replace the verb with the matched command
		return bestMatch, tokens, "", nil
	}

	// If confidence is between 50% and 80%, ask if they meant the command
	if score >= 50 {
		return "", nil, fmt.Sprintf("Command '%s' not understood. Did you mean '%s'?", verb, bestMatch), nil
	}

	// No good match found
	return "", nil, fmt.Sprintf("Command '%s' not understood.", verb), nil
}

// tokenizeInput breaks the input into individual tokens
func tokenizeInput(input string) []string {
	// Sanitize input first
	input = strings.TrimSpace(input)

	// Control character removal prevents terminal manipulation
	input = strings.Map(func(r rune) rune {
		if r < 32 && r != '\t' {
			return -1
		}
		return r
	}, input)

	var tokens []string
	var current strings.Builder
	inQuotes := false

	for i := 0; i < len(input); i++ {
		switch input[i] {
		case '"':
			inQuotes = !inQuotes
		case ' ', '\t':
			if !inQuotes && current.Len() > 0 {
				tokens = append(tokens, current.String())
				current.Reset()
			} else if inQuotes {
				current.WriteByte(input[i])
			}
		default:
			current.WriteByte(input[i])
		}
	}

	if current.Len() > 0 {
		tokens = append(tokens, current.String())
	}

	return tokens
}

// fuzzyMatchOrdinal attempts to fuzzy match an input string to an ordinal word
// Returns the matched ordinal, its position value, and whether a match was found
// Assumes ordinalIndex has been built during game initialization
func fuzzyMatchOrdinal(input string) (string, int, bool) {
	input = strings.ToLower(strings.TrimSpace(input))

	// First check for exact match
	if position, exists := ordinalWords[input]; exists {
		return input, position, true
	}

	// Try fuzzy matching using pre-built index
	var bestMatch string
	var bestScore int

	for _, ordinal := range ordinalIndex {
		score := fuzzy.Ratio(input, ordinal)
		if score > bestScore {
			bestScore = score
			bestMatch = ordinal
		}
	}

	// Use standard 80% threshold
	if bestScore >= 80 {
		return bestMatch, ordinalWords[bestMatch], true
	}

	return "", 0, false
}

// ParseTargetWithOrdinal parses a target string and extracts ordinal position and item name
// Returns: ordinal position (1-based), item name, and whether an ordinal was found
// Examples:
//
//	"sword" -> 1, "sword", false (default to first)
//	"second sword" -> 2, "sword", true
//	"third goblin" -> 3, "goblin", true
func ParseTargetWithOrdinal(target string) (int, string, bool) {
	target = strings.ToLower(strings.TrimSpace(target))
	parts := strings.SplitN(target, " ", 2)

	// If only one word, return it as the item name with position 1
	if len(parts) == 1 {
		return 1, target, false
	}

	// Check if first word is an ordinal (with fuzzy matching)
	if _, position, isOrdinal := fuzzyMatchOrdinal(parts[0]); isOrdinal {
		return position, parts[1], true
	}

	// No ordinal found, return full target as item name
	return 1, target, false
}

// ExtractBaseNoun extracts the base noun from an item or exit name
// This helps match "red door", "blue door", "green door" all as "door"
// Returns the last word as the base noun
// Examples:
//
//	"red door" -> "door"
//	"silver sword" -> "sword"
//	"door" -> "door"
func ExtractBaseNoun(name string) string {
	words := strings.Fields(strings.ToLower(name))
	if len(words) == 0 {
		return ""
	}
	return words[len(words)-1]
}

// MatchesTarget checks if an item/exit name matches the target string
// Supports both full name matching and base noun matching
// Examples:
//
//	MatchesTarget("red door", "door") -> true
//	MatchesTarget("red door", "red door") -> true
//	MatchesTarget("red door", "blue door") -> false
func MatchesTarget(itemName, target string) bool {
	itemNameLower := strings.ToLower(itemName)
	targetLower := strings.ToLower(target)

	// First check if the full name contains the target
	if strings.Contains(itemNameLower, targetLower) {
		return true
	}

	// Then check if the base noun matches
	itemBaseNoun := ExtractBaseNoun(itemName)
	targetBaseNoun := ExtractBaseNoun(target)

	return itemBaseNoun == targetBaseNoun
}
