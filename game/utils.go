package game

import (
	"context"
	"fmt"
	"math"
	"math/rand"
	"time"

	"golang.org/x/sync/errgroup"

	"github.com/robinje/multi-user-dungeon/core"
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

// performAutoSave executes the save operations with proper error handling
func (g *Game) performAutoSave(ctx context.Context) error {
	// Create a context with timeout for the save operation
	saveCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()

	// Create error group for concurrent saves
	group, ctx := errgroup.WithContext(saveCtx)

	// Save characters concurrently
	group.Go(func() error {
		if err := g.SaveActiveCharacters(); err != nil {
			return fmt.Errorf("failed to save characters: %w", err)
		}
		return nil
	})

	// Save items concurrently
	group.Go(func() error {
		if err := g.SaveActiveItems(); err != nil {
			return fmt.Errorf("failed to save items: %w", err)
		}
		return nil
	})

	// Save rooms concurrently
	group.Go(func() error {
		if err := g.SaveActiveRooms(); err != nil {
			return fmt.Errorf("failed to save rooms: %w", err)
		}
		return nil
	})

	// Wait for all save operations to complete
	if err := group.Wait(); err != nil {
		return fmt.Errorf("auto-save operation failed: %w", err)
	}

	return nil
}

// runSaveOperation executes a single save operation with metrics
func (g *Game) runSaveOperation(ctx context.Context) {
	start := time.Now()

	err := g.performAutoSave(ctx)
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
func AutoSave(ctx context.Context, game *Game) error {
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
	game.runSaveOperation(ctx)

	// Main auto-save loop
	for {
		select {
		case <-ctx.Done():
			core.Logger.Info("Auto-save routine stopping due to context cancellation")
			// Perform final save before shutting down
			game.runSaveOperation(context.Background())
			return ctx.Err()

		case <-ticker.C:
			game.runSaveOperation(ctx)
		}
	}
}
