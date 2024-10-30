package main

import (
	"errors"
	"fmt"
	"net"
	"os"

	"github.com/robinje/multi-user-dungeon/core"
	"golang.org/x/crypto/ssh"
)

// SSHServer starts the SSH server on the configured port and listens for incoming connections.
func SSHServer(server *core.Server, game *core.Game, stop chan os.Signal) error {

	if err := configureSSH(server); err != nil {
		stop <- os.Interrupt
		return fmt.Errorf("failed to configure SSH server: %v", err)
	}

	// Start listening on the configured port
	address := fmt.Sprintf(":%d", server.Port)
	listener, err := net.Listen("tcp", address)
	if err != nil {
		return fmt.Errorf("failed to listen on port %d: %v", server.Port, err)
	}

	server.Listener = listener
	core.Logger.Info("SSH server listening", "port", server.Port)

	// Start accepting connections in a separate goroutine
	go acceptConnections(server, game)

	return nil
}

// configureSSH configures the SSH server with the provided private key and authentication settings.
func configureSSH(server *core.Server) error {
	core.Logger.Info("Configuring SSH server", "port", server.Port)

	// Read the private key from disk
	privateKeyPath := server.Config.Server.PrivateKeyPath
	if privateKeyPath == "" {
		privateKeyPath = "./server.key" // Default path if not specified
	}
	privateBytes, err := os.ReadFile(privateKeyPath)
	if err != nil {
		return fmt.Errorf("failed to read private key from %s: %v", privateKeyPath, err)
	}

	// Parse the private key
	private, err := ssh.ParsePrivateKey(privateBytes)
	if err != nil {
		return fmt.Errorf("failed to parse private key: %v", err)
	}

	// Configure SSH server settings
	server.SSHConfig = &ssh.ServerConfig{
		PasswordCallback: func(conn ssh.ConnMetadata, password []byte) (*ssh.Permissions, error) {
			// Authenticate the player
			authenticated := Authenticate(conn.User(), string(password), server.Config)
			if authenticated {
				core.Logger.Info("Player authenticated", "player_name", conn.User())
				return nil, nil
			}
			core.Logger.Warn("Player failed authentication", "player_name", conn.User())
			return nil, fmt.Errorf("password rejected for %q", conn.User())
		},
	}

	// Add the host key to the SSH configuration
	server.SSHConfig.AddHostKey(private)
	return nil
}

// Authenticate checks the provided username and password against the authentication system.
// Returns true if authentication is successful, false otherwise.
func Authenticate(username, password string, config core.Configuration) bool {
	core.Logger.Info("Authenticating user", "username", username)

	// I really want the USER UUID passed up.
	response, err := core.SignInUser(username, password, config)
	core.Logger.Debug("Authentication response", "response", response)

	if err != nil {
		core.Logger.Error("Authentication attempt failed for user", "username", username, "error", err)
		return false
	}
	return true
}

func acceptConnections(server *core.Server, game *core.Game) {
	for {
		conn, err := server.Listener.Accept()
		if err != nil {
			if errors.Is(err, net.ErrClosed) {
				core.Logger.Info("SSH server listener closed, stopping accept loop")
				return
			}
			core.Logger.Error("Error accepting connection", "error", err)
			continue
		}

		server.WaitGroup.Add(1)
		go handleConnection(server, game, conn)
	}
}

func handleConnection(server *core.Server, game *core.Game, conn net.Conn) {

	// Perform SSH handshake
	sshConn, chans, reqs, err := ssh.NewServerConn(conn, server.SSHConfig)
	if err != nil {
		core.Logger.Error("Failed to perform SSH handshake", "error", err)
		return
	}
	defer sshConn.Close()

	// Discard global requests
	go ssh.DiscardRequests(reqs)

	// Handle channels
	handleChannels(server, game, sshConn, chans)
}
