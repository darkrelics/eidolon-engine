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

	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/gofrs/uuid/v5"
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

// Initialize a new room
func NewRoom(ctx context.Context, roomID int64, area, title, description string, persistent bool, scriptID string) *Room {

	Logger.Debug("New Room...Initalizing Room...", "roomID", roomID, "persistent", persistent, "scriptID", scriptID)

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

// Load room data from DynamoDB
func (g *Game) LoadRooms() error {

	Logger.Info("Load Rooms...Loading Rooms...")

	// Load room data from DynamoDB
	var roomsData []RoomData
	err := g.database.Scan(g.ctx, "rooms", &roomsData)
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
			exitUUID, err := uuid.FromString(exitID)
			if err != nil {
				Logger.Warn("Error parsing exit ID", "error", err)
				continue
			}
			g.rooms[roomData.RoomID].exits[exitUUID] = g.exits[exitUUID]
		}
	}

	// Load item prototypes
	prototypes, err := LoadPrototypes(g.ctx, g.database)
	if err != nil {
		Logger.Warn("Error loading prototypes", "error", err)
	} else {
		g.mutex.Lock()
		g.prototypes = prototypes
		g.mutex.Unlock()
	}

	return nil
}

// LoadRoom loads a single room by ID from the database
func (g *Game) LoadRoom(roomID int64) (*Room, error) {
	Logger.Info("Loading single room", "roomID", roomID)

	// Check if room already exists
	g.mutex.RLock()
	if existingRoom, exists := g.rooms[roomID]; exists {
		g.mutex.RUnlock()
		return existingRoom, nil
	}
	g.mutex.RUnlock()

	// Load room data from database
	roomData := &RoomData{}
	key := map[string]types.AttributeValue{
		"RoomID": &types.AttributeValueMemberN{Value: fmt.Sprintf("%d", roomID)},
	}

	err := g.database.Get(g.ctx, "rooms", key, roomData)
	if err != nil {
		Logger.Warn("Could not load room from database", "roomID", roomID, "error", err)
		return nil, fmt.Errorf("room not found: %w", err)
	}

	// Create new room
	newRoom := NewRoom(
		g.ctx,
		roomData.RoomID,
		roomData.Area,
		roomData.Title,
		roomData.Description,
		roomData.Persistent,
		roomData.ScriptID,
	)

	// Associate exits with the room
	for _, exitID := range roomData.ExitIDs {
		exitUUID, err := uuid.FromString(exitID)
		if err != nil {
			Logger.Warn("Error parsing exit ID", "error", err)
			continue
		}
		if exit, exists := g.exits[exitUUID]; exists {
			newRoom.exits[exitUUID] = exit
		}
	}

	// Add room to game
	g.mutex.Lock()
	g.rooms[roomID] = newRoom
	g.mutex.Unlock()

	Logger.Info("Successfully loaded room", "roomID", roomID, "title", newRoom.title)
	return newRoom, nil
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

	// Check for item cleanup every 10 minutes (600 ticks = 10 minutes @ 1 second per tick)
	if r.idleCounter%600 == 0 && r.idleCounter > 0 {
		Logger.Info("Room item cleanup interval reached", "roomID", r.roomID, "title", r.title, "idleMinutes", r.idleCounter/60)

		// Clean up marked items in the room
		r.cleanupItems(game)
	}

	// Check if room unload threshold has been reached (3600 ticks = 60 minutes @ 1 second per tick)
	if r.idleCounter >= 3600 {
		Logger.Info("Room unload threshold reached", "roomID", r.roomID, "title", r.title, "persistent", r.persistent)

		// For persistent rooms, only deactivate scripts but keep room loaded
		if r.persistent {
			r.scriptActive = false
			Logger.Info("Deactivating scripts for idle persistent room", "roomID", r.roomID)
			// Reset idle counter for persistent rooms to prevent repeated deactivation logs
			r.idleCounter = 0
		} else {
			// For non-persistent rooms, unload the room
			Logger.Info("Unloading non-persistent idle room", "roomID", r.roomID)

			// Clean up ALL items in the room from game.items map
			itemsToDelete := make([]string, 0)
			for itemID, item := range r.items {
				delete(game.items, itemID)
				// Track items that might need database cleanup
				if item != nil && item.lastSaved.After(item.lastEdited) {
					itemsToDelete = append(itemsToDelete, itemID.String())
				}
			}
			Logger.Info("Cleaned up all room items", "roomID", r.roomID, "itemCount", len(r.items))

			// We must unlock mutex before calling Stop to avoid deadlock
			r.mutex.Unlock()

			// Delete items from database if needed (minimize DB access)
			if len(itemsToDelete) > 0 {
				r.deleteItemsFromDatabase(game, itemsToDelete)
			}

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
	var itemsToDeleteFromDB []string

	for id, item := range r.items {
		if item != nil && item.markedForDeletion {
			itemsToRemove = append(itemsToRemove, id)
			// Track items that have been saved to database
			if item.lastSaved.After(item.lastEdited) {
				itemsToDeleteFromDB = append(itemsToDeleteFromDB, id.String())
			}
		}
	}

	// Remove the items from room and game maps
	for _, id := range itemsToRemove {
		delete(r.items, id)
		// Also remove from game's items map
		delete(game.items, id)
	}

	// Delete items from database if needed (batch operation to minimize DB access)
	if len(itemsToDeleteFromDB) > 0 {
		roomID := r.roomID // Capture for goroutine
		go RunWithPanicRecovery("room.deleteItems", func() {
			// Run database deletion asynchronously to avoid blocking room operations
			r.deleteItemsFromDatabase(game, itemsToDeleteFromDB)
		}, "roomID", roomID, "itemCount", len(itemsToDeleteFromDB))
	}

	if len(itemsToRemove) > 0 {
		Logger.Info("Cleaned up marked items from idle room",
			"roomID", r.roomID,
			"itemsRemoved", len(itemsToRemove),
			"dbItemsDeleted", len(itemsToDeleteFromDB),
			"totalItemsBefore", itemCount,
			"totalItemsAfter", len(r.items))
	}
}

// deleteItemsFromDatabase deletes items from the database in batch to minimize DB access
func (r *Room) deleteItemsFromDatabase(game *Game, itemIDs []string) {
	if len(itemIDs) == 0 {
		return
	}

	Logger.Info("Deleting items from database", "roomID", r.roomID, "itemCount", len(itemIDs))

	// Use batch delete to minimize DB calls
	err := game.database.BatchDeleteItems(game.ctx, itemIDs)
	if err != nil {
		Logger.Error("Failed to batch delete items from database", "roomID", r.roomID, "error", err)
	}
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

	// Collect recipients while holding the lock
	room.mutex.RLock()
	recipients := make([]*Character, 0, len(room.characters))
	for _, c := range room.characters {
		if c != nil && c != except && c.player != nil {
			recipients = append(recipients, c)
		}
	}
	room.mutex.RUnlock()

	// Send messages without holding the lock to prevent deadlock
	for _, c := range recipients {
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
	// First check if already stopped to avoid unnecessary work
	r.mutex.Lock()
	if !r.running {
		r.mutex.Unlock()
		Logger.Warn("Attempted to stop a room that is not running", "roomID", r.roomID)
		return
	}

	// Mark as not running and get references to cancel func and channels
	r.running = false
	cancelFunc := r.cancel
	commandIn := r.commandIn
	commandOut := r.commandOut
	r.mutex.Unlock()

	Logger.Info("Stopping room goroutine", "roomID", r.roomID, "title", r.title)

	// Cancel the room's context to signal all operations to stop
	// This is done outside the lock to prevent deadlock
	cancelFunc()

	// Close channels after releasing the lock
	// This prevents deadlock if channel operations were waiting on the mutex
	close(commandIn)
	close(commandOut)
	// Note: we don't close gameCommandOut as it belongs to the Game
}

// run is the main goroutine function for a room
func (r *Room) run(game *Game) {
	RunWithPanicRecoveryCallback("room.run", func() {
		r.runInternal(game)
	}, func(err error) {
		// Attempt graceful cleanup
		r.Stop()
	}, "roomID", r.roomID)
}

// runInternal contains the actual room processing logic
func (r *Room) runInternal(game *Game) {
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
				// Check if this is an intentional shutdown
				select {
				case <-r.ctx.Done():
					// Context was canceled, this is expected during shutdown
					Logger.Debug("Room command channel closed during shutdown", "roomID", r.roomID)
				default:
					// Context not canceled, this is unexpected
					Logger.Warn("Room command channel closed unexpectedly", "roomID", r.roomID)
				}
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

	// Process the command using the room command handler
	response := r.ProcessRoomCommand(cmd, game)

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

// GetDescription returns a formatted string description of the room
func (r *Room) GetDescription(character *Character) string {
	r.mutex.RLock()
	defer r.mutex.RUnlock()

	var roomInfo strings.Builder
	roomInfo.Grow(1024) // Pre-allocate reasonable buffer

	// Room Title and Description
	roomInfo.WriteString("\n\r[")
	roomInfo.WriteString(ApplyColor("bright_white", r.title))
	roomInfo.WriteString("]\n\r")
	roomInfo.WriteString(r.description)
	roomInfo.WriteString("\n\r")

	// Exits - collect while under lock
	exits := make([]string, 0, len(r.exits))
	for _, exit := range r.exits {
		if exit != nil && exit.visible {
			// Include exit description if available
			if exit.description != "" {
				exits = append(exits, fmt.Sprintf("%s (%s)", exit.direction, exit.description))
			} else {
				exits = append(exits, exit.direction)
			}
		}
	}

	if len(exits) == 0 {
		roomInfo.WriteString(msgNoExits)
	} else {
		sort.Strings(exits)
		roomInfo.WriteString("Obvious exits: ")
		roomInfo.WriteString(strings.Join(exits, ", "))
		roomInfo.WriteString("\n\r")
	}

	// Characters - collect while under lock
	chars := make([]string, 0, len(r.characters))
	for _, c := range r.characters {
		if c != nil && c != character {
			chars = append(chars, c.name)
		}
	}

	if len(chars) == 0 {
		roomInfo.WriteString(msgAlone)
	} else {
		roomInfo.WriteString(msgAlsoHere)
		roomInfo.WriteString(strings.Join(chars, ", "))
		roomInfo.WriteString("\n\r")
	}

	// Items - collect while under lock
	items := make([]string, 0, len(r.items))
	for _, item := range r.items {
		if item != nil && item.canPickUp {
			items = append(items, item.name)
		}
	}

	if len(items) > 0 {
		roomInfo.WriteString(msgItems)
		for _, item := range items {
			roomInfo.WriteString("- ")
			roomInfo.WriteString(item)
			roomInfo.WriteString("\n\r")
		}
	}

	return roomInfo.String()
}
