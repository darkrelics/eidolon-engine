package main

import (
	"fmt"
	"math"
	"math/rand"
	"strings"
	"sync"
	"unicode"
)

type Index struct {
	IndexID uint64
	mu      sync.RWMutex
}

func (i *Index) GetID() uint64 {
	i.mu.Lock()
	defer i.mu.Unlock()

	i.IndexID++
	return i.IndexID
}

func (i *Index) SetID(id uint64) {
	i.mu.Lock()
	defer i.mu.Unlock()

	if id > i.IndexID {
		i.IndexID = id
	}
}

// wrapText wraps the given text to the specified width, preserving
// empty lines and whitespace. It uses \r\n as the line break.
func wrapText(text string, width int) string {
	var result strings.Builder

	// Split the text into lines
	lines := strings.Split(text, "\n")

	for i, line := range lines {
		// Preserve empty lines
		if len(strings.TrimSpace(line)) == 0 {
			result.WriteString(line)
			if i < len(lines)-1 {
				result.WriteString("\r\n")
			}
			continue
		}

		// Wrap the line to the specified width
		for len(line) > 0 {
			if len(line) <= width {
				result.WriteString(line)
				break
			}

			// Find the last space within the width
			lastSpace := strings.LastIndex(line[:width+1], " ")
			if lastSpace == -1 {
				// No space found, force break at width
				result.WriteString(line[:width])
				line = line[width:]
			} else {
				// Break at the last space
				result.WriteString(line[:lastSpace])
				line = strings.TrimLeft(line[lastSpace+1:], " ")
			}

			result.WriteString("\r\n")
		}

		// Add newline between original lines if not the last line
		if i < len(lines)-1 {
			result.WriteString("\r\n")
		}
	}

	return result.String()
}

func getLookTarget(character *Character, target string) string {
	room := character.Room
	if room == nil {
		return "\n\rYou are floating in the void.\n\r"
	}

	room.Mutex.RLock()
	defer room.Mutex.RUnlock()

	// Check for items first
	for _, item := range room.Items {
		if item != nil && strings.Contains(strings.ToLower(item.Name), target) {
			return fmt.Sprintf("\n\r%s\n\r%s\n\r",
				ApplyColor("bright_white", item.Name),
				item.Description)
		}
	}

	// Check for characters
	for _, c := range room.Characters {
		if c != nil && strings.Contains(strings.ToLower(c.Name), target) {
			return fmt.Sprintf("\n\rYou look at %s.\n\r", c.Name)
		}
	}

	return fmt.Sprintf("\n\rYou don't see '%s' here.\n\r", target)
}

func isValidPassword(password string) bool {
	if len(password) < 8 {
		return false
	}

	var (
		hasUpper   bool
		hasLower   bool
		hasNumber  bool
		hasSpecial bool
	)

	for _, char := range password {
		switch {
		case unicode.IsUpper(char):
			hasUpper = true
		case unicode.IsLower(char):
			hasLower = true
		case unicode.IsNumber(char):
			hasNumber = true
		case unicode.IsPunct(char) || unicode.IsSymbol(char):
			hasSpecial = true
		}
	}

	return hasUpper && hasLower && hasNumber && hasSpecial
}

// parseDims parses terminal dimensions from the SSH payload.
func ParseDims(b []byte) (width, height int) {
	width = int(b[0])<<24 | int(b[1])<<16 | int(b[2])<<8 | int(b[3])
	height = int(b[4])<<24 | int(b[5])<<16 | int(b[6])<<8 | int(b[7])
	return width, height
}

func Challenge(attacker, defender, balance float64) float64 {
	// Calculate the difference to determine the shift
	diff := attacker - defender

	// Simplified sigmoid function evaluation at x=0 with shift
	sigmoidValue := 1 / (1 + math.Exp(balance*diff))

	// Generate a random float64 number
	randomNumber := rand.Float64()

	// Divide the random number by the sigmoid value
	result := randomNumber / sigmoidValue

	return result
}

// LoadCharacterNames loads all character names from the database to initialize the bloom filter.
func LoadCharacterNames(kp *KeyPair) (map[string]bool, error) {
	names := make(map[string]bool)

	var characters []struct {
		CharacterName string `dynamodbav:"Name"`
	}

	err := kp.Scan("characters", &characters)
	if err != nil {
		Logger.Error("Error scanning characters table", "error", err)
		return nil, fmt.Errorf("error scanning characters: %w", err)
	}

	for _, character := range characters {
		names[strings.ToLower(character.CharacterName)] = true
	}

	if len(names) == 0 {
		Logger.Warn("No characters found in the database")
		return names, nil // Return empty map without error
	}

	return names, nil
}
