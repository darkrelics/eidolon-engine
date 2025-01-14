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
	config        *Configuration
	globalContext context.Context
	context       context.Context
	cancel        context.CancelFunc
	mutex         sync.RWMutex
	game          *Game
	database      *KeyPair
	start         time.Time
	playerCount   atomic.Uint64
	players       map[uint64]*Player
	shutdownOnce  sync.Once
	cognito       *cognitoidentityprovider.CognitoIdentityProvider
	index         *Index
	activeMotDs   []*MOTD
}

type Index struct {
	IndexID uint64
	mu      sync.RWMutex
}

func NewServer(globalCtx context.Context, config *Configuration) (*Server, error) {

	fmt.Println("Initializing server...")

	ctx, cancel := context.WithCancel(context.Background())

	database, err := NewKeyPair(config)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("database init error: %w", err)
	}

	serverSession, err := session.NewSession(&aws.Config{Region: aws.String(config.aws.region)})
	if err != nil {
		cancel()
		return nil, fmt.Errorf("AWS session init error: %w", err)
	}

	index := &Index{
		IndexID: 0,
		mu:      sync.RWMutex{},
	}

	server := &Server{
		config:        config,
		globalContext: globalCtx,
		context:       ctx,
		cancel:        cancel,
		mutex:         sync.RWMutex{},
		game:          nil,
		start:         time.Now(),
		database:      database,
		playerCount:   atomic.Uint64{},
		players:       make(map[uint64]*Player),
		shutdownOnce:  sync.Once{},
		cognito:       cognitoidentityprovider.New(serverSession),
		index:         index,
	}

	server.playerCount.Store(0)

	server.activeMotDs = nil

	return server, nil
}

func (s *Server) Stop() error {

	fmt.Println("Stopping server...")

	// Log out players

	// Shutdown Interfaces

	s.shutdownOnce.Do(func() {
		s.cancel()
	})

	return nil
}
