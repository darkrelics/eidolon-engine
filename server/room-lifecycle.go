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
	"fmt"
	"time"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/gofrs/uuid/v5"
)

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

	// Start the room goroutine FIRST - let it handle script loading internally
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

	// Mark as not running and get reference to cancel func
	r.running = false
	cancelFunc := r.cancel
	roomID := r.roomID
	scriptID := r.scriptID
	r.mutex.Unlock()

	Logger.Info("Stopping room goroutine", "roomID", roomID, "title", r.title)

	// Cancel the room's context to signal all operations to stop
	// This is done outside the lock to prevent deadlock
	cancelFunc()

	// Wait for the room goroutine to complete
	<-r.done

	// Unload the room's script if it has one
	if scriptID != "" && ScriptMgr != nil {
		ScriptMgr.UnloadRoomScript(roomID)
	}

	// Close channels after room goroutine completes
	close(r.commandIn)
	close(r.commandOut)
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
	Logger.Debug("Room goroutine started", "roomID", r.roomID, "title", r.title)

	// Signal completion when this function returns - do this at the very end instead of defer
	defer func() {
		Logger.Debug("Room goroutine ending, closing done channel", "roomID", r.roomID)
		close(r.done)
	}()

	// Handle script loading if room has a script - proper order of operations
	if r.scriptID != "" && r.scriptActive {
		if ScriptMgr == nil {
			Logger.Warn("Script manager not available, scripts will be unavailable", "roomID", r.roomID, "scriptID", r.scriptID)
			r.scriptActive = false
		} else {
			Logger.Info("Loading script for room", "roomID", r.roomID, "scriptID", r.scriptID)

			// Step 1: Pull script from cache or S3
			if err := ScriptMgr.LoadScriptForRoom(r.scriptID, r); err != nil {
				Logger.Error("Failed to load room script", "roomID", r.roomID, "scriptID", r.scriptID, "error", err)
				r.scriptActive = false
			} else {
				Logger.Info("Script loaded successfully", "roomID", r.roomID, "scriptID", r.scriptID)

				// Step 2: Call onRoomStart event if script loaded properly
				Logger.Debug("ABOUT TO EXECUTE onRoomStart event", "roomID", r.roomID, "scriptID", r.scriptID)

				// Add detailed logging before calling ExecuteRoomEvent
				Logger.Debug("Calling ScriptMgr.ExecuteRoomEvent", "roomID", r.roomID, "scriptID", r.scriptID, "event", "onRoomStart")
				if err := ScriptMgr.ExecuteRoomEvent(r, "onRoomStart"); err != nil {
					Logger.Error("Failed to execute onRoomStart event", "roomID", r.roomID, "scriptID", r.scriptID, "error", err)
					r.scriptActive = false
				} else {
					Logger.Debug("Successfully executed onRoomStart event", "roomID", r.roomID, "scriptID", r.scriptID)
				}
			}
		}
	}

	// Signal that room is ready to accept characters
	r.mutex.Lock()
	r.isReady = true
	r.mutex.Unlock()
	close(r.ready)

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
			// Execute periodic script tick if room has an active script
			if r.scriptID != "" && r.scriptActive && ScriptMgr != nil {
				// Check if script has periodic events
				sm := ScriptMgr
				sm.mutex.RLock()
				hasPeriodic := false
				if cached, exists := sm.scriptCache[r.scriptID]; exists && cached.metadata != nil {
					hasPeriodic = cached.metadata.Periodic
				}
				sm.mutex.RUnlock()

				if hasPeriodic {
					Logger.Debug("Executing onTick for room", "roomID", r.roomID, "scriptID", r.scriptID)
					if err := ScriptMgr.ExecuteRoomEvent(r, "onTick"); err != nil {
						Logger.Error("Failed to execute onTick event", "roomID", r.roomID, "error", err)
					}
				}
			}

			// Process combat movements
			r.processCombatMovements()

			// Process flee attempts
			r.processFlee()

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

	Logger.Debug("Room processCommand: Processing command", "roomID", r.roomID, "verb", cmd.Verb, "character", cmd.Character.name)

	// Process the command using the room command handler
	response := r.ProcessRoomCommand(cmd, game)

	Logger.Debug("Room processCommand: Got response", "roomID", r.roomID, "verb", cmd.Verb, "success", response.Success, "hasError", response.Error != nil)

	// Send response back to character
	select {
	case cmd.Response <- response:
		Logger.Debug("Room processCommand: Response sent", "roomID", r.roomID, "verb", cmd.Verb)
	default:
		Logger.Error("Room processCommand: Failed to send response - channel full or closed", "roomID", r.roomID, "verb", cmd.Verb)
	}
}

// IncrementIdleCounter increments the idle counter for an empty room and handles cleanup if threshold is reached
func (r *Room) IncrementIdleCounter(game *Game) {
	r.mutex.Lock()

	// Only increment if room is empty
	if len(r.characters) > 0 {
		// Reset counter if characters are present
		r.idleCounter = 0
		r.mutex.Unlock()
		return
	}

	// Increment the idle counter
	r.idleCounter++

	// Check for item cleanup every 10 minutes (600 ticks = 10 minutes @ 1 second per tick)
	if r.idleCounter%600 == 0 && r.idleCounter > 0 {
		Logger.Debug("Room item cleanup interval reached", "roomID", r.roomID, "title", r.title, "idleMinutes", r.idleCounter/60)

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
			r.mutex.Unlock()
		} else {
			// For non-persistent rooms, unload the room
			Logger.Info("Unloading non-persistent idle room", "roomID", r.roomID)

			// Clean up ALL items in the room from game.items map
			itemsToDelete := make([]string, 0)
			itemIDsToDelete := make([]uuid.UUID, 0, len(r.items))
			for itemID, item := range r.items {
				itemIDsToDelete = append(itemIDsToDelete, itemID)
				// Track items that might need database cleanup
				if item != nil && item.lastSaved.After(item.lastEdited) {
					itemsToDelete = append(itemsToDelete, itemID.String())
				}
			}
			// Use thread-safe method to delete items
			game.DeleteItems(itemIDsToDelete)
			Logger.Info("Cleaned up all room items", "roomID", r.roomID, "itemCount", len(r.items))

			// Must unlock before Stop to avoid deadlock
			r.mutex.Unlock()

			// Delete items from database if needed (minimize DB access)
			if len(itemsToDelete) > 0 {
				r.deleteItemsFromDatabase(game, itemsToDelete)
			}

			r.Stop()

			// Clear exit references to this room to prevent stale references
			game.clearExitReferencesToRoom(r.roomID)

			// Remove room from game's room map
			game.mutex.Lock()
			delete(game.rooms, r.roomID)
			game.mutex.Unlock()
		}
	} else {
		r.mutex.Unlock()
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
		game.DeleteItem(id)
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

func (g *Game) LoadRooms() error {

	Logger.Info("Load Rooms...Loading Rooms...")

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
			if exit, ok := g.exits[exitUUID]; ok {
				g.rooms[roomData.RoomID].exits[exitUUID] = exit
			} else {
				Logger.Warn("Exit not found in game exits", "exitID", exitID, "roomID", roomData.RoomID)
			}
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

	// Start persistent rooms
	persistentCount := 0
	for roomID, room := range g.rooms {
		if room.persistent {
			Logger.Debug("Starting persistent room", "roomID", roomID, "title", room.title)
			room.Start(g)
			persistentCount++
		}
	}

	Logger.Info("Persistent rooms started", "count", persistentCount)
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

// processCombatMovements handles all combat movement for characters in the room
func (r *Room) processCombatMovements() {
	r.mutex.RLock()
	charactersToMove := make([]*Character, 0)
	for _, char := range r.characters {
		if char != nil {
			char.mutex.RLock()
			if char.combatMovement != nil {
				charactersToMove = append(charactersToMove, char)
			}
			char.mutex.RUnlock()
		}
	}
	r.mutex.RUnlock()

	// Process each character's movement
	for _, char := range charactersToMove {
		char.mutex.Lock()
		movement := char.combatMovement
		if movement == nil {
			char.mutex.Unlock()
			continue
		}

		// Calculate movement speed based on Agility
		agility := char.attributes["Agility"]
		if agility < 0 {
			agility = 0
		} else if agility > 10 {
			agility = 10
		}
		moveSpeed := agility * 3.0
		if moveSpeed < 1.0 {
			moveSpeed = 1.0
		}

		switch movement.mode {
		case "advance":
			// Find target
			var target *Character
			r.mutex.RLock()
			for _, c := range r.characters {
				if c != nil && c.id == movement.targetID {
					target = c
					break
				}
			}
			r.mutex.RUnlock()

			if target == nil || target.room != r {
				// Target no longer in room
				char.combatMovement = nil
				char.facing = nil
				char.mutex.Unlock()
				char.DisplayMessage("\n\rYour target is no longer here.\n\r")
				continue
			}

			// Get current range
			currentRange := r.getCombatRange(char, target)

			// Move towards target
			if currentRange > movement.targetRange {
				newRange := currentRange - moveSpeed
				if newRange < movement.targetRange {
					newRange = movement.targetRange
				}

				r.setCombatRange(char, target, newRange)

				// Check if reached target range
				if newRange <= movement.targetRange {
					char.combatMovement = nil
					rangeName := "close combat with"
					if movement.targetRange == 3.0 {
						rangeName = "melee range with"
					} else if movement.targetRange == 10.0 {
						rangeName = "pole range with"
					}
					char.DisplayMessage(fmt.Sprintf("\n\rYou reach %s %s.\n\r", rangeName, target.name))
					target.DisplayMessage(fmt.Sprintf("\n\r%s reaches %s you.\n\r", char.name, rangeName))
					SendRoomMessage(r, fmt.Sprintf("\n\r%s reaches %s %s.\n\r", char.name, rangeName, target.name), char, target)
				}
			} else {
				// Already at or closer than target range
				char.combatMovement = nil
			}

		case "retreat":
			// Find all combat opponents
			r.mutex.RLock()
			ranges := r.combatRanges[char.id]
			r.mutex.RUnlock()

			if ranges == nil || len(ranges) == 0 {
				char.combatMovement = nil
				char.mutex.Unlock()
				continue
			}

			// Move away from all opponents
			allAtRange := true
			for opponentID, currentRange := range ranges {
				if currentRange < movement.targetRange {
					allAtRange = false
					newRange := currentRange + moveSpeed
					if newRange > movement.targetRange {
						newRange = movement.targetRange
					}

					// Find opponent character
					var opponent *Character
					r.mutex.RLock()
					for _, c := range r.characters {
						if c != nil && c.id == opponentID {
							opponent = c
							break
						}
					}
					r.mutex.RUnlock()

					if opponent != nil {
						r.setCombatRange(char, opponent, newRange)
					}
				}
			}

			if allAtRange {
				char.combatMovement = nil
				char.DisplayMessage("\n\rYou reach your desired distance.\n\r")
			}
		}

		char.mutex.Unlock()
	}
}

// processFlee handles flee attempts for characters
func (r *Room) processFlee() {
	r.mutex.RLock()
	charactersToFlee := make([]*Character, 0)
	for _, char := range r.characters {
		if char != nil {
			char.mutex.RLock()
			if char.fleeTarget != nil {
				charactersToFlee = append(charactersToFlee, char)
			}
			char.mutex.RUnlock()
		}
	}
	r.mutex.RUnlock()

	for _, char := range charactersToFlee {
		char.mutex.Lock()
		fleeState := char.fleeTarget
		if fleeState == nil {
			char.mutex.Unlock()
			continue
		}

		// Check timeout (30 seconds)
		elapsed := time.Since(fleeState.startTime).Seconds()
		if elapsed >= 30 {
			char.mutex.Unlock()
			r.handleFleeTimeout(char, fleeState)
			continue
		}

		// Get character's agility for movement speed
		agility := char.attributes["agility"]
		if agility < 1 {
			agility = 1
		}

		// Calculate movement speed (same as retreat)
		moveSpeed := agility * 0.5 // Units per second

		// Find closest adversary
		minRange := float64(1000)
		var hasAdversary bool
		r.mutex.RLock()
		if ranges, exists := r.combatRanges[char.id]; exists {
			for _, range_ := range ranges {
				if range_ < minRange {
					minRange = range_
					hasAdversary = true
				}
			}
		}
		// Also check if character is a target
		for attackerID, targets := range r.combatRanges {
			if attackerID != char.id {
				if range_, exists := targets[char.id]; exists && range_ < minRange {
					minRange = range_
					hasAdversary = true
				}
			}
		}
		r.mutex.RUnlock()

		if !hasAdversary {
			// No adversaries, complete flee immediately
			char.mutex.Unlock()
			r.completeFlee(char, fleeState)
			continue
		}

		// Move away from all adversaries
		r.mutex.Lock()
		if ranges, exists := r.combatRanges[char.id]; exists {
			for targetID, currentRange := range ranges {
				newRange := currentRange + moveSpeed*0.1 // 0.1 second tick
				ranges[targetID] = newRange
			}
		}
		// Also update ranges where character is the target
		for attackerID, targets := range r.combatRanges {
			if attackerID != char.id {
				if currentRange, exists := targets[char.id]; exists {
					newRange := currentRange + moveSpeed*0.1
					targets[char.id] = newRange
				}
			}
		}
		r.mutex.Unlock()

		// Check if flee conditions are met
		if fleeState.hasDirection {
			// With direction: flee at 20+ range
			if minRange >= 20 {
				char.mutex.Unlock()
				r.completeFlee(char, fleeState)
				continue
			}
		} else {
			// Without direction: flee at 45+ range
			if minRange >= 45 {
				char.mutex.Unlock()
				r.completeFlee(char, fleeState)
				continue
			}
		}

		char.mutex.Unlock()
	}
}

// handleFleeTimeout handles when a flee attempt times out
func (r *Room) handleFleeTimeout(char *Character, fleeState *FleeState) {
	char.mutex.Lock()
	char.fleeTarget = nil
	exitDirection := fleeState.exitDirection
	char.mutex.Unlock()

	// Remove from combat
	r.removeCharacterFromCombat(char)

	if exitDirection != "" {
		// Flee through specified exit
		char.DisplayMessage(fmt.Sprintf("\n\rYou flee %s in panic!\n\r", exitDirection))
		SendRoomMessage(r, fmt.Sprintf("\n\r%s flees %s in panic!\n\r", char.name, exitDirection), char)
		r.forceMovementCommand(char, exitDirection)
	} else {
		// Flee through first available exit
		r.mutex.RLock()
		var firstExit *Exit
		for _, exit := range r.exits {
			if exit != nil && exit.visible {
				firstExit = exit
				break
			}
		}
		r.mutex.RUnlock()

		if firstExit != nil {
			char.DisplayMessage(fmt.Sprintf("\n\rYou flee %s in panic!\n\r", firstExit.direction))
			SendRoomMessage(r, fmt.Sprintf("\n\r%s flees %s in panic!\n\r", char.name, firstExit.direction), char)
			r.forceMovementCommand(char, firstExit.direction)
		} else {
			// No exits available, just remove from combat
			char.DisplayMessage("\n\rYou manage to escape from combat!\n\r")
			SendRoomMessage(r, fmt.Sprintf("\n\r%s manages to escape from combat!\n\r", char.name), char)
		}
	}
}

// completeFlee completes a successful flee attempt
func (r *Room) completeFlee(char *Character, fleeState *FleeState) {
	char.mutex.Lock()
	char.fleeTarget = nil
	exitDirection := fleeState.exitDirection
	char.mutex.Unlock()

	if exitDirection != "" {
		// Flee through specified exit
		char.DisplayMessage(fmt.Sprintf("\n\rYou successfully flee %s!\n\r", exitDirection))
		SendRoomMessage(r, fmt.Sprintf("\n\r%s flees %s!\n\r", char.name, exitDirection), char)
		r.forceMovementCommand(char, exitDirection)
	} else {
		// Just remove from combat
		r.removeCharacterFromCombat(char)
		char.DisplayMessage("\n\rYou successfully escape from combat!\n\r")
		SendRoomMessage(r, fmt.Sprintf("\n\r%s escapes from combat!\n\r", char.name), char)
	}
}

// forceMovementCommand forces a character to move in a direction
func (r *Room) forceMovementCommand(char *Character, direction string) {
	// Create a movement command request
	cmd := &CommandRequest{
		ID:        uuid.Must(uuid.NewV4()),
		Character: char,
		Verb:      direction,
		Args:      []string{direction},
		Timestamp: time.Now(),
	}

	// Process the movement command
	response := handleMovementCommand(cmd, char.game)
	if !response.Success && response.Error != nil {
		Logger.Error("Room: Failed to force movement", "character", char.name, "direction", direction, "error", response.Error)
	}
}
