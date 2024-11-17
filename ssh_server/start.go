package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"golang.org/x/sync/errgroup"

	"github.com/robinje/multi-user-dungeon/core"
)

func main() {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	fmt.Println("Starting Server...")

	configFile := flag.String("config", "config.yml", "Configuration file")
	flag.Parse()

	config, err := loadConfiguration(*configFile)
	if err != nil {
		fmt.Printf("Error loading configuration: %v\n", err)
		os.Exit(1)
	}

	if err := core.InitializeLogging(&config); err != nil {
		fmt.Printf("Error initializing logging: %v\n", err)
		os.Exit(1)
	}

	core.Logger.Info("Configuration loaded", "config", config)

	server, game, err := initializeSystem(&config)
	if err != nil {
		core.Logger.Error("System initialization failed", "error", err)
		os.Exit(1)
	}

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)

	// Use errgroup for goroutine management
	g, ctx := errgroup.WithContext(ctx)

	g.Go(func() error {
		return core.SendMetrics(ctx, server, 1*time.Minute)
	})

	g.Go(func() error {
		return core.AutoSave(ctx, game)
	})

	g.Go(func() error {
		return sshServer(ctx, server, game)
	})

	// Handle shutdown signal
	g.Go(func() error {
		select {
		case <-stop:
			core.Logger.Info("Interrupt received, initiating graceful shutdown...")
			cancel()
		case <-ctx.Done():
		}
		return nil
	})

	// Wait for all goroutines to complete or for an error
	if err := g.Wait(); err != nil {
		core.Logger.Error("Error during operation", "error", err)
	}

	shutdown(server, game)
	core.Logger.Info("Server shutdown complete")
}

func initializeSystem(config *core.Configuration) (*core.Server, *core.Game, error) {
	server, err := core.NewServer(config)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to create server: %w", err)
	}

	game, err := core.NewGame(config)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to create game: %w", err)
	}

	return server, game, nil
}

func shutdown(server *core.Server, game *core.Game) {
	const shutdownTimeout = 60 * time.Second
	ctx, cancel := context.WithTimeout(context.Background(), shutdownTimeout)
	defer cancel()

	core.Logger.Info("Initiating graceful shutdown...")

	shutdownDone := make(chan struct{})
	go func() {
		defer close(shutdownDone)

		// Notify all players
		for _, character := range game.Characters {
			select {
			case character.Player.ToPlayer <- "\n\rServer is shutting down. You will be logged out shortly.\n\r":
			case <-ctx.Done():
				return
			}

			select {
			case character.Player.ToPlayer <- character.Player.Prompt:
			case <-ctx.Done():
				return
			}
		}

		// Log out characters
		for _, character := range game.Characters {
			core.Logger.Info("Logging out character", "characterName", character.Name)
			character.Cleanup()
			character.Player.Cleanup()
		}

		// Save game state
		core.Logger.Info("Performing final auto-save...")
		if err := game.SaveActiveRooms(); err != nil {
			core.Logger.Error("Error saving rooms during shutdown", "error", err)
		}
		if err := game.SaveActiveItems(); err != nil {
			core.Logger.Error("Error saving items during shutdown", "error", err)
		}

		// Close listener
		if server.Listener != nil {
			core.Logger.Info("Closing server listener...")
			if err := server.Listener.Close(); err != nil {
				core.Logger.Error("Error closing server listener", "error", err)
			}
		}
	}()

	select {
	case <-shutdownDone:
		core.Logger.Info("Graceful shutdown completed")
	case <-ctx.Done():
		core.Logger.Error("Shutdown timed out")
	}
}
