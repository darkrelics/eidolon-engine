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

	"golang.org/x/crypto/ssh"
)

func NewSSHInterface(GlobalContext *context.Context, ServerContext *context.Context, config *Configuration) (*Interface_SSH, error) {

	// Create a new SSH Interface
	ssh_interface := &Interface_SSH{
		Config:         config,
		GlobalContext:  *GlobalContext,
		ServerContext:  *ServerContext,
		Context:        context.Background(),
		Cancel:         nil,
		Mutex:          sync.RWMutex{},
		StartTime:      time.Now(),
		Port:           config.SSH.Port,
		PrivateKeyPath: config.SSH.PrivateKeyPath,
		Connections:    0,
	}

	return ssh_interface, nil

}

// sshServer starts the SSH server on the configured port and listens for incoming connections.
func sshServer(ctx context.Context, ssh_interface *Interface_SSH, game *Game) error {
	if ssh_interface == nil {
		return fmt.Errorf("server instance is nil")
	}
	if game == nil {
		return fmt.Errorf("game instance is nil")
	}

	if err := initializeServer(ctx, ssh_interface); err != nil {
		Logger.Error("Server initialization failed", "error", err)
		return fmt.Errorf("server initialization failed: %w", err)
	}

	// Start accepting connections
	errChan := make(chan error, 1)
	go func() {
		if err := acceptConnections(ctx, ssh_interface); err != nil {
			Logger.Error("Connection acceptance failed", "error", err)
			errChan <- err
		}
	}()

	// Monitor for context cancellation or connection errors
	select {
	case <-ctx.Done():
		Logger.Info("SSH server stopping due to context cancellation")
		return fmt.Errorf("ssh server stopped: %w", ctx.Err())
	case err := <-errChan:
		if err != nil {
			return fmt.Errorf("ssh server failed: %w", err)
		}
		return nil
	}
}

func initializeServer(ctx context.Context, ssh_interface *Interface_SSH) error {
	if ssh_interface == nil {
		return fmt.Errorf("server instance is nil")
	}

	if err := configureSSH(ctx, ssh_interface); err != nil {
		return fmt.Errorf("SSH configuration failed: %w", err)
	}

	if ssh_interface.Port == 0 {
		return fmt.Errorf("server port is not configured")
	}

	address := fmt.Sprintf(":%d", ssh_interface.Port)
	listener, err := net.Listen("tcp", address)
	if err != nil {
		return fmt.Errorf("failed to listen on port %d: %w", ssh_interface.Port, err)
	}

	// Check if context was cancelled during initialization
	select {
	case <-ctx.Done():
		listener.Close()
		return fmt.Errorf("server initialization cancelled: %w", ctx.Err())
	default:
		ssh_interface.Listener = listener
		Logger.Info("SSH server listening", "port", ssh_interface.Port)
		return nil
	}
}

// configureSSH configures the SSH server with the provided private key and authentication settings.
func configureSSH(ctx context.Context, ssh_interface *Interface_SSH) error {
	if ssh_interface == nil {
		return fmt.Errorf("server instance is nil")
	}

	if ssh_interface.PrivateKeyPath == "" {
		return fmt.Errorf("private key path is not configured")
	}

	Logger.Info("Configuring SSH server", "port", ssh_interface.Port)

	// Read the private key from disk
	privateKeyPath := ssh_interface.PrivateKeyPath
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
		ssh_interface.SSHConfig = &ssh.ServerConfig{
			PasswordCallback: func(conn ssh.ConnMetadata, password []byte) (*ssh.Permissions, error) {
				select {
				case <-ctx.Done():
					return nil, fmt.Errorf("authentication cancelled: %w", ctx.Err())
				default:
					// Authenticate the player
					authenticated := Authenticate(conn.User(), string(password), ssh_interface)
					if authenticated {
						Logger.Info("Player authenticated", "player_name", conn.User())
						return nil, nil
					}
					Logger.Warn("Player failed authentication", "player_name", conn.User())
					return nil, fmt.Errorf("password rejected for %q", conn.User())
				}
			},
		}

		// Add the host key to the SSH configuration
		ssh_interface.SSHConfig.AddHostKey(private)
		return nil
	}
}

// Authenticate checks the provided username and password against the authentication system.
// Returns true if authentication is successful, false otherwise.
func Authenticate(username, password string, ssh_interface *Interface_SSH) bool {
	Logger.Info("Authenticating user", "username", username)

	// response, err := SignInUser(username, password, ssh_interface)
	// if err != nil {
	// 	Logger.Error("Authentication failed", "username", username, "error", err, "response", response)
	// 	return false
	// }

	// Logger.Debug("Authentication successful", "username", username, "response", response)
	return true
}

// acceptConnections handles incoming connections to the SSH server
func acceptConnections(ctx context.Context, ssh_interface *Interface_SSH) error {
	for {
		select {
		case <-ctx.Done():
			Logger.Info("Context cancelled, stopping accept loop")
			ssh_interface.Listener.Close()
			return ctx.Err()

		default:
			_, err := ssh_interface.Listener.Accept()
			if err != nil {
				if errors.Is(err, net.ErrClosed) {
					Logger.Info("SSH server listener closed, stopping accept loop")
					return nil
				}

				// Handle connection errors
				switch e := err.(type) {
				case *net.OpError:
					// If it's a timeout or temporary error condition, retry
					if e.Timeout() || strings.Contains(e.Error(), "connection reset by peer") {
						Logger.Warn("Temporary network error", "error", err)
						time.Sleep(100 * time.Millisecond)
						continue
					}
					return fmt.Errorf("network operation error: %w", err)
				}

				return fmt.Errorf("error accepting connection: %w", err)
			}

		}
	}
}

// handleConnection processes an individual SSH connection
func handleConnection(ctx context.Context, ssh_interface *Interface_SSH, game *Game, conn net.Conn) {
	defer conn.Close()

	// Create connection-specific context that can be cancelled independently
	connCtx, cancel := context.WithCancel(ctx)
	defer cancel()

	remoteAddr := conn.RemoteAddr().String()

	// Set initial handshake timeout
	if err := conn.SetDeadline(time.Now().Add(30 * time.Second)); err != nil {
		Logger.Error("Failed to set handshake deadline",
			"error", err,
			"remoteAddr", remoteAddr)
		return
	}

	// Perform SSH handshake
	sshConn, chans, reqs, err := ssh.NewServerConn(conn, ssh_interface.SSHConfig)
	if err != nil {
		Logger.Error("Failed to perform SSH handshake",
			"error", err,
			"remoteAddr", remoteAddr)
		return
	}
	defer sshConn.Close()

	// Reset deadline after successful handshake
	if err := conn.SetDeadline(time.Time{}); err != nil {
		Logger.Error("Failed to reset connection deadline",
			"error", err,
			"remoteAddr", remoteAddr,
			"user", sshConn.User())
		return
	}

	Logger.Info("New SSH connection established",
		"user", sshConn.User(),
		"remoteAddr", remoteAddr,
		"clientVersion", string(sshConn.ClientVersion()))

	// Handle global requests in a separate goroutine
	go discardRequests(reqs)

	// Handle channels with connection-specific context
	handleChannels(connCtx, ssh_interface, game, sshConn, chans)
}

func discardRequests(reqs <-chan *ssh.Request) {
	for req := range reqs {
		Logger.Debug("Discarding SSH request", "type", req.Type, "wantReply", req.WantReply)
		if req.WantReply {
			req.Reply(false, nil)
		}
	}
}

// handleChannels processes SSH channels for a connection
func handleChannels(ctx context.Context, ssh_interface *Interface_SSH, game *Game, sshConn *ssh.ServerConn, channels <-chan ssh.NewChannel) {
	// Logger.Debug("Active Player Indices:", "playerIndices", server.PlayerIndex)
	playerName := sshConn.User()
	Logger.Info("New connection", "address", sshConn.RemoteAddr().String(), "user", playerName)

	for {
		select {
		case <-ctx.Done():
			Logger.Info("Closing connection due to context cancellation", "player", playerName)
			return

		case newChannel, ok := <-channels:
			if !ok {
				Logger.Info("Channel closed", "player", playerName)
				return
			}

			channel, requests, err := newChannel.Accept()
			if err != nil {
				Logger.Error("Could not accept channel", "error", err)
				continue
			}

			// // Check for existing connection
			// server.Mutex.RLock()
			// for index := range server.Players {
			// 	if server.Players[index].PlayerID == playerName {
			// 		server.Mutex.RUnlock()
			// 		Logger.Warn("Player already connected", "playerName", playerName)
			// 		channel.Write([]byte("You are already connected. Goodbye.\n\r"))
			// 		sshConn.Close()
			// 		return
			// 	}
			// }
			// server.Mutex.RUnlock()

			// Initialize or load player data
			// characterList, seenMotD, err := InitializePlayerData(ssh_interface, playerName)
			if err != nil {
				Logger.Error("Failed to initialize player data", "error", err, "player", playerName)
				continue
			}

			// Create player context as child of connection context
			playerCtx, playerCancel := context.WithCancel(ctx)
			player := &Player{
				// Server:        server,
				// Index:         server.PlayerIndex.GetID(),
				PlayerID: playerName,
				// CharacterList: characterList,
				// SeenMotD:      seenMotD,
				ToPlayer:      make(chan string, 10),
				FromPlayer:    make(chan string, 10),
				Echo:          true,
				Prompt:        "",
				Connection:    channel,
				ConsoleWidth:  80,
				ConsoleHeight: 24,
				LoginTime:     time.Now(),
				Mutex:         sync.RWMutex{},
				Context:       playerCtx,
				Cancel:        playerCancel,
			}

			// server.Mutex.Lock()
			// server.Players[player.Index] = player
			// server.Mutex.Unlock()

			// Start player handlers with context
			go handleSSHRequests(playerCtx, player, requests)
			// go handlePlayerSession(playerCtx, server, game, player)

			Logger.Info("Player session started",
				"playerName", playerName,
				"index", player.Index)
		}
	}
}

// handleSSHRequests handles SSH requests from the client.
func handleSSHRequests(ctx context.Context, player *Player, requests <-chan *ssh.Request) {
	for {
		select {
		case <-ctx.Done():
			Logger.Info("Context cancelled, exiting handleSSHRequests loop",
				"player", player.PlayerID)
			return

		case req, ok := <-requests:
			if !ok {
				Logger.Info("Request channel closed, exiting handleSSHRequests loop",
					"player", player.PlayerID)
				return
			}

			player.Mutex.Lock()
			handleRequest(req, player)
			player.Mutex.Unlock()
		}
	}
}

// handleRequest processes individual SSH requests
func handleRequest(req *ssh.Request, player *Player) {
	switch req.Type {
	case "shell":
		Logger.Debug("Accepting shell request",
			"player", player.PlayerID)
		req.Reply(true, nil)

	case "pty-req":
		termLen := req.Payload[3]
		w, h := ParseDims(req.Payload[termLen+4:])
		player.ConsoleWidth = w
		player.ConsoleHeight = h
		Logger.Debug("Terminal size set",
			"player", player.PlayerID,
			"width", w,
			"height", h)
		req.Reply(true, nil)

	case "window-change":
		w, h := ParseDims(req.Payload)
		player.ConsoleWidth = w
		player.ConsoleHeight = h
		Logger.Debug("Window size changed",
			"player", player.PlayerID,
			"width", w,
			"height", h)

	default:
		Logger.Warn("Unsupported request",
			"type", req.Type,
			"player", player.PlayerID)
		req.Reply(false, nil)
	}
}
