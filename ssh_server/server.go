package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"net"
	"os"
	"os/signal"
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
	_, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Create a channel to listen for interrupt signals
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)

	// Start the SSH server to accept incoming connections in a goroutine
	go func() {
		if err := StartSSHServer(server); err != nil {
			core.Logger.Error("Failed to start server", "error", err)
			stop <- os.Interrupt // Trigger shutdown if server fails to start
		}
	}()

	// Start sending metrics in a separate goroutine
	metricsDone := make(chan struct{})
	go func() {
		defer close(metricsDone)
		if err := core.SendMetrics(server, 1*time.Minute); err != nil {
			core.Logger.Error("Error in SendMetrics", "error", err)
		}
	}()

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

	// Wait for metrics goroutine to finish
	select {
	case <-metricsDone:
		core.Logger.Info("Metrics goroutine stopped")
	case <-time.After(5 * time.Second):
		core.Logger.Warn("Timed out waiting for metrics goroutine to stop")
	}

	core.Logger.Warn("Server shutdown complete")
}

// NewServer initializes a new server instance with the given configuration.
// It sets up the database connection, loads game data, and prepares the server for incoming connections.
func NewServer(config core.Configuration) (*core.Server, error) {
	core.Logger.Info("Initializing server...")

	// Initialize the server struct with the provided configuration
	server := &core.Server{
		Port:        config.Server.Port,
		PlayerIndex: &core.Index{},
		Config:      config,
		Context:     context.Background(),
		StartTime:   time.Now(),
		Rooms:       make(map[int64]*core.Room),
		Characters:  make(map[uuid.UUID]*core.Character),
		Balance:     config.Game.Balance,
		AutoSave:    config.Game.AutoSave,
		Health:      config.Game.StartingHealth,
		Essence:     config.Game.StartingEssence,
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
		// If bloom filter is critical, consider exiting
		return nil, fmt.Errorf("failed to initialize bloom filter: %v", err)
	}

	// Load archetypes from the database
	core.Logger.Info("Loading archetypes from database...")
	err = server.LoadArchetypes()
	if err != nil {
		core.Logger.Error("Error loading archetypes from database", "error", err)
		// If archetypes are critical, consider exiting
		return nil, fmt.Errorf("failed to load archetypes: %v", err)
	}

	// Add a default room if none exist
	if len(server.Rooms) == 0 {
		core.Logger.Info("Adding default room...")
		server.Rooms[0] = core.NewRoom(0, "The Void", "The Void", "You are in a void of nothingness. If you are here, something has gone terribly wrong.")
	}

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

// Authenticate checks the provided username and password against the authentication system.
// Returns true if authentication is successful, false otherwise.
func Authenticate(username, password string, config core.Configuration) bool {
	core.Logger.Info("Authenticating user", "username", username)

	response, err := core.SignInUser(username, password, config)
	core.Logger.Debug("Authentication response", "response", response)

	if err != nil {
		core.Logger.Error("Authentication attempt failed for user", "username", username, "error", err)
		return false
	}
	return true
}

// StartSSHServer starts the SSH server to accept incoming player connections.
func StartSSHServer(server *core.Server) error {
	core.Logger.Info("Starting SSH server", "port", server.Port)

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

	// Start listening on the configured port
	address := fmt.Sprintf(":%d", server.Port)
	listener, err := net.Listen("tcp", address)
	if err != nil {
		return fmt.Errorf("failed to listen on port %d: %v", server.Port, err)
	}

	server.Listener = listener
	core.Logger.Info("SSH server listening", "port", server.Port)

	// Start accepting connections in a separate goroutine
	go func() {
		for {
			conn, err := server.Listener.Accept()
			if err != nil {
				if errors.Is(err, net.ErrClosed) {
					// The listener has been closed, exit the goroutine
					core.Logger.Info("SSH server listener closed, stopping accept loop")
					return
				}
				core.Logger.Error("Error accepting connection", "error", err)
				continue
			}

			// Increment the WaitGroup before starting the goroutine
			server.WaitGroup.Add(1)
			go func() {
				defer server.WaitGroup.Done()
				handleConnection(server, conn)
			}()
		}
	}()

	return nil
}

func handleConnection(server *core.Server, conn net.Conn) {
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

// handleChannels handles the channels opened by the SSH client.
func handleChannels(server *core.Server, sshConn *ssh.ServerConn, channels <-chan ssh.NewChannel) {
	core.Logger.Info("New connection", "address", sshConn.RemoteAddr().String(), "user", sshConn.User())

	for newChannel := range channels {
		// Accept the channel
		channel, requests, err := newChannel.Accept()
		if err != nil {
			core.Logger.Error("Could not accept channel", "error", err)
			continue
		}

		playerName := sshConn.User()
		playerIndex := server.PlayerIndex.GetID()

		// Attempt to read the player from the database
		_, characterList, seenMotD, err := server.Database.ReadPlayer(playerName)
		if err != nil {
			if err.Error() == "player not found" {
				// Create a new player record if not found
				core.Logger.Info("Creating new player record", "player_name", playerName)
				characterList = make(map[string]uuid.UUID)
				seenMotD = []uuid.UUID{} // Initialize an empty slice for new players
				err = server.Database.WritePlayer(&core.Player{
					PlayerID:      playerName,
					CharacterList: characterList,
					SeenMotD:      seenMotD,
				})
				if err != nil {
					core.Logger.Error("Error creating player record", "error", err)
					continue
				}
			} else {
				core.Logger.Error("Error reading player from database", "error", err)
				continue
			}
		}

		// Create the Player struct with data from the database or as a new player
		player := &core.Player{
			PlayerID:      playerName,
			Index:         playerIndex,
			ToPlayer:      make(chan string),
			FromPlayer:    make(chan string),
			PlayerError:   make(chan error),
			Echo:          true,
			Prompt:        "> ",
			Connection:    channel,
			Server:        server,
			CharacterList: characterList,
			SeenMotD:      seenMotD,
		}

		// Handle SSH requests (pty-req, shell, window-change)
		go HandleSSHRequests(player, requests)

		// Start the goroutine responsible for player I/O
		go core.PlayerInput(player)
		go core.PlayerOutput(player)

		// Initialize player session
		go func(p *core.Player) {
			defer p.Connection.Close()

			core.Logger.Info("Player connected", "player_name", p.PlayerID)

			// Send welcome message
			core.DisplayUnseenMOTDs(server, p)

			// Character Selection Dialog
			character, err := core.SelectCharacter(p, server)
			if err != nil {
				core.Logger.Error("Error during character selection", "error", err)
				return
			}

			// Enter the main input loop for the player
			core.InputLoop(character)

			// Close the player's output channel
			close(player.ToPlayer)

			// Save the player's character and data to the database
			err = server.Database.WriteCharacter(character)
			if err != nil {
				core.Logger.Error("Error saving character", "character_id", character.ID, "error", err)
			}

			err = server.Database.WritePlayer(player)
			if err != nil {
				core.Logger.Error("Error saving player data", "player_name", player.PlayerID, "error", err)
			}

			core.Logger.Info("Player disconnected", "player_name", p.PlayerID)
		}(player)
	}
}

// parseDims parses terminal dimensions from the SSH payload.
func parseDims(b []byte) (width, height int) {
	width = int(b[0])<<24 | int(b[1])<<16 | int(b[2])<<8 | int(b[3])
	height = int(b[4])<<24 | int(b[5])<<16 | int(b[6])<<8 | int(b[7])
	return width, height
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

	// Use ExecuteQuitCommand for each character
	for _, character := range server.Characters {
		core.Logger.Info("Logging out character", "characterName", character.Name)
		core.ExecuteQuitCommand(character, []string{"quit"})
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
