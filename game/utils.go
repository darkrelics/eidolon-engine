package game

import (
	"bufio"
	"context"
	"fmt"
	"math"
	"math/rand"
	"os"
	"strings"
	"time"

	"github.com/bits-and-blooms/bloom/v3"

	"github.com/robinje/multi-user-dungeon/core"
	"github.com/robinje/multi-user-dungeon/game/character"
)

const FalsePositiveRate = 0.01 // 1% bloom filter false positive rate

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

func performAutoSave(ctx context.Context, g *core.Game) error {
	// Create a context with timeout for the save operation
	saveCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()

	// Create error channel to collect errors from goroutines
	errChan := make(chan error, 3)

	// Launch save operations concurrently
	go func() {
		if err := SaveActiveCharacters(g); err != nil {
			errChan <- fmt.Errorf("failed to save characters: %w", err)
			return
		}
		errChan <- nil
	}()

	go func() {
		if err := SaveActiveItems(g); err != nil {
			errChan <- fmt.Errorf("failed to save items: %w", err)
			return
		}
		errChan <- nil
	}()

	go func() {
		if err := SaveActiveRooms(g); err != nil {
			errChan <- fmt.Errorf("failed to save rooms: %w", err)
			return
		}
		errChan <- nil
	}()

	// Wait for all operations to complete or context cancellation
	for i := 0; i < 3; i++ {
		select {
		case err := <-errChan:
			if err != nil {
				return fmt.Errorf("auto-save operation failed: %w", err)
			}
		case <-saveCtx.Done():
			return fmt.Errorf("auto-save operation timed out: %w", saveCtx.Err())
		}
	}

	return nil
}

// runSaveOperation executes a single save operation with metrics
func runSaveOperation(ctx context.Context, g *core.Game) {
	start := time.Now()

	err := performAutoSave(ctx, g)
	duration := time.Since(start)

	if err != nil {
		core.Logger.Error("Auto-save failed",
			"error", err,
			"duration", duration)
	} else {
		core.Logger.Debug("Auto-save completed successfully",
			"duration", duration)
	}
}

// AutoSave runs the main auto-save loop
func AutoSave(ctx context.Context, game *core.Game) error {
	if game == nil {
		return fmt.Errorf("game instance is nil")
	}

	// Configure the auto-save interval
	interval := game.AutoSave
	if interval == 0 {
		interval = 5 // Default to 5 minutes
		core.Logger.Warn("Auto-save interval not configured, defaulting to 5 minutes")
	}

	saveInterval := time.Duration(interval) * time.Minute
	core.Logger.Info("Starting auto-save routine", "interval", saveInterval)

	// Create ticker for periodic saves
	ticker := time.NewTicker(saveInterval)
	defer ticker.Stop()

	// Perform initial save
	runSaveOperation(ctx, game)

	// Main auto-save loop
	for {
		select {
		case <-ctx.Done():
			core.Logger.Info("Auto-save routine stopping due to context cancellation")
			// Perform final save before shutting down
			runSaveOperation(context.Background(), game)
			return ctx.Err()

		case <-ticker.C:
			runSaveOperation(ctx, game)
		}
	}
}

// InitializeBloomFilter initializes the bloom filter with existing character names,
// as well as names from ../data/names.txt and ../data/obscenity.txt.
func InitializeBloomFilter(game *core.Game) error {
	// Load character names from the database
	characterNames, err := LoadCharacterNames(game.Database)
	if err != nil {
		return fmt.Errorf("failed to load character names: %w", err)
	}

	// Load additional names from names.txt
	namesFilePath := "../data/names.txt"
	namesFromFile, err := loadNamesFromFile(namesFilePath)
	if err != nil {
		return fmt.Errorf("failed to load names from %s: %w", namesFilePath, err)
	}

	// Load obscenity words from obscenity.txt
	obscenityFilePath := "../data/obscenity.txt"
	obscenities, err := loadNamesFromFile(obscenityFilePath)
	if err != nil {
		return fmt.Errorf("failed to load obscenities from %s: %w", obscenityFilePath, err)
	}

	// Calculate total number of items to add to the bloom filter
	totalItems := len(characterNames)
	for range characterNames { // Assuming characterNames is a map; adjust if it's a slice
		// Counting items in characterNames
	}
	totalItems += len(namesFromFile)
	totalItems += len(obscenities)

	// Ensure a minimum size
	if totalItems < 100 {
		totalItems = 100
	}

	fpRate := FalsePositiveRate

	// Initialize the bloom filter with the estimated number of items and false positive rate
	game.CharacterBloomFilter = bloom.NewWithEstimates(uint(totalItems), fpRate)

	// Add character names to the bloom filter
	for name := range characterNames {
		game.CharacterBloomFilter.AddString(strings.ToLower(name))
	}

	// Add names from names.txt to the bloom filter
	for _, name := range namesFromFile {
		game.CharacterBloomFilter.AddString(name)
	}

	// Add obscenities to the bloom filter
	for _, word := range obscenities {
		game.CharacterBloomFilter.AddString(word)
	}

	core.Logger.Debug("Bloom filter initialized",
		"estimatedSize", totalItems,
		"falsePositiveRate", fpRate,
		"totalItemsAdded", totalItems,
	)

	return nil
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

// LoadCharacterNames loads all character names from the database to initialize the bloom filter.
func LoadCharacterNames(kp *core.KeyPair) (map[string]bool, error) {
	names := make(map[string]bool)

	var characters []struct {
		CharacterName string `dynamodbav:"Name"`
	}

	err := kp.Scan("characters", &characters)
	if err != nil {
		core.Logger.Error("Error scanning characters table", "error", err)
		return nil, fmt.Errorf("error scanning characters: %w", err)
	}

	for _, character := range characters {
		names[strings.ToLower(character.CharacterName)] = true
	}

	if len(names) == 0 {
		core.Logger.Warn("No characters found in the database")
		return names, nil // Return empty map without error
	}

	return names, nil
}

// SaveActiveCharacters saves all active characters to the database if they have been edited since the last save.
func SaveActiveCharacters(g *core.Game) error {

	core.Logger.Debug("Saving active characters...")

	for _, c := range g.Characters {
		// Check if the character's LastEdited is before LastSaved
		if !c.LastEdited.After(c.LastSaved) {
			core.Logger.Debug("Character not edited since last save, skipping", "characterName", c.Name)
			continue // Skip writing this character
		}

		c.Mutex.Lock()
		// Attempt to write the character to the database
		err := character.WriteCharacter(c, g.Database)
		if err != nil {
			core.Logger.Error("Error saving character", "characterName", c.Name, "error", err)
			continue // Continue saving other characters even if one fails
		}

		// Update LastSaved after a successful write
		c.LastSaved = time.Now()
		core.Logger.Debug("Character saved successfully", "characterName", c.Name)
		c.Mutex.Unlock()
	}

	core.Logger.Info("Active characters saved successfully.")
	return nil
}
