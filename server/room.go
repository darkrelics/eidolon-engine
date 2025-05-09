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
	"context"
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
)

// CommandTier represents the level at which a command will be processed
type CommandTier int

const (
	// CharacterTier commands are processed by the character immediately
	CharacterTier CommandTier = iota
	// RoomTier commands are processed by the room
	RoomTier
	// GameTier commands are processed by the game
	GameTier
)

// CommandState represents the current state of a command
type CommandState int

const (
	// CommandPending indicates the command is waiting to be processed
	CommandPending CommandState = iota
	// CommandProcessing indicates the command is being processed
	CommandProcessing
	// CommandCompleted indicates the command has completed successfully
	CommandCompleted
	// CommandFailed indicates the command failed
	CommandFailed
	// CommandRejected indicates the command was rejected
	CommandRejected
)

// CommandRequest encapsulates a command request sent between components
type CommandRequest struct {
	ID        uuid.UUID             // Unique ID for the command
	Character *Character            // Character issuing the command
	Verb      string                // Command verb
	Args      []string              // Command arguments
	Tier      CommandTier           // Which tier should process this command
	State     CommandState          // Current state of the command
	Timestamp time.Time             // When the command was created
	Response  chan *CommandResponse // Channel for direct response
}

// CommandResponse encapsulates a response to a command
type CommandResponse struct {
	RequestID uuid.UUID // ID of the original request
	Success   bool      // Whether the command succeeded
	Message   string    // Response message
	Error     error     // Error, if any
	Timestamp time.Time // When the response was created
}

// Room represents the in-memory structure for a room
type Room struct {
	roomID         int64
	area           string
	title          string
	description    string
	exits          map[uuid.UUID]*Exit
	characters     map[uuid.UUID]*Character
	items          map[uuid.UUID]*Item
	persistent     bool   // Flag indicating if room should remain loaded when empty
	scriptID       string // ID of the script that defines room-specific behaviors
	mutex          sync.RWMutex
	lastEdited     time.Time
	lastSaved      time.Time
	lastActive     time.Time             // Timestamp of last activity in the room
	ctx            context.Context       // Context for room goroutine lifecycle
	cancel         context.CancelFunc    // Cancel function for room context
	running        bool                  // Flag indicating if room goroutine is running
	commandIn      chan *CommandRequest  // Channel for commands sent to the room
	commandOut     chan *CommandResponse // Channel for responses from the room
	gameCommandOut chan *CommandRequest  // Channel for commands the room escalates to the game
	gameCommandIn  chan *CommandResponse // Channel for responses from the game to the room
}

// RoomData represents the structure for storing room data in DynamoDB
type RoomData struct {
	RoomID      int64    `json:"roomID" dynamodbav:"RoomID"`
	Area        string   `json:"area" dynamodbav:"Area"`
	Title       string   `json:"title" dynamodbav:"Title"`
	Description string   `json:"description" dynamodbav:"Description"`
	ExitIDs     []string `json:"exitID" dynamodbav:"ExitID"`
	ItemIDs     []string `json:"itemID" dynamodbav:"ItemID"`
	Persistent  bool     `json:"persistent" dynamodbav:"Persistent"`
	ScriptID    string   `json:"scriptID" dynamodbav:"ScriptID"`
}

// Exit represents the in-memory structure for an exit
type Exit struct {
	exitID      uuid.UUID
	direction   string
	description string
	targetRoom  *Room
	visible     bool
	lastEdited  time.Time
	lastSaved   time.Time
}

// ExitData represents the structure for storing exit data in DynamoDB
type ExitData struct {
	ExitID      string `json:"ExitID" dynamodbav:"ExitID"`
	Direction   string `json:"Direction" dynamodbav:"Direction"`
	Description string `json:"Description" dynamodbav:"Description"`
	TargetRoom  int64  `json:"TargetRoom" dynamodbav:"TargetRoom"`
	Visible     bool   `json:"Visible" dynamodbav:"Visible"`
}

// Initialize a new room

func NewRoom(ctx context.Context, roomID int64, area, title, description string, persistent bool, scriptID string) *Room {

	Logger.Info("New Room...Initalizing Room...", "roomID", roomID, "persistent", persistent, "scriptID", scriptID)

	now := time.Now()

	// Create a new context for the room, which will be canceled when the room is stopped
	roomCtx, cancel := context.WithCancel(ctx)

	return &Room{
		roomID:         roomID,
		area:           area,
		title:          title,
		description:    description,
		exits:          make(map[uuid.UUID]*Exit),
		characters:     make(map[uuid.UUID]*Character),
		items:          make(map[uuid.UUID]*Item),
		persistent:     persistent,
		scriptID:       scriptID,
		mutex:          sync.RWMutex{},
		lastEdited:     now,
		lastSaved:      now,
		lastActive:     now,
		ctx:            roomCtx,
		cancel:         cancel,
		running:        false,
		commandIn:      make(chan *CommandRequest, 50),  // Buffer for incoming commands
		commandOut:     make(chan *CommandResponse, 50), // Buffer for outgoing responses
		gameCommandOut: make(chan *CommandRequest, 10),  // Buffer for commands to game
		gameCommandIn:  make(chan *CommandResponse, 10), // Buffer for responses from game
	}
}

// Initialize a new exit

func NewExit(exitID uuid.UUID, direction string, description string, targetRoom *Room, visible bool) *Exit {

	Logger.Info("New Exit...Initalizing Exit...")

	return &Exit{
		exitID:      exitID,
		direction:   direction,
		description: description,
		targetRoom:  targetRoom,
		visible:     visible,
		lastEdited:  time.Now(),
		lastSaved:   time.Now(),
	}
}

// Load exit data from DynamoDB

func (g *Game) LoadExits() error {

	Logger.Info("Load Exits...Loading Exits...")

	var exitsData []ExitData

	err := g.database.Scan("exits", &exitsData)
	if err != nil {
		Logger.Error("Error scanning exits table", "error", err)
		return nil
	}

	for _, exitData := range exitsData {
		exitID, err := uuid.Parse(exitData.ExitID)
		if err != nil {
			Logger.Warn("Error parsing exit ID", "error", err)
		}

		g.exits[exitID] = NewExit(exitID, exitData.Direction, exitData.Description, g.rooms[exitData.TargetRoom], exitData.Visible)
	}

	return nil
}

// Load room data from DynamoDB

func (g *Game) LoadRooms() error {

	Logger.Info("Load Rooms...Loading Rooms...")

	// Load room data from DynamoDB
	var roomsData []RoomData
	err := g.database.Scan("rooms", &roomsData)
	if err != nil {
		Logger.Error("Error scanning rooms table", "error", err)
		return fmt.Errorf("error scanning rooms: %w", err)
	}

	// Populate all rooms

	for _, roomData := range roomsData {
		g.rooms[roomData.RoomID] = NewRoom(
			g.ctx,
			roomData.RoomID,
			roomData.Area,
			roomData.Title,
			roomData.Description,
			roomData.Persistent,
			roomData.ScriptID,
		)
	}

	// Load exit data

	err = g.LoadExits()
	if err != nil {
		Logger.Warn("Error loading exits", "error", err)
	}

	// Assocate exits with rooms

	for _, roomData := range roomsData {
		for _, exitID := range roomData.ExitIDs {
			exitUUID, err := uuid.Parse(exitID)
			if err != nil {
				Logger.Warn("Error parsing exit ID", "error", err)
				continue
			}
			g.rooms[roomData.RoomID].exits[exitUUID] = g.exits[exitUUID]
		}
	}

	// Load item data

	return nil

}

// UpdateActivity updates the lastActive timestamp for a room
func (r *Room) UpdateActivity() {
	r.mutex.Lock()
	defer r.mutex.Unlock()

	r.lastActive = time.Now()
	r.lastEdited = r.lastActive
}

// IsIdle checks if a room has been idle for the specified duration
func (r *Room) IsIdle(duration time.Duration) bool {
	r.mutex.RLock()
	defer r.mutex.RUnlock()

	return len(r.characters) == 0 && time.Since(r.lastActive) > duration
}

// GetScriptID returns the script ID for the room
func (r *Room) GetScriptID() string {
	r.mutex.RLock()
	defer r.mutex.RUnlock()

	return r.scriptID
}

// SendRoomMessageExcept sends a message to all characters in a room except one
func SendRoomMessageExcept(room *Room, message string, except *Character) {
	if room == nil {
		return
	}

	// Update room activity before acquiring lock to avoid concurrency issues
	room.UpdateActivity()

	room.mutex.RLock()
	defer room.mutex.RUnlock()

	for _, c := range room.characters {
		if c != nil && c != except && c.player != nil {
			select {
			case c.player.commandOut <- message:
				// After sending room message, send the prompt again to ensure consistent UI
				select {
				case c.player.commandOut <- c.prompt:
					// Prompt sent successfully
				default:
					Logger.Warn("Failed to send prompt after room message to player",
						"recipient", c.name)
				}
			default:
				Logger.Warn("Failed to send room message to player",
					"recipient", c.name,
					"message", message)
			}
		}
	}
}

// Start begins the room goroutine to process room-level commands
func (r *Room) Start(game *Game) {
	r.mutex.Lock()
	defer r.mutex.Unlock()

	if r.running {
		Logger.Warn("Attempted to start an already running room", "roomID", r.roomID)
		return
	}

	Logger.Info("Starting room goroutine", "roomID", r.roomID, "title", r.title)
	r.running = true

	// Start the room goroutine
	go r.run(game)
}

// Stop signals the room goroutine to shut down
func (r *Room) Stop() {
	r.mutex.Lock()
	defer r.mutex.Unlock()

	if !r.running {
		Logger.Warn("Attempted to stop a room that is not running", "roomID", r.roomID)
		return
	}

	Logger.Info("Stopping room goroutine", "roomID", r.roomID, "title", r.title)

	// Cancel the room's context to signal all operations to stop
	r.cancel()
	r.running = false

	// Close channels (deferred until after context cancelation to prevent race conditions)
	close(r.commandIn)
	close(r.commandOut)
	// Note: we don't close gameCommandOut as it belongs to the Game
}

// run is the main goroutine function for a room
func (r *Room) run(game *Game) {
	Logger.Info("Room goroutine started", "roomID", r.roomID, "title", r.title)

	// Set up idle room detection timer
	idleCheckInterval := 1 * time.Minute
	idleTimer := time.NewTicker(idleCheckInterval)
	defer idleTimer.Stop()

	// Room processing loop
	for {
		select {
		case <-r.ctx.Done():
			// Context was canceled, shut down the room
			Logger.Info("Room context canceled, shutting down", "roomID", r.roomID)
			return

		case cmd, ok := <-r.commandIn:
			// Handle incoming command requests
			if !ok {
				Logger.Warn("Room command channel closed unexpectedly", "roomID", r.roomID)
				return
			}

			// Process the command
			r.processCommand(cmd, game)

		case <-idleTimer.C:
			// Check if the room is idle (empty and non-persistent)
			if !r.persistent && r.IsIdle(10*time.Minute) {
				Logger.Info("Room has been idle, shutting down", "roomID", r.roomID, "title", r.title)
				r.Stop()
				return
			}
		}
	}
}

// processCommand handles a command request in the room
func (r *Room) processCommand(cmd *CommandRequest, game *Game) {
	if cmd == nil {
		Logger.Error("Received nil command request", "roomID", r.roomID)
		return
	}

	Logger.Debug("Processing room command", "roomID", r.roomID, "verb", cmd.Verb, "gameState", game.characterCount.Load())

	// Update the command state
	cmd.State = CommandProcessing

	// Update room activity timestamp
	r.UpdateActivity()

	// Handle command based on its type
	switch cmd.Tier {
	case RoomTier:
		// Process room-level command
		r.handleRoomCommand(cmd)

	case GameTier:
		// Forward command to game tier
		Logger.Debug("Escalating command to game tier", "roomID", r.roomID, "verb", cmd.Verb)

		// Set the game reference for possible callbacks
		cmd.Character.game = game

		select {
		case r.gameCommandOut <- cmd:
			// Successfully forwarded
		default:
			// Channel full or closed, return error
			response := &CommandResponse{
				RequestID: cmd.ID,
				Success:   false,
				Error:     fmt.Errorf("unable to forward command to game: channel full or closed"),
				Timestamp: time.Now(),
			}
			r.sendCommandResponse(cmd, response)
		}

	default:
		// Invalid tier for room processing
		Logger.Warn("Room received command with invalid tier", "roomID", r.roomID, "verb", cmd.Verb, "tier", cmd.Tier)
		response := &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("invalid command tier for room processing"),
			Timestamp: time.Now(),
		}
		r.sendCommandResponse(cmd, response)
	}
}

// handleRoomCommand processes room-level commands
func (r *Room) handleRoomCommand(cmd *CommandRequest) {
	// Handle different room commands based on verb
	var response *CommandResponse

	switch cmd.Verb {
	case "say", "talk":
		// Handle in-room chat
		response = r.handleSayCommand(cmd)
	case "emote", "me":
		// Handle emotes
		response = r.handleEmoteCommand(cmd)
	case "look":
		// Handle looking at room or objects in room
		response = r.handleLookCommand(cmd)
	case "whisper":
		// Handle private communication in room
		response = r.handleWhisperCommand(cmd)
	case "get", "take", "drop", "put":
		// Handle item manipulation
		response = r.handleItemCommand(cmd)
	case "north", "south", "east", "west", "up", "down", "go":
		// Handle movement
		response = r.handleMovementCommand(cmd)
	default:
		// Command not recognized at room level
		response = &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("command not recognized at room level: %s", cmd.Verb),
			Timestamp: time.Now(),
		}
	}

	// Send the response
	r.sendCommandResponse(cmd, response)
}

// handleSayCommand processes the "say" command
func (r *Room) handleSayCommand(cmd *CommandRequest) *CommandResponse {
	// Check if there's a message to say
	if len(cmd.Args) < 2 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("what do you want to say?"),
			Timestamp: time.Now(),
		}
	}

	// Extract the message
	message := strings.Join(cmd.Args[1:], " ")

	// Format the message for the speaker and others
	selfMsg := fmt.Sprintf("\n\rYou say: %s\n\r", message)
	othersMsg := fmt.Sprintf("\n\r%s says: %s\n\r", cmd.Character.name, message)

	// Send to everyone in the room except the speaker
	for _, c := range r.characters {
		if c != nil && c != cmd.Character && c.player != nil {
			select {
			case c.player.commandOut <- othersMsg:
				// Message sent successfully
				select {
				case c.player.commandOut <- c.prompt:
					// Prompt sent successfully
				default:
					Logger.Warn("Failed to send prompt after say command", "recipient", c.name)
				}
			default:
				Logger.Warn("Failed to send say message to player",
					"recipient", c.name,
					"speaker", cmd.Character.name)
			}
		}
	}

	// Return the message for the speaker
	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   selfMsg,
		Timestamp: time.Now(),
	}
}

// handleEmoteCommand processes the "emote" command
func (r *Room) handleEmoteCommand(cmd *CommandRequest) *CommandResponse {
	// Check if there's an emote to perform
	if len(cmd.Args) < 2 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("what do you want to do?"),
			Timestamp: time.Now(),
		}
	}

	// Extract the emote action
	action := strings.Join(cmd.Args[1:], " ")

	// Format the emote message
	emoteMsg := fmt.Sprintf("\n\r%s %s\n\r", cmd.Character.name, action)

	// Send to everyone in the room including the actor
	for _, c := range r.characters {
		if c != nil && c != cmd.Character && c.player != nil {
			select {
			case c.player.commandOut <- emoteMsg:
				// Message sent successfully
				select {
				case c.player.commandOut <- c.prompt:
					// Prompt sent successfully
				default:
					Logger.Warn("Failed to send prompt after emote", "recipient", c.name)
				}
			default:
				Logger.Warn("Failed to send emote to player",
					"recipient", c.name,
					"actor", cmd.Character.name)
			}
		}
	}

	// Return the message for the actor
	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   emoteMsg,
		Timestamp: time.Now(),
	}
}

// handleLookCommand processes the "look" command within the room
func (r *Room) handleLookCommand(cmd *CommandRequest) *CommandResponse {
	// Format depends on whether looking at room or specific object
	var lookMsg string

	if len(cmd.Args) < 2 {
		// Looking at the room itself
		r.mutex.RLock()
		lookMsg = fmt.Sprintf("\n\r[%s]\n\r%s\n\r", r.title, r.description)

		// Add exits
		var exits []string
		for _, exit := range r.exits {
			if exit != nil && exit.visible {
				exits = append(exits, exit.direction)
			}
		}

		if len(exits) == 0 {
			lookMsg += "There are no visible exits.\n\r"
		} else {
			sort.Strings(exits)
			lookMsg += "Obvious exits: " + strings.Join(exits, ", ") + "\n\r"
		}

		// Add characters
		var chars []string
		for _, c := range r.characters {
			if c != nil && c != cmd.Character {
				chars = append(chars, c.name)
			}
		}

		if len(chars) == 0 {
			lookMsg += "You are alone.\n\r"
		} else {
			lookMsg += "Also here: " + strings.Join(chars, ", ") + "\n\r"
		}

		// Add items
		var items []string
		for _, item := range r.items {
			if item != nil {
				items = append(items, item.name)
			}
		}

		if len(items) > 0 {
			lookMsg += "Items in the room:\n\r"
			for _, item := range items {
				lookMsg += fmt.Sprintf("- %s\n\r", item)
			}
		}
		r.mutex.RUnlock()
	} else {
		// Looking at a specific object in the room
		target := strings.ToLower(strings.Join(cmd.Args[1:], " "))

		// Check for special targets
		switch target {
		case "room", "here":
			// Recursive call to look at the room
			return r.handleLookCommand(&CommandRequest{
				ID:        cmd.ID,
				Character: cmd.Character,
				Verb:      "look",
				Args:      []string{"look"},
				Response:  cmd.Response,
			})
		case "self", "me", "myself":
			// Look at self
			lookMsg = fmt.Sprintf("\n\rYou see yourself, %s.\n\r", cmd.Character.name)
		default:
			// Look for a character in the room
			r.mutex.RLock()
			foundTarget := false

			// Check characters
			for _, c := range r.characters {
				if c != nil && strings.Contains(strings.ToLower(c.name), target) {
					if c == cmd.Character {
						lookMsg = fmt.Sprintf("\n\rYou see yourself, %s.\n\r", cmd.Character.name)
					} else {
						lookMsg = fmt.Sprintf("\n\r%s is here.\n\r", c.name)
					}
					foundTarget = true
					break
				}
			}

			// Check exits if no character found
			if !foundTarget {
				for _, exit := range r.exits {
					if exit != nil && exit.visible && strings.Contains(strings.ToLower(exit.direction), target) {
						if exit.description != "" {
							lookMsg = fmt.Sprintf("\n\r%s\n\r", exit.description)
						} else {
							lookMsg = fmt.Sprintf("\n\rYou see an exit leading %s.\n\r", exit.direction)
						}
						foundTarget = true
						break
					}
				}
			}

			// Check items if still not found
			if !foundTarget {
				for _, item := range r.items {
					if item != nil && strings.Contains(strings.ToLower(item.name), target) {
						lookMsg = fmt.Sprintf("\n\rYou see %s.\n\r", item.name)
						if item.description != "" {
							lookMsg += item.description + "\n\r"
						}
						foundTarget = true
						break
					}
				}
			}
			r.mutex.RUnlock()

			// If nothing found
			if !foundTarget {
				lookMsg = fmt.Sprintf("\n\rYou don't see '%s' here.\n\r", target)
			}
		}
	}

	// Update room activity timestamp
	r.UpdateActivity()

	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   lookMsg,
		Timestamp: time.Now(),
	}
}

// handleWhisperCommand processes the "whisper" command
func (r *Room) handleWhisperCommand(cmd *CommandRequest) *CommandResponse {
	// Check for valid arguments: whisper <target> <message>
	if len(cmd.Args) < 3 {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("whisper to whom what?"),
			Timestamp: time.Now(),
		}
	}

	// Get target name and message
	targetName := cmd.Args[1]
	message := strings.Join(cmd.Args[2:], " ")

	// Find the target character in the room
	r.mutex.RLock()
	var targetChar *Character
	for _, c := range r.characters {
		if c != nil && strings.HasPrefix(strings.ToLower(c.name), strings.ToLower(targetName)) {
			targetChar = c
			break
		}
	}
	r.mutex.RUnlock()

	// Check if target was found
	if targetChar == nil {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you don't see %s here", targetName),
			Timestamp: time.Now(),
		}
	}

	// Cannot whisper to yourself
	if targetChar == cmd.Character {
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("you can't whisper to yourself"),
			Timestamp: time.Now(),
		}
	}

	// Format messages
	senderMsg := fmt.Sprintf("\n\rYou whisper to %s: %s\n\r", targetChar.name, message)
	targetMsg := fmt.Sprintf("\n\r%s whispers to you: %s\n\r", cmd.Character.name, message)
	othersMsg := fmt.Sprintf("\n\r%s whispers something to %s.\n\r", cmd.Character.name, targetChar.name)

	// Send to target
	if targetChar.player != nil {
		select {
		case targetChar.player.commandOut <- targetMsg:
			// Message sent successfully
			select {
			case targetChar.player.commandOut <- targetChar.prompt:
				// Prompt sent successfully
			default:
				Logger.Warn("Failed to send prompt after whisper", "recipient", targetChar.name)
			}
		default:
			Logger.Warn("Failed to send whisper to target",
				"recipient", targetChar.name,
				"sender", cmd.Character.name)
		}
	}

	// Send message to others in the room (they just see that whispering happened)
	r.mutex.RLock()
	for _, c := range r.characters {
		if c != nil && c != cmd.Character && c != targetChar && c.player != nil {
			select {
			case c.player.commandOut <- othersMsg:
				// Message sent successfully
				select {
				case c.player.commandOut <- c.prompt:
					// Prompt sent successfully
				default:
					Logger.Warn("Failed to send prompt after whisper notification", "recipient", c.name)
				}
			default:
				// Not critical if others don't see the notification
			}
		}
	}
	r.mutex.RUnlock()

	// Return message to sender
	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   true,
		Message:   senderMsg,
		Timestamp: time.Now(),
	}
}

// handleItemCommand processes item-related commands like get, take, drop, etc.
func (r *Room) handleItemCommand(cmd *CommandRequest) *CommandResponse {
	// This is a placeholder. Real implementation would handle items
	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   false,
		Error:     fmt.Errorf("item commands are not implemented yet"),
		Timestamp: time.Now(),
	}
}

// handleMovementCommand processes room movement commands
func (r *Room) handleMovementCommand(cmd *CommandRequest) *CommandResponse {
	// This is a placeholder. Real implementation would handle movement
	return &CommandResponse{
		RequestID: cmd.ID,
		Success:   false,
		Error:     fmt.Errorf("movement commands are not implemented yet"),
		Timestamp: time.Now(),
	}
}

// sendCommandResponse sends a response to a command
func (r *Room) sendCommandResponse(cmd *CommandRequest, response *CommandResponse) {
	if cmd.Response != nil {
		// Send direct response if channel provided
		select {
		case cmd.Response <- response:
			// Response sent successfully
		default:
			Logger.Warn("Failed to send direct command response", "roomID", r.roomID, "commandID", cmd.ID)
		}
	} else {
		// Send to commandOut channel
		select {
		case r.commandOut <- response:
			// Response sent to commandOut channel
		default:
			Logger.Warn("Failed to send command response to commandOut channel", "roomID", r.roomID, "commandID", cmd.ID)
		}
	}
}
