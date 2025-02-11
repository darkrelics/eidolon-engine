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

func NewServer(globalCtx context.Context, config *Configuration) (*Server, error) {

	fmt.Println("New Server...Initializing server...")

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
		game:         nil,
		start:        time.Now(),
		database:     database,
		playerCount:  atomic.Uint64{},
		players:      make(map[uint64]*Player),
		shutdownOnce: sync.Once{},
		cognito:      cognitoidentityprovider.New(serverSession),
		index:        index,
	}

	server.playerCount.Store(0)

	server.activeMotDs = nil

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

	fmt.Println("Run server...")

	fmt.Println("Starting SSH Interface...")

	// Start SSH Interface

	fmt.Println("SSH Interface started successfully")

	// Wait until server is stopped

	select {
	case <-s.ctx.Done():
		return nil
	case err := <-errorChan:
		Logger.Error("System error", "error", err)
		return nil
	}

}
