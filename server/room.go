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
	idleCounter    int                   // Counter for tracking idle time (increments per game tick)
	scriptActive   bool                  // Flag indicating if room scripts are currently active
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
		idleCounter:    0,
		scriptActive:   scriptID != "", // Initialize script as active if a script is assigned
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

// HandleCharacterEntry handles character entering a room, resets idle counter and activates scripts
func (r *Room) HandleCharacterEntry() {
	r.mutex.Lock()
	defer r.mutex.Unlock()

	// Reset idle counter
	r.idleCounter = 0

	// For persistent rooms with scripts assigned, activate scripts
	if r.persistent && r.scriptID != "" && !r.scriptActive {
		r.scriptActive = true
		Logger.Info("Activating scripts for persistent room with character entry", "roomID", r.roomID)
	}
}

// IncrementIdleCounter increments the idle counter for an empty room and handles cleanup if threshold is reached
func (r *Room) IncrementIdleCounter(game *Game) {
	r.mutex.Lock()
	defer r.mutex.Unlock()

	// Only increment if room is empty
	if len(r.characters) > 0 {
		// Reset counter if characters are present
		r.idleCounter = 0
		return
	}

	// Increment the idle counter
	r.idleCounter++

	// Check if idle threshold has been reached (600 ticks = 10 minutes @ 1 second per tick)
	if r.idleCounter >= 600 {
		Logger.Info("Room idle threshold reached", "roomID", r.roomID, "title", r.title, "persistent", r.persistent)

		// Clean up items in the room
		r.cleanupItems(game)

		// For persistent rooms, deactivate scripts but keep room loaded
		if r.persistent {
			r.scriptActive = false
			Logger.Info("Deactivating scripts for idle persistent room", "roomID", r.roomID)
		} else {
			// For non-persistent rooms, unload the room
			Logger.Info("Unloading non-persistent idle room", "roomID", r.roomID)

			// We must unlock mutex before calling Stop to avoid deadlock
			r.mutex.Unlock()
			r.Stop()
			r.mutex.Lock() // Re-lock for the remainder of the function

			// Remove room from game's room map
			delete(game.rooms, r.roomID)
		}
	}
}

// cleanupItems removes items that are marked for deletion from the room
func (r *Room) cleanupItems(game *Game) {
	itemCount := len(r.items)

	// Create temporary list of items to remove
	var itemsToRemove []uuid.UUID

	for id, item := range r.items {
		if item != nil && item.markedForDeletion {
			itemsToRemove = append(itemsToRemove, id)
		}
	}

	// Remove the items
	for _, id := range itemsToRemove {
		delete(r.items, id)
		// Also remove from game's items map if needed
		delete(game.items, id)
	}

	Logger.Info("Cleaned up marked items from idle room",
		"roomID", r.roomID,
		"itemsRemoved", len(itemsToRemove),
		"totalItemsBefore", itemCount,
		"totalItemsAfter", len(r.items))
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

	// Set up a 1-second ticker to match game heartbeat
	ticker := time.NewTicker(1 * time.Second)
	defer ticker.Stop()

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

		case <-ticker.C:
			// Increment idle counter if room is empty
			r.mutex.RLock()
			isEmpty := len(r.characters) == 0
			r.mutex.RUnlock()

			if isEmpty {
				// Increment the idle counter for empty rooms
				r.IncrementIdleCounter(game)
			}
		}
	}
}

// processCommand handles a command request within the room context
func (r *Room) processCommand(cmd *CommandRequest, game *Game) {
	if cmd == nil {
		Logger.Error("Received nil command in room", "roomID", r.roomID)
		return
	}

	Logger.Debug("Processing room command",
		"roomID", r.roomID,
		"verb", cmd.Verb,
		"character", cmd.Character.name)

	// Create default response
	response := &CommandResponse{
		RequestID: cmd.ID,
		Success:   false,
		Timestamp: time.Now(),
	}

	// Process command based on verb
	switch strings.ToLower(cmd.Verb) {
	case "say", "\"", "'": // Handle speech commands
		// TODO: Implement say command handling
		response.Error = fmt.Errorf("say command not implemented yet")

	case "look", "l": // Handle look command (additional room-based look processing)
		// This is typically handled at the character level, but might have room-level effects
		response.Success = true
		// No message/error for success since character handler already showed the room

	case "north", "south", "east", "west", "up", "down", "n", "s", "e", "w", "u", "d":
		// Handle direct movement commands
		direction := cmd.Verb
		// Expand shortened directions
		switch direction {
		case "n":
			direction = "north"
		case "s":
			direction = "south"
		case "e":
			direction = "east"
		case "w":
			direction = "west"
		case "u":
			direction = "up"
		case "d":
			direction = "down"
		}

		// Add the direction as an argument to the command
		movementCmd := &CommandRequest{
			ID:        cmd.ID,
			Character: cmd.Character,
			Verb:      "move",
			Args:      []string{"move", direction},
			Tier:      cmd.Tier,
			State:     cmd.State,
			Timestamp: cmd.Timestamp,
			Response:  cmd.Response,
		}

		resp := r.handleMovementCommand(movementCmd)

		// Copy response fields
		response.Success = resp.Success
		response.Message = resp.Message
		response.Error = resp.Error

	case "go", "move": // Handle explicit movement commands with direction argument
		// Check if a direction was provided
		if len(cmd.Args) < 2 {
			response.Error = fmt.Errorf(msgNoDirection)
			break
		}

		resp := r.handleMovementCommand(cmd)

		// Copy response fields
		response.Success = resp.Success
		response.Message = resp.Message
		response.Error = resp.Error

	case "get", "take", "drop", "put": // Handle item commands
		resp := r.handleItemCommand(cmd)

		// Copy response fields
		response.Success = resp.Success
		response.Message = resp.Message
		response.Error = resp.Error

	default:
		// Unknown command at room level
		Logger.Warn("Unhandled room command", "verb", cmd.Verb, "roomID", r.roomID)
		response.Error = fmt.Errorf("unknown room command: %s", cmd.Verb)
	}

	// Send response back to character
	select {
	case cmd.Response <- response:
		// Response sent successfully
	default:
		Logger.Error("Failed to send command response",
			"verb", cmd.Verb,
			"characterName", cmd.Character.name,
			"roomID", r.roomID)
	}
}

// handleMovementCommand processes room movement commands
func (r *Room) handleMovementCommand(cmd *CommandRequest) *CommandResponse {
	// Create the response structure
	response := &CommandResponse{
		RequestID: cmd.ID,
		Success:   false,
		Timestamp: time.Now(),
	}

	// First check if the character is allowed to move (no wait time)
	canMove, reason := cmd.Character.CanExecuteCommand()
	if !canMove {
		response.Error = fmt.Errorf("%s", reason)
		return response
	}

	// Get the direction from the command
	var direction string
	if cmd.Verb == "go" || cmd.Verb == "move" {
		// Using the "go" or "move" command with a direction argument
		if len(cmd.Args) < 2 {
			response.Error = fmt.Errorf(msgNoDirection)
			return response
		}
		direction = strings.ToLower(cmd.Args[1])
	} else {
		// Using a direction as the command itself
		direction = strings.ToLower(cmd.Verb)
	}

	// Check if character is trying to leave combat
	// TODO: Implement combat system check here

	// Check if there's an exit in the specified direction
	r.mutex.RLock()
	var targetExit *Exit

	// Find the exit by direction
	for _, exit := range r.exits {
		if exit != nil && strings.EqualFold(exit.direction, direction) && exit.visible {
			targetExit = exit
			break
		}
	}
	r.mutex.RUnlock()

	// If no exit is found
	if targetExit == nil {
		response.Error = fmt.Errorf(msgInvalidDir)
		return response
	}

	// If exit has no target room
	if targetExit.targetRoom == nil {
		response.Error = fmt.Errorf(msgPathNowhere)
		return response
	}

	// Perform the movement
	sourceRoom := r.roomID
	targetRoom := targetExit.targetRoom
	character := cmd.Character

	// Remove character from current room
	r.mutex.Lock()
	delete(r.characters, character.id)
	r.mutex.Unlock()

	// Add character to new room
	targetRoom.mutex.Lock()
	targetRoom.characters[character.id] = character
	// Update room activity
	targetRoom.lastActive = time.Now()
	targetRoom.mutex.Unlock()

	// Update character's room reference
	character.mutex.Lock()
	character.room = targetRoom
	character.mutex.Unlock()

	// Handle room entry effects
	targetRoom.HandleCharacterEntry()

	// Notify the original room that character has left
	leaveMsg := fmt.Sprintf("\n\r%s leaves %s.\n\r", character.name, direction)
	SendRoomMessageExcept(r, leaveMsg, character)

	// Notify the new room that character has arrived
	enterMsg := fmt.Sprintf("\n\r%s arrives from the %s.\n\r", character.name, getOppositeDirection(direction))
	SendRoomMessageExcept(targetRoom, enterMsg, character)

	// Show the new room to the character
	executeLookCommand(character, []string{"look"})

	// Set a wait time for the movement action
	character.SetCommandWaitTime(1 * time.Second)

	// Log the movement
	Logger.Info("Character moved",
		"character", character.name,
		"from", sourceRoom,
		"to", targetRoom.roomID,
		"direction", direction)

	response.Success = true
	return response
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

// getOppositeDirection returns the opposite direction
func getOppositeDirection(direction string) string {
	switch strings.ToLower(direction) {
	case "north":
		return "south"
	case "south":
		return "north"
	case "east":
		return "west"
	case "west":
		return "east"
	case "up":
		return "down"
	case "down":
		return "up"
	case "in":
		return "out"
	case "out":
		return "in"
	default:
		return "somewhere"
	}
}
