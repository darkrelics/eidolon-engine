package main

import (
	"context"
	"errors"
	"fmt"
	"net"
	"os"
	"strings"
	"time"

	"github.com/robinje/multi-user-dungeon/core"
	"golang.org/x/crypto/ssh"
)

// sshServer starts the SSH server on the configured port and listens for incoming connections.
func sshServer(ctx context.Context, server *core.Server, game *core.Game) error {
	if server == nil {
		return fmt.Errorf("server instance is nil")
	}
	if game == nil {
		return fmt.Errorf("game instance is nil")
	}

	if err := initializeServer(ctx, server); err != nil {
		core.Logger.Error("Server initialization failed", "error", err)
		return fmt.Errorf("server initialization failed: %w", err)
	}

	// Start accepting connections
	errChan := make(chan error, 1)
	go func() {
		if err := acceptConnections(ctx, server, game); err != nil {
			core.Logger.Error("Connection acceptance failed", "error", err)
			errChan <- err
		}
	}()

	// Monitor for context cancellation or connection errors
	select {
	case <-ctx.Done():
		core.Logger.Info("SSH server stopping due to context cancellation")
		return fmt.Errorf("ssh server stopped: %w", ctx.Err())
	case err := <-errChan:
		if err != nil {
			return fmt.Errorf("ssh server failed: %w", err)
		}
		return nil
	}
}

func initializeServer(ctx context.Context, server *core.Server) error {
	if server == nil {
		return fmt.Errorf("server instance is nil")
	}

	if err := configureSSH(ctx, server); err != nil {
		return fmt.Errorf("SSH configuration failed: %w", err)
	}

	if server.Port == 0 {
		return fmt.Errorf("server port is not configured")
	}

	address := fmt.Sprintf(":%d", server.Port)
	listener, err := net.Listen("tcp", address)
	if err != nil {
		return fmt.Errorf("failed to listen on port %d: %w", server.Port, err)
	}

	// Check if context was cancelled during initialization
	select {
	case <-ctx.Done():
		listener.Close()
		return fmt.Errorf("server initialization cancelled: %w", ctx.Err())
	default:
		server.Listener = listener
		core.Logger.Info("SSH server listening", "port", server.Port)
		return nil
	}
}

// configureSSH configures the SSH server with the provided private key and authentication settings.
func configureSSH(ctx context.Context, server *core.Server) error {
	if server == nil {
		return fmt.Errorf("server instance is nil")
	}

	if server.PrivateKeyPath == "" {
		return fmt.Errorf("private key path is not configured")
	}

	core.Logger.Info("Configuring SSH server", "port", server.Port)

	// Read the private key from disk
	privateKeyPath := server.PrivateKeyPath
	privateBytes, err := os.ReadFile(privateKeyPath)
	if err != nil {
		return fmt.Errorf("failed to read private key from %s: %w", privateKeyPath, err)
	}

	select {
	case <-ctx.Done():
		return fmt.Errorf("ssh configuration cancelled: %w", ctx.Err())
	default:
		// Parse the private key
		private, err := ssh.ParsePrivateKey(privateBytes)
		if err != nil {
			return fmt.Errorf("failed to parse private key: %w", err)
		}

		// Configure SSH server settings
		server.SSHConfig = &ssh.ServerConfig{
			PasswordCallback: func(conn ssh.ConnMetadata, password []byte) (*ssh.Permissions, error) {
				select {
				case <-ctx.Done():
					return nil, fmt.Errorf("authentication cancelled: %w", ctx.Err())
				default:
					// Authenticate the player
					authenticated := Authenticate(conn.User(), string(password), server)
					if authenticated {
						core.Logger.Info("Player authenticated", "player_name", conn.User())
						return nil, nil
					}
					core.Logger.Warn("Player failed authentication", "player_name", conn.User())
					return nil, fmt.Errorf("password rejected for %q", conn.User())
				}
			},
		}

		// Add the host key to the SSH configuration
		server.SSHConfig.AddHostKey(private)
		return nil
	}
}

// Authenticate checks the provided username and password against the authentication system.
// Returns true if authentication is successful, false otherwise.
func Authenticate(username, password string, server *core.Server) bool {
	core.Logger.Info("Authenticating user", "username", username)

	response, err := core.SignInUser(username, password, server)
	if err != nil {
		core.Logger.Error("Authentication failed", "username", username, "error", err, "response", response)
		return false
	}

	core.Logger.Debug("Authentication successful", "username", username, "response", response)
	return true
}

// acceptConnections handles incoming connections to the SSH server
func acceptConnections(ctx context.Context, server *core.Server, game *core.Game) error {
	for {
		select {
		case <-ctx.Done():
			core.Logger.Info("Context cancelled, stopping accept loop")
			server.Listener.Close()
			return ctx.Err()

		default:
			conn, err := server.Listener.Accept()
			if err != nil {
				if errors.Is(err, net.ErrClosed) {
					core.Logger.Info("SSH server listener closed, stopping accept loop")
					return nil
				}

				// Handle connection errors
				switch e := err.(type) {
				case *net.OpError:
					// If it's a timeout or temporary error condition, retry
					if e.Timeout() || strings.Contains(e.Error(), "connection reset by peer") {
						core.Logger.Warn("Temporary network error", "error", err)
						time.Sleep(100 * time.Millisecond)
						continue
					}
					return fmt.Errorf("network operation error: %w", err)
				}

				return fmt.Errorf("error accepting connection: %w", err)
			}

			server.WaitGroup.Add(1)
			go func() {
				defer server.WaitGroup.Done()
				handleConnection(ctx, server, game, conn)
			}()
		}
	}
}

// handleConnection processes an individual SSH connection
func handleConnection(ctx context.Context, server *core.Server, game *core.Game, conn net.Conn) {
	defer server.WaitGroup.Done()
	defer conn.Close()

	// Create connection-specific context that can be cancelled independently
	connCtx, cancel := context.WithCancel(ctx)
	defer cancel()

	remoteAddr := conn.RemoteAddr().String()

	// Set initial handshake timeout
	if err := conn.SetDeadline(time.Now().Add(30 * time.Second)); err != nil {
		core.Logger.Error("Failed to set handshake deadline",
			"error", err,
			"remoteAddr", remoteAddr)
		return
	}

	// Perform SSH handshake
	sshConn, chans, reqs, err := ssh.NewServerConn(conn, server.SSHConfig)
	if err != nil {
		core.Logger.Error("Failed to perform SSH handshake",
			"error", err,
			"remoteAddr", remoteAddr)
		return
	}
	defer sshConn.Close()

	// Reset deadline after successful handshake
	if err := conn.SetDeadline(time.Time{}); err != nil {
		core.Logger.Error("Failed to reset connection deadline",
			"error", err,
			"remoteAddr", remoteAddr,
			"user", sshConn.User())
		return
	}

	core.Logger.Info("New SSH connection established",
		"user", sshConn.User(),
		"remoteAddr", remoteAddr,
		"clientVersion", string(sshConn.ClientVersion()))

	// Handle global requests in a separate goroutine
	go discardRequests(reqs)

	// Handle channels with connection-specific context
	handleChannels(connCtx, server, game, sshConn, chans)
}

func discardRequests(reqs <-chan *ssh.Request) {
	for req := range reqs {
		core.Logger.Debug("Discarding SSH request", "type", req.Type, "wantReply", req.WantReply)
		if req.WantReply {
			req.Reply(false, nil)
		}
	}
}
