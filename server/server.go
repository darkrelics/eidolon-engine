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
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/cognitoidentityprovider"
	"github.com/gofrs/uuid/v5"
)

type Server struct {
	config        *Configuration
	ctx           context.Context
	cancel        context.CancelFunc
	mutex         sync.RWMutex
	game          *Game
	database      *KeyPair
	start         time.Time
	playerCount   atomic.Uint64
	players       map[uint64]*Player
	playersByUUID map[uuid.UUID]*Player
	shutdownOnce  sync.Once
	cognito       *cognitoidentityprovider.Client
	index         *Index
	activeMotDs   []*MOTD
	sshInterface  *Interface_SSH
}

type Index struct {
	IndexID uint64
	mu      sync.RWMutex
}

func (i *Index) GetID() uint64 {
	i.mu.Lock()
	defer i.mu.Unlock()

	i.IndexID++
	return i.IndexID
}

func (i *Index) SetID(id uint64) {
	i.mu.Lock()
	defer i.mu.Unlock()

	if id > i.IndexID {
		i.IndexID = id
	}
}

func NewServer(globalCtx context.Context, cfg *Configuration) (*Server, error) {

	Logger.Info("New Server...Initializing server...")

	ctx, cancel := context.WithCancel(globalCtx)

	database, err := NewKeyPair(ctx, cfg)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("database init error: %w", err)
	}

	awsConfig, err := config.LoadDefaultConfig(ctx,
		config.WithRegion(cfg.AWS.Region),
	)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("AWS config init error: %w", err)
	}

	index := &Index{
		IndexID: 0,
		mu:      sync.RWMutex{},
	}

	server := &Server{
		config:        cfg,
		ctx:           ctx,
		cancel:        cancel,
		mutex:         sync.RWMutex{},
		start:         time.Now(),
		database:      database,
		playerCount:   atomic.Uint64{},
		players:       make(map[uint64]*Player),
		playersByUUID: make(map[uuid.UUID]*Player),
		shutdownOnce:  sync.Once{},
		cognito:       cognitoidentityprovider.NewFromConfig(awsConfig),
		index:         index,
	}

	server.playerCount.Store(0)

	// Load active MOTDs
	if err := server.LoadMOTDs(); err != nil {
		Logger.Error("Failed to load MOTDs", "error", err)
		// Continue startup despite MOTD loading failure
	}

	return server, nil
}

func (s *Server) Run(errorChan chan error) error {
	var runErr error
	RunWithPanicRecoveryCallback("server.Run", func() {
		runErr = s.runInternal(errorChan)
	}, func(err error) {
		errorChan <- fmt.Errorf("panic in Server: %v", err)
	})
	return runErr
}

// runInternal contains the actual server loop logic
func (s *Server) runInternal(errorChan chan error) error {
	Logger.Info("Running server...")

	// Start SSH Interface if enabled
	if s.config.SSH.Enabled {
		if err := s.startSSHInterface(errorChan); err != nil {
			return err
		}
	} else {
		Logger.Info("SSH Interface disabled")
	}

	// Run server main loop
	ticker := time.NewTicker(5 * time.Minute)
	defer ticker.Stop()

	for {
		select {
		case <-s.ctx.Done():
			Logger.Info("Server context cancelled, initiating shutdown")
			return s.shutdown()
		case <-ticker.C:
			// Periodic cleanup of stale sessions
			s.cleanupStaleSessions()
		}
	}
}

func (s *Server) startSSHInterface(errorChan chan error) error {
	var err error
	s.sshInterface, err = NewSSHInterface(s)
	if err != nil {
		Logger.Error("Failed to start SSH interface", "error", err)
		return fmt.Errorf("failed to start SSH interface: %w", err)
	}

	go s.runSSHInterface(errorChan)

	Logger.Info("SSH Interface started successfully")
	return nil
}

func (s *Server) Stop() error {
	Logger.Info("Server: Stopping server...")
	defer Logger.Info("Server: Server stopped")

	var shutdownError error

	s.shutdownOnce.Do(func() {
		// Cancel the context to signal all components to shut down
		s.cancel()

		// Give components time to react to context cancellation
		time.Sleep(100 * time.Millisecond)

		// Stop all active players
		s.stopAllPlayers()

		// Stop the SSH interface if it's running
		if s.sshInterface != nil {
			if err := s.sshInterface.Stop(); err != nil {
				if !strings.Contains(err.Error(), "use of closed network connection") {
					Logger.Error("Error stopping SSH interface", "error", err)
					shutdownError = err
				}
			}
		}

		Logger.Info("Server shutdown complete")
	})

	return shutdownError
}

func (s *Server) shutdown() error {
	return s.Stop()
}

func (s *Server) stopAllPlayers() {
	s.mutex.RLock()
	playersCopy := make([]*Player, 0, len(s.players))
	for _, player := range s.players {
		playersCopy = append(playersCopy, player)
	}
	s.mutex.RUnlock()

	// Stop each player outside the main lock to avoid deadlocks
	for _, player := range playersCopy {
		if player != nil {
			player.Stop()
		}
	}
}

func (s *Server) cleanupStaleSessions() {
	Logger.Debug("Running session cleanup")

	s.mutex.RLock()
	now := time.Now()
	stalePlayerIDs := make([]uint64, 0)

	for id, player := range s.players {
		if player == nil {
			stalePlayerIDs = append(stalePlayerIDs, id)
			continue
		}

		// Check for players with closed connections
		if player.connection == nil {
			stalePlayerIDs = append(stalePlayerIDs, id)
		}

		// Check for inactive players (no activity for 30 minutes)
		if now.Sub(player.login) > 30*time.Minute {
			player.mutex.RLock()
			lastActivity := player.lastEdited
			player.mutex.RUnlock()

			if now.Sub(lastActivity) > 30*time.Minute {
				stalePlayerIDs = append(stalePlayerIDs, id)
			}
		}
	}
	s.mutex.RUnlock()

	// Remove stale players outside the main lock
	for _, id := range stalePlayerIDs {
		s.RemovePlayer(id)
	}

	if len(stalePlayerIDs) > 0 {
		Logger.Info("Cleaned up stale sessions", "count", len(stalePlayerIDs))
	}
}

// AddPlayer registers a new player with the server, handling existing sessions
func (s *Server) AddPlayer(player *Player) error {
	if player == nil {
		return fmt.Errorf("player is nil")
	}

	id := s.index.GetID()

	player.mutex.Lock()
	player.index = id
	player.mutex.Unlock()

	s.mutex.Lock()
	defer s.mutex.Unlock()

	// Check for existing session
	existingPlayer, exists := s.playersByUUID[player.id]
	if exists {
		// Disconnect existing session
		go s.DuplicatePlayer(existingPlayer)

		// Wait a bit to allow existing session to clean up
		time.Sleep(100 * time.Millisecond)
	}

	// Add the new player to both maps
	s.players[id] = player
	s.playersByUUID[player.id] = player

	s.playerCount.Add(1)
	Logger.Info("Player added", "playerID", id, "playerUUID", player.id.String())

	return nil
}

// DuplicatePlayer handles the process of disconnecting a player with an existing session
func (s *Server) DuplicatePlayer(existingPlayer *Player) {
	if existingPlayer == nil {
		return
	}
	
	RunWithPanicRecovery("server.DuplicatePlayer", func() {
		Logger.Info("Player already logged in, disconnecting previous session",
			"playerID", existingPlayer.id.String(),
			"email", existingPlayer.email)

		// Send a message to the existing player
		select {
		case existingPlayer.commandOut <- "\r\nYou are being disconnected because your account has logged in from another location.\r\n":
			// Message sent successfully
		default:
			// Channel might be full or closed, log and continue
			Logger.Warn("Could not send disconnect message to existing player",
				"playerID", existingPlayer.id.String())
		}

		// Stop the existing player session
		existingPlayer.Stop()

		Logger.Info("Waiting for player session to clean up", "playerID", existingPlayer.id.String())
	}, "playerID", existingPlayer.id.String())
}

func (s *Server) PlayerCount() uint64 {
	return s.playerCount.Load()
}

// GetPlayer returns a player by their UUID
func (s *Server) GetPlayer(uuid uuid.UUID) *Player {
	s.mutex.RLock()
	defer s.mutex.RUnlock()

	return s.playersByUUID[uuid]
}

// BroadcastMessage sends a message to all connected players
func (s *Server) BroadcastMessage(message string) {
	s.mutex.RLock()
	players := make([]*Player, 0, len(s.players))
	for _, player := range s.players {
		if player != nil {
			players = append(players, player)
		}
	}
	s.mutex.RUnlock()

	// Send messages outside the lock to avoid deadlocks
	for _, player := range players {
		select {
		case player.commandOut <- message:
			// Message sent successfully
		default:
			Logger.Warn("Failed to send broadcast message to player", "playerID", player.id.String())
		}
	}
}

// GetPlayerList returns a list of all connected players
func (s *Server) GetPlayerList() []uuid.UUID {
	s.mutex.RLock()
	defer s.mutex.RUnlock()

	playerList := make([]uuid.UUID, 0, len(s.playersByUUID))
	for uuid := range s.playersByUUID {
		playerList = append(playerList, uuid)
	}

	return playerList
}

// runSSHInterface runs the SSH interface in a goroutine
func (s *Server) runSSHInterface(errorChan chan error) {
	RunWithPanicRecoveryCallback("server.runSSHInterface", func() {
		s.sshInterface.Run(errorChan)
		Logger.Info("SSH Interface finished")
	}, func(err error) {
		errorChan <- fmt.Errorf("panic in SSH interface: %v", err)
	})
}
