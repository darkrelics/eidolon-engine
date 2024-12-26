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
	index         uint64
	playerID      string
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
	server        *Server
	mutex         sync.RWMutex
	interfaceCtx  context.Context
	ctx           context.Context
	cancel        context.CancelFunc
	shutdownOnce  sync.Once
}

type PlayerData struct {
	PlayerID      string            `json:"PlayerID" dynamodbav:"PlayerID"`
	CharacterList map[string]string `json:"characterList" dynamodbav:"CharacterList"`
	SeenMotDs     []string          `json:"seenMotD" dynamodbav:"SeenMotD"`
}

func NewPlayer(server *Server, playerName string, conn ssh.Channel, interfaceCtx context.Context) (*Player, error) {
	playerCtx, playerCancel := context.WithCancel(context.Background())

	player := &Player{
		server:        server,
		interfaceCtx:  interfaceCtx,
		playerID:      playerName,
		toPlayer:      make(chan string, 10),
		fromPlayer:    make(chan string, 10),
		playerError:   make(chan error, 1),
		echo:          true,
		connection:    conn,
		consoleWidth:  80,
		consoleHeight: 24,
		login:         time.Now(),
		ctx:           playerCtx,
		cancel:        playerCancel,
	}

	// Load player data
	if err := player.loadData(); err != nil {
		playerCancel()
		return nil, fmt.Errorf("player data load: %w", err)
	}

	// Register with server
	id, err := server.AddPlayer(player)
	if err != nil {
		playerCancel()
		return nil, fmt.Errorf("server registration: %w", err)
	}
	player.index = id

	return player, nil
}

func (p *Player) Run(requests <-chan *ssh.Request) {
	Logger.Info("starting player session", "player", p.playerID)
	defer p.Stop()

	// Create channels for each goroutine
	requestDone := make(chan error, 1)
	inputDone := make(chan error, 1)
	outputDone := make(chan error, 1)

	// Start request handler
	go func() {
		requestDone <- p.handleRequests(p.ctx, requests)
	}()

	// Start input handler
	go func() {
		inputDone <- p.handleInput(p.ctx)
	}()

	// Start output handler
	go func() {
		outputDone <- p.handleOutput(p.ctx)
	}()

	// Display MOTDs
	if err := DisplayUnseenMOTDs(p); err != nil {
		Logger.Error("motd display error", "player", p.playerID, "error", err)
		return
	}

	// Character selection loop
	for {
		character, err := SelectCharacter(p.ctx, p)
		if err != nil {
			Logger.Error("character selection error", "player", p.playerID, "error", err)
			return
		}

		p.character = character
		charDone := make(chan error, 1)
		go func() {
			charDone <- character.Run()
		}()

		select {
		case <-p.ctx.Done():
			Logger.Info("player session ended", "player", p.playerID)
			return
		case <-p.interfaceCtx.Done():
			return
		case <-p.server.context.Done():
			return
		case <-p.server.globalContext.Done():
			return
		case err := <-requestDone:
			Logger.Error("ssh request handler error", "player", p.playerID, "error", err)
			return
		case err := <-inputDone:
			Logger.Error("input handler error", "player", p.playerID, "error", err)
			return
		case err := <-outputDone:
			Logger.Error("output handler error", "player", p.playerID, "error", err)
			return
		case err := <-charDone:
			if err != nil {
				Logger.Error("character error", "player", p.playerID, "error", err)
				return
			}
			p.character = nil
			continue
		}
	}
}

func (p *Player) Stop() error {
	var stopErr error
	p.shutdownOnce.Do(func() {
		p.cancel()

		if p.character != nil {
			if err := p.character.Stop(); err != nil {
				Logger.Error("character stop error", "playerID", p.playerID, "error", err)
				stopErr = err
				return
			}
		}

		p.saveData()

		if p.connection != nil {
			p.connection.Close()
		}

		close(p.toPlayer)
		close(p.fromPlayer)
		close(p.playerError)

		if p.server != nil {
			_ = p.server.RemovePlayer(p.index)
		}

		Logger.Info("player stopped", "playerID", p.playerID)
	})
	return stopErr
}

func (p *Player) handleRequests(ctx context.Context, requests <-chan *ssh.Request) error {
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case req, ok := <-requests:
			if !ok {
				return nil
			}
			p.processRequest(req)
		}
	}
}

func (p *Player) handleInput(ctx context.Context) error {
	var inputBuffer []rune
	reader := bufio.NewReader(p.connection)

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
			r, _, err := reader.ReadRune()
			if err != nil {
				if err == io.EOF {
					return nil
				}
				return fmt.Errorf("read error: %w", err)
			}

			if !p.processInput(r, &inputBuffer) {
				return nil
			}
		}
	}
}

func (p *Player) handleOutput(ctx context.Context) error {
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case msg, ok := <-p.toPlayer:
			if !ok {
				return nil
			}
			if _, err := p.connection.Write([]byte(wrapText(msg, p.consoleWidth))); err != nil {
				return fmt.Errorf("write error: %w", err)
			}
		}
	}
}

func (p *Player) processRequest(req *ssh.Request) {
	p.mutex.Lock()
	defer p.mutex.Unlock()

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
}

func (p *Player) processInput(r rune, buffer *[]rune) bool {
	switch r {
	case '\n', '\r':
		if len(*buffer) > 0 {
			select {
			case p.fromPlayer <- string(*buffer):
				if p.echo {
					p.connection.Write([]byte("\r\n"))
					p.connection.Write([]byte(p.prompt))
				}
				*buffer = (*buffer)[:0]
			case <-p.ctx.Done():
				return false
			}
		}

	case '\b', 127: // Backspace
		if len(*buffer) > 0 {
			*buffer = (*buffer)[:len(*buffer)-1]
			if p.echo {
				p.connection.Write([]byte("\b \b"))
			}
		}

	case '\x03': // Ctrl-C
		p.playerError <- errors.New("player interrupt")
		return false

	default:
		if len(*buffer) < 1024 {
			*buffer = append(*buffer, r)
			if p.echo {
				p.connection.Write([]byte(string(r)))
			}
		}
	}
	return true
}

func (p *Player) loadData() error {
	_, charList, motd, err := p.ReadPlayer(p.playerID)
	if err != nil {
		if err.Error() == "player not found" {
			return nil
		}
		return fmt.Errorf("database read: %w", err)
	}

	p.mutex.Lock()
	p.characterList = charList
	p.seenMotD = motd
	p.mutex.Unlock()

	return nil
}

func (p *Player) saveData() error {
	if err := p.WritePlayer(); err != nil {
		Logger.Error("failed to save player data", "playerID", p.playerID, "error", err)
		return fmt.Errorf("database write: %w", err)
	}
	return nil
}

// WritePlayer stores the player data into the DynamoDB database.
func (p *Player) WritePlayer() error {

	k := p.server.database

	pd := PlayerData{
		PlayerID:      p.playerID,
		CharacterList: make(map[string]string),
		SeenMotDs:     make([]string, len(p.seenMotD)),
	}

	// Convert UUIDs to strings for CharacterList
	for charName, charID := range p.characterList {
		pd.CharacterList[charName] = charID.String()
	}

	// Convert UUIDs to strings for SeenMotDs
	for i, motdID := range p.seenMotD {
		pd.SeenMotDs[i] = motdID.String()
	}

	// Write the player data to the DynamoDB table with proper error handling
	err := k.Put("players", pd)
	if err != nil {
		Logger.Error("Error storing player data", "playerName", p.playerID, "error", err)
		return fmt.Errorf("error storing player data: %w", err)
	}

	Logger.Debug("Successfully wrote player data", "playerName", p.playerID, "characterCount", len(p.characterList), "seenMotDCount", len(p.seenMotD))
	return nil
}

// ReadPlayer retrieves the player data from the DynamoDB database.
func (p *Player) ReadPlayer(playerName string) (string, map[string]uuid.UUID, []uuid.UUID, error) {
	Logger.Debug("Reading player data from database", "playerName", playerName)

	k := p.server.database

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
