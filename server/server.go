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

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/cognitoidentityprovider"
)

type Server struct {
	config       *Configuration
	ctx          context.Context
	cancel       context.CancelFunc
	mutex        sync.RWMutex
	game         *Game
	database     *KeyPair
	start        time.Time
	playerCount  atomic.Uint64
	players      map[uint64]*Player
	shutdownOnce sync.Once
	cognito      *cognitoidentityprovider.CognitoIdentityProvider
	index        *Index
	activeMotDs  []*MOTD
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

func NewServer(globalCtx context.Context, config *Configuration) (*Server, error) {

	Logger.Info("New Server...Initializing server...")

	ctx, cancel := context.WithCancel(globalCtx)

	database, err := NewKeyPair(config)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("database init error: %w", err)
	}

	serverSession, err := session.NewSession(&aws.Config{Region: aws.String(config.AWS.Region)})
	if err != nil {
		cancel()
		return nil, fmt.Errorf("AWS session init error: %w", err)
	}

	index := &Index{
		IndexID: 0,
		mu:      sync.RWMutex{},
	}

	server := &Server{
		config:       config,
		ctx:          ctx,
		cancel:       cancel,
		mutex:        sync.RWMutex{},
		start:        time.Now(),
		database:     database,
		playerCount:  atomic.Uint64{},
		players:      make(map[uint64]*Player),
		shutdownOnce: sync.Once{},
		cognito:      cognitoidentityprovider.New(serverSession),
		index:        index,
	}

	server.playerCount.Store(0)

	return server, nil
}

func (s *Server) Stop() error {

	Logger.Info("Server: Stopping server...")
	defer Logger.Info("Server: Server stopped")

	// Log out players

	// Shutdown Interfaces

	s.shutdownOnce.Do(func() {
		s.cancel()
	})

	return nil
}

func (s *Server) Run(errorChan chan error) error {

	Logger.Info("Run server...")

	Logger.Info("Starting SSH Interface...")

	var sshInterface *Interface_SSH

	// Start SSH Interface

	if s.config.SSH.Enabled {
		var err error
		sshInterface, err = NewSSHInterface(s)
		if err != nil {
			Logger.Error("Failed to start SSH interface", "error", err)
			// Add error to the error channel so main can handle it
			errorChan <- fmt.Errorf("SSH interface initialization failed: %w", err)
		} else {
			// Only run if no error and interface is properly initialized
			go sshInterface.Run(errorChan)
		}
	}

	Logger.Info("SSH Interface started successfully")

	// Wait until server is stopped

	select {
	case <-s.ctx.Done():
		if s.config.SSH.Enabled {
			if sshInterface != nil {
				sshInterface.Stop()
			}

		}
		return nil

	}

}

func (s *Server) AddPlayer(player *Player) error {

	if player == nil {
		return fmt.Errorf("player is nil")
	}

	id := s.index.GetID()

	player.mutex.Lock()
	player.index = id
	player.mutex.Unlock()

	s.mutex.Lock()
	s.players[id] = player
	s.mutex.Unlock()

	s.playerCount.Add(1)
	Logger.Info("Player added", "playerID", id)

	return nil
}

func (s *Server) RemovePlayer(playerID uint64) error {

	s.mutex.Lock()
	defer s.mutex.Unlock()

	delete(s.players, playerID)

	s.playerCount.Add(^uint64(0))

	return nil
}

func (s *Server) PlayerCount() uint64 {
	return s.playerCount.Load()
}
