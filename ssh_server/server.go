package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"net"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"github.com/google/uuid"
	"github.com/robinje/multi-user-dungeon/core"
	"golang.org/x/crypto/ssh"
	"gopkg.in/yaml.v3"
)

func main() {
	// Parse command-line flags
	configFile := flag.String("config", "config.yml", "Configuration file")
	flag.Parse()

	// Load configuration from the specified file
	config, err := loadConfiguration(*configFile)
	if err != nil {
		fmt.Printf("Error loading configuration: %v\n", err)
		os.Exit(1)
	}

	// Initialize logging based on the loaded configuration
	if err := core.InitializeLogging(&config); err != nil {
		fmt.Printf("Error initializing logging: %v\n", err)
		os.Exit(1)
	}

	core.Logger.Info("Configuration loaded", "config", config)

	// Create a new server instance
	server, err := NewServer(config)
	if err != nil {
		core.Logger.Error("Failed to create server", "error", err)
		os.Exit(1)
	}

	// Create a context that we can cancel
	ctx, cancel := context.WithCancel(context.Background())

	server.Context = ctx

	// Create a channel to listen for interrupt signals
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)

	// Start the SSH server to accept incoming connections in a goroutine
	go StartSSHServer(server, stop)

	// Start sending metrics in a separate goroutine
	go core.SendMetrics(server, 1*time.Minute)

	// Start the auto-save routine in a separate goroutine
	go core.AutoSave(server)

	// Wait for interrupt signal
	<-stop

	core.Logger.Warn("Interrupt received, initiating graceful shutdown...")

	// Cancel the context to signal all goroutines to stop
	cancel()

	// Create a timeout context for shutdown operations
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer shutdownCancel()

	// Perform graceful shutdown
	if err := GracefulShutdown(shutdownCtx, server); err != nil {
		core.Logger.Error("Error during shutdown", "error", err)
	}

	core.Logger.Warn("Server shutdown complete")
}

// NewServer initializes a new server instance with the given configuration.
// It sets up the database connection, loads game data, and prepares the server for incoming connections.
func NewServer(config core.Configuration) (*core.Server, error) {
	core.Logger.Info("Initializing server...")

	// Initialize the server struct with the provided configuration
	server := &core.Server{
		Config:      config,
		Context:     context.Background(),
		Mutex:       sync.Mutex{},
		WaitGroup:   sync.WaitGroup{},
		StartTime:   time.Now(),
		Port:        config.Server.Port,
		PlayerCount: 0,
		PlayerIndex: &core.Index{},
		Players:     make(map[uint64]*core.Player),
		Characters:  make(map[uuid.UUID]*core.Character),
		Rooms:       make(map[int64]*core.Room),
		Prototypes:  make(map[uuid.UUID]*core.Prototype),
		Items:       make(map[uuid.UUID]*core.Item),
	}

	core.Logger.Info("Initializing database...")

	// Initialize the database connection
	var err error
	server.Database, err = core.NewKeyPair(config.Aws.Region)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize database: %v", err)
	}

	// Initialize the player index
	server.PlayerIndex.IndexID = 1

	// Initialize the bloom filter for character names
	core.Logger.Info("Initializing bloom filter...")
	err = server.InitializeBloomFilter()
	if err != nil {
		core.Logger.Error("Error initializing bloom filter", "error", err)
		return nil, fmt.Errorf("failed to initialize bloom filter: %v", err)
	}

	// Load archetypes from the database
	core.Logger.Info("Loading archetypes from database...")
	err = server.LoadArchetypes()
	if err != nil {
		core.Logger.Error("Error loading archetypes from database", "error", err)
	}

	// Create Default Room
	core.Logger.Info("Adding default room...")
	server.Rooms[0] = core.NewRoom(0, "The Void", "The Void", "You are in a void of nothingness. If you are here, something has gone terribly wrong.")

	// Load rooms from the database
	core.Logger.Info("Loading rooms from database...")
	loadedRooms, err := server.Database.LoadRooms()
	if err != nil {
		core.Logger.Error("Error loading rooms from database", "error", err)
		// Proceeding with default room(s) if rooms failed to load
	} else {
		// Merge loaded rooms with existing rooms, preserving the default room
		for id, room := range loadedRooms {
			server.Rooms[id] = room
		}
	}

	// Load active MOTDs from the database
	core.Logger.Info("Loading active MOTDs from database...")
	activeMOTDs, err := server.Database.GetAllMOTDs()
	if err != nil {
		core.Logger.Error("Failed to load active MOTDs", "error", err)
		// Proceeding without MOTDs if failed to load
	} else {
		server.ActiveMotDs = activeMOTDs
		core.Logger.Info("Loaded active MOTDs", "count", len(activeMOTDs))
	}

	return server, nil
}

// loadConfiguration reads the configuration file and unmarshals it into a Configuration struct.
func loadConfiguration(configFile string) (core.Configuration, error) {
	var config core.Configuration

	data, err := os.ReadFile(configFile)
	if err != nil {
		return config, fmt.Errorf("error reading config file: %w", err)
	}

	err = yaml.Unmarshal(data, &config)
	if err != nil {
		return config, fmt.Errorf("error unmarshalling config: %w", err)
	}

	return config, nil
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
			w, h := parseDims(req.Payload[termLen+4:])
			player.ConsoleWidth, player.ConsoleHeight = w, h
			req.Reply(true, nil)
		case "window-change":
			// Update terminal dimensions
			w, h := parseDims(req.Payload)
			player.ConsoleWidth, player.ConsoleHeight = w, h
		default:
			// Reject unsupported requests
			req.Reply(false, nil)
		}
	}
}

func GracefulShutdown(ctx context.Context, server *core.Server) error {
	core.Logger.Info("Initiating graceful shutdown...")

	// Notify all players of impending shutdown
	for _, character := range server.Characters {
		character.Player.ToPlayer <- "\n\rServer is shutting down. You will be logged out shortly.\n\r"
		character.Player.ToPlayer <- character.Player.Prompt
	}

	// Wait a moment for messages to be sent
	time.Sleep(10 * time.Second)

	// Log out all characters
	for _, character := range server.Characters {
		core.Logger.Info("Logging out character", "characterName", character.Name)
		character.Player.Cleanup()
	}

	// Perform final auto-save
	core.Logger.Info("Performing final auto-save...")
	if err := server.SaveActiveRooms(); err != nil {
		core.Logger.Error("Error saving rooms during shutdown", "error", err)
	}
	if err := server.SaveActiveItems(); err != nil {
		core.Logger.Error("Error saving items during shutdown", "error", err)
	}

	// Close the server listener
	if server.Listener != nil {
		core.Logger.Info("Closing server listener...")
		if err := server.Listener.Close(); err != nil {
			core.Logger.Error("Error closing server listener", "error", err)
		}

		// Wait for ongoing connections to finish (with a timeout)
		shutdownCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
		defer cancel()

		done := make(chan struct{})
		go func() {
			server.WaitGroup.Wait()
			close(done)
		}()

		select {
		case <-done:
			core.Logger.Info("All connections closed successfully")
		case <-shutdownCtx.Done():
			core.Logger.Warn("Timed out waiting for connections to close")
		}
	}

	core.Logger.Info("Graceful shutdown completed")
	return nil
}

// parseDims parses terminal dimensions from the SSH payload.
func parseDims(b []byte) (width, height int) {
	width = int(b[0])<<24 | int(b[1])<<16 | int(b[2])<<8 | int(b[3])
	height = int(b[4])<<24 | int(b[5])<<16 | int(b[6])<<8 | int(b[7])
	return width, height
}
