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

func NewServer(globalCtx context.Context, config *Configuration) (*Server, error) {

	fmt.Println("Initializing server...")

	ctx, cancel := context.WithCancel(context.Background())

	database, err := NewKeyPair(config.Aws.Region)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("database init error: %w", err)
	}

	sess, err := session.NewSession(&aws.Config{Region: aws.String(config.Aws.Region)})
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
		game:          nil,
		start:         time.Now(),
		database:      database,
		players:       make(map[uint64]*Player),
		cognito:       cognitoidentityprovider.New(sess),
		index:         index,
	}

	return server, nil
}

func (s *Server) Run() error {
	Logger.Info("Starting server...")

	sshInterface, err := NewSSHInterface(s)
	if err != nil {
		return fmt.Errorf("ssh interface init error: %w", err)
	}

	// Create error channel for SSH interface
	sshErrChan := make(chan error, 1)
	go func() {
		sshErrChan <- sshInterface.Run()
	}()

	// Wait for either a shutdown signal or SSH interface error
	select {
	case <-s.globalContext.Done():
		return s.shutdown("global shutdown")
	case <-s.context.Done():
		return s.shutdown("server shutdown")
	case err := <-sshErrChan:
		if err != nil {
			return fmt.Errorf("ssh interface error: %w", err)
		}
		return nil
	}
}

func (s *Server) Stop() error {

	fmt.Println("Stopping server...")

	var stopErr error

	// Modify system to specifically stop the interfaces.

	// Modify system to specifically replace the players.

	s.shutdownOnce.Do(func() {
		s.cancel()
		stopErr = s.shutdown("manual stop")
	})

	return stopErr
}

func (s *Server) shutdown(reason string) error {
	Logger.Info("server shutdown", "reason", reason)
	s.mutex.Lock()
	defer s.mutex.Unlock()

	for _, player := range s.players {
		player.Stop()
	}

	return nil
}

func (s *Server) AddPlayer(player *Player) (uint64, error) {
	if player == nil {
		return 0, fmt.Errorf("player cannot be nil")
	}

	id := s.index.GetID()

	s.mutex.Lock()
	s.players[id] = player
	s.mutex.Unlock()

	s.playerCount.Add(1)
	Logger.Info("player added", "id", id, "name", player.playerID)

	return id, nil
}

func (s *Server) RemovePlayer(id uint64) *Player {
	s.mutex.Lock()
	player := s.players[id]
	delete(s.players, id)
	s.mutex.Unlock()

	if player != nil {
		s.playerCount.Add(^uint64(0))
		Logger.Info("player removed", "id", id, "name", player.playerID)
	}

	return player
}

func (s *Server) PlayerCount() uint64 {
	return s.playerCount.Load()
}
