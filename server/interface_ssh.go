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

type Interface_SSH struct {
	Config         *Configuration
	Server         *Server
	GlobalContext  context.Context
	ServerContext  context.Context
	Context        context.Context
	Cancel         context.CancelFunc
	Mutex          sync.RWMutex
	StartTime      time.Time
	Port           uint16
	PrivateKeyPath string
	Listener       net.Listener
	Connections    uint64
	Database       *KeyPair
	SSHConfig      *ssh.ServerConfig
}

func NewSSHInterface(globalCtx context.Context, server *Server) (*Interface_SSH, error) {
	if !server.Config.SSH.Enabled {
		return nil, fmt.Errorf("ssh interface is disabled in configuration")
	}

	ctx, cancel := context.WithCancel(server.Context)

	sshInterface := &Interface_SSH{
		Config:         server.Config,
		Server:         server,
		GlobalContext:  globalCtx,
		ServerContext:  server.Context,
		Context:        ctx,
		Cancel:         cancel,
		Port:           server.Config.SSH.Port,
		PrivateKeyPath: server.Config.SSH.PrivateKeyPath,
		Mutex:          sync.RWMutex{},
		StartTime:      time.Now(),
		Database:       server.Database,
	}

	if err := configureSSH(ctx, sshInterface); err != nil {
		cancel()
		return nil, fmt.Errorf("ssh configuration failed: %w", err)
	}

	if err := initializeServer(ctx, sshInterface); err != nil {
		cancel()
		return nil, fmt.Errorf("server initialization failed: %w", err)
	}

	// Monitor server context for shutdown
	go func() {
		<-server.Context.Done()
		sshInterface.Cancel()
	}()

	return sshInterface, nil
}

func (ssh_interface *Interface_SSH) RunServer(server *Server) {
	for {
		select {
		case <-ssh_interface.GlobalContext.Done():
			Logger.Info("SSH interface stopping - global shutdown")
			return
		case <-ssh_interface.ServerContext.Done():
			Logger.Info("SSH interface stopping - server shutdown")
			return
		case <-ssh_interface.Context.Done():
			Logger.Info("SSH interface stopping - interface shutdown")
			return
		default:
			conn, err := ssh_interface.Listener.Accept()
			if err != nil {
				if errors.Is(err, net.ErrClosed) {
					return
				}
				Logger.Error("Connection accept failed", "error", err)
				continue
			}
			go handleConnection(ssh_interface.Context, ssh_interface, server, conn)
		}
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
	authOutput, err := ssh_interface.Server.SignInUser(username, password)
	if err != nil {
		Logger.Error("Authentication failed", "username", username, "error", err)
		return false
	}

	if authOutput.AuthenticationResult == nil {
		Logger.Error("No authentication result", "username", username)
		return false
	}

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
func handleConnection(ctx context.Context, ssh_interface *Interface_SSH, server *Server, conn net.Conn) {
	remoteAddr := conn.RemoteAddr().String()
	Logger.Info("New SSH connection", "remoteAddr", remoteAddr)

	// Set initial handshake deadline
	if err := conn.SetDeadline(time.Now().Add(30 * time.Second)); err != nil {
		Logger.Error("Failed to set handshake deadline", "error", err, "remoteAddr", remoteAddr)
		conn.Close()
		return
	}

	// Perform SSH handshake
	sshConn, chans, reqs, err := ssh.NewServerConn(conn, ssh_interface.SSHConfig)
	if err != nil {
		Logger.Error("SSH handshake failed", "error", err, "remoteAddr", remoteAddr)
		conn.Close()
		return
	}

	// Clear deadline after handshake
	if err := conn.SetDeadline(time.Time{}); err != nil {
		Logger.Error("Failed to clear deadline", "error", err, "remoteAddr", remoteAddr)
		sshConn.Close()
		return
	}

	// Create session context
	sessionCtx, sessionCancel := context.WithCancel(ctx)
	defer sessionCancel()

	// Start request handler
	go discardRequests(sessionCtx, reqs)

	// Start channel handler
	go func() {
		handleChannels(sessionCtx, ssh_interface, server, sshConn, chans)
		sessionCancel()
	}()

	// Wait for session end
	<-sessionCtx.Done()
	sshConn.Close()
	Logger.Info("SSH connection closed", "user", sshConn.User(), "remoteAddr", remoteAddr)
}

func discardRequests(ctx context.Context, reqs <-chan *ssh.Request) {
	for {
		select {
		case <-ctx.Done():
			return
		case req, ok := <-reqs:
			if !ok {
				return
			}
			Logger.Debug("Discarding SSH request", "type", req.Type, "wantReply", req.WantReply)
			if req.WantReply {
				req.Reply(false, nil)
			}
		}
	}
}

// handleChannels processes SSH channels for a connection
func handleChannels(ctx context.Context, ssh_interface *Interface_SSH, server *Server, sshConn *ssh.ServerConn, channels <-chan ssh.NewChannel) {
	playerName := sshConn.User()

	for {
		select {
		case <-ctx.Done():
			Logger.Info("Connection closing", "player", playerName)
			return

		case newChannel, ok := <-channels:
			if !ok {
				Logger.Info("Channel closed", "player", playerName)
				return
			}

			channel, requests, err := newChannel.Accept()
			if err != nil {
				Logger.Error("Channel accept failed", "error", err)
				continue
			}

			playerCtx, playerCancel := context.WithCancel(ctx)
			player := &Player{
				Server:        server,
				PlayerID:      playerName,
				ToPlayer:      make(chan string, 10),
				FromPlayer:    make(chan string, 10),
				Echo:          true,
				Connection:    channel,
				ConsoleWidth:  80,
				ConsoleHeight: 24,
				LoginTime:     time.Now(),
				Mutex:         sync.RWMutex{},
				Context:       playerCtx,
				Cancel:        playerCancel,
			}

			go handleSSHRequests(playerCtx, player, requests)
			if err := ssh_interface.Server.AddPlayer(player); err != nil {
				Logger.Error("Failed to add player", "error", err)
				playerCancel()
				continue
			}
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
