/*
Eidolon Engine

Copyright 2024-2025 Jason Robinson

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package main

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/bits-and-blooms/bloom/v3"
	"github.com/google/uuid"
)

var NAMES_PATH = "../data/names.txt"
var OBSCENITY_PATH = "../data/obscenity.txt"

type Game struct {
	config               *Configuration
	globalCtx            context.Context
	ctx                  context.Context
	cancel               context.CancelFunc
	mutex                sync.RWMutex
	start                time.Time
	characterCount       atomic.Uint64
	ticker               *time.Ticker
	database             *KeyPair
	archetypes           map[string]*Archetype
	archetypeOptions     []string
	characterBloomFilter *bloom.BloomFilter
	characters           map[uuid.UUID]*Character
	rooms                map[int64]*Room
	exits                map[uuid.UUID]*Exit
	prototypes           map[uuid.UUID]*Prototype
	items                map[uuid.UUID]*Item
	startingHealth       uint16
	startingEssence      uint16
	balance              float64
	autoSaveInterval     uint16
}

// Initalize the game engine

func NewGame(globalCtx context.Context, config *Configuration) (*Game, error) {

	fmt.Println("New Game...Initalizing Game...")

	ctx, cancel := context.WithCancel(globalCtx)

	// Create a new game object

	game := &Game{
		config:           config,
		globalCtx:        globalCtx,
		ctx:              ctx,
		cancel:           cancel,
		mutex:            sync.RWMutex{},
		start:            time.Now(),
		characterCount:   atomic.Uint64{},
		archetypes:       make(map[string]*Archetype),
		archetypeOptions: make([]string, 0),
		characters:       make(map[uuid.UUID]*Character),
		rooms:            make(map[int64]*Room),
		exits:            make(map[uuid.UUID]*Exit),
		prototypes:       make(map[uuid.UUID]*Prototype),
		items:            make(map[uuid.UUID]*Item),
		ticker:           nil,
		startingHealth:   config.Game.StartingHealth,
		startingEssence:  config.Game.StartingEssence,
		balance:          config.Game.Balance,
		autoSaveInterval: 5,
	}

	game.characterCount.Store(0)

	// Initialize Game Database Interface

	database, err := NewKeyPair(config)
	if err != nil {
		return nil, fmt.Errorf("database init error: %w", err)
	}

	game.database = database

	// Load Character Bloom Filter

	if err := game.InitCharacterBloomFilter(); err != nil {
		Logger.Warn("Error initializing character bloom filter", "error", err)
	}

	// Load Archetypes

	if err := game.LoadArchetypes(); err != nil {
		Logger.Error("Error loading archetypes", "error", err)
	}

	// Build Archetype Options

	if err := game.BuildArchetypeOptions(); err != nil {
		Logger.Error("Error loading archetype options", "error", err)
	}

	// Create Default Room

	game.rooms[0] = NewRoom(0, "The Void", "The Void", "Default void room.")

	// Load Rooms

	if err := game.LoadRooms(); err != nil {
		Logger.Error("Error loading rooms", "error", err)
	}

	return game, nil

}

// Load names from the database.

func (g *Game) LoadCharacterNames() ([]string, error) {

	fmt.Println("Loading character names from database...")

	var names []string

	var characters []struct {
		CharacterName string `dynamodbav:"Name"`
	}

	err := g.database.Scan("characters", &characters)
	if err != nil {
		Logger.Error("Error scanning characters table", "error", err)
		return nil, fmt.Errorf("error scanning characters: %w", err)
	}

	for _, character := range characters {
		names = append(names, strings.ToLower(character.CharacterName))
	}

	return names, nil
}

// Load names from a file.

func LoadNameFromFile(path string) ([]string, error) {

	fmt.Println("Loading names from file", "path", path)

	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("error opening file: %w", err)
	}
	defer file.Close()

	var names []string
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		if name := strings.TrimSpace(scanner.Text()); name != "" {
			names = append(names, strings.ToLower(name))
		}
	}

	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("file read error: %w", err)
	}

	return names, nil
}

// Initialize Character Name Bloom Filter

func (g *Game) InitCharacterBloomFilter() error {

	fmt.Println("Initializing character name bloom filter...")

	names, err := g.LoadCharacterNames()
	if err != nil {
		Logger.Warn("Error loading character names from database", "error", err)
	}

	namesFromFile, err := LoadNameFromFile(NAMES_PATH)
	if err != nil {
		Logger.Warn("Error loading character names from file", "error", err)
	}

	obscenities, err := LoadNameFromFile(OBSCENITY_PATH)
	if err != nil {
		Logger.Warn("Error loading obscenities from file", "error", err)
	}

	totalItems := len(names) + len(namesFromFile) + len(obscenities)
	if totalItems < 100 {
		totalItems = 100
	}

	g.characterBloomFilter = bloom.NewWithEstimates(uint(totalItems), 0.01)

	completeNames := make([]string, 0, totalItems)
	completeNames = append(completeNames, names...)
	completeNames = append(completeNames, namesFromFile...)
	completeNames = append(completeNames, obscenities...)

	for _, name := range completeNames {
		g.characterBloomFilter.AddString(strings.ToLower(name))
	}

	return nil
}

func (g *Game) Stop() error {

	fmt.Println("Stopping game engine...")

	g.cancel()

	// Save all data

	// Logout all characters

	return nil

}

// Run the game engine

func (g *Game) Run(errChan chan error) error {

	fmt.Println("Starting game engine...")

	// Start Game Heart Beat

	g.ticker = time.NewTicker(time.Second)
	defer g.ticker.Stop()

	for {
		select {
		case <-g.globalCtx.Done():
			Logger.Info("Global shutdown requested")
			return nil
		case <-g.ctx.Done():
			Logger.Info("Game shutdown requested")
			return nil
		case <-g.ticker.C:
			// Run game logic
			err := g.tick()
			if err != nil {
				Logger.Error("Error running game logic", "error", err)
				errChan <- fmt.Errorf("error running game logic: %w", err)
				return fmt.Errorf("error running game logic: %w", err)
			}
		}
	}
}

// Game heart beat

func (g *Game) tick() error {

	fmt.Print(".")

	// Run game logic
	return nil
}
