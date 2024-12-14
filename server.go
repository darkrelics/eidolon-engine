package main

import (
	"context"
	"fmt"
	"sync"
	"time"
)

// NewServer initializes a new server instance with the given configuration.
// It sets up the database connection, loads game data, and prepares the server for incoming connections.
func NewServer(GlobalContext context.Context, config *Configuration) (*Server, error) {
	Logger.Info("Initializing server...")

	// Initialize the server struct with the provided configuration
	server := &Server{
		Config:        config,
		GlobalContext: GlobalContext,
		Context:       context.Background(),
		Cancel:        nil,
		Mutex:         sync.RWMutex{},
		StartTime:     time.Now(),
		PlayerCount:   0,
		PlayerIndex:   &Index{},
		Players:       make(map[uint64]*Player),
	}

	fmt.Println("Initializing database...")

	database, err := NewKeyPair(config.Aws.Region)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize database: %v", err)
	}

	server.Database = database

	// Initialize the player index
	server.PlayerIndex.IndexID = 1

	return server, nil
}

func RunServer(server *Server) error {
	Logger.Info("Starting server...")

	for {
		select {
		case <-server.GlobalContext.Done():
			Logger.Info("System shutting down...")
			return nil
		case <-server.Context.Done():
			Logger.Info("Server shutting down...")
			return nil
		}
	}

}
