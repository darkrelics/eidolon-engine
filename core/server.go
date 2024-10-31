package core

import (
	"context"
	"fmt"
	"sync"
	"time"
)

// NewServer initializes a new server instance with the given configuration.
// It sets up the database connection, loads game data, and prepares the server for incoming connections.
func NewServer(config *Configuration) (*Server, error) {
	Logger.Info("Initializing server...")

	// Initialize the server struct with the provided configuration
	server := &Server{
		Config:      config,
		Context:     context.Background(),
		Mutex:       sync.Mutex{},
		WaitGroup:   sync.WaitGroup{},
		StartTime:   time.Now(),
		Port:        config.Server.Port,
		PlayerCount: 0,
		PlayerIndex: &Index{},
		Players:     make(map[uint64]*Player),
	}

	Logger.Info("Initializing database...")

	var err error
	server.Database, err = NewKeyPair(config.Aws.Region)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize database: %v", err)
	}

	// Initialize the player index
	server.PlayerIndex.IndexID = 1

	// Load active MOTDs from the database
	Logger.Info("Loading active MOTDs from database...")
	activeMOTDs, err := server.Database.GetAllMOTDs()
	if err != nil {
		Logger.Error("Failed to load active MOTDs", "error", err)
		// Proceeding without MOTDs if failed to load
	} else {
		server.ActiveMotDs = activeMOTDs
		Logger.Info("Loaded active MOTDs", "count", len(activeMOTDs))
	}

	return server, nil
}
