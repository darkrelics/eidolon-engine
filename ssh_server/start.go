package main

import (
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/robinje/multi-user-dungeon/core"
)

func main() {

	fmt.Println("Starting Server...")

	// Parse command-line flags
	configFile := flag.String("config", "config.yml", "Configuration file")
	flag.Parse()

	// Load configuration from the specified file
	fmt.Println("Loading Configuration...")
	config, err := loadConfiguration(*configFile)
	if err != nil {
		fmt.Printf("Error loading configuration: %v\n", err)
		os.Exit(1)
	}

	// Initialize logging based on the loaded configuration
	fmt.Println("Initializing Logging...")
	if err := core.InitializeLogging(&config); err != nil {
		fmt.Printf("Error initializing logging: %v\n", err)
		os.Exit(1)
	}

	core.Logger.Info("Configuration loaded", "config", config)

	// Create a new server instance
	server, err := core.NewServer(&config)
	if err != nil {
		core.Logger.Error("Failed to create server", "error", err)
		os.Exit(1)
	}

	// Create the game instance
	game, err := core.NewGame(&config)
	if err != nil {
		core.Logger.Error("Failed to create game", "error", err)
		os.Exit(1)
	}

	// Create a channel to listen for interrupt signals
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)

	// Start sending metrics in a separate goroutine
	go core.SendMetrics(server, 1*time.Minute)

	// Start the auto-save routine in a separate goroutine
	go core.AutoSave(game)

	// Start the SSH server to accept incoming connections in a goroutine
	go SSHServer(server, game, stop)

	// Wait for interrupt signal
	<-stop

	core.Logger.Info("Interrupt received, initiating graceful shutdown...")

	// Perform graceful shutdown
	if err := Shutdown(server, game); err != nil {
		core.Logger.Error("Error during shutdown", "error", err)
	}

	core.Logger.Info("Server shutdown complete")
}

func Shutdown(server *core.Server, game *core.Game) error {
	core.Logger.Info("Initiating graceful shutdown...")

	// Notify all players of impending shutdown
	for _, character := range game.Characters {
		character.Player.ToPlayer <- "\n\rServer is shutting down. You will be logged out shortly.\n\r"
		character.Player.ToPlayer <- character.Player.Prompt
	}

	// Wait a moment for messages to be sent
	time.Sleep(60 * time.Second)

	// Log out all characters
	for _, character := range game.Characters {
		core.Logger.Info("Logging out character", "characterName", character.Name)
		character.Player.Cleanup()
	}

	// Perform final auto-save
	core.Logger.Info("Performing final auto-save...")
	if err := game.SaveActiveRooms(); err != nil {
		core.Logger.Error("Error saving rooms during shutdown", "error", err)
	}
	if err := game.SaveActiveItems(); err != nil {
		core.Logger.Error("Error saving items during shutdown", "error", err)
	}

	// Close the server listener
	if server.Listener != nil {
		core.Logger.Info("Closing server listener...")
		if err := server.Listener.Close(); err != nil {
			core.Logger.Error("Error closing server listener", "error", err)
		}

		// Wait for ongoing connections to finish
		time.Sleep(60 * time.Second)
	}

	core.Logger.Info("Graceful shutdown completed")
	return nil
}
