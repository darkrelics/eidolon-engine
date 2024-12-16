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
	Config        *Configuration
	GlobalContext context.Context
	Context       context.Context
	Cancel        context.CancelFunc
	Mutex         sync.RWMutex
	Database      *KeyPair
	StartTime     time.Time
	playerCount   atomic.Uint64
	Players       map[uint64]*Player
	shutdownOnce  sync.Once
	cognito       *cognitoidentityprovider.CognitoIdentityProvider
}

func NewServer(globalCtx context.Context, config *Configuration) (*Server, error) {
	ctx, cancel := context.WithCancel(globalCtx)

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

	server := &Server{
		Config:        config,
		GlobalContext: globalCtx,
		Context:       ctx,
		Cancel:        cancel,
		StartTime:     time.Now(),
		Database:      database,
		Players:       make(map[uint64]*Player),
		cognito:       cognitoidentityprovider.New(sess),
	}

	return server, nil
}

func (s *Server) Run() error {
	Logger.Info("Starting server...")

	sshInterface, err := NewSSHInterface(s.GlobalContext, s)
	if err != nil {
		return fmt.Errorf("ssh interface init error: %w", err)
	}

	go sshInterface.RunServer(s)

	for {
		select {
		case <-s.GlobalContext.Done():
			return s.shutdown("global shutdown")
		case <-s.Context.Done():
			return s.shutdown("server shutdown")
		}
	}
}

func (s *Server) Stop(ctx context.Context) error {

	var stopErr error

	s.shutdownOnce.Do(func() {
		s.Cancel()
		stopErr = s.shutdown("manual stop")
	})

	return stopErr
}

func (s *Server) shutdown(reason string) error {
	Logger.Info("server shutdown", "reason", reason)
	s.Mutex.Lock()
	defer s.Mutex.Unlock()

	for _, player := range s.Players {
		player.Cleanup()
	}

	return nil
}

func (s *Server) GetPlayerCount() uint64 {
	return s.playerCount.Load()
}

func (s *Server) incrementPlayerCount() uint64 {
	return s.playerCount.Add(1)
}

func (s *Server) decrementPlayerCount() uint64 {
	return s.playerCount.Add(^uint64(0))
}

func (s *Server) AddPlayer(player *Player) error {
	if player == nil {
		return fmt.Errorf("player cannot be nil")
	}

	s.Mutex.Lock()
	defer s.Mutex.Unlock()

	playerID := s.incrementPlayerCount()
	s.Players[playerID] = player

	Logger.Info("Player added", "id", playerID, "name", player.PlayerID)
	return nil
}
