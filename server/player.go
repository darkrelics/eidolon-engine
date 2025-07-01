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
	"context"
	"fmt"
	"sync"
	"sync/atomic"
	"time"

	"github.com/gofrs/uuid/v5"
	"golang.org/x/crypto/ssh"
)

type Player struct {
	ctx           context.Context
	cancel        context.CancelFunc
	index         uint64
	id            uuid.UUID   // Using uuid.UUID type instead of string
	email         string      // Field to store email address
	commandOut    chan string // Commands to player
	commandIn     chan string // Commands from player
	playerError   chan error
	consoleDone   chan bool
	echo          bool
	prompt        string
	connection    ssh.Channel
	consoleWidth  int
	consoleHeight int
	characterList map[string]*PlayerCharacterInfo
	seenMotD      []uuid.UUID
	character     *Character
	login         time.Time
	lastEdited    time.Time
	lastSaved     time.Time
	server        *Server
	mutex         sync.RWMutex
	shutdownOnce  sync.Once
	done          chan struct{} // Channel signaled when all goroutines complete
	inputBuffer   *InputBuffer  // Track current input line content
}

func NewPlayerSSH(server *Server, playerEmail string, conn ssh.Channel, interfaceCtx context.Context, userUUID uuid.UUID) (*Player, error) {
	ctx, cancel := context.WithCancel(server.ctx)

	player := &Player{
		server:        server,
		id:            userUUID,    // Using uuid.UUID directly
		email:         playerEmail, // Store email separately
		commandOut:    make(chan string, 10),
		commandIn:     make(chan string, 10),
		playerError:   make(chan error, 1),
		consoleDone:   make(chan bool, 1),
		echo:          true,
		connection:    conn,
		consoleWidth:  80,
		consoleHeight: 24,
		login:         time.Now(),
		ctx:           ctx,
		cancel:        cancel,
		shutdownOnce:  sync.Once{},
		done:          make(chan struct{}),
		inputBuffer:   NewInputBuffer(),
	}

	// Load player data
	if err := player.Load(userUUID); err != nil {
		cancel()
		return nil, fmt.Errorf("player data load: %w", err)
	}

	// Register with server
	err := server.AddPlayer(player)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("player registration: %w", err)
	}

	return player, nil
}

func (p *Player) RunSSH(requests <-chan *ssh.Request) {
	Logger.Info("Player connected", "player_name", p.id)

	defer p.Stop()

	// Create channels for each goroutine
	requestDone := make(chan error, 1)
	inputDone := make(chan error, 1)
	outputDone := make(chan error, 1)

	// Channel to track when all goroutines have completed
	allDone := make(chan struct{})
	var activeGoroutines int32 = 4

	// Helper to track goroutine completion
	trackDone := func() {
		if atomic.AddInt32(&activeGoroutines, -1) == 0 {
			close(allDone)
		}
	}

	// Start handlers
	go func() {
		defer trackDone()
		p.handleRequests(p.ctx, requests, requestDone)
	}()

	go func() {
		defer trackDone()
		p.handleInput(p.ctx, inputDone)
	}()

	go func() {
		defer trackDone()
		p.handleOutput(p.ctx, outputDone)
	}()

	// Display MOTDs after connection is established but before entering main loop
	if err := DisplayUnseenMOTDs(p); err != nil {
		Logger.Error("motd display error", "player", p.id, "error", err)
		// Continue despite MOTD display error
	}

	// Start Player Interface
	go func() {
		defer trackDone()
		p.Console(p.consoleDone)
	}()

	// Monitor for completion in a separate goroutine
	go func() {
		<-allDone
		close(p.done)
	}()

	// Wait for shutdown conditions
	select {
	case <-p.ctx.Done():
		Logger.Info("Player session ending due to context cancellation", "player", p.id)
		return
	case err := <-p.playerError:
		if err != nil {
			Logger.Error("Player error", "player_name", p.id, "error", err)
		}
		return
	case err := <-requestDone:
		if err != nil && err != context.Canceled {
			Logger.Error("Request handler error", "player", p.id, "error", err)
		}
		return
	case err := <-inputDone:
		if err != nil && err != context.Canceled {
			Logger.Error("Input handler error", "player", p.id, "error", err)
		}
		return
	case err := <-outputDone:
		if err != nil && err != context.Canceled {
			Logger.Error("Output handler error", "player", p.id, "error", err)
		}
		return
	case <-p.consoleDone:
		Logger.Info("Player console session ended", "player", p.id)
		return
	}
}

func (p *Player) Stop() {
	if p == nil {
		return
	}

	// Use shutdownOnce to ensure we only perform cleanup once
	p.shutdownOnce.Do(func() {
		Logger.Info("Player disconnected", "player_name", p.id)

		// Cancel context if not already done
		select {
		case <-p.ctx.Done():
			// Context is already canceled
		default:
			// Cancel the context to signal all goroutines to exit
			p.cancel()
		}

		// Stop the character if active
		if p.character != nil {
			Logger.Info("Stopping active character", "character", p.character.name)
			p.character.Stop()
			p.character = nil
		}

		// Save player data with fresh context for shutdown
		saveCtx := context.Background()
		if err := p.SaveWithContext(saveCtx); err != nil {
			Logger.Error("Player: Failed to save on disconnect", "error", err, "player", p.id)
		}

		// Close the connection
		if p.connection != nil {
			p.connection.Close()
		}

		// Remove from server (do this last to avoid race conditions)
		if p.server != nil {
			p.server.mutex.Lock()
			delete(p.server.players, p.index)
			delete(p.server.playersByUUID, p.id)
			p.server.playerCount.Add(^uint64(0)) // Decrement count
			p.server.mutex.Unlock()
			Logger.Info("Player removed from server", "player_name", p.id)
		}

		// Wait for all goroutines to complete
		<-p.done

		// Close channels after all operations are done
		close(p.commandOut)
		close(p.commandIn)
		close(p.playerError)
	})
}

func (p *Player) MarkCharacterDead(characterName string) {
	p.mutex.Lock()
	defer p.mutex.Unlock()

	if characterInfo, exists := p.characterList[characterName]; exists {
		characterInfo.Dead = true
		p.lastEdited = time.Now()

		// Save player data
		if err := p.Save(); err != nil {
			Logger.Error("Failed to save player data after character death", "player", p.id, "character", characterName, "error", err)
		}
	}
}

func (s *Server) RemovePlayer(playerID uint64) error {
	s.mutex.RLock()
	player, exists := s.players[playerID]
	s.mutex.RUnlock()

	if !exists || player == nil {
		Logger.Warn("Attempted to remove non-existent player", "playerID", playerID)
		return nil
	}

	Logger.Info("Removing inactive player", "playerID", player.id.String(), "playerIndex", playerID)

	// Stop the player properly - this handles all cleanup
	player.Stop()

	return nil
}
