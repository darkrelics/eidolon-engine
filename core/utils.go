package core

import (
	"bufio"
	"fmt"
	"os"
	"strings"
	"unicode"
)

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
