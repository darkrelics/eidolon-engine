package core

import (
	"bufio"
	"fmt"
	"math"
	"math/rand"
	"os"
	"strings"
	"time"
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

func AutoSave(server *Server) {
	Logger.Info("Starting auto-save routine...")

	for {
		// Sleep for the configured duration
		time.Sleep(time.Duration(server.AutoSave) * time.Minute)

		Logger.Info("Starting auto-save process...")

		// Save active characters
		if err := server.SaveActiveCharacters(); err != nil {
			Logger.Error("Failed to save characters", "error", err)
		} else {
			Logger.Info("Active characters saved successfully")
		}

		// Save active items
		if err := server.SaveActiveItems(); err != nil {
			Logger.Error("Failed to save items", "error", err)
		} else {
			Logger.Info("Active items saved successfully")
		}

		Logger.Info("Auto-save process completed")

		// Save active rooms
		if err := server.SaveActiveRooms(); err != nil {
			Logger.Error("Failed to save rooms", "error", err)
		} else {
			Logger.Info("Active rooms saved successfully")
		}

	}
}

func wrapText(text string, width int) string {
	var result strings.Builder
	lines := strings.Split(text, "\n")

	for _, line := range lines {
		if len(line) == 0 {
			result.WriteString("\r\n")
			continue
		}

		words := strings.Fields(line)
		if len(words) == 0 {
			continue
		}

		lineLen := 0
		for _, word := range words {
			wordLen := len(word)
			if lineLen+wordLen+1 > width {
				result.WriteString("\r\n")
				lineLen = 0
			} else if lineLen > 0 {
				result.WriteString(" ")
				lineLen++
			}
			result.WriteString(word)
			lineLen += wordLen
		}
		result.WriteString("\r\n")
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
