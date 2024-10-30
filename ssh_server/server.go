package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"github.com/google/uuid"
	"github.com/robinje/multi-user-dungeon/core"
)

func main() {
	// Parse command-line flags
	configFile := flag.String("config", "config.yml", "Configuration file")
	flag.Parse()

	// Load configuration from the specified file
	config, err := loadConfiguration(*configFile)
	if err != nil {
		fmt.Printf("Error loading configuration: %v\n", err)
		os.Exit(1)
	}

	// Initialize logging based on the loaded configuration
	if err := core.InitializeLogging(&config); err != nil {
		fmt.Printf("Error initializing logging: %v\n", err)
		os.Exit(1)
	}

	core.Logger.Info("Configuration loaded", "config", config)

	// Create a new server instance
	server, err := NewServer(config)
	if err != nil {
		core.Logger.Error("Failed to create server", "error", err)
		os.Exit(1)
	}

	// Create a context that we can cancel
	ctx, cancel := context.WithCancel(context.Background())

	server.Context = ctx

	// Create a channel to listen for interrupt signals
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)

	// Start the SSH server to accept incoming connections in a goroutine
	go StartSSHServer(server, stop)

	// Start sending metrics in a separate goroutine
	go core.SendMetrics(server, 1*time.Minute)

	// Start the auto-save routine in a separate goroutine
	go core.AutoSave(server)

	// Wait for interrupt signal
	<-stop

	core.Logger.Warn("Interrupt received, initiating graceful shutdown...")

	// Cancel the context to signal all goroutines to stop
	cancel()

	// Create a timeout context for shutdown operations
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer shutdownCancel()

	// Perform graceful shutdown
	if err := GracefulShutdown(shutdownCtx, server); err != nil {
		core.Logger.Error("Error during shutdown", "error", err)
	}

	core.Logger.Warn("Server shutdown complete")
}

// NewServer initializes a new server instance with the given configuration.
// It sets up the database connection, loads game data, and prepares the server for incoming connections.
func NewServer(config core.Configuration) (*core.Server, error) {
	core.Logger.Info("Initializing server...")

	// Initialize the server struct with the provided configuration
	server := &core.Server{
		Config:      config,
		Context:     context.Background(),
		Mutex:       sync.Mutex{},
		WaitGroup:   sync.WaitGroup{},
		StartTime:   time.Now(),
		Port:        config.Server.Port,
		PlayerCount: 0,
		PlayerIndex: &core.Index{},
		Players:     make(map[uint64]*core.Player),
		Characters:  make(map[uuid.UUID]*core.Character),
		Rooms:       make(map[int64]*core.Room),
		Prototypes:  make(map[uuid.UUID]*core.Prototype),
		Items:       make(map[uuid.UUID]*core.Item),
	}

	core.Logger.Info("Initializing database...")

	// Initialize the database connection
	var err error
	server.Database, err = core.NewKeyPair(config.Aws.Region)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize database: %v", err)
	}

	// Initialize the player index
	server.PlayerIndex.IndexID = 1

	// Initialize the bloom filter for character names
	core.Logger.Info("Initializing bloom filter...")
	err = server.InitializeBloomFilter()
	if err != nil {
		core.Logger.Error("Error initializing bloom filter", "error", err)
		return nil, fmt.Errorf("failed to initialize bloom filter: %v", err)
	}

	// Load archetypes from the database
	core.Logger.Info("Loading archetypes from database...")
	err = server.LoadArchetypes()
	if err != nil {
		core.Logger.Error("Error loading archetypes from database", "error", err)
	}

	// Create Default Room
	core.Logger.Info("Adding default room...")
	server.Rooms[0] = core.NewRoom(0, "The Void", "The Void", "You are in a void of nothingness. If you are here, something has gone terribly wrong.")

	// Load rooms from the database
	core.Logger.Info("Loading rooms from database...")
	loadedRooms, err := server.Database.LoadRooms()
	if err != nil {
		core.Logger.Error("Error loading rooms from database", "error", err)
		// Proceeding with default room(s) if rooms failed to load
	} else {
		// Merge loaded rooms with existing rooms, preserving the default room
		for id, room := range loadedRooms {
			server.Rooms[id] = room
		}
	}

	// Load active MOTDs from the database
	core.Logger.Info("Loading active MOTDs from database...")
	activeMOTDs, err := server.Database.GetAllMOTDs()
	if err != nil {
		core.Logger.Error("Failed to load active MOTDs", "error", err)
		// Proceeding without MOTDs if failed to load
	} else {
		server.ActiveMotDs = activeMOTDs
		core.Logger.Info("Loaded active MOTDs", "count", len(activeMOTDs))
	}

	return server, nil
}

func GracefulShutdown(ctx context.Context, server *core.Server) error {
	core.Logger.Info("Initiating graceful shutdown...")

	// Notify all players of impending shutdown
	for _, character := range server.Characters {
		character.Player.ToPlayer <- "\n\rServer is shutting down. You will be logged out shortly.\n\r"
		character.Player.ToPlayer <- character.Player.Prompt
	}

	// Wait a moment for messages to be sent
	time.Sleep(10 * time.Second)

	// Log out all characters
	for _, character := range server.Characters {
		core.Logger.Info("Logging out character", "characterName", character.Name)
		character.Player.Cleanup()
	}

	// Perform final auto-save
	core.Logger.Info("Performing final auto-save...")
	if err := server.SaveActiveRooms(); err != nil {
		core.Logger.Error("Error saving rooms during shutdown", "error", err)
	}
	if err := server.SaveActiveItems(); err != nil {
		core.Logger.Error("Error saving items during shutdown", "error", err)
	}

	// Close the server listener
	if server.Listener != nil {
		core.Logger.Info("Closing server listener...")
		if err := server.Listener.Close(); err != nil {
			core.Logger.Error("Error closing server listener", "error", err)
		}

		// Wait for ongoing connections to finish (with a timeout)
		shutdownCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
		defer cancel()

		done := make(chan struct{})
		go func() {
			server.WaitGroup.Wait()
			close(done)
		}()

		select {
		case <-done:
			core.Logger.Info("All connections closed successfully")
		case <-shutdownCtx.Done():
			core.Logger.Warn("Timed out waiting for connections to close")
		}
	}

	core.Logger.Info("Graceful shutdown completed")
	return nil
}
