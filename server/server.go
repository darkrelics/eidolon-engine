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
func NewServer(ctx context.Context, config *core.Configuration) (*core.Server, error) {
	core.Logger.Info("Initializing server...")

	// Initialize the server struct with the provided configuration
	server := &core.Server{
		Context:             ctx,
		Mutex:               sync.RWMutex{},
		WaitGroup:           sync.WaitGroup{},
		Region:              config.Aws.Region,
		StartTime:           time.Now(),
		ApplicationName:     config.Logging.ApplicationName,
		LogLevel:            config.Logging.LogLevel,
		LogGroup:            config.Logging.LogGroup,
		LogStream:           config.Logging.LogStream,
		MetricNamespace:     config.Logging.MetricNamespace,
		PrivateKeyPath:      config.Server.PrivateKeyPath,
		Port:                config.Server.Port,
		CognitoClientID:     config.Cognito.ClientID,
		CognitoClientSecret: config.Cognito.ClientSecret,
		PlayerCount:         0,
		PlayerIndex:         &core.Index{},
		Players:             make(map[uint64]*core.Player),
	}

	fmt.Println("Initializing database...")

	var err error
	server.Database, err = core.NewKeyPair(config.Aws.Region)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize database: %v", err)
	}

	// Initialize the player index
	server.PlayerIndex.IndexID = 1

	// Load active MOTDs from the database
	fmt.Println("Loading active MOTDs from database...")
	activeMOTDs, err := GetAllMOTDs(server.Database)
	if err != nil {
		fmt.Println("Failed to load active MOTDs", "error", err)
		// Proceeding without MOTDs if failed to load
	} else {
		server.ActiveMotDs = activeMOTDs
		fmt.Println("Loaded active MOTDs", "count", len(activeMOTDs))
	}

	return server, nil
}
