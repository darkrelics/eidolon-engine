/*
Eidolon Engine

Copyright 2024-2025 Jason Robinson

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

func NewGame(globalCtx context.Context, config *Configuration) (*Game, error) {

	Logger.Info("New Game...Initializing Game...")

	ctx, cancel := context.WithCancel(globalCtx)

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

	database, err := NewKeyPair(ctx, config)
	if err != nil {
		return nil, fmt.Errorf("database init error: %w", err)
	}

	game.database = database

	if err := game.InitCharacterBloomFilter(); err != nil {
		Logger.Warn("Error initializing character bloom filter", "error", err)
	}

	// Initialize script manager BEFORE loading rooms
	Logger.Info("Initializing Script Manager...")
	if err := InitScriptManager(config); err != nil {
		Logger.Error("Script manager initialization failed - continuing without scripting", "error", err)
		Logger.Error("AWS credentials or configuration may be missing", "scriptsS3Bucket", config.S3.ScriptsBucket, "awsRegion", config.AWS.Region)
	} else {
		Logger.Info("Script manager initialized successfully")
	}

	game.rooms[0] = NewRoom(ctx, 0, "The Void", "The Void", "Default void room.", true, "") // Default room is always persistent, no script

	if err := game.LoadRooms(); err != nil {
		Logger.Error("Error loading rooms", "error", err)
	}

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

	if err := game.LoadArchetypes(); err != nil {
		Logger.Error("Error loading archetypes", "error", err)
	}

	game.BuildArchetypeOptions()

	game.initCommands()

	// Build fuzzy matching indices
	game.buildCommandIndex() // Build command index for fuzzy matching
	buildOrdinalIndex()      // Build ordinal index for fuzzy matching

	return game, nil

}

func (g *Game) LoadCharacterNames() ([]string, error) {

	Logger.Info("Loading character names from database...")

	// Load only character names for bloom filter
	names, err := g.database.LoadCharacterNames(g.ctx)
	if err != nil {
		Logger.Error("Error loading character names", "error", err)
		return nil, err
	}

	Logger.Info("Character name loading complete",
		"totalNames", len(names))

	return names, nil
}

func LoadNameFromFile(path string) ([]string, error) {

	Logger.Info("Loading names from file", "path", path)

	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("error opening file: %w", err)
	}
	defer func() {
		if err := file.Close(); err != nil {
			Logger.Error("LoadNameFromFile: Failed to close file", "error", err)
		}
	}()

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

func (g *Game) InitCharacterBloomFilter() error {

	Logger.Info("Initializing character name bloom filter...")

	names, err := g.LoadCharacterNames()
	if err != nil {
		Logger.Warn("Error loading character names from database", "error", err)
	}

	namesFromFile, err := LoadNameFromFile(g.config.Game.NamesPath)
	if err != nil {
		Logger.Warn("Error loading character names from file", "error", err)
	}

	obscenities, err := LoadNameFromFile(g.config.Game.ObscenityPath)
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

	// CRITICAL: Save all character data BEFORE cancelling context
	// This ensures all database operations complete successfully during shutdown
	// Customer data persistence is our highest priority
	g.saveAllCharacters()

	// Logout all characters after saving
	g.logoutAllCharacters()

	// Only cancel context after all critical data is persisted
	// This prevents database operations from failing due to cancelled context
	g.cancel()

	return nil

}

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

	g.ticker = time.NewTicker(time.Second)
	defer g.ticker.Stop()

	for {
		select {
		case <-g.ctx.Done():
			Logger.Info("Game shutdown requested")
			return nil
		case <-g.ticker.C:
			// Game tick processes time-based events
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

func (g *Game) tick() error {
	g.processGameCommands()

	if time.Now().Unix()%30 == 0 {
		g.processCharacterHealing()
	}

	return nil
}

func (g *Game) processCharacterHealing() {
	g.mutex.RLock()
	defer g.mutex.RUnlock()

	for _, character := range g.characters {
		if character != nil && character.player != nil {
			character.CalculateCurrentHealth()
		}
	}
}

func (g *Game) processGameCommands() {
	// Process commands from rooms and characters with single read lock
	g.mutex.RLock()
	defer g.mutex.RUnlock()

	// Room command collection prevents blocking
	for _, room := range g.rooms {
		if room != nil && room.running {
			// Non-blocking check for commands from this room
			select {
			case cmd, ok := <-room.gameCommandOut:
				if !ok {
					// Channel closed, skip this room
					continue
				}
				// Async handling prevents command queue blocking
				go RunWithPanicRecovery("game.handleCommand", func() {
					g.handleGameCommand(cmd)
				}, "verb", cmd.Verb, "character", cmd.Character.name)
			default:
				// No command waiting, continue to next room
			}
		}
	}

	// Direct character commands bypass room processing
	for _, character := range g.characters {
		if character != nil {
			// Non-blocking check for commands from this character
			select {
			case cmd, ok := <-character.gameCommandOut:
				if !ok {
					// Channel closed, skip this character
					continue
				}
				// Async handling prevents command queue blocking
				go RunWithPanicRecovery("game.handleCommand", func() {
					g.handleGameCommand(cmd)
				}, "verb", cmd.Verb, "character", cmd.Character.name)
			default:
				// No command waiting, continue to next character
			}
		}
	}
}

func (g *Game) handleGameCommand(cmd *CommandRequest) {
	if cmd == nil {
		Logger.Error("Received nil command request in game handler")
		return
	}

	Logger.Debug("Processing game-tier command", "verb", cmd.Verb, "character", cmd.Character.name)

	// Update command state
	cmd.State = CommandProcessing

	// Game handler processes global-scope commands
	response := g.ProcessGameCommand(cmd)

	// Response delivery completes command cycle
	g.sendCommandResponse(cmd, response)
}

func (g *Game) DeleteItem(itemID uuid.UUID) {
	g.mutex.Lock()
	defer g.mutex.Unlock()
	delete(g.items, itemID)
}

func (g *Game) DeleteItems(itemIDs []uuid.UUID) {
	g.mutex.Lock()
	defer g.mutex.Unlock()
	for _, itemID := range itemIDs {
		delete(g.items, itemID)
	}
}

func (g *Game) clearExitReferencesToRoom(roomID int64) {
	g.mutex.Lock()
	defer g.mutex.Unlock()

	// Iterate through all exits and clear references to this room
	for _, exit := range g.exits {
		if exit != nil && exit.targetRoomID == roomID {
			// Since we already hold the game mutex, we can safely clear the reference
			exit.targetRoom = nil
		}
	}

	Logger.Debug("Cleared exit references to room", "roomID", roomID)
}

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

func (g *Game) saveAllCharacters() {
	// Use a separate context with timeout to ensure saves don't hang indefinitely
	saveCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	g.mutex.RLock()
	characterCount := len(g.characters)
	g.mutex.RUnlock()

	Logger.Info("Saving all characters during shutdown", "characterCount", characterCount)

	savedCount := 0
	g.mutex.RLock()
	for _, character := range g.characters {
		if character != nil {
			// Override character's game context with our save context to ensure DB operations succeed
			if err := character.SaveWithContext(saveCtx); err != nil {
				Logger.Error("Error saving character during shutdown", "characterName", character.name, "error", err)
			} else {
				savedCount++
			}
		}
	}
	g.mutex.RUnlock()

	Logger.Info("Completed saving characters during shutdown", "savedCount", savedCount, "totalCount", characterCount)
}

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
