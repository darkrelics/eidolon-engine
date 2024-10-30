package core

import (
	"bufio"
	"fmt"
	"math"
	"math/rand"
	"os"
	"strings"
	"time"
	"unicode"
)

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

func AutoSave(game *Game) {
	Logger.Info("Starting auto-save routine...")

	for {
		// Sleep for the configured duration
		time.Sleep(time.Duration(game.Server.Config.Game.AutoSave) * time.Minute)

		Logger.Info("Starting auto-save process...")

		// Save active characters
		if err := game.SaveActiveCharacters(); err != nil {
			Logger.Error("Failed to save characters", "error", err)
		} else {
			Logger.Debug("Active characters saved successfully")
		}

		// Save active items
		if err := game.SaveActiveItems(); err != nil {
			Logger.Error("Failed to save items", "error", err)
		} else {
			Logger.Debug("Active items saved successfully")
		}

		Logger.Debug("Auto-save process completed")

		// Save active rooms
		if err := game.SaveActiveRooms(); err != nil {
			Logger.Error("Failed to save rooms", "error", err)
		} else {
			Logger.Debug("Active rooms saved successfully")
		}

	}
}

func wrapText(text string, width int) string {
	var result strings.Builder
	lines := strings.Split(text, "\n")

	for i, line := range lines {
		// Preserve empty lines
		if len(line) == 0 {
			if i < len(lines)-1 { // Only add newline if not the last line
				result.WriteString("\r\n")
			}
			continue
		}

		// If the line is just whitespace, preserve it
		if strings.TrimSpace(line) == "" {
			result.WriteString(line)
			if i < len(lines)-1 {
				result.WriteString("\r\n")
			}
			continue
		}

		// Process line with content
		currentLine := line
		for len(currentLine) > 0 {
			if len(currentLine) <= width {
				result.WriteString(currentLine)
				break
			}

			// Find the last space within width
			lastSpace := strings.LastIndex(currentLine[:width+1], " ")
			if lastSpace == -1 {
				// No space found, force break at width
				result.WriteString(currentLine[:width])
				currentLine = currentLine[width:]
			} else {
				// Break at last space
				result.WriteString(currentLine[:lastSpace])
				currentLine = currentLine[lastSpace+1:]
			}

			if len(currentLine) > 0 {
				result.WriteString("\r\n")
			}
		}

		// Add newline between original lines if not the last line
		if i < len(lines)-1 {
			result.WriteString("\r\n")
		}
	}

	return result.String()
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

// loadNamesFromFile reads a file line by line and returns a slice of names.
func loadNamesFromFile(filePath string) ([]string, error) {
	file, err := os.Open(filePath)
	if err != nil {
		return nil, fmt.Errorf("failed to open %s: %w", filePath, err)
	}
	defer file.Close()

	var names []string
	scanner := bufio.NewScanner(file)
	lineNumber := 1
	for scanner.Scan() {
		name := strings.TrimSpace(scanner.Text())
		if name != "" {
			names = append(names, strings.ToLower(name))
		}
		lineNumber++
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("error reading %s: %w", filePath, err)
	}

	return names, nil
}

func getLookTarget(character *Character, target string) string {
	room := character.Room
	if room == nil {
		return "\n\rYou are floating in the void.\n\r"
	}

	room.Mutex.Lock()
	defer room.Mutex.Unlock()

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
