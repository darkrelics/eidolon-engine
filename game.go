package main

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/google/uuid"
)

// NewGame initializes the game struct.
func NewGame(GlobalContext context.Context, config *Configuration) (*Game, error) {
	Logger.Info("Initializing game...")

	game := &Game{
		Config:         config,
		GlobalContext:  GlobalContext,
		Context:        context.Background(),
		Cancel:         nil,
		Mutex:          sync.RWMutex{},
		StartTime:      time.Now(),
		CharacterCount: 0,
		Characters:     make(map[uuid.UUID]*Character),
		Rooms:          make(map[int64]*Room),
		Prototypes:     make(map[uuid.UUID]*Prototype),
		Items:          make(map[uuid.UUID]*Item),
		Ticker:         time.NewTicker(time.Second),
	}

	var err error
	database, err := NewKeyPair(config.Aws.Region)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize database: %v", err)
	}

	game.Database = database

	// Initialize the bloom filter for character names
	Logger.Info("Initializing bloom filter...")
	err = InitializeBloomFilter(game)
	if err != nil {
		Logger.Error("Error initializing bloom filter", "error", err)
		return nil, fmt.Errorf("failed to initialize bloom filter: %v", err)
	}

	// Load archetypes from the database
	Logger.Info("Loading archetypes from database...")
	err = LoadArchetypes(game)
	if err != nil {
		Logger.Error("Error loading archetypes from database", "error", err)
	}

	// Create Default Room
	Logger.Info("Adding default room...")
	game.Rooms[0] = NewRoom(0, "The Void", "The Void", "You are in a void of nothingness. If you are here, something has gone terribly wrong.")

	// Load rooms from the database
	Logger.Info("Loading rooms from database...")
	loadedRooms, err := LoadRooms(game.Database)
	if err != nil {
		Logger.Error("Error loading rooms from database", "error", err)
		// Proceeding with default room(s) if rooms failed to load
	} else {
		// Merge loaded rooms with existing rooms, preserving the default room
		for id, room := range loadedRooms {
			game.Rooms[id] = room
		}
	}

	return game, nil
}

// RunGame starts the game loop.
func RunGame(game *Game) error {
	Logger.Info("Starting game...")

	for {
		select {
		case <-game.GlobalContext.Done():
			Logger.Info("System shutting down...")
			return nil
		case <-game.Context.Done():
			Logger.Info("Game shutting down...")
			return nil
		}
	}
}
