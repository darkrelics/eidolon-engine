package core

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"strconv"
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
	key := map[string]*dynamodb.AttributeValue{
		"PlayerID": {S: aws.String(playerName)},
	}

	var pd PlayerData

	// Read the player data from the DynamoDB table with proper error handling
	err := k.Get("players", key, &pd)
	if err != nil {
		Logger.Error("Error reading player data", "playerName", playerName, "error", err)
		return "", nil, nil, fmt.Errorf("player not found")
	}

	// Convert character IDs from strings to UUIDs
	characterList := make(map[string]uuid.UUID)
	for name, idString := range pd.CharacterList {
		id, err := uuid.Parse(idString)
		if err != nil {
			Logger.Error("Error parsing UUID for character", "characterName", name, "error", err)
			continue // Skip invalid UUIDs
		}
		characterList[name] = id
	}

	// Convert SeenMotDs from strings to UUIDs
	seenMotDs := make([]uuid.UUID, 0, len(pd.SeenMotDs))
	for _, idString := range pd.SeenMotDs {
		id, err := uuid.Parse(idString)
		if err != nil {
			Logger.Error("Error parsing UUID for seen MOTD", "idString", idString, "error", err)
			continue // Skip invalid UUIDs
		}
		seenMotDs = append(seenMotDs, id)
	}

	Logger.Debug("Successfully read player data", "playerName", pd.PlayerID, "characterCount", len(characterList), "seenMotDCount", len(seenMotDs))
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
				inputBuffer = inputBuffer[:0]
			}
			if p.Echo {
				p.Connection.Write([]byte("\r\n"))
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

// SelectCharacter handles the character selection process for a player.
// It presents the player with options to select or create a character.
func SelectCharacter(player *Player, server *Server) (*Character, error) {
	Logger.Debug("Player is selecting a character", "playerName", player.PlayerID)

	var options []string

	sendCharacterOptions := func() {
		player.ToPlayer <- "Select a character:\n\r"
		player.ToPlayer <- "0: Create a new character\n\r"

		if len(player.CharacterList) > 0 {
			i := 1
			for name := range player.CharacterList {
				player.ToPlayer <- fmt.Sprintf("%d: %s\n\r", i, name)
				options = append(options, name)
				i++
			}
			player.ToPlayer <- "X: Delete a character\n\r"
		} else {
			player.ToPlayer <- "No existing characters found.\n\r"
		}
		player.ToPlayer <- "Enter the number of your choice or 'X' to delete: "
	}

	for {
		options = []string{} // Reset options for each iteration
		sendCharacterOptions()

		input, ok := <-player.FromPlayer
		if !ok {
			Logger.Error("Failed to receive input from player", "playerName", player.PlayerID)
			return nil, fmt.Errorf("failed to receive input")
		}

		input = strings.TrimSpace(strings.ToUpper(input))

		if input == "X" && len(player.CharacterList) > 0 {
			// Handle character deletion
			player.ToPlayer <- "Select a character to delete: \n\r"
			for i, name := range options {
				player.ToPlayer <- fmt.Sprintf("%d: %s\n\r", i+1, name)
			}
			player.ToPlayer <- "Enter the number of the character to delete: "

			deleteChoice, ok := <-player.FromPlayer
			if !ok {
				Logger.Error("Failed to receive delete choice from player", "playerName", player.PlayerID)
				return nil, fmt.Errorf("failed to receive delete choice")
			}

			deleteIndex, err := strconv.Atoi(strings.TrimSpace(deleteChoice))
			if err != nil || deleteIndex < 1 || deleteIndex > len(options) {
				player.ToPlayer <- "Invalid choice. Returning to character selection.\n\r"
				continue
			}

			characterToDelete := options[deleteIndex-1]
			err = server.DeleteCharacter(player, characterToDelete)
			if err != nil {
				Logger.Error("Failed to delete character", "characterName", characterToDelete, "error", err)
				player.ToPlayer <- fmt.Sprintf("Failed to delete character: %v\n\r", err)
			} else {
				player.ToPlayer <- fmt.Sprintf("\n\rCharacter '%s' has been deleted.\n\r", characterToDelete)
			}
			continue
		}

		choice, err := strconv.Atoi(input)
		if err != nil || choice < 0 || choice > len(options) {
			player.ToPlayer <- "Invalid choice. Please select a valid option.\n\r"
			continue
		}

		var character *Character
		if choice == 0 {
			character, err = server.CreateCharacter(player)
			if err != nil {
				player.ToPlayer <- fmt.Sprintf("\n\rError creating character: %v\n\r", err)
				continue
			}
		} else if choice <= len(options) {
			characterName := options[choice-1]
			characterID := player.CharacterList[characterName]
			character, err = server.Database.LoadCharacter(characterID, player, server)
			if err != nil {
				Logger.Error("Error loading character for player", "characterName", characterName, "playerName", player.PlayerID, "error", err)
				player.ToPlayer <- fmt.Sprintf("Error loading character: %v\n\r", err)
				continue
			}
		}

		if character == nil {
			player.ToPlayer <- "Failed to create or load character. Please try again.\n\r"
			continue
		}

		// Ensure the character is added to the server's character list
		server.Mutex.Lock()
		server.Characters[character.ID] = character
		server.Mutex.Unlock()

		// Add character to the room and notify other players
		if character.Room != nil {
			// Notify the room that the character has entered
			character.Room.Mutex.Lock()
			character.Room.Characters[character.ID] = character
			character.Room.Mutex.Unlock()
		}

		Logger.Debug("Character selected and added to server", "characterName", character.Name, "characterID", character.ID)

		return character, nil
	}
}

func (p *Player) Cleanup() {
	// Use player mutex to protect cleanup state
	p.Mutex.Lock()
	defer p.Mutex.Unlock()

	// Check if already cleaned up
	if p.CTX == nil {
		Logger.Debug("Cleanup already performed for player", "playerID", p.PlayerID)
		return
	}

	Logger.Debug("Starting player cleanup", "playerID", p.PlayerID)

	// Cancel context first to stop any ongoing operations
	if p.Cancel != nil {
		p.Cancel()
		p.Cancel = nil
	}

	// Safely close connection
	if p.Connection != nil {
		// Best effort to send goodbye message
		p.Connection.Write([]byte("\n\rGoodbye!\n\r"))
		p.Connection.Close()
		p.Connection = nil
	}

	// Save data before closing channels
	if p.Character != nil {
		// Remove character from room
		if p.Character.Room != nil {
			p.Character.Room.Mutex.Lock()
			if _, exists := p.Character.Room.Characters[p.Character.ID]; exists {
				delete(p.Character.Room.Characters, p.Character.ID)

				// Notify other players in room - safely
				roomMsg := fmt.Sprintf("\n\r%s has left.\n\r", p.Character.Name)
				for _, c := range p.Character.Room.Characters {
					if c != nil && c.Player != nil && c.Player.ToPlayer != nil {
						select {
						case c.Player.ToPlayer <- roomMsg:
						default:
							// Channel is blocked or closed, skip
						}
						select {
						case c.Player.ToPlayer <- c.Player.Prompt:
						default:
							// Channel is blocked or closed, skip
						}
					}
				}
			}
			p.Character.Room.Mutex.Unlock()

		}

		// Save character state to database
		if err := p.Server.Database.WriteCharacter(p.Character); err != nil {
			Logger.Error("Failed to save character state during cleanup",
				"characterName", p.Character.Name,
				"error", err)
		}

		// Remove character from server's character list
		if p.Server != nil {
			p.Server.Mutex.Lock()
			delete(p.Server.Characters, p.Character.ID)
			p.Server.Mutex.Unlock()
		}

		// Save player data
		if err := p.Server.Database.WritePlayer(p); err != nil {
			Logger.Error("Failed to save player data during cleanup",
				"playerName", p.PlayerID,
				"error", err)
		}

		// Clear character reference
		p.Mutex.Lock()
		p.Character = nil
		p.Mutex.Unlock()

		// Remove Player from server's player map
		if p.Server != nil {
			p.Server.Mutex.Lock()
			delete(p.Server.Players, p.Index)
			p.Server.Mutex.Unlock()
		}
	}

	// Safely close channels if they exist
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

	// Clear context
	p.CTX = nil

	Logger.Info("Player cleanup completed", "playerID", p.PlayerID)
}
