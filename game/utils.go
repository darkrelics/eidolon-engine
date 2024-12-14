package main

import (
	"context"
	"fmt"
	"math"
	"math/rand"
	"strings"
	"time"

	"github.com/robinje/multi-user-dungeon/character"
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

func performAutoSave(ctx context.Context, g *Game) error {
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
func runSaveOperation(ctx context.Context, g *Game) {
	start := time.Now()

	err := performAutoSave(ctx, g)
	duration := time.Since(start)

	if err != nil {
		Logger.Error("Auto-save failed",
			"error", err,
			"duration", duration)
	} else {
		Logger.Debug("Auto-save completed successfully",
			"duration", duration)
	}
}

// AutoSave runs the main auto-save loop
func AutoSave(ctx context.Context, game *Game) error {
	if game == nil {
		return fmt.Errorf("game instance is nil")
	}

	// Configure the auto-save interval
	interval := game.AutoSave
	if interval == 0 {
		interval = 5 // Default to 5 minutes
		Logger.Warn("Auto-save interval not configured, defaulting to 5 minutes")
	}

	saveInterval := time.Duration(interval) * time.Minute
	Logger.Info("Starting auto-save routine", "interval", saveInterval)

	// Create ticker for periodic saves
	ticker := time.NewTicker(saveInterval)
	defer ticker.Stop()

	// Perform initial save
	runSaveOperation(ctx, game)

	// Main auto-save loop
	for {
		select {
		case <-ctx.Done():
			Logger.Info("Auto-save routine stopping due to context cancellation")
			// Perform final save before shutting down
			runSaveOperation(context.Background(), game)
			return ctx.Err()

		case <-ticker.C:
			runSaveOperation(ctx, game)
		}
	}
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

// SaveActiveCharacters saves all active characters to the database if they have been edited since the last save.
func SaveActiveCharacters(g *Game) error {

	Logger.Debug("Saving active characters...")

	for _, c := range g.Characters {
		// Check if the character's LastEdited is before LastSaved
		if !c.LastEdited.After(c.LastSaved) {
			Logger.Debug("Character not edited since last save, skipping", "characterName", c.Name)
			continue // Skip writing this character
		}

		c.Mutex.Lock()
		// Attempt to write the character to the database
		err := character.WriteCharacter(c, g.Database)
		if err != nil {
			Logger.Error("Error saving character", "characterName", c.Name, "error", err)
			continue // Continue saving other characters even if one fails
		}

		// Update LastSaved after a successful write
		c.LastSaved = time.Now()
		Logger.Debug("Character saved successfully", "characterName", c.Name)
		c.Mutex.Unlock()
	}

	Logger.Info("Active characters saved successfully.")
	return nil
}
