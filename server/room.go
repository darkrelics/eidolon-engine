/*
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

*/

package main

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/gofrs/uuid/v5"
)

// Room represents the in-memory structure for a room
type Room struct {
	roomID           int64
	area             string
	title            string
	description      string
	exits            map[uuid.UUID]*Exit
	characters       map[uuid.UUID]*Character
	items            map[uuid.UUID]*Item
	persistent       bool                                // Flag indicating if room should remain loaded when empty
	scriptID         string                              // ID of the script that defines room-specific behaviors
	combatRanges     map[uuid.UUID]map[uuid.UUID]float64 // Combat ranges between characters (outer: attacker, inner: target -> range)
	charactersToMove map[uuid.UUID]*Character            // Characters with active combat movement
	charactersToFlee map[uuid.UUID]*Character            // Characters with active flee state
	mutex            sync.RWMutex
	lastEdited       time.Time
	lastSaved        time.Time
	lastActive       time.Time             // Timestamp of last activity in the room
	idleCounter      int                   // Counter for tracking idle time (increments per game tick)
	scriptActive     bool                  // Flag indicating if room scripts are currently active
	ctx              context.Context       // Context for room goroutine lifecycle
	cancel           context.CancelFunc    // Cancel function for room context
	running          bool                  // Flag indicating if room goroutine is running
	commandIn        chan *CommandRequest  // Channel for commands sent to the room
	commandOut       chan *CommandResponse // Channel for responses from the room
	gameCommandOut   chan *CommandRequest  // Channel for commands the room escalates to the game
	gameCommandIn    chan *CommandResponse // Channel for responses from the game to the room
	done             chan struct{}         // Channel signaled when room goroutine completes
	ready            chan struct{}         // Channel signaled when room is ready to accept characters
	isReady          bool                  // Flag indicating if room is ready
}

// RoomData represents the structure for storing room data in DynamoDB
type RoomData struct {
	RoomID      int64    `json:"RoomID" dynamodbav:"RoomID"`
	Area        string   `json:"Area" dynamodbav:"Area"`
	Title       string   `json:"Title" dynamodbav:"Title"`
	Description string   `json:"Description" dynamodbav:"Description"`
	ExitIDs     []string `json:"ExitID" dynamodbav:"ExitID"`
	Persistent  bool     `json:"Persistent" dynamodbav:"Persistent"`
	ScriptID    string   `json:"ScriptID" dynamodbav:"ScriptID"`
}

func NewRoom(ctx context.Context, roomID int64, area, title, description string, persistent bool, scriptID string) *Room {

	Logger.Debug("New Room...Initializing Room...", "roomID", roomID, "persistent", persistent, "scriptID", scriptID)

	now := time.Now()

	// Create a new context for the room, which will be canceled when the room is stopped
	roomCtx, cancel := context.WithCancel(ctx)

	return &Room{
		roomID:           roomID,
		area:             area,
		title:            title,
		description:      description,
		exits:            make(map[uuid.UUID]*Exit),
		characters:       make(map[uuid.UUID]*Character),
		items:            make(map[uuid.UUID]*Item),
		persistent:       persistent,
		scriptID:         scriptID,
		combatRanges:     make(map[uuid.UUID]map[uuid.UUID]float64),
		charactersToMove: make(map[uuid.UUID]*Character),
		charactersToFlee: make(map[uuid.UUID]*Character),
		mutex:            sync.RWMutex{},
		lastEdited:       now,
		lastSaved:        now,
		lastActive:       now,
		idleCounter:      0,
		scriptActive:     scriptID != "", // Initialize script as active if a script is assigned
		ctx:              roomCtx,
		cancel:           cancel,
		running:          false,
		isReady:          false,
		commandIn:        make(chan *CommandRequest, 50),  // Buffer for incoming commands - sized for burst handling
		commandOut:       make(chan *CommandResponse, 50), // Buffer for outgoing responses
		gameCommandOut:   make(chan *CommandRequest, 10),  // Buffer for commands to game
		gameCommandIn:    make(chan *CommandResponse, 10), // Buffer for responses from game
		done:             make(chan struct{}),             // Channel to signal goroutine completion
		ready:            make(chan struct{}),             // Channel to signal room is ready
	}
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
func (r *Room) HandleCharacterEntry(character *Character) {
	r.mutex.Lock()
	// Reset idle counter
	r.idleCounter = 0

	// For persistent rooms with scripts assigned, activate scripts
	var activateLog bool
	var roomID int64
	if r.persistent && r.scriptID != "" && !r.scriptActive {
		r.scriptActive = true
		activateLog = true
		roomID = r.roomID
	}
	r.mutex.Unlock()

	if activateLog {
		Logger.Info("Activating scripts for persistent room with character entry", "roomID", roomID)
	}

	// Don't trigger script events here - let the room goroutine handle it
	// This prevents race conditions where scripts aren't loaded yet
}

// GetScriptID returns the script ID for the room
func (r *Room) GetScriptID() string {
	r.mutex.RLock()
	defer r.mutex.RUnlock()

	return r.scriptID
}

// IsRunning returns whether the room goroutine is running
func (r *Room) IsRunning() bool {
	r.mutex.RLock()
	defer r.mutex.RUnlock()

	return r.running
}

// SendRoomMessage sends a message to all characters in a room except one
func SendRoomMessage(room *Room, message string, except ...*Character) {
	if room == nil {
		return
	}

	// Create a map for faster exclusion checking
	excludeMap := make(map[*Character]bool)
	for _, char := range except {
		if char != nil {
			excludeMap[char] = true
		}
	}

	// Collect recipients and update activity while holding the lock
	room.mutex.Lock()
	room.lastActive = time.Now()
	room.lastEdited = room.lastActive
	recipients := make([]*Character, 0, len(room.characters))
	for _, c := range room.characters {
		if c != nil && !excludeMap[c] && c.player != nil {
			recipients = append(recipients, c)
		}
	}
	room.mutex.Unlock()

	// Send messages without holding the lock to prevent deadlock
	for _, c := range recipients {
		c.DisplayMessage(message)
	}
}

// WaitReady waits for the room to be ready to accept characters
func (r *Room) WaitReady() {
	r.mutex.RLock()
	if r.isReady {
		r.mutex.RUnlock()
		return
	}
	roomID := r.roomID
	r.mutex.RUnlock()

	Logger.Debug("Waiting for room to be ready", "roomID", roomID)
	// Wait for ready signal with timeout
	select {
	case <-r.ready:
		Logger.Debug("Room is ready", "roomID", roomID)
	case <-time.After(10 * time.Second):
		Logger.Error("Room failed to become ready in time", "roomID", roomID)
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

	// Exits - we need to collect for sorting
	var exits []string
	for _, exit := range r.exits {
		if exit != nil && exit.visible {
			if exits == nil {
				exits = make([]string, 0, len(r.exits))
			}
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

	// Characters - write directly without collecting
	charCount := 0
	for _, c := range r.characters {
		if c != nil && c != character && c.IsVisibleTo(character) {
			if charCount == 0 {
				roomInfo.WriteString(msgAlsoHere)
			} else {
				roomInfo.WriteString(", ")
			}
			roomInfo.WriteString(c.name)
			charCount++
		}
	}

	if charCount == 0 {
		roomInfo.WriteString(msgAlone)
	} else {
		roomInfo.WriteString("\n\r")
	}

	// Items - write directly without collecting
	itemCount := 0
	for _, item := range r.items {
		if item != nil && item.canPickUp {
			if itemCount == 0 {
				roomInfo.WriteString(msgItems)
			}
			roomInfo.WriteString("- ")
			roomInfo.WriteString(item.name)
			roomInfo.WriteString("\n\r")
			itemCount++
		}
	}

	return roomInfo.String()
}

// AddCharacterToMove adds a character to the charactersToMove list
func (r *Room) AddCharacterToMove(char *Character) {
	if char == nil {
		return
	}
	r.mutex.Lock()
	defer r.mutex.Unlock()
	r.charactersToMove[char.id] = char
}

// RemoveCharacterToMove removes a character from the charactersToMove list
func (r *Room) RemoveCharacterToMove(char *Character) {
	if char == nil {
		return
	}
	r.mutex.Lock()
	defer r.mutex.Unlock()
	delete(r.charactersToMove, char.id)
}

// AddCharacterToFlee adds a character to the charactersToFlee list
func (r *Room) AddCharacterToFlee(char *Character) {
	if char == nil {
		return
	}
	r.mutex.Lock()
	defer r.mutex.Unlock()
	r.charactersToFlee[char.id] = char
}

// RemoveCharacterToFlee removes a character from the charactersToFlee list
func (r *Room) RemoveCharacterToFlee(char *Character) {
	if char == nil {
		return
	}
	r.mutex.Lock()
	defer r.mutex.Unlock()
	delete(r.charactersToFlee, char.id)
}
