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
	"github.com/gofrs/uuid/v5"
)

// TODO: Move to config
var NAMES_PATH = "../data/names.txt"
var OBSCENITY_PATH = "../data/obscenity.txt"

type Game struct {
	config               *Configuration
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
	commands             map[string]CommandInfo
	startingHealth       uint16
	startingEssence      uint16
	balance              float64
	autoSaveInterval     uint16
}

// Initalize the game engine

func NewGame(globalCtx context.Context, config *Configuration) (*Game, error) {

	Logger.Info("New Game...Initalizing Game...")

	ctx, cancel := context.WithCancel(globalCtx)

	// Create a new game object

	game := &Game{
		config:           config,
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
		commands:         make(map[string]CommandInfo),
		ticker:           nil,
		startingHealth:   config.Game.StartingHealth,
		startingEssence:  config.Game.StartingEssence,
		balance:          config.Game.Balance,
		autoSaveInterval: 5,
	}

	game.characterCount.Store(0)

	// Initialize Game Database Interface

	database, err := NewKeyPair(ctx, config)
	if err != nil {
		return nil, fmt.Errorf("database init error: %w", err)
	}

	game.database = database

	// Load Character Bloom Filter

	if err := game.InitCharacterBloomFilter(); err != nil {
		Logger.Warn("Error initializing character bloom filter", "error", err)
	}

	// Create Default Room

	game.rooms[0] = NewRoom(ctx, 0, "The Void", "The Void", "Default void room.", true, "") // Default room is always persistent, no script

	// Load Rooms

	if err := game.LoadRooms(); err != nil {
		Logger.Error("Error loading rooms", "error", err)
	}

	// Load Item Prototypes

	prototypes, err := LoadPrototypes(ctx, game.database)
	if err != nil {
		Logger.Warn("Error loading item prototypes", "error", err)
	} else {
		game.prototypes = prototypes

		// Validate prototypes after loading
		if err := ValidatePrototypes(prototypes); err != nil {
			Logger.Error("Error validating prototypes", "error", err)
		}
	}

	// Load Archetypes

	if err := game.LoadArchetypes(); err != nil {
		Logger.Error("Error loading archetypes", "error", err)
	}

	// Build Archetype Options

	if err := game.BuildArchetypeOptions(); err != nil {
		Logger.Error("Error loading archetype options", "error", err)
	}

	game.initCommands()

	return game, nil

}

// Load names from the database.

func (g *Game) LoadCharacterNames() ([]string, error) {

	Logger.Info("Loading character names from database...")

	var names []string

	// Load all characters and players in one operation
	characters, players, err := g.database.LoadCharactersAndPlayers(g.ctx)
	if err != nil {
		Logger.Error("Error loading characters and players", "error", err)
		return nil, err
	}

	// Build a map of character IDs to their owning players
	characterToPlayers := make(map[string][]string)
	for _, player := range players {
		for _, charID := range player.CharacterList {
			characterToPlayers[charID] = append(characterToPlayers[charID], player.PlayerID)
		}
	}

	// Process characters
	for _, character := range characters {
		// Check if character has a player association
		associatedPlayers, hasAssociation := characterToPlayers[character.CharacterID]
		
		if !hasAssociation || len(associatedPlayers) == 0 {
			// Character has no player association - delete it
			Logger.Warn("Deleting orphaned character", 
				"characterID", character.CharacterID,
				"characterName", character.CharacterName)
			
			err := g.database.DeleteCharacter(g.ctx, character.CharacterID)
			if err != nil {
				Logger.Error("Failed to delete orphaned character",
					"characterID", character.CharacterID,
					"error", err)
			}
			continue
		}

		// Check for duplicate associations
		if len(associatedPlayers) > 1 {
			Logger.Warn("Character has multiple player associations",
				"characterID", character.CharacterID,
				"characterName", character.CharacterName,
				"players", associatedPlayers)
			
			// Keep only the first association
			for i := 1; i < len(associatedPlayers); i++ {
				err := g.database.RemoveCharacterFromPlayer(g.ctx, associatedPlayers[i], character.CharacterName)
				if err != nil {
					Logger.Error("Failed to remove duplicate character association",
						"playerID", associatedPlayers[i],
						"characterID", character.CharacterID,
						"error", err)
				}
			}
		}

		// Add valid character name to bloom filter
		names = append(names, strings.ToLower(character.CharacterName))
	}

	Logger.Info("Character name loading complete",
		"totalNames", len(names),
		"totalCharacters", len(characters))

	return names, nil
}


// Load names from a file.

func LoadNameFromFile(path string) ([]string, error) {

	Logger.Info("Loading names from file", "path", path)

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

	Logger.Info("Initializing character name bloom filter...")

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

	Logger.Info("Stopping game engine...")

	g.cancel()

	// Save all active characters
	g.saveAllCharacters()

	// Logout all characters
	g.logoutAllCharacters()

	return nil

}

// Run the game engine

func (g *Game) Run(errChan chan error) error {
	var runErr error
	RunWithPanicRecoveryCallback("game.Run", func() {
		runErr = g.runInternal(errChan)
	}, func(err error) {
		SendErrorNonBlocking(errChan, fmt.Errorf("panic in Game: %v", err), "Game")
	})
	return runErr
}

// runInternal contains the actual game loop logic
func (g *Game) runInternal(errChan chan error) error {
	Logger.Info("Starting game engine...")

	// Start Game Heart Beat

	g.ticker = time.NewTicker(time.Second)
	defer g.ticker.Stop()

	for {
		select {
		case <-g.ctx.Done():
			Logger.Info("Game shutdown requested")
			return nil
		case <-g.ticker.C:
			// Run game logic
			err := g.tick()
			if err != nil {
				Logger.Error("Error running game logic", "error", err)
				gameErr := fmt.Errorf("error running game logic: %w", err)
				SendErrorNonBlocking(errChan, gameErr, "Game")
				return gameErr
			}
		}
	}
}

// Game heart beat

func (g *Game) tick() error {
	// Process any pending game-tier commands
	g.processGameCommands()

	// Run other game logic
	return nil
}

// processGameCommands processes any commands that have been escalated to game tier
func (g *Game) processGameCommands() {
	// Collect active rooms and characters while holding the lock
	g.mutex.RLock()

	// Make a slice of rooms to process
	activeRooms := make([]*Room, 0, len(g.rooms))
	for _, room := range g.rooms {
		if room != nil && room.running {
			activeRooms = append(activeRooms, room)
		}
	}

	// Make a slice of characters to process
	activeCharacters := make([]*Character, 0, len(g.characters))
	for _, character := range g.characters {
		if character != nil {
			activeCharacters = append(activeCharacters, character)
		}
	}

	g.mutex.RUnlock()

	// Now process commands without holding the lock
	// Process commands from all active rooms
	for _, room := range activeRooms {
		// Non-blocking check for commands from this room
		select {
		case cmd, ok := <-room.gameCommandOut:
			if !ok {
				// Channel closed, skip this room
				continue
			}
			// Handle the command asynchronously
			go RunWithPanicRecovery("game.handleCommand", func() {
				g.handleGameCommand(cmd)
			}, "verb", cmd.Verb, "character", cmd.Character.name)
		default:
			// No command waiting, continue to next room
		}
	}

	// Process commands from characters directly
	for _, character := range activeCharacters {
		// Non-blocking check for commands from this character
		select {
		case cmd, ok := <-character.gameCommandOut:
			if !ok {
				// Channel closed, skip this character
				continue
			}
			// Handle the command asynchronously
			go RunWithPanicRecovery("game.handleCommand", func() {
				g.handleGameCommand(cmd)
			}, "verb", cmd.Verb, "character", cmd.Character.name)
		default:
			// No command waiting, continue to next character
		}
	}
}

// handleGameCommand processes a command at the game tier
func (g *Game) handleGameCommand(cmd *CommandRequest) {
	if cmd == nil {
		Logger.Error("Received nil command request in game handler")
		return
	}

	Logger.Debug("Processing game-tier command", "verb", cmd.Verb, "character", cmd.Character.name)

	// Update command state
	cmd.State = CommandProcessing

	// Process the command using our game command handler
	response := g.ProcessGameCommand(cmd)

	// Send response
	g.sendCommandResponse(cmd, response)
}

// handleEnvironmentCommand processes environment-related commands
func (g *Game) handleEnvironmentCommand(cmd *CommandRequest) *CommandResponse {
	var msg string

	switch cmd.Verb {
	case "time":
		// Report game time
		gameTime := time.Now() // Placeholder for actual game time
		msg = fmt.Sprintf("\n\rCurrent game time: %s\n\r", gameTime.Format("15:04:05"))
	case "weather":
		// Report game weather
		msg = "\n\rThe weather is clear and pleasant.\n\r" // Placeholder for actual weather system
	}

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   msg,
		Timestamp: time.Now(),
	}
}

// handleGlobalCommunicationCommand processes global communication commands
func (g *Game) handleGlobalCommunicationCommand(cmd *CommandRequest) *CommandResponse {
	if len(cmd.Args) < 2 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("what do you want to %s?", cmd.Verb),
			Timestamp: time.Now(),
		}
	}

	// Extract the message
	message := strings.Join(cmd.Args[1:], " ")

	// Format based on command type
	var broadcastMsg string
	switch cmd.Verb {
	case "shout":
		broadcastMsg = fmt.Sprintf("\n\r%s shouts: %s\n\r", cmd.Character.name, message)
	case "announce":
		broadcastMsg = fmt.Sprintf("\n\r[Announcement] %s: %s\n\r", cmd.Character.name, message)
	}

	// Collect recipients while holding the lock
	g.mutex.RLock()
	recipients := make([]*Character, 0, len(g.characters))
	for _, c := range g.characters {
		if c != nil && c != cmd.Character && c.player != nil {
			recipients = append(recipients, c)
		}
	}
	g.mutex.RUnlock()

	// Broadcast to all recipients without holding the lock
	for _, c := range recipients {
		select {
		case c.player.commandOut <- broadcastMsg:
			// Message sent successfully
			select {
			case c.player.commandOut <- c.prompt:
				// Prompt sent successfully
			default:
				// Could not send prompt, but that's ok
			}
		default:
			// Could not send message, character's buffer might be full
			Logger.Warn("Failed to send global message to player",
				"recipient", c.name,
				"sender", cmd.Character.name)
		}
	}

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   broadcastMsg, // Also send to the originating character
		Timestamp: time.Now(),
	}
}

// sendCommandResponse sends a response to a command request
func (g *Game) sendCommandResponse(cmd *CommandRequest, response *CommandResponse) {
	if cmd == nil || response == nil {
		return
	}

	// If direct response channel is provided, use it
	if cmd.Response != nil {
		select {
		case cmd.Response <- response:
			// Response sent successfully
			return
		default:
			Logger.Warn("Failed to send direct command response",
				"characterName", cmd.Character.name,
				"commandID", cmd.ID)
			// Fall through to try character's gameCommandIn channel
		}
	}

	// Otherwise, send through character's gameCommandIn channel
	if cmd.Character != nil && cmd.Character.gameCommandIn != nil {
		select {
		case cmd.Character.gameCommandIn <- response:
			// Response sent successfully
		default:
			Logger.Warn("Failed to send command response to character",
				"characterName", cmd.Character.name,
				"commandID", cmd.ID)
		}
	}
}

func (g *Game) ValidateCharacterName(name string) error {

	if len(name) < 4 {
		return fmt.Errorf("character name is too short")
	}

	if len(name) > 20 {
		return fmt.Errorf("character name is too long")
	}

	if g.characterBloomFilter.TestString(strings.ToLower(name)) {
		return fmt.Errorf("character name is invalid")
	}

	return nil
}

// saveAllCharacters saves all active characters
func (g *Game) saveAllCharacters() {
	// Collect characters while holding the lock
	g.mutex.RLock()
	characters := make([]*Character, 0, len(g.characters))
	for _, character := range g.characters {
		if character != nil {
			characters = append(characters, character)
		}
	}
	g.mutex.RUnlock()

	// Save characters without holding the lock
	for _, character := range characters {
		if err := character.Save(); err != nil {
			Logger.Error("Error saving character during shutdown", "characterName", character.name, "error", err)
		}
	}
}

// logoutAllCharacters logs out all active characters
func (g *Game) logoutAllCharacters() {
	// Collect characters while holding the lock
	g.mutex.RLock()
	characters := make([]*Character, 0, len(g.characters))
	for _, character := range g.characters {
		if character != nil {
			characters = append(characters, character)
		}
	}
	g.mutex.RUnlock()

	// Stop characters without holding the lock
	for _, character := range characters {
		character.Stop()
	}
}
