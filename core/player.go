package core

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/service/dynamodb"
	"github.com/google/uuid"
)

// WritePlayer stores the player data into the DynamoDB database.
func (k *KeyPair) WritePlayer(player *Player) error {
	pd := PlayerData{
		PlayerID:      player.PlayerID,
		CharacterList: make(map[string]string),
		SeenMotDs:     make([]string, len(player.SeenMotD)),
	}

	// Convert UUIDs to strings for CharacterList
	for charName, charID := range player.CharacterList {
		pd.CharacterList[charName] = charID.String()
	}

	// Convert UUIDs to strings for SeenMotDs
	for i, motdID := range player.SeenMotD {
		pd.SeenMotDs[i] = motdID.String()
	}

	// Write the player data to the DynamoDB table with proper error handling
	err := k.Put("players", pd)
	if err != nil {
		Logger.Error("Error storing player data", "playerName", player.PlayerID, "error", err)
		return fmt.Errorf("error storing player data: %w", err)
	}

	Logger.Debug("Successfully wrote player data", "playerName", player.PlayerID, "characterCount", len(player.CharacterList), "seenMotDCount", len(player.SeenMotD))
	return nil
}

// ReadPlayer retrieves the player data from the DynamoDB database.
func (k *KeyPair) ReadPlayer(playerName string) (string, map[string]uuid.UUID, []uuid.UUID, error) {
	Logger.Debug("Reading player data from database", "playerName", playerName)

	key := map[string]*dynamodb.AttributeValue{
		"PlayerID": {S: aws.String(playerName)},
	}

	var pd PlayerData
	err := k.Get("players", key, &pd)
	if err != nil {
		if strings.Contains(err.Error(), "item not found") {
			// Return empty maps for new players instead of error
			Logger.Info("First time player, creating new data", "playerName", playerName)
			return playerName, make(map[string]uuid.UUID), make([]uuid.UUID, 0), nil
		}
		Logger.Error("Error reading player data", "playerName", playerName, "error", err)
		return "", nil, nil, fmt.Errorf("error reading player data: %w", err)
	}

	// Convert character IDs from strings to UUIDs
	characterList := make(map[string]uuid.UUID)
	for name, idString := range pd.CharacterList {
		id, err := uuid.Parse(idString)
		if err != nil {
			Logger.Error("Error parsing character UUID", "characterName", name, "uuid", idString, "error", err)
			continue
		}
		characterList[name] = id
	}

	// Convert SeenMotDs from strings to UUIDs
	seenMotDs := make([]uuid.UUID, 0, len(pd.SeenMotDs))
	for _, idString := range pd.SeenMotDs {
		id, err := uuid.Parse(idString)
		if err != nil {
			Logger.Error("Error parsing MOTD UUID", "uuid", idString, "error", err)
			continue
		}
		seenMotDs = append(seenMotDs, id)
	}

	Logger.Debug("Successfully read player data",
		"playerName", pd.PlayerID,
		"characterCount", len(characterList),
		"seenMotDCount", len(seenMotDs))

	return pd.PlayerID, characterList, seenMotDs, nil
}

// PlayerInput handles the player's input in a separate goroutine.
// It reads input from the player's SSH connection and sends it to the FromPlayer channel.
func PlayerInput(p *Player) {
	Logger.Debug("Player input goroutine started", "playerName", p.PlayerID)

	var inputBuffer []rune
	reader := bufio.NewReader(p.Connection)

	defer func() {
		close(p.FromPlayer)
		Logger.Debug("Player input goroutine ended", "playerName", p.PlayerID)
	}()

	// Send initial prompt
	if p.Echo {
		p.ToPlayer <- p.Prompt
	}

	for {
		r, _, err := reader.ReadRune()
		if err != nil {
			if err == io.EOF {
				Logger.Info("Player disconnected", "playerName", p.PlayerID)
				p.PlayerError <- err
				p.Cleanup()
				return
			} else {
				Logger.Error("Error reading from player", "playerName", p.PlayerID, "error", err)
				p.PlayerError <- err
				continue
			}
		}

		switch r {
		case '\n', '\r':
			if len(inputBuffer) > 0 {
				p.FromPlayer <- string(inputBuffer)
				// Echo the final newline
				if p.Echo {
					p.Connection.Write([]byte("\r\n"))
					// Send prompt after command
					p.ToPlayer <- p.Prompt
				}
				inputBuffer = inputBuffer[:0]
			}
		case '\b', 127: // Backspace and Delete
			if len(inputBuffer) > 0 {
				inputBuffer = inputBuffer[:len(inputBuffer)-1]
				if p.Echo {
					p.Connection.Write([]byte("\b \b"))
				}
			}
		case '\x03': // Ctrl+C
			Logger.Info("Player sent interrupt signal", "playerName", p.PlayerID)
			p.PlayerError <- errors.New("player interrupt")
			p.Cleanup()
			return
		default:
			if len(inputBuffer) < 1024 { // Max input size
				inputBuffer = append(inputBuffer, r)
				if p.Echo {
					p.Connection.Write([]byte(string(r)))
				}
			}
		}
	}
}

// PlayerOutput handles sending messages to the player in a separate goroutine.
// It reads messages from the ToPlayer channel and writes them to the player's SSH connection.
func PlayerOutput(p *Player) {
	Logger.Debug("Player output goroutine started", "playerName", p.PlayerID)

	// Use a defer to cleanup but don't close FromPlayer here
	defer Logger.Debug("Player output goroutine ended", "playerName", p.PlayerID)

	for message := range p.ToPlayer {
		wrappedMessage := wrapText(message, p.ConsoleWidth)
		_, err := p.Connection.Write([]byte(wrappedMessage))
		if err != nil {
			Logger.Warn("Failed to send message to player", "playerName", p.PlayerID, "error", err)
			return
		}
	}

	Logger.Debug("Message channel closed for player", "playerName", p.PlayerID)
}

// InputLoop is the main loop that handles player commands.
// It reads commands from the player's input and executes them accordingly.
func InputLoop(c *Character) {
	if c == nil || c.Player == nil {
		Logger.Error("Invalid character or player in input loop")
		return
	}

	// Add safety check for CTX
	if c.Player.CTX == nil {
		Logger.Error("Player context is nil", "characterName", c.Name)
		return
	}

	Logger.Debug("Starting input loop for character", "characterName", c.Name)

	// Initially execute the look command with no additional tokens
	ExecuteLookCommand(c, []string{})

	// Safety check before sending prompt
	if c.Player.ToPlayer == nil {
		Logger.Error("Player ToPlayer channel is nil", "characterName", c.Name)
		return
	}

	// Send initial prompt - blocking write for initial prompt is acceptable
	select {
	case c.Player.ToPlayer <- c.Player.Prompt:
	case <-c.Player.CTX.Done():
		c.Player.Cleanup()
		return
	}

	// Create a ticker that ticks once per second
	commandTicker := time.NewTicker(time.Second)
	defer commandTicker.Stop()

	var lastCommand string
	shouldQuit := false

	// Create command processing timeout
	const commandTimeout = 5 * time.Second

	for !shouldQuit {
		// Additional safety check inside loop
		if c.Player == nil || c.Player.CTX == nil {
			Logger.Error("Player or context became nil during loop", "characterName", c.Name)
			return
		}

		select {
		case <-c.Player.CTX.Done():
			Logger.Info("Player context cancelled", "characterName", c.Name)
			shouldQuit = true
			continue

		case inputLine, more := <-c.Player.FromPlayer:
			if !more {
				Logger.Debug("Input channel closed for player", "playerName", c.Player.PlayerID)
				shouldQuit = true
				continue
			}
			if lastCommand == "" { // Only accept new command if previous one is processed
				lastCommand = strings.Replace(inputLine, "\n", "\n\r", -1)
			}

		case <-commandTicker.C:
			if lastCommand != "" {
				// Create timeout context for command processing
				cmdCtx, cancel := context.WithTimeout(c.Player.CTX, commandTimeout)

				// Process command in separate goroutine
				done := make(chan bool, 1)
				go func() {
					verb, tokens, err := ValidateCommand(strings.TrimSpace(lastCommand))
					if err != nil {
						select {
						case c.Player.ToPlayer <- err.Error() + "\n\r":
						case <-cmdCtx.Done():
							return
						}
					} else {
						// Execute the command
						shouldQuit = ExecuteCommand(c, verb, tokens)
						Logger.Debug("Player issued command",
							"playerName", c.Player.PlayerID,
							"command", strings.Join(tokens, " "))
					}
					done <- true
				}()

				// Wait for command completion or timeout
				select {
				case <-done:
					if !shouldQuit {
						// Non-blocking prompt send
						select {
						case c.Player.ToPlayer <- c.Player.Prompt:
						case <-cmdCtx.Done():
						default:
							Logger.Warn("Unable to send prompt", "characterName", c.Name)
						}
					}
				case <-cmdCtx.Done():
					Logger.Warn("Command processing timed out",
						"characterName", c.Name,
						"command", lastCommand)
				}

				cancel()         // Cleanup timeout context
				lastCommand = "" // Clear the command regardless of execution result
			}
		}
	}

	// Cleanup on exit
	c.Player.Cleanup()
	Logger.Debug("Input loop ended for character", "characterName", c.Name)
}

func (p *Player) Cleanup() {
	// Use player mutex to protect cleanup state
	p.Mutex.Lock()
	defer p.Mutex.Unlock()

	// Save character data first if it exists
	if p.Character != nil {
		Logger.Debug("Saving character during cleanup", "characterName", p.Character.Name)
		if err := p.Game.Database.WriteCharacter(p.Character); err != nil {
			Logger.Error("Failed to save character during cleanup",
				"characterName", p.Character.Name,
				"error", err)
		}

		// If character is in a room, remove them
		if p.Character.Room != nil {
			p.Character.Room.Mutex.Lock()
			delete(p.Character.Room.Characters, p.Character.ID)
			p.Character.Room.Mutex.Unlock()
		}
	}

	// Save player data
	Logger.Debug("Saving player data during cleanup", "playerID", p.PlayerID)
	if err := p.Game.Database.WritePlayer(p); err != nil {
		Logger.Error("Failed to save player during cleanup",
			"playerID", p.PlayerID,
			"error", err)
	}

	// Cancel context immediately if it exists
	if p.Cancel != nil {
		p.Cancel()
		p.Cancel = nil
		p.CTX = nil
	}

	// Force close connection immediately if it exists
	if p.Connection != nil {
		p.Connection.Close()
		p.Connection = nil
	}

	// Force close channels without waiting
	if p.ToPlayer != nil {
		close(p.ToPlayer)
		p.ToPlayer = nil
	}
	if p.FromPlayer != nil {
		close(p.FromPlayer)
		p.FromPlayer = nil
	}
	if p.PlayerError != nil {
		close(p.PlayerError)
		p.PlayerError = nil
	}

	// Remove Player from server's player map immediately
	if p.Game.Server != nil {
		p.Game.Server.Mutex.Lock()
		delete(p.Game.Server.Players, p.Index)
		p.Game.Server.Mutex.Unlock()
	}

	Logger.Info("Player cleanup completed", "playerID", p.PlayerID)
}
