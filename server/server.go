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
	sshInterface *Interface_SSH
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

func (s *Server) Run(errorChan chan error) error {
	Logger.Info("Run server...")

	Logger.Info("Starting SSH Interface...")

	// Start SSH Interface
	if s.config.SSH.Enabled {
		var err error
		sshInterface, err := NewSSHInterface(s)
		if err != nil {
			Logger.Error("Failed to start SSH interface", "error", err)
		} else {
			// Store the interface before starting the goroutine
			s.mutex.Lock()
			s.sshInterface = sshInterface
			s.mutex.Unlock()

			go sshInterface.Run(errorChan)
			Logger.Info("SSH Interface started successfully")
		}
	} else {
		Logger.Info("SSH Interface disabled")
	}

	// Wait until server is stopped
	<-s.ctx.Done()

	// Now it's safe to explicitly stop the SSH interface
	if s.sshInterface != nil {
		if err := s.sshInterface.Stop(); err != nil {
			// Only log serious errors, not just "already closed"
			if !strings.Contains(err.Error(), "use of closed network connection") {
				Logger.Error("Error stopping SSH interface", "error", err)
			}
		}
	}

	return nil
}

func (s *Server) Stop() error {
	Logger.Info("Server: Stopping server...")
	defer Logger.Info("Server: Server stopped")

	// Use the shutdownOnce to ensure we only execute this once
	s.shutdownOnce.Do(func() {
		// Cancel the context first - this signals all components to shut down
		s.cancel()

		// No need to explicitly stop the SSH interface here as it will
		// detect the context cancellation

		// Give components time to react to context cancellation
		time.Sleep(100 * time.Millisecond)
	})

	return nil
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
