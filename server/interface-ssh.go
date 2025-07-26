/*
Eidolon Engine

Copyright 2024-2025 Jason Robinson

*/

package main

import (
	"context"
	"errors"
	"fmt"
	"net"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/gofrs/uuid/v5"
	"golang.org/x/crypto/ssh"
	"golang.org/x/time/rate"
)

type Interface_SSH struct {
	config         *Configuration
	server         *Server
	ctx            context.Context
	cancel         context.CancelFunc
	mutex          sync.RWMutex
	start          time.Time
	port           uint16
	privateKeyPath string
	listener       net.Listener
	sshConfig      *ssh.ServerConfig
	authAttempts   map[string]*AuthAttempt // IP-based rate limiting
	userAttempts   map[string]*AuthAttempt // Username-based rate limiting
	globalLimiter  *rate.Limiter           // Global rate limiter across all connections
	authMutex      sync.RWMutex
}

func NewSSHInterface(server *Server) (*Interface_SSH, error) {
	if !server.config.SSH.Enabled {
		return nil, fmt.Errorf("ssh interface is disabled")
	}

	privateBytes, err := os.ReadFile(server.config.SSH.PrivateKeyPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read private key: %w", err)
	}

	private, err := ssh.ParsePrivateKey(privateBytes)
	if err != nil {
		return nil, fmt.Errorf("failed to parse private key: %w", err)
	}

	art := "Eidolon Engine\nCopyright 2024-2025 Jason Robinson\n"

	ctx, cancel := context.WithCancel(server.ctx)

	config := server.config

	// Create the SSH interface structure
	sshInterface := &Interface_SSH{
		config:         config,
		server:         server,
		ctx:            ctx,
		cancel:         cancel,
		port:           config.SSH.Port,
		privateKeyPath: config.SSH.PrivateKeyPath,
		start:          time.Now(),
		authAttempts:   make(map[string]*AuthAttempt),
		userAttempts:   make(map[string]*AuthAttempt),
		globalLimiter:  rate.NewLimiter(globalAuthLimitRate, globalAuthLimitBurst),
	}

	// Set up the SSH server config
	sshConfig := &ssh.ServerConfig{
		PasswordCallback: func(conn ssh.ConnMetadata, password []byte) (*ssh.Permissions, error) {
			return PasswordCallBack(conn, password, sshInterface)
		},
		NoClientAuth: false,
		BannerCallback: func(conn ssh.ConnMetadata) string {
			return art
		},
		AuthLogCallback: func(conn ssh.ConnMetadata, method string, err error) {
			if err != nil {
				Logger.Info("SSH auth attempt", "method", method, "success", false, "client", conn.RemoteAddr())
			} else {
				Logger.Info("SSH auth attempt", "method", method, "success", true, "client", conn.RemoteAddr())
			}
		},
	}

	sshConfig.AddHostKey(private)
	sshInterface.sshConfig = sshConfig

	// Try to create the listener
	address := fmt.Sprintf(":%d", server.config.SSH.Port)
	listener, err := net.Listen("tcp", address)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("failed to listen on port %d: %w", server.config.SSH.Port, err)
	}

	sshInterface.listener = listener

	// Start cleanup routine for expired auth attempts
	go sshInterface.cleanupAuthAttempts()

	return sshInterface, nil
}

func (ssh_interface *Interface_SSH) handleConnection(conn net.Conn, ctx context.Context) {
	defer func() {
		if err := conn.Close(); err != nil {
			Logger.Error("SSH: Failed to close connection", "error", err)
		}
	}()

	// Set authentication timeout
	if err := conn.SetDeadline(time.Now().Add(authTimeout)); err != nil {
		Logger.Error("Failed to set handshake deadline", "error", err)
		return
	}

	sshConn, chans, reqs, err := ssh.NewServerConn(conn, ssh_interface.sshConfig)
	if err != nil {
		Logger.Error("SSH handshake failed", "remote_addr", conn.RemoteAddr(), "error", err)
		return
	}
	defer func() {
		if err := sshConn.Close(); err != nil {
			Logger.Error("SSH: Failed to close SSH connection", "error", err)
		}
	}()

	// Deadline removal allows unlimited session duration
	if err := conn.SetDeadline(time.Time{}); err != nil {
		Logger.Error("Failed to clear deadline", "error", err)
		return
	}

	// Handle SSH requests with context cancellation
	go ssh_interface.handleSSHRequests(ctx, reqs)

	// Extract UUID from permissions
	userUUIDStr := ""
	if sshConn.Permissions != nil && sshConn.Permissions.Extensions != nil {
		userUUIDStr = sshConn.Permissions.Extensions["uuid"]
	}

	if userUUIDStr == "" {
		Logger.Error("No UUID found for authenticated user", "email", sshConn.User())
		return
	}

	// Parse the UUID string
	userUUID, err := uuid.FromString(userUUIDStr)
	if err != nil {
		Logger.Error("Failed to parse UUID", "uuid_string", userUUIDStr, "error", err)
		return
	}

	for newChannel := range chans {
		if newChannel.ChannelType() != "session" {
			if err := newChannel.Reject(ssh.UnknownChannelType, "unknown channel type"); err != nil {
				Logger.Error("SSH: Failed to reject channel", "error", err)
			}
			continue
		}

		channel, requests, err := newChannel.Accept()
		if err != nil {
			Logger.Error("Could not accept channel", "error", err)
			continue
		}

		player, err := NewPlayerSSH(ssh_interface.server, sshConn.User(), channel, ctx, userUUID)
		if err != nil {
			Logger.Error("Failed to create player", "error", err)
			if err := channel.Close(); err != nil {
				Logger.Error("SSH: Failed to close channel", "error", err)
			}
			continue
		}

		// Player execution tied to connection lifecycle
		go ssh_interface.runPlayer(player, requests)
	}
}

func (ssh_interface *Interface_SSH) Run(errorChan chan error) {
	Logger.Info("Starting SSH interface", "port", ssh_interface.port)

	// Make sure listener is not nil
	if ssh_interface.listener == nil {
		Logger.Error("SSH listener is nil, cannot run interface")
		SendErrorNonBlocking(errorChan, fmt.Errorf("SSH listener is nil"), "SSHInterface")
		return
	}

	defer func() {
		if err := ssh_interface.listener.Close(); err != nil {
			Logger.Error("SSH: Failed to close listener", "error", err)
		}
	}()

	// Create a done channel to signal the loop to exit
	done := make(chan struct{})

	// Set up a goroutine to listen for context cancellation
	go ssh_interface.listenForCancellation(done)

	for {
		select {
		case <-done:
			return
		default:
			// Set a short timeout for Accept to ensure we can exit cleanly
			if err := ssh_interface.listener.(*net.TCPListener).SetDeadline(time.Now().Add(1 * time.Second)); err != nil {
				Logger.Error("SSH: Failed to set deadline on listener", "error", err)
			}

			conn, err := ssh_interface.listener.Accept()
			if err != nil {
				if errors.Is(err, net.ErrClosed) {
					Logger.Warn("Listener closed", "error", err)
					return
				}

				// Check for timeout error which we use to poll for context cancellation
				if netErr, ok := err.(net.Error); ok && netErr.Timeout() {
					// Check if context is done to exit
					select {
					case <-done:
						return
					default:
						// Just a timeout, continue
						continue
					}
				}

				Logger.Error("Connection accept failed", "error", err)
				continue
			}

			Logger.Info("New connection", "remote_addr", conn.RemoteAddr())

			// Create a child context for this connection
			connCtx, connCancel := context.WithCancel(ssh_interface.ctx)

			// Context-aware handling enables clean shutdown
			go ssh_interface.handleConnectionWithContext(conn, connCtx, connCancel)
		}
	}
}

func (ssh_interface *Interface_SSH) Stop() error {
	Logger.Info("Stopping SSH interface")

	// Cancel the context first
	ssh_interface.cancel()

	// Use a mutex to ensure we only close the listener once
	ssh_interface.mutex.Lock()
	defer ssh_interface.mutex.Unlock()

	// Check if listener is already closed
	if ssh_interface.listener != nil {
		// Try to close the listener but don't report error if it's already closed
		err := ssh_interface.listener.Close()
		if err != nil && !strings.Contains(err.Error(), "use of closed network connection") {
			return err
		}
		ssh_interface.listener = nil
	}

	return nil
}

// parseDims parses terminal dimensions from the SSH payload.
func ParseDims(b []byte) (width, height int) {
	if len(b) < 8 {
		return 0, 0
	}

	width = int(b[0])<<24 | int(b[1])<<16 | int(b[2])<<8 | int(b[3])
	height = int(b[4])<<24 | int(b[5])<<16 | int(b[6])<<8 | int(b[7])
	return width, height
}

// handleSSHRequests processes SSH requests for a connection
func (ssh_interface *Interface_SSH) handleSSHRequests(ctx context.Context, reqs <-chan *ssh.Request) {
	RunWithPanicRecovery("ssh.handleSSHRequests", func() {
		for {
			select {
			case <-ctx.Done():
				return
			case req, ok := <-reqs:
				if !ok {
					return
				}
				if req.WantReply {
					if err := req.Reply(false, nil); err != nil {
						Logger.Error("SSH: Failed to reply to request", "error", err)
					}
				}
			}
		}
	})
}

// runPlayer runs a player's SSH session
func (ssh_interface *Interface_SSH) runPlayer(player *Player, requests <-chan *ssh.Request) {
	RunWithPanicRecoveryCallback("ssh.runPlayer", func() {
		player.RunSSH(requests)
	}, func(err error) {
		// Ensure player is cleaned up
		player.Stop()
	}, "playerID", player.id)
}

// listenForCancellation listens for context cancellation and closes the listener
func (ssh_interface *Interface_SSH) listenForCancellation(done chan struct{}) {
	RunWithPanicRecovery("ssh.listenForCancellation", func() {
		select {
		case <-ssh_interface.server.ctx.Done():
			if err := ssh_interface.listener.Close(); err != nil {
				Logger.Error("SSH: Failed to close listener during cancellation", "error", err)
			}
			close(done)
		case <-ssh_interface.ctx.Done():
			if err := ssh_interface.listener.Close(); err != nil {
				Logger.Error("SSH: Failed to close listener during cancellation", "error", err)
			}
			close(done)
		}
	})
}

// handleConnectionWithContext handles an SSH connection with proper context management
func (ssh_interface *Interface_SSH) handleConnectionWithContext(conn net.Conn, ctx context.Context, cancel context.CancelFunc) {
	defer cancel()
	RunWithPanicRecovery("ssh.handleConnectionWithContext", func() {
		ssh_interface.handleConnection(conn, ctx)
	}, "remoteAddr", conn.RemoteAddr().String())
}

// getClientIP extracts the client IP from SSH connection metadata
func getClientIP(conn ssh.ConnMetadata) string {
	addr := conn.RemoteAddr().String()
	idx := strings.LastIndex(addr, ":")
	if idx != -1 {
		return addr[:idx]
	}
	return addr
}
