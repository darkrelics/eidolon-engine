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

	"github.com/gofrs/uuid/v5"
)

// CanExecuteCommand checks if character can perform a command based on wait time and state
func (c *Character) CanExecuteCommand() (bool, string) {
	c.mutex.RLock()
	defer c.mutex.RUnlock()

	// Validation prevents operations on nil references
	if c.player == nil {
		return false, "Character not properly connected."
	}

	if c.room == nil {
		return false, "Character not in a valid room."
	}

	// Check wait time
	if time.Now().Before(c.waitUntil) {
		waitTime := time.Until(c.waitUntil).Seconds()
		return false, fmt.Sprintf("You must wait %.1f seconds before your next action.", waitTime)
	}

	// Check character state if needed
	// Currently just check if there's a state set at all
	if c.charState == "" {
		// Default state is standing
		c.charState = "standing"
	}

	return true, ""
}

// SetCommandWaitTime sets a wait time for the character's next command
func (c *Character) SetCommandWaitTime(duration time.Duration) {
	c.mutex.Lock()
	defer c.mutex.Unlock()

	c.waitUntil = time.Now().Add(duration)
}

func (c *Character) Save() error {
	return c.SaveWithContext(c.game.ctx)
}

// SaveWithContext saves the character to the database with a specific context
// This is used during shutdown to ensure saves complete even after game context is cancelled
func (c *Character) SaveWithContext(ctx context.Context) error {

	Logger.Debug("Saving character", "characterName", c.name)

	kp := c.game.database
	if kp == nil || kp.db == nil {
		Logger.Error("Database not available, skipping save", "characterName", c.name)
		c.lastSaved = time.Now()
		return nil
	}

	// Convert inventory to ID map
	inventoryIDs := make(map[string]string)
	c.mutex.RLock()
	for name, item := range c.inventory {
		if item != nil {
			inventoryIDs[name] = item.id.String()
		}
	}
	inventoryCopy := make(map[string]*Item)
	for k, v := range c.inventory {
		inventoryCopy[k] = v
	}

	// Get hand item IDs
	var leftHandID, rightHandID string
	if c.leftHand != nil {
		leftHandID = c.leftHand.id.String()
	}
	if c.rightHand != nil {
		rightHandID = c.rightHand.id.String()
	}
	c.mutex.RUnlock()

	// Character data structure matches DynamoDB schema
	characterData := &CharacterData{
		CharacterID:   c.id.String(),
		PlayerID:      c.player.id.String(),
		CharacterName: c.name,
		Attributes:    c.attributes,
		Skills:        c.skills,
		Essence:       c.essence,
		Health:        c.health,
		RoomID:        c.room.roomID,
		Inventory:     inventoryIDs,
		LeftHandID:    leftHandID,
		RightHandID:   rightHandID,
		Hidden:        c.hidden,
	}

	// Transactional save ensures data consistency
	err := kp.SaveCharacterWithInventory(ctx, characterData, inventoryCopy)
	if err != nil {
		Logger.Error("Error saving character and inventory", "characterName", c.name, "error", err)
		return fmt.Errorf("error saving character and inventory: %w", err)
	}

	Logger.Debug("Successfully saved character and inventory", "characterName", c.name, "characterID", c.id.String(), "itemCount", len(inventoryIDs))

	c.lastSaved = time.Now()

	return nil
}

// CreateCharacter creates a new character for the player.
func (p *Player) CreateCharacter(name string, archetype string) (*Character, error) {

	Logger.Debug("Creating character", "name", name)

	if p == nil {
		return nil, fmt.Errorf("player is invalid")
	}

	// Validate character name
	if err := p.server.game.ValidateCharacterName(name); err != nil {
		return nil, err
	}

	p.server.game.characterBloomFilter.AddString(strings.ToLower(name))

	// Create Character with default values from config
	character := &Character{
		game:             p.server.game,
		id:               GenerateUUIDv7(),
		player:           p,
		name:             name,
		attributes:       make(map[string]float64),
		skills:           make(map[string]float64),
		essence:          float64(p.server.game.startingEssence), // Default from config
		health:           float64(p.server.game.startingHealth),  // Default from config
		inventory:        make(map[string]*Item),
		mutex:            sync.RWMutex{},
		advancing:        false,
		facing:           nil,
		combatRange:      make(map[uuid.UUID]float64),
		lastEdited:       time.Now(),
		charState:        "standing", // Default character state
		waitUntil:        time.Now(), // No initial wait time
		roomCommandOut:   make(chan *CommandRequest, 20),
		roomCommandIn:    make(chan *CommandResponse, 20),
		gameCommandOut:   make(chan *CommandRequest, 10), // Smaller buffer as game commands are less frequent
		gameCommandIn:    make(chan *CommandResponse, 10),
		playerCommandOut: make(chan string, 20),
		playerCommandIn:  make(chan string, 20),
		end:              make(chan bool, 1),
		prompt:           "> ",
	}

	// Track if we need cleanup on error
	var err error
	needsCleanup := true

	// Ensure cleanup of channels on error
	defer func() {
		if needsCleanup && err != nil {
			// Channel cleanup prevents goroutine leaks
			close(character.roomCommandOut)
			close(character.roomCommandIn)
			close(character.gameCommandOut)
			close(character.gameCommandIn)
			close(character.playerCommandOut)
			close(character.playerCommandIn)
			close(character.end)
			Logger.Debug("Cleaned up channels after character creation error", "characterName", name)
		}
	}()

	if archetype != "" {
		if archetypeObj, ok := p.server.game.archetypes[archetype]; ok {
			for attr, value := range archetypeObj.Attributes {
				character.attributes[attr] = value
			}

			for skill, value := range archetypeObj.Skills {
				character.skills[skill] = value
			}

			// Use archetype's Health and Essence if specified, otherwise keep defaults
			if archetypeObj.Health > 0 {
				character.health = float64(archetypeObj.Health)
			}
			if archetypeObj.Essence > 0 {
				character.essence = float64(archetypeObj.Essence)
			}

			if startRoom, ok := p.server.game.rooms[archetypeObj.StartRoom]; ok {
				character.room = startRoom
			} else if defaultRoom, ok := p.server.game.rooms[0]; ok {
				character.room = defaultRoom
			} else {
				Logger.Error("No valid starting room available", "archetype", archetype)
				return nil, fmt.Errorf("no valid starting room available")
			}

			// Prototype instantiation creates unique item instances
			Logger.Debug("Processing starting items for archetype", "archetype", archetype, "itemCount", len(archetypeObj.StartingItems))
			if len(archetypeObj.StartingItems) > 0 {
				for i, startingItem := range archetypeObj.StartingItems {
					Logger.Debug("Processing starting item", "archetype", archetype, "itemIndex", i, "prototypeID", startingItem.PrototypeID, "slot", startingItem.Slot)
					// Find prototype by ID
					prototypeIDUUID, err := uuid.FromString(startingItem.PrototypeID)
					if err != nil {
						Logger.Warn("Invalid prototype ID in archetype", "archetype", archetype, "prototypeID", startingItem.PrototypeID, "error", err)
						continue
					}

					// Find prototype in game's prototypes
					Logger.Debug("Looking for prototype", "prototypeID", prototypeIDUUID.String(), "count", len(p.server.game.prototypes))
					p.server.game.mutex.RLock()
					prototype, ok := p.server.game.prototypes[prototypeIDUUID]
					p.server.game.mutex.RUnlock()
					if !ok {
						Logger.Warn("Prototype not found", "archetype", archetype, "prototypeID", startingItem.PrototypeID)
						// Dump all prototype IDs for debugging
						p.server.game.mutex.RLock()
						for protoID := range p.server.game.prototypes {
							Logger.Debug("Available prototype", "prototypeID", protoID.String())
						}
						p.server.game.mutex.RUnlock()
						continue
					}

					// Item creation copies prototype properties
					item, err := CreateItemFromPrototype(prototype, p.server.game)
					if err != nil {
						Logger.Error("Failed to create item from prototype", "prototypeID", startingItem.PrototypeID, "error", err)
						continue
					}

					// Items will be saved transactionally with character

					// Worn state determines equipment vs inventory
					if startingItem.IsWorn && item.wearable {
						item.isWorn = true

					}

					// Inventory addition establishes ownership
					character.inventory[startingItem.Slot] = item
					Logger.Debug("Added starting item to character", "characterName", character.name, "itemName", item.name, "slot", startingItem.Slot)
				}
			}
		} else {
			Logger.Warn("Invalid archetype", "archetype", archetype)
			if defaultRoom, ok := p.server.game.rooms[0]; ok {
				character.room = defaultRoom
			} else {
				return nil, fmt.Errorf("no default room available")
			}
		}

	} else {
		Logger.Info("No archetype selected")
		if defaultRoom, ok := p.server.game.rooms[0]; ok {
			character.room = defaultRoom
		} else {
			return nil, fmt.Errorf("no default room available")
		}
	}

	err = character.Save()
	if err != nil {
		Logger.Error("Error saving character", "error", err)
		return nil, fmt.Errorf("error saving character: %w", err)
	}

	// Mark that cleanup is not needed on successful creation
	needsCleanup = false
	return character, nil
}

// Run manages the character's command processing lifecycle
// This is now a simple wrapper around RunConsole for backward compatibility
func (c *Character) Run(done chan bool) {
	Logger.Debug("Starting character run", "characterName", c.name)
	c.RunConsole(done)
}

// Stop cleanly shuts down the character session
func (c *Character) Stop() {
	// Ensure Stop logic is only executed once
	c.mutex.Lock()
	if c.stopped {
		c.mutex.Unlock()
		Logger.Debug("Character already stopped", "characterName", c.name)
		return
	}
	c.stopped = true
	c.mutex.Unlock()

	Logger.Info("Stopping character session", "characterName", c.name)

	// Notify the room of departure before removing the character
	if c.room != nil {
		SendRoomMessage(c.room, fmt.Sprintf("\n\r%s has left.\n\r", c.name), c)
	}

	// Room removal prevents ghost character references
	if c.room != nil {
		// Trigger onCharacterLeave event before removing character
		if c.room.scriptID != "" && c.room.scriptActive && ScriptMgr != nil {
			if err := ScriptMgr.ExecuteRoomEvent(c.room, "onCharacterLeave", c); err != nil {
				Logger.Error("Error executing onCharacterLeave during character stop", "roomID", c.room.roomID, "characterName", c.name, "error", err)
			}
		}

		c.room.mutex.Lock()
		delete(c.room.characters, c.id)
		c.room.lastActive = time.Now() // Update the timestamp when character leaves
		c.room.mutex.Unlock()
	}

	// Game removal completes character deactivation
	c.game.mutex.Lock()
	delete(c.game.characters, c.id)
	c.game.mutex.Unlock()

	// State persistence preserves player progress
	// Use a fresh context for shutdown saves to ensure they complete
	saveCtx := context.Background()

	err := c.SaveWithContext(saveCtx)
	if err != nil {
		Logger.Error("Error saving character during shutdown", "characterName", c.name, "error", err)
	}

	// Clean up character inventory and hand items from game.items map
	c.mutex.Lock()
	itemIDsToDelete := make([]uuid.UUID, 0, len(c.inventory)+2)
	for _, item := range c.inventory {
		if item != nil {
			itemIDsToDelete = append(itemIDsToDelete, item.id)
		}
	}
	// Also clean up hand items
	if c.leftHand != nil {
		itemIDsToDelete = append(itemIDsToDelete, c.leftHand.id)
	}
	if c.rightHand != nil {
		itemIDsToDelete = append(itemIDsToDelete, c.rightHand.id)
	}
	c.mutex.Unlock()

	if len(itemIDsToDelete) > 0 {
		c.game.DeleteItems(itemIDsToDelete)
		Logger.Info("Cleaned up character inventory items", "characterName", c.name, "itemCount", len(itemIDsToDelete))
	}

	// Store a reference to the player before resetting
	player := c.player

	// Signal shutdown without closing the channel
	select {
	case c.end <- true:
		// Successfully sent shutdown signal
	default:
		// Channel is full or no receiver, which is fine
		// The stopped flag will prevent any issues
	}

	// If we have a valid player reference, inform them we're returning to console
	if player != nil {
		// Reset the player's character reference
		player.character = nil
	}
}

// cleanupAndSignalDone stops the character and signals completion on the done channel
func (c *Character) cleanupAndSignalDone(done chan bool) {
	// Recover from any panic to prevent crash
	defer func() {
		if r := recover(); r != nil {
			Logger.Error("Panic in cleanupAndSignalDone", "error", r, "characterName", c.name)
		}
	}()

	// Stop the character
	c.Stop()

	// Signal completion if channel is valid
	if done != nil {
		// Check if channel is closed by attempting a non-blocking send
		select {
		case done <- true:
			// Successfully sent
		default:
			// Channel might be full or closed, log but don't panic
			Logger.Warn("Failed to signal done channel", "characterName", c.name)
		}
	}
}

// FormatCharacterDescription creates a description of a character for look command
func FormatCharacterDescription(target *Character, viewer *Character) string {
	target.mutex.RLock()
	defer target.mutex.RUnlock()

	var desc strings.Builder
	desc.WriteString(fmt.Sprintf("\n\r%s\n\r", target.name))

	// Basic appearance info
	desc.WriteString("You see a ")

	// Future: equipment and attributes will enhance descriptions
	// This is placeholder logic
	if target.health < float64(target.game.startingHealth)/2 {
		desc.WriteString("wounded ")
	}

	desc.WriteString("person.\n\r")

	// Equipment description
	var visibleItems []string
	for _, item := range target.inventory {
		if item != nil && item.isWorn {
			visibleItems = append(visibleItems, fmt.Sprintf("%s on %s", item.name, strings.Join(item.wornOn, " and ")))
		}
	}

	if len(visibleItems) > 0 {
		desc.WriteString("They are wearing ")
		desc.WriteString(strings.Join(visibleItems, ", "))
		desc.WriteString(".\n\r")
	}

	return desc.String()
}
