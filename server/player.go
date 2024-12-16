package main

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"runtime/debug"
	"strings"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/service/dynamodb"
	"github.com/google/uuid"
	"golang.org/x/crypto/ssh"
	"golang.org/x/sync/errgroup"
)

type Player struct {
	Index         uint64
	PlayerID      string
	ToPlayer      chan string
	FromPlayer    chan string
	PlayerError   chan error
	Echo          bool
	Prompt        string
	Connection    ssh.Channel
	ConsoleWidth  int
	ConsoleHeight int
	SeenMotD      []uuid.UUID
	CharacterList map[string]uuid.UUID
	Character     *Character
	LoginTime     time.Time
	Server        *Server
	Mutex         sync.RWMutex
	Context       context.Context
	Cancel        context.CancelFunc
}

type PlayerData struct {
	PlayerID      string            `json:"PlayerID" dynamodbav:"PlayerID"`
	CharacterList map[string]string `json:"characterList" dynamodbav:"CharacterList"`
	SeenMotDs     []string          `json:"seenMotD" dynamodbav:"SeenMotD"`
}

func (k *KeyPair) WritePlayer(player *Player) error {
	pd := PlayerData{
		PlayerID:      player.PlayerID,
		CharacterList: make(map[string]string),
		SeenMotDs:     make([]string, len(player.SeenMotD)),
	}

	for charName, charID := range player.CharacterList {
		pd.CharacterList[charName] = charID.String()
	}

	for i, motdID := range player.SeenMotD {
		pd.SeenMotDs[i] = motdID.String()
	}

	err := k.Put("players", pd)
	if err != nil {
		Logger.Error("Error storing player data", "playerName", player.PlayerID, "error", err)
		return fmt.Errorf("error storing player data: %w", err)
	}

	Logger.Debug("Successfully wrote player data", "playerName", player.PlayerID)
	return nil
}

func (k *KeyPair) ReadPlayer(playerName string) (string, map[string]uuid.UUID, []uuid.UUID, error) {
	Logger.Debug("Reading player data", "playerName", playerName)

	key := map[string]*dynamodb.AttributeValue{
		"PlayerID": {S: aws.String(playerName)},
	}

	var pd PlayerData
	err := k.Get("players", key, &pd)
	if err != nil {
		if strings.Contains(err.Error(), "item not found") {
			Logger.Info("First time player", "playerName", playerName)
			return playerName, make(map[string]uuid.UUID), make([]uuid.UUID, 0), nil
		}
		Logger.Error("Error reading player data", "playerName", playerName, "error", err)
		return "", nil, nil, fmt.Errorf("error reading player data: %w", err)
	}

	characterList := make(map[string]uuid.UUID)
	for name, idString := range pd.CharacterList {
		id, err := uuid.Parse(idString)
		if err != nil {
			Logger.Error("Error parsing character UUID", "characterName", name, "uuid", idString)
			continue
		}
		characterList[name] = id
	}

	seenMotDs := make([]uuid.UUID, 0, len(pd.SeenMotDs))
	for _, idString := range pd.SeenMotDs {
		id, err := uuid.Parse(idString)
		if err != nil {
			Logger.Error("Error parsing MOTD UUID", "uuid", idString)
			continue
		}
		seenMotDs = append(seenMotDs, id)
	}

	return pd.PlayerID, characterList, seenMotDs, nil
}

func PlayerInput(ctx context.Context, p *Player) {
	Logger.Debug("Starting player input", "playerName", p.PlayerID)

	var inputBuffer []rune
	reader := bufio.NewReader(p.Connection)

	defer func() {
		close(p.FromPlayer)
		Logger.Debug("Player input ended", "playerName", p.PlayerID)
	}()

	if p.Echo {
		select {
		case p.ToPlayer <- p.Prompt:
		case <-ctx.Done():
			return
		}
	}

	for {
		select {
		case <-ctx.Done():
			return

		default:
			r, _, err := reader.ReadRune()
			if err != nil {
				if err == io.EOF {
					Logger.Info("Player disconnected", "playerName", p.PlayerID)
					p.PlayerError <- err
					p.Cleanup()
					return
				}
				Logger.Error("Error reading from player", "playerName", p.PlayerID, "error", err)
				p.PlayerError <- err
				continue
			}

			switch r {
			case '\n', '\r':
				if len(inputBuffer) > 0 {
					select {
					case p.FromPlayer <- string(inputBuffer):
					case <-ctx.Done():
						return
					}

					if p.Echo {
						p.Connection.Write([]byte("\r\n"))
						select {
						case p.ToPlayer <- p.Prompt:
						case <-ctx.Done():
							return
						}
					}
					inputBuffer = inputBuffer[:0]
				}

			case '\b', 127:
				if len(inputBuffer) > 0 {
					inputBuffer = inputBuffer[:len(inputBuffer)-1]
					if p.Echo {
						p.Connection.Write([]byte("\b \b"))
					}
				}

			case '\x03':
				Logger.Info("Player interrupt", "playerName", p.PlayerID)
				p.PlayerError <- errors.New("player interrupt")
				p.Cleanup()
				return

			default:
				if len(inputBuffer) < 1024 {
					inputBuffer = append(inputBuffer, r)
					if p.Echo {
						p.Connection.Write([]byte(string(r)))
					}
				}
			}
		}
	}
}

func PlayerOutput(ctx context.Context, p *Player) {
	Logger.Debug("Starting player output", "playerName", p.PlayerID)
	defer Logger.Debug("Player output ended", "playerName", p.PlayerID)

	for {
		select {
		case <-ctx.Done():
			return

		case message, ok := <-p.ToPlayer:
			if !ok {
				return
			}
			wrappedMessage := wrapText(message, p.ConsoleWidth)
			if _, err := p.Connection.Write([]byte(wrappedMessage)); err != nil {
				Logger.Warn("Failed to send message", "playerName", p.PlayerID, "error", err)
				return
			}
		}
	}
}

func processPlayerCommand(cmdCtx context.Context, c *Character, lastCommand string, done chan<- bool) {
	defer func() {
		if r := recover(); r != nil {
			Logger.Error("Panic in command processing",
				"characterName", c.Name,
				"command", lastCommand,
				"panic", r)
			done <- true
		}
	}()

	verb, tokens, err := ValidateCommand(strings.TrimSpace(lastCommand))
	if err != nil {
		select {
		case c.Player.ToPlayer <- err.Error() + "\n\r":
		case <-cmdCtx.Done():
			return
		}
	} else {
		ExecuteCommand(c, verb, tokens)
		Logger.Debug("Command executed",
			"playerName", c.Player.PlayerID,
			"command", strings.Join(tokens, " "))
	}
	done <- true
}

func InputLoop(ctx context.Context, c *Character) {
	if c == nil || c.Player == nil {
		Logger.Error("Invalid character or player")
		return
	}

	if c.Player.Context == nil {
		Logger.Error("Player context is nil", "characterName", c.Name)
		return
	}

	Logger.Debug("Starting input loop", "characterName", c.Name)

	defer func() {
		c.Player.Cleanup()
		Logger.Debug("Input loop ended", "characterName", c.Name)
	}()

	ExecuteLookCommand(c, []string{})

	if c.Player.ToPlayer == nil {
		Logger.Error("ToPlayer channel is nil", "characterName", c.Name)
		return
	}

	select {
	case c.Player.ToPlayer <- c.Player.Prompt:
	case <-c.Player.Context.Done():
		return
	}

	var lastCommand string
	const commandTimeout = 5 * time.Second

	for {
		if c.Player == nil || c.Player.Context == nil {
			Logger.Error("Player or context nil", "characterName", c.Name)
			return
		}

		select {
		case <-c.Player.Context.Done():
			Logger.Info("Context cancelled", "characterName", c.Name)
			c.End <- true
			return

		case <-c.End:
			Logger.Info("Character ended", "characterName", c.Name)
			return

		case inputLine, ok := <-c.Player.FromPlayer:
			if !ok {
				Logger.Debug("Input channel closed", "playerName", c.Player.PlayerID)
				c.End <- true
				return
			}
			if lastCommand == "" {
				lastCommand = strings.Replace(inputLine, "\n", "\n\r", -1)
			}

		case <-c.Game.ticker.C:
			if lastCommand != "" {
				cmdCtx, cancel := context.WithTimeout(c.Player.Context, commandTimeout)
				done := make(chan bool, 1)

				go processPlayerCommand(cmdCtx, c, lastCommand, done)

				select {
				case <-c.End:
					cancel()
					return
				case <-done:
					select {
					case c.Player.ToPlayer <- c.Player.Prompt:
					case <-cmdCtx.Done():
					default:
						Logger.Warn("Prompt send failed", "characterName", c.Name)
					}
				case <-cmdCtx.Done():
					Logger.Warn("Command timeout", "characterName", c.Name, "command", lastCommand)
				}

				cancel()
				lastCommand = ""
			}
		}
	}
}

func (p *Player) Cleanup() {
	if p.Server == nil {
		Logger.Error("Server nil during cleanup", "playerID", p.PlayerID)
		return
	}

	if p.Server.Players == nil {
		Logger.Error("Players map nil in Server", "playerID", p.PlayerID)
		return
	}

	p.Mutex.Lock()
	defer p.Mutex.Unlock()

	if err := p.Server.Database.WritePlayer(p); err != nil {
		Logger.Error("Failed to save player data", "playerID", p.PlayerID, "error", err)
	}

	if p.Cancel != nil {
		p.Cancel()
	}

	if p.Connection != nil {
		p.Connection.Close()
	}

	close(p.ToPlayer)
	close(p.FromPlayer)
	close(p.PlayerError)

	p.Server.Mutex.Lock()
	delete(p.Server.Players, p.Index)
	p.Server.Mutex.Unlock()

	Logger.Info("Cleanup complete", "playerID", p.PlayerID)
}

func NewPlayer(server *Server, playerName string) (*Player, error) {
	characterList := make(map[string]uuid.UUID)
	seenMotD := make([]uuid.UUID, 0)

	ctx, cancel := context.WithCancel(server.Context)

	player := &Player{
		PlayerID:      playerName,
		CharacterList: characterList,
		SeenMotD:      seenMotD,
		Server:        server,
		Context:       ctx,
		Cancel:        cancel,
		ToPlayer:      make(chan string, 10),
		FromPlayer:    make(chan string, 10),
		PlayerError:   make(chan error, 1),
		Echo:          true,
		LoginTime:     time.Now(),
	}

	err := server.Database.WritePlayer(player)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("error creating player: %w", err)
	}

	return player, nil
}

func InitializePlayerData(server *Server, playerName string) (*Player, error) {
	_, charList, motd, err := server.Database.ReadPlayer(playerName)
	if err != nil {
		if err.Error() == "player not found" {
			Logger.Info("Creating new player", "playerName", playerName)
			return NewPlayer(server, playerName)
		}
		return nil, fmt.Errorf("error reading player: %w", err)
	}

	ctx, cancel := context.WithCancel(server.Context)

	player := &Player{
		PlayerID:      playerName,
		CharacterList: charList,
		SeenMotD:      motd,
		Server:        server,
		Context:       ctx,
		Cancel:        cancel,
		ToPlayer:      make(chan string, 10),
		FromPlayer:    make(chan string, 10),
		PlayerError:   make(chan error, 1),
		Echo:          true,
		LoginTime:     time.Now(),
	}

	return player, nil
}

// handlePlayerSession manages a player's game session
func handlePlayerSession(ctx context.Context, server *Server, game *Game, player *Player) {
	// Ensure connection cleanup even on panic
	defer func() {
		if r := recover(); r != nil {
			stack := debug.Stack()
			Logger.Error("Panic in player session", "playerName", player.PlayerID, "panic", r, "stack", string(stack))
		}
		if player != nil && player.Connection != nil {
			if player.Character != nil {
				player.Character.Cleanup()
			}
			player.Cleanup()
		}
	}()

	// Create session-specific context
	sessionCtx, cancel := context.WithCancel(ctx)
	defer cancel()

	// Start I/O handlers
	ioGroup, ioCtx := errgroup.WithContext(sessionCtx)
	ioGroup.Go(func() error {
		PlayerInput(ioCtx, player)
		return nil
	})
	ioGroup.Go(func() error {
		PlayerOutput(ioCtx, player)
		return nil
	})

	Logger.Info("Starting player session",
		"playerName", player.PlayerID,
		"playerIndex", player.Index)

	// Display welcome messages and MOTDs
	Logger.Debug("Displaying welcome messages", "playerName", player.PlayerID)
	if err := DisplayUnseenMOTDs(server, player); err != nil {
		Logger.Error("Failed to display MOTDs", "playerName", player.PlayerID, "error", err)
		return
	}

	// Character Selection
	Logger.Debug("Starting character selection", "playerName", player.PlayerID)
	character, err := SelectCharacter(sessionCtx, game, player)
	if err != nil {
		Logger.Error("Character selection failed", "playerName", player.PlayerID, "error", err)
		return
	}

	if character == nil {
		Logger.Error("No character selected", "playerName", player.PlayerID)
		return
	}

	Logger.Info("Character selected for player", "playerName", player.PlayerID, "characterName", character.Name, "characterID", character.ID)

	// Update player with selected character
	player.Mutex.Lock()
	player.Prompt = "> "
	player.Character = character
	player.Mutex.Unlock()

	// Create a channel for input loop completion
	inputDone := make(chan struct{})

	// Start the input loop
	go func() {
		defer close(inputDone)
		Logger.Debug("Starting input loop", "playerName", player.PlayerID, "characterName", character.Name)
		InputLoop(sessionCtx, character)
	}()

	// Wait for session end conditions
	select {
	case <-sessionCtx.Done():
		Logger.Info("Session context cancelled",
			"playerName", player.PlayerID,
			"characterName", character.Name)

	case <-ctx.Done():
		Logger.Info("Parent context cancelled",
			"playerName", player.PlayerID,
			"characterName", character.Name)

	case <-inputDone:
		Logger.Info("Input loop completed normally",
			"playerName", player.PlayerID,
			"characterName", character.Name)
	}

	// Cleanup
	cancel() // Ensure all child goroutines are cancelled
	if err := ioGroup.Wait(); err != nil {
		Logger.Error("Error in I/O handlers",
			"playerName", player.PlayerID,
			"error", err)
	}

	if character != nil {
		character.Cleanup()
	}
	player.Cleanup()

	Logger.Info("Player session ended", "playerName", player.PlayerID)
}
