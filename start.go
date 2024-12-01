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
	"gopkg.in/yaml.v3"

	"github.com/robinje/multi-user-dungeon/core"
)

func main() {

	// Create the global context.

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	fmt.Println("Loading configuration...")

	configFile := flag.String("config", "config.yml", "Configuration file")
	flag.Parse()

	config, err := loadConfiguration(*configFile)
	if err != nil {
		fmt.Printf("Error loading configuration: %v\n", err)
		os.Exit(1)
	}

	CloudWatch, err := core.InitializeLogging(MetricsConfig)
	if err != nil {
		fmt.Printf("Error initializing logging: %v\n", err)
		os.Exit(1)
	}

	core.Logger.Info("Configuration loaded", "config", config)

	server, game, err := initializeSystem(ctx, &config)
	if err != nil {
		core.Logger.Error("System initialization failed", "error", err)
		os.Exit(1)
	}

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)

	// Use errgroup for goroutine management
	g, ctx := errgroup.WithContext(ctx)

	g.Go(func() error {
		return CloudWatch.SendMetrics(ctx, server, 1*time.Minute)
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

// loadConfiguration reads the configuration file and unmarshals it into a Configuration struct.
func loadConfiguration(configFile string) (core.Configuration, error) {
	var config core.Configuration

	data, err := os.ReadFile(configFile)
	if err != nil {
		return config, fmt.Errorf("error reading config file '%s': %w", configFile, err)
	}

	err = yaml.Unmarshal(data, &config)
	if err != nil {
		return config, fmt.Errorf("error unmarshalling config from '%s': %w", configFile, err)
	}

	return config, nil
}

// TODO: Break up for Game and Server Initialization

func initializeSystem(ctx context.Context, config *Configuration) (*Server, *core.Game, error) {
	server, err := NewServer(ctx, config)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to create server: %w", err)
	}

	game, err := core.NewGame(config)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to create game: %w", err)
	}

	// Return early if context is cancelled
	select {
	case <-ctx.Done():
		return nil, nil, fmt.Errorf("initialization cancelled: %w", ctx.Err())
	default:
		return server, game, nil
	}
}

func shutdown(server *Server, game *core.Game) {
	const shutdownTimeout = 60 * time.Second
	ctx, cancel := context.WithTimeout(context.Background(), shutdownTimeout)
	defer cancel()

	core.Logger.Info("Initiating graceful shutdown...")

	g, ctx := errgroup.WithContext(ctx)

	// Notify all players and cleanup characters
	g.Go(func() error {
		for _, character := range game.Characters {
			select {
			case character.Player.ToPlayer <- "\n\rServer is shutting down. You will be logged out shortly.\n\r":
			case <-ctx.Done():
				return ctx.Err()
			}

			select {
			case character.Player.ToPlayer <- character.Player.Prompt:
			case <-ctx.Done():
				return ctx.Err()
			}

			core.Logger.Info("Logging out character", "characterName", character.Name)
			character.Cleanup()
			character.Player.Cleanup()
		}
		return nil
	})

	// Save game state
	g.Go(func() error {
		core.Logger.Info("Performing final auto-save...")
		if err := game.SaveActiveRooms(); err != nil {
			core.Logger.Error("Error saving rooms during shutdown", "error", err)
			return fmt.Errorf("failed to save rooms: %w", err)
		}
		if err := game.SaveActiveItems(); err != nil {
			core.Logger.Error("Error saving items during shutdown", "error", err)
			return fmt.Errorf("failed to save items: %w", err)
		}
		return nil
	})

	// Close server listener
	g.Go(func() error {
		if server.Listener != nil {
			core.Logger.Info("Closing server listener...")
			if err := server.Listener.Close(); err != nil {
				core.Logger.Error("Error closing server listener", "error", err)
				return fmt.Errorf("failed to close listener: %w", err)
			}
		}
		return nil
	})

	// Wait for all shutdown operations to complete
	if err := g.Wait(); err != nil {
		if err == context.DeadlineExceeded {
			core.Logger.Error("Shutdown timed out")
		} else {
			core.Logger.Error("Error during shutdown", "error", err)
		}
	} else {
		core.Logger.Info("Graceful shutdown completed")
	}
}
