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

type Game struct {
	Config               *Configuration
	GlobalContext        context.Context
	Context              context.Context
	Cancel               context.CancelFunc
	Mutex                sync.RWMutex
	StartTime            time.Time
	characterCount       atomic.Uint64
	ticker               *time.Ticker
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
	AutoSaveInterval     uint16
	shutdownOnce         sync.Once
}

func NewGame(globalCtx context.Context, config *Configuration) (*Game, error) {
	Logger.Info("Initializing game engine...")

	ctx, cancel := context.WithCancel(globalCtx)

	game := &Game{
		Config:        config,
		GlobalContext: globalCtx,
		Context:       ctx,
		Cancel:        cancel,
		StartTime:     time.Now(),
		Characters:    make(map[uuid.UUID]*Character),
		Rooms:         make(map[int64]*Room),
		Prototypes:    make(map[uuid.UUID]*Prototype),
		Items:         make(map[uuid.UUID]*Item),
		ticker:        time.NewTicker(time.Second),
	}

	database, err := NewKeyPair(config.Aws.Region)
	if err != nil {
		return nil, fmt.Errorf("database init error: %w", err)
	}
	game.Database = database

	if err := game.initBloomFilter(); err != nil {
		return nil, fmt.Errorf("bloom filter init error: %w", err)
	}

	if err := LoadArchetypes(game); err != nil {
		Logger.Error("archetype loading failed", "error", err)
	}

	game.Rooms[0] = NewRoom(0, "The Void", "The Void", "Default void room.")

	if rooms, err := game.Database.LoadRooms(); err != nil {
		Logger.Error("room loading failed", "error", err)
	} else {
		for id, room := range rooms {
			game.Rooms[id] = room
		}
	}

	return game, nil
}

func (g *Game) Run() error {
	Logger.Info("Starting game engine...")
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-g.GlobalContext.Done():
			return g.shutdown("global shutdown")
		case <-g.Context.Done():
			return g.shutdown("game shutdown")
		case <-ticker.C:
			g.tick()
		}
	}
}

func (g *Game) Stop() error {
	var stopErr error
	g.shutdownOnce.Do(func() {
		g.Cancel()
		stopErr = g.shutdown("manual stop")
	})
	return stopErr
}

func (g *Game) initBloomFilter() error {
	names, err := LoadCharacterNames(g.Database)
	if err != nil {
		return fmt.Errorf("character names load error: %w", err)
	}

	namesFromFile, err := loadNamesFromFile("../data/names.txt")
	if err != nil {
		return fmt.Errorf("names file load error: %w", err)
	}

	obscenities, err := loadNamesFromFile("../data/obscenity.txt")
	if err != nil {
		return fmt.Errorf("obscenity file load error: %w", err)
	}

	totalItems := len(names) + len(namesFromFile) + len(obscenities)
	if totalItems < 100 {
		totalItems = 100
	}

	g.CharacterBloomFilter = bloom.NewWithEstimates(uint(totalItems), 0.01)

	for name := range names {
		g.CharacterBloomFilter.AddString(strings.ToLower(name))
	}
	for _, name := range append(namesFromFile, obscenities...) {
		g.CharacterBloomFilter.AddString(strings.ToLower(name))
	}

	return nil
}

func (g *Game) AutoSave(ctx context.Context) error {
	if g.AutoSaveInterval == 0 {
		return nil
	}

	ticker := time.NewTicker(time.Duration(g.AutoSaveInterval) * time.Minute)
	defer ticker.Stop()

	if err := g.saveAll(ctx); err != nil {
		Logger.Error("initial save failed", "error", err)
	}

	for {
		select {
		case <-ctx.Done():
			return g.saveAll(context.Background())
		case <-ticker.C:
			if err := g.saveAll(ctx); err != nil {
				Logger.Error("auto-save failed", "error", err)
			}
		}
	}
}

func (g *Game) saveAll(ctx context.Context) error {
	saveCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()

	var wg sync.WaitGroup
	errChan := make(chan error, 3)

	wg.Add(3)
	go func() {
		defer wg.Done()
		if err := g.SaveActiveCharacters(); err != nil {
			errChan <- fmt.Errorf("character save error: %w", err)
		}
	}()

	go func() {
		defer wg.Done()
		if err := SaveActiveItems(g); err != nil {
			errChan <- fmt.Errorf("item save error: %w", err)
		}
	}()

	go func() {
		defer wg.Done()
		if err := SaveActiveRooms(g); err != nil {
			errChan <- fmt.Errorf("room save error: %w", err)
		}
	}()

	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()

	select {
	case <-saveCtx.Done():
		return fmt.Errorf("save timeout: %w", saveCtx.Err())
	case err := <-errChan:
		return err
	case <-done:
		return nil
	}
}

func (g *Game) SaveActiveCharacters() error {
	g.Mutex.RLock()
	defer g.Mutex.RUnlock()

	for _, c := range g.Characters {
		if !c.LastEdited.After(c.LastSaved) {
			continue
		}

		c.Mutex.Lock()
		c.LastSaved = time.Now()
		c.Mutex.Unlock()
	}

	return nil
}

func (g *Game) tick() {
	g.Mutex.RLock()
	defer g.Mutex.RUnlock()
	// Game tick logic here
}

func (g *Game) shutdown(reason string) error {
	Logger.Info("game shutdown", "reason", reason)
	if err := g.saveAll(context.Background()); err != nil {
		return fmt.Errorf("shutdown save failed: %w", err)
	}
	return nil
}

func loadNamesFromFile(path string) ([]string, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("file open error: %w", err)
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
