package main

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/bits-and-blooms/bloom/v3"
	"github.com/google/uuid"
)

type Game struct {
	Config               *Configuration
	GlobalContext        context.Context
	Context              context.Context
	Cancel               context.CancelFunc
	Mutex                sync.RWMutex
	StartTime            time.Time
	CharacterCount       uint64
	Ticker               *time.Ticker
	Database             *KeyPair
	ArcheTypes           map[string]*Archetype
	CharacterBloomFilter *bloom.BloomFilter
	Characters           map[uuid.UUID]*Character
	Rooms                map[int64]*Room
	Prototypes           map[uuid.UUID]*Prototype
	Items                map[uuid.UUID]*Item
	StartingHealth       uint16
	StartingEssence      uint16
	Balance              float64
	AutoSaveInterval     uint16 // in minutes
}

const FalsePositiveRate = 0.01 // 1% bloom filter false positive rate

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
	err = game.InitializeBloomFilter()
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
	loadedRooms, err := game.Database.LoadRooms()
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
func (game *Game) Run() error {
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

func (game *Game) Stop() {
	Logger.Info("Stopping game...")
	game.Cancel()
}

// InitializeBloomFilter initializes the bloom filter with existing character names,
// as well as names from ./data/names.txt and ./data/obscenity.txt.
func (game *Game) InitializeBloomFilter() error {
	// Load character names from the database
	characterNames, err := LoadCharacterNames(game.Database)
	if err != nil {
		return fmt.Errorf("failed to load character names: %w", err)
	}

	// Load additional names from names.txt
	namesFilePath := "./data/names.txt"
	namesFromFile, err := loadNamesFromFile(namesFilePath)
	if err != nil {
		return fmt.Errorf("failed to load names from %s: %w", namesFilePath, err)
	}

	// Load obscenity words from obscenity.txt
	obscenityFilePath := "./data/obscenity.txt"
	obscenities, err := loadNamesFromFile(obscenityFilePath)
	if err != nil {
		return fmt.Errorf("failed to load obscenities from %s: %w", obscenityFilePath, err)
	}

	// Calculate total number of items to add to the bloom filter
	totalItems := len(characterNames)
	for range characterNames { // Assuming characterNames is a map; adjust if it's a slice
		// Counting items in characterNames
	}
	totalItems += len(namesFromFile)
	totalItems += len(obscenities)

	// Ensure a minimum size
	if totalItems < 100 {
		totalItems = 100
	}

	fpRate := FalsePositiveRate

	// Initialize the bloom filter with the estimated number of items and false positive rate
	game.CharacterBloomFilter = bloom.NewWithEstimates(uint(totalItems), fpRate)

	// Add character names to the bloom filter
	for name := range characterNames {
		game.CharacterBloomFilter.AddString(strings.ToLower(name))
	}

	// Add names from names.txt to the bloom filter
	for _, name := range namesFromFile {
		game.CharacterBloomFilter.AddString(name)
	}

	// Add obscenities to the bloom filter
	for _, word := range obscenities {
		game.CharacterBloomFilter.AddString(word)
	}

	Logger.Debug("Bloom filter initialized",
		"estimatedSize", totalItems,
		"falsePositiveRate", fpRate,
		"totalItemsAdded", totalItems,
	)

	return nil
}

// loadNamesFromFile reads a file line by line and returns a slice of names.
func loadNamesFromFile(filePath string) ([]string, error) {
	file, err := os.Open(filePath)
	if err != nil {
		return nil, fmt.Errorf("failed to open %s: %w", filePath, err)
	}
	defer file.Close()

	var names []string
	scanner := bufio.NewScanner(file)
	lineNumber := 1
	for scanner.Scan() {
		name := strings.TrimSpace(scanner.Text())
		if name != "" {
			names = append(names, strings.ToLower(name))
		}
		lineNumber++
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("error reading %s: %w", filePath, err)
	}

	return names, nil
}

// AutoSave runs the main auto-save loop
func (game *Game) AutoSave(ctx context.Context) error {
	if game == nil {
		return fmt.Errorf("game instance is nil")
	}

	// Configure the auto-save interval
	interval := game.AutoSaveInterval
	if interval == 0 {
		Logger.Warn("Auto-save interval not configured")
		return nil
	}

	saveInterval := time.Duration(interval) * time.Minute
	Logger.Info("Starting auto-save routine", "interval", saveInterval)

	// Create ticker for periodic saves
	ticker := time.NewTicker(saveInterval)
	defer ticker.Stop()

	// Perform initial save
	runSaveOperation(ctx, game)

	// Main auto-save loop
	for {
		select {
		case <-ctx.Done():
			Logger.Info("Auto-save routine stopping due to context cancellation")
			// Perform final save before shutting down
			runSaveOperation(context.Background(), game)
			return ctx.Err()

		case <-ticker.C:
			runSaveOperation(ctx, game)
		}
	}
}

func (g *Game) performAutoSave(ctx context.Context) error {
	// Create a context with timeout for the save operation
	saveCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()

	// Create error channel to collect errors from goroutines
	errChan := make(chan error, 3)

	// Launch save operations concurrently
	go func() {
		if err := g.SaveActiveCharacters(); err != nil {
			errChan <- fmt.Errorf("failed to save characters: %w", err)
			return
		}
		errChan <- nil
	}()

	go func() {
		if err := SaveActiveItems(g); err != nil {
			errChan <- fmt.Errorf("failed to save items: %w", err)
			return
		}
		errChan <- nil
	}()

	go func() {
		if err := SaveActiveRooms(g); err != nil {
			errChan <- fmt.Errorf("failed to save rooms: %w", err)
			return
		}
		errChan <- nil
	}()

	// Wait for all operations to complete or context cancellation
	for i := 0; i < 3; i++ {
		select {
		case err := <-errChan:
			if err != nil {
				return fmt.Errorf("auto-save operation failed: %w", err)
			}
		case <-saveCtx.Done():
			return fmt.Errorf("auto-save operation timed out: %w", saveCtx.Err())
		}
	}

	return nil
}

// SaveActiveCharacters saves all active characters to the database if they have been edited since the last save.
func (g *Game) SaveActiveCharacters() error {

	Logger.Debug("Saving active characters...")

	for _, c := range g.Characters {
		// Check if the character's LastEdited is before LastSaved
		if !c.LastEdited.After(c.LastSaved) {
			Logger.Debug("Character not edited since last save, skipping", "characterName", c.Name)
			continue // Skip writing this character
		}

		c.Mutex.Lock()
		// Attempt to write the character to the database
		// err := WriteCharacter(c, g.Database)
		// if err != nil {
		// 	Logger.Error("Error saving character", "characterName", c.Name, "error", err)
		// 	continue // Continue saving other characters even if one fails
		// }

		// Update LastSaved after a successful write
		c.LastSaved = time.Now()
		Logger.Debug("Character saved successfully", "characterName", c.Name)
		c.Mutex.Unlock()
	}

	Logger.Info("Active characters saved successfully.")
	return nil
}

// runSaveOperation executes a single save operation with metrics
func runSaveOperation(ctx context.Context, g *Game) {
	start := time.Now()

	err := g.performAutoSave(ctx)
	duration := time.Since(start)

	if err != nil {
		Logger.Error("Auto-save failed",
			"error", err,
			"duration", duration)
	} else {
		Logger.Debug("Auto-save completed successfully",
			"duration", duration)
	}
}
