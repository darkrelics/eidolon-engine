package server

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/robinje/multi-user-dungeon/core"
)

// NewServer initializes a new server instance with the given configuration.
// It sets up the database connection, loads game data, and prepares the server for incoming connections.
func NewServer(GlobalContext context.Context, config *core.Configuration) (*core.Server, error) {
	core.Logger.Info("Initializing server...")

	// Initialize the server struct with the provided configuration
	server := &core.Server{
		Config:        config,
		GlobalContext: GlobalContext,
		Context:       context.Background(),
		Cancel:        nil,
		Mutex:         sync.RWMutex{},
		StartTime:     time.Now(),
		PlayerCount:   0,
		PlayerIndex:   &core.Index{},
		Players:       make(map[uint64]*core.Player),
	}

	fmt.Println("Initializing database...")

	database, err := core.NewKeyPair(config.Aws.Region)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize database: %v", err)
	}

	server.Database = database

	// Initialize the player index
	server.PlayerIndex.IndexID = 1

	return server, nil
}

func RunServer(server *core.Server) error {
	core.Logger.Info("Starting server...")

	for {
		select {
		case <-server.GlobalContext.Done():
			core.Logger.Info("System shutting down...")
			return nil
		case <-server.Context.Done():
			core.Logger.Info("Server shutting down...")
			return nil
		}
	}

}
