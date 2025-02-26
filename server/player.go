/*
Eidolon Engine

Copyright 2024-2025 Jason Robinson

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package main

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"strings"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/service/dynamodb"
	"github.com/google/uuid"
	"golang.org/x/crypto/ssh"
)

type Player struct {
	ctx           context.Context
	cancel        context.CancelFunc
	index         uint64
	id            uuid.UUID // Using uuid.UUID type instead of string
	email         string    // Field to store email address
	toPlayer      chan string
	fromPlayer    chan string
	playerError   chan error
	echo          bool
	prompt        string
	connection    ssh.Channel
	consoleWidth  int
	consoleHeight int
	characterList map[string]uuid.UUID
	seenMotD      []uuid.UUID
	character     *Character
	login         time.Time
	lastEdited    time.Time
	lastSaved     time.Time
	server        *Server
	mutex         sync.RWMutex
	shutdownOnce  sync.Once
}

type PlayerData struct {
	PlayerID      string            `json:"PlayerID" dynamodbav:"PlayerID"` // Store UUID as string in DynamoDB
	Email         string            `json:"Email" dynamodbav:"Email"`       // Store email
	CharacterList map[string]string `json:"CharacterList" dynamodbav:"CharacterList"`
	SeenMotDs     []string          `json:"SeenMotD" dynamodbav:"SeenMotD"`
}

func (p *Player) Load(playerID uuid.UUID) error {
	Logger.Debug("Loading player data", "player_id", playerID.String())

	database := p.server.database

	key := map[string]*dynamodb.AttributeValue{
		"PlayerID": {S: aws.String(playerID.String())},
	}

	var playerData PlayerData

	p.characterList = make(map[string]uuid.UUID)
	p.seenMotD = make([]uuid.UUID, 0)

	err := database.Get("players", key, &playerData)
	if err != nil {
		if strings.Contains(err.Error(), "item not found") {
			Logger.Info("New player", "player_id", playerID.String(), "email", p.email)
			p.Save()
			return nil
		}
		Logger.Error("Error loading player data", "error", err)
		return err
	}

	Logger.Info("Player data loaded", "player_id", playerID.String(), "email", playerData.Email)

	p.mutex.Lock()
	defer p.mutex.Unlock()

	// Update email from database
	p.email = playerData.Email

	for characterName, characterID := range playerData.CharacterList {
		parsedUUID, err := uuid.Parse(characterID)
		if err != nil {
			Logger.Error("Error parsing character ID", "character_id", characterID)
			continue
		}
		p.characterList[characterName] = parsedUUID
	}

	for _, motdID := range playerData.SeenMotDs {
		motdUUID, err := uuid.Parse(motdID)
		if err != nil {
			Logger.Error("Error parsing MOTD ID", "motd_id", motdID)
			continue
		}
		p.seenMotD = append(p.seenMotD, motdUUID)
	}

	p.lastEdited = time.Now()
	p.lastSaved = time.Now()

	return nil
}

func (p *Player) Save() error {
	Logger.Info("Saving player data", "player_id", p.id.String(), "email", p.email)

	database := p.server.database

	playerData := PlayerData{
		PlayerID:      p.id.String(),
		Email:         p.email,
		CharacterList: make(map[string]string),
		SeenMotDs:     make([]string, len(p.seenMotD)),
	}

	// Convert character IDs to strings
	for characterName, characterID := range p.characterList {
		playerData.CharacterList[characterName] = characterID.String()
	}

	// Convert MOTD IDs to strings
	for i, motdID := range p.seenMotD {
		playerData.SeenMotDs[i] = motdID.String()
	}

	err := database.Put("players", playerData)
	if err != nil {
		Logger.Error("Error saving player data", "error", err)
		p.toPlayer <- "Error saving player data. Please contact an administrator.\n"
		return fmt.Errorf("error saving player data: %w", err)
	}

	p.mutex.Lock()
	p.lastSaved = time.Now()
	p.mutex.Unlock()

	return nil
}

func NewPlayerSSH(server *Server, playerEmail string, conn ssh.Channel, interfaceCtx context.Context, userUUID uuid.UUID) (*Player, error) {
	ctx, cancel := context.WithCancel(server.ctx)

	player := &Player{
		server:        server,
		id:            userUUID,    // Using uuid.UUID directly
		email:         playerEmail, // Store email separately
		toPlayer:      make(chan string, 10),
		fromPlayer:    make(chan string, 10),
		playerError:   make(chan error, 1),
		echo:          true,
		connection:    conn,
		consoleWidth:  80,
		consoleHeight: 24,
		login:         time.Now(),
		ctx:           ctx,
		cancel:        cancel,
		shutdownOnce:  sync.Once{},
	}

	// Load player data
	if err := player.Load(userUUID); err != nil {
		cancel()
		return nil, fmt.Errorf("player data load: %w", err)
	}

	// Register with server
	err := server.AddPlayer(player)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("player registration: %w", err)
	}

	return player, nil
}

func (p *Player) RunSSH(requests <-chan *ssh.Request) {
	Logger.Info("Player connected", "player_name", p.id)

	defer p.Stop()

	// Create channels for each goroutine
	requestDone := make(chan error, 1)
	inputDone := make(chan error, 1)
	outputDone := make(chan error, 1)

	// Start handlers
	go p.handleRequests(p.ctx, requests, requestDone)
	go p.handleInput(p.ctx, inputDone)
	go p.handleOutput(p.ctx, outputDone)

	// Display MOTDs after connection is established but before entering main loop
	if err := DisplayUnseenMOTDs(p); err != nil {
		Logger.Error("motd display error", "player", p.id, "error", err)
		// Continue despite MOTD display error
	}

	// Start Player Interface
	p.Console()

	// Wait for shutdown conditions
	select {
	case <-p.ctx.Done():
		Logger.Info("Player session ending due to context cancellation", "player", p.id)
		return
	case err := <-p.playerError:
		if err != nil {
			Logger.Error("Player error", "player_name", p.id, "error", err)
		}
		return
	case err := <-requestDone:
		if err != nil && err != context.Canceled {
			Logger.Error("Request handler error", "player", p.id, "error", err)
		}
		return
	case err := <-inputDone:
		if err != nil && err != context.Canceled {
			Logger.Error("Input handler error", "player", p.id, "error", err)
		}
		return
	case err := <-outputDone:
		if err != nil && err != context.Canceled {
			Logger.Error("Output handler error", "player", p.id, "error", err)
		}
		return
	}
}

func (p *Player) Stop() {
	p.shutdownOnce.Do(func() {
		Logger.Info("Player disconnected", "player_name", p.id)

		// First cancel the context to signal all goroutines to exit
		p.cancel()

		// Save player data
		p.Save()

		// Close the connection
		if p.connection != nil {
			p.connection.Close()
		}

		// Remove from server
		if p.server != nil {
			_ = p.server.RemovePlayer(p.index)
		}

		time.Sleep(100 * time.Millisecond)

		close(p.toPlayer)
		close(p.fromPlayer)
		close(p.playerError)

		Logger.Info("Player stopped", "player_name", p.id)
	})
}

func (p *Player) handleRequests(ctx context.Context, requests <-chan *ssh.Request, done chan error) {
	defer func() {
		if r := recover(); r != nil {
			Logger.Warn("Recovered in handleRequests", "player", p.id, "recover", r)
			done <- fmt.Errorf("panic in request handler: %v", r)
		}
	}()

	for {
		select {
		case <-ctx.Done():
			done <- ctx.Err()
			return
		case req, ok := <-requests:
			if !ok {
				Logger.Debug("Request channel closed", "player", p.id)
				done <- nil
				return
			}

			p.mutex.Lock()
			switch req.Type {
			case "shell":
				req.Reply(true, nil)
			case "pty-req":
				termLen := req.Payload[3]
				w, h := ParseDims(req.Payload[termLen+4:])
				p.consoleWidth = w
				p.consoleHeight = h
				req.Reply(true, nil)
			case "window-change":
				w, h := ParseDims(req.Payload)
				p.consoleWidth = w
				p.consoleHeight = h
			default:
				req.Reply(false, nil)
			}
			p.mutex.Unlock()
		}
	}
}

func (p *Player) handleInput(ctx context.Context, done chan error) {
	defer func() {
		if r := recover(); r != nil {
			Logger.Warn("Recovered in handleInput", "player", p.id, "recover", r)
			done <- fmt.Errorf("panic in input handler: %v", r)
		}
	}()

	var inputBuffer []rune
	reader := bufio.NewReader(p.connection)

	for {
		select {
		case <-ctx.Done():
			done <- ctx.Err()
			return
		default:
			r, _, err := reader.ReadRune()
			if err != nil {
				if err == io.EOF {
					Logger.Info("Connection closed by client", "player", p.id)
					done <- nil
					return
				}
				Logger.Error("Error reading input", "player", p.id, "error", err)
				done <- fmt.Errorf("read error: %w", err)
				return
			}

			// Handle different input cases
			switch r {
			case '\n', '\r':
				if len(inputBuffer) > 0 {
					select {
					case p.fromPlayer <- string(inputBuffer):
						if p.echo {
							p.connection.Write([]byte("\r\n"))
							p.connection.Write([]byte(p.prompt))
						}
						inputBuffer = inputBuffer[:0]
					case <-ctx.Done():
						done <- ctx.Err()
						return
					}
				}

			case '\b', 127: // Backspace
				if len(inputBuffer) > 0 {
					inputBuffer = inputBuffer[:len(inputBuffer)-1]
					if p.echo {
						p.connection.Write([]byte("\b \b"))
					}
				}

			case '\x03': // Ctrl-C
				done <- errors.New("player interrupt")
				return

			default:
				if len(inputBuffer) < 1024 {
					inputBuffer = append(inputBuffer, r)
					if p.echo {
						p.connection.Write([]byte(string(r)))
					}
				}
			}
		}
	}
}

func (p *Player) handleOutput(ctx context.Context, done chan error) {
	defer func() {
		if r := recover(); r != nil {
			Logger.Warn("Recovered in handleOutput", "player", p.id, "recover", r)
			done <- fmt.Errorf("panic in output handler: %v", r)
		}
	}()

	for {
		select {
		case <-ctx.Done():
			done <- ctx.Err()
			return
		case msg, ok := <-p.toPlayer:
			if !ok {
				Logger.Debug("Output channel closed", "player", p.id)
				done <- nil
				return
			}

			if _, err := p.connection.Write([]byte(wrapText(msg, p.consoleWidth))); err != nil {
				Logger.Error("Write error in output handler", "player", p.id, "error", err)
				done <- fmt.Errorf("write error: %w", err)
				return
			}
		}
	}
}

// wrapText wraps the given text to the specified width, preserving
// empty lines and whitespace. It uses \r\n as the line break.
func wrapText(text string, width int) string {
	var result strings.Builder

	// Split the text into lines
	lines := strings.Split(text, "\n")

	for i, line := range lines {
		// Preserve empty lines
		if len(strings.TrimSpace(line)) == 0 {
			result.WriteString(line)
			if i < len(lines)-1 {
				result.WriteString("\r\n")
			}
			continue
		}

		// Wrap the line to the specified width
		for len(line) > 0 {
			if len(line) <= width {
				result.WriteString(line)
				break
			}

			// Find the last space within the width
			lastSpace := strings.LastIndex(line[:width+1], " ")
			if lastSpace == -1 {
				// No space found, force break at width
				result.WriteString(line[:width])
				line = line[width:]
			} else {
				// Break at the last space
				result.WriteString(line[:lastSpace])
				line = strings.TrimLeft(line[lastSpace+1:], " ")
			}

			result.WriteString("\r\n")
		}

		// Add newline between original lines if not the last line
		if i < len(lines)-1 {
			result.WriteString("\r\n")
		}
	}

	return result.String()
}
