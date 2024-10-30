package main

import (
	"context"
	"errors"
	"fmt"
	"net"
	"os"

	"github.com/robinje/multi-user-dungeon/core"
	"golang.org/x/crypto/ssh"
)

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

func acceptConnections(server *core.Server) {
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
		go handleConnection(server, conn)
	}
}

func handleConnection(server *core.Server, conn net.Conn) {
	defer server.WaitGroup.Done()

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
	handleChannels(server, sshConn, chans)
}

func handlePlayerSession(server *core.Server, player *core.Player) {
	// Ensure connection cleanup even on panic
	defer func() {
		if r := recover(); r != nil {
			core.Logger.Error("Panic in player session",
				"playerName", player.PlayerID,
				"panic", r)
		}
		if player != nil && player.Connection != nil {
			player.Connection.Close()
		}
	}()

	core.Logger.Info("Starting player session",
		"playerName", player.PlayerID,
		"playerIndex", player.Index)

	// Send welcome message and MOTDs
	core.Logger.Debug("Displaying welcome messages",
		"playerName", player.PlayerID)
	core.DisplayUnseenMOTDs(server, player)

	// Character Selection Dialog
	core.Logger.Debug("Starting character selection",
		"playerName", player.PlayerID)
	character, err := core.SelectCharacter(player, server)
	if err != nil {
		core.Logger.Error("Character selection failed",
			"playerName", player.PlayerID,
			"error", err)
		return
	}

	if character == nil {
		core.Logger.Error("No character selected",
			"playerName", player.PlayerID)
		return
	}

	core.Logger.Info("Character selected for player",
		"playerName", player.PlayerID,
		"characterName", character.Name,
		"characterID", character.ID)

	// Set the selected character in the player struct
	player.Character = character

	// Create a done channel to signal when the input loop is complete
	done := make(chan struct{})

	// Start the input loop in a goroutine
	go func() {
		defer close(done)
		core.Logger.Debug("Starting input loop",
			"playerName", player.PlayerID,
			"characterName", character.Name)
		core.InputLoop(character)
	}()

	// Wait for either context cancellation or input loop completion
	select {
	case <-player.CTX.Done():
		core.Logger.Info("Player session context cancelled",
			"playerName", player.PlayerID,
			"characterName", character.Name)
	case <-done:
		core.Logger.Info("Player input loop completed normally",
			"playerName", player.PlayerID,
			"characterName", character.Name)
	}

	// Save character data
	if character != nil {
		core.Logger.Debug("Saving character data",
			"playerName", player.PlayerID,
			"characterName", character.Name)
		err = server.Database.WriteCharacter(character)
		if err != nil {
			core.Logger.Error("Failed to save character data",
				"playerName", player.PlayerID,
				"characterName", character.Name,
				"error", err)
		}
	}

	// Save player data
	if player != nil {
		core.Logger.Debug("Saving player data",
			"playerName", player.PlayerID)
		err = server.Database.WritePlayer(player)
		if err != nil {
			core.Logger.Error("Failed to save player data",
				"playerName", player.PlayerID,
				"error", err)
		}

		core.Logger.Debug("Initiating player cleanup",
			"playerName", player.PlayerID)
		player.Cleanup()
	}

	core.Logger.Info("Player session ended",
		"playerName", player.PlayerID)
}

func handleChannels(server *core.Server, sshConn *ssh.ServerConn, channels <-chan ssh.NewChannel) {
	playerName := sshConn.User()
	core.Logger.Info("New connection", "address", sshConn.RemoteAddr().String(), "user", playerName)

	for newChannel := range channels {
		channel, requests, err := newChannel.Accept()
		if err != nil {
			core.Logger.Error("Could not accept channel", "error", err)
			continue
		}

		// Check for existing player
		server.Mutex.Lock()
		for _, player := range server.Players {
			if player != nil && player.PlayerID == playerName {
				if player.Cancel != nil {
					player.Cancel()
				}
			}
		}
		server.Mutex.Unlock()

		// Simple player initialization
		ctx, cancel := context.WithCancel(context.Background())
		player := &core.Player{
			PlayerID:   playerName,
			Index:      server.PlayerIndex.GetID(),
			ToPlayer:   make(chan string, 100),
			FromPlayer: make(chan string, 10),
			Connection: channel,
			Server:     server,
			CTX:        ctx,
			Cancel:     cancel,
		}

		server.Mutex.Lock()
		server.Players[player.Index] = player
		server.Mutex.Unlock()

		go HandleSSHRequests(player, requests)
		go core.PlayerInput(player)
		go core.PlayerOutput(player)
		go handlePlayerSession(server, player)

		core.Logger.Info("Player session started", "playerName", playerName)
	}
}

// StartSSHServer starts the SSH server on the configured port and listens for incoming connections.
func StartSSHServer(server *core.Server, stop chan os.Signal) error {
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
	go acceptConnections(server)

	return nil
}

// HandleSSHRequests handles SSH requests from the client.
func HandleSSHRequests(player *core.Player, requests <-chan *ssh.Request) {
	core.Logger.Debug("Handling SSH requests for player", "player_name", player.PlayerID)

	for req := range requests {
		switch req.Type {
		case "shell":
			// Accept the shell request
			req.Reply(true, nil)
		case "pty-req":
			// Parse terminal dimensions
			termLen := req.Payload[3]
			w, h := core.ParseDims(req.Payload[termLen+4:])
			player.ConsoleWidth, player.ConsoleHeight = w, h
			req.Reply(true, nil)
		case "window-change":
			// Update terminal dimensions
			w, h := core.ParseDims(req.Payload)
			player.ConsoleWidth, player.ConsoleHeight = w, h
		default:
			// Reject unsupported requests
			req.Reply(false, nil)
		}
	}
}
