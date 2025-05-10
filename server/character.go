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
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
)

// CanExecuteCommand checks if character can perform a command based on wait time and state
func (c *Character) CanExecuteCommand() (bool, string) {
	c.mutex.RLock()
	defer c.mutex.RUnlock()

	// Check wait time
	if time.Now().Before(c.waitUntil) {
		waitTime := time.Until(c.waitUntil).Round(time.Second)
		return false, fmt.Sprintf("You must wait %v before your next action.", waitTime)
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

// Save saves the character to the database
func (c *Character) Save() error {

	Logger.Debug("Saving character", "characterName", c.name)

	kp := c.game.database

	// Convert inventory to ID map
	inventoryIDs := make(map[string]string)
	for name, item := range c.inventory {
		inventoryIDs[name] = item.id.String()
	}

	// Create character data for storage
	characterData := &CharacterData{
		CharacterID:   c.id.String(),
		PlayerID:      c.player.id.String(),
		CharacterName: c.name,
		Attributes:    c.attributes,
		Abilities:     c.abilities,
		Essence:       c.essence,
		Health:        c.health,
		RoomID:        c.room.roomID,
		Inventory:     inventoryIDs,
	}

	// Write to database
	err := kp.Put("characters", characterData)
	if err != nil {
		Logger.Error("Error writing character data", "characterName", c.name, "error", err)
		return fmt.Errorf("error writing character data: %w", err)
	}

	Logger.Debug("Successfully wrote character to database", "characterName", c.name, "characterID", c.id.String())

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

	// Create Character
	character := &Character{
		game:             p.server.game,
		id:               GenerateUUIDv7(),
		player:           p,
		name:             name,
		attributes:       make(map[string]float64),
		abilities:        make(map[string]float64),
		essence:          float64(p.server.game.startingEssence),
		health:           float64(p.server.game.startingHealth),
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
		gameCommandOut:   make(chan *CommandRequest, 10),
		gameCommandIn:    make(chan *CommandResponse, 10),
		playerCommandOut: make(chan string, 20),
		playerCommandIn:  make(chan string, 20),
		end:              make(chan bool, 1),
		prompt:           "> ",
	}

	if archetype != "" {
		if archetype, ok := p.server.game.archetypes[archetype]; ok {
			for attr, value := range archetype.Attributes {
				character.attributes[attr] = value
			}

			for ability, value := range archetype.Abilities {
				character.abilities[ability] = value
			}

			if startRoom, ok := p.server.game.rooms[archetype.StartRoom]; ok {
				character.room = startRoom
			}
		} else {
			Logger.Warn("Invalid archetype", "archetype", archetype)
			character.room = p.server.game.rooms[0]
		}

	} else {
		Logger.Info("No archetype selected")
		character.room = p.server.game.rooms[0]
	}

	err := character.Save()
	if err != nil {
		Logger.Error("Error saving character", "error", err)
		return nil, fmt.Errorf("error saving character: %w", err)
	}

	return character, nil
}

// Run is the main loop that handles player commands.
func (c *Character) Run(done chan bool) {
	if c == nil || c.player == nil {
		Logger.Error("Invalid character or player in Run method")
		done <- true
		return
	}

	// Ensure character is properly stopped when the function exits
	defer c.Stop(done)

	Logger.Debug("Starting character run", "characterName", c.name)

	// If the room is nil, move the character to room 0
	if c.room == nil {
		Logger.Warn("Character room is nil, defaulting to room ID 0", "characterName", c.name)
		c.room = c.game.rooms[0]
	}

	// Add character to game's active characters
	c.game.mutex.Lock()
	c.game.characters[c.id] = c
	c.game.mutex.Unlock()

	// Add character to the room
	c.room.mutex.Lock()
	if c.room.characters == nil {
		c.room.characters = make(map[uuid.UUID]*Character)
	}
	c.room.characters[c.id] = c
	// Update room activity timestamp
	c.room.lastActive = time.Now()
	c.room.mutex.Unlock()

	// Call HandleCharacterEntry to reset idle counter and activate scripts
	c.room.HandleCharacterEntry()

	// Notify room of arrival (without holding locks)
	SendRoomMessageExcept(c.room, fmt.Sprintf("\n\r%s has arrived.\n\r", c.name), c)

	// Show initial room description
	if err := executeLookCommand(c, []string{"look"}); err != nil {
		Logger.Warn("Failed to show initial room", "characterName", c.name, "error", err)
	}

	// Send initial prompt
	c.playerCommandOut <- c.prompt

	const idleTimeout = 30 * time.Second
	timer := time.NewTimer(idleTimeout)
	defer timer.Stop()

	// Channel to track when a command is processing
	commandProcessing := make(chan struct{}, 1)

	for {
		timer.Reset(idleTimeout)

		select {
		case inputLine, ok := <-c.playerCommandIn:
			if !ok {
				Logger.Info("Player input channel closed", "characterName", c.name)
				return
			}

			// Signal that a command is processing
			select {
			case commandProcessing <- struct{}{}:
			default:
				// Channel already has a value, which is fine
			}

			// Process the command
			isQuit, err := ProcessCommand(c, strings.TrimSpace(inputLine))
			if err != nil {
				// Send error message to player
				c.playerCommandOut <- err.Error() + "\n\r"
			} else {
				// Command processed successfully
				Logger.Debug("Command processed", "characterName", c.name, "command", inputLine)
			}

			// If the quit command was processed, exit the loop
			if isQuit {
				Logger.Info("Quit command processed, exiting character loop", "characterName", c.name)
				return
			}

			// Clear the processing signal
			select {
			case <-commandProcessing:
			default:
				// Channel already empty, which is fine
			}

			// Always send prompt after processing a command
			c.playerCommandOut <- c.prompt

		case <-c.end:
			Logger.Info("Character end signaled", "characterName", c.name)
			return

		case <-timer.C:
			if c.player == nil {
				Logger.Warn("Player connection lost", "characterName", c.name)
				return
			}
		}
	}
}

// Stop cleanly shuts down the character session
func (c *Character) Stop(done chan bool) {

	defer func() {
		done <- true
	}()

	Logger.Info("Stopping character session", "characterName", c.name)

	// Notify the room of departure before removing the character
	if c.room != nil {
		SendRoomMessageExcept(c.room, fmt.Sprintf("\n\r%s has left.\n\r", c.name), c)
	}

	// Remove character from room and update room activity timestamp
	if c.room != nil {
		c.room.mutex.Lock()
		delete(c.room.characters, c.id)
		c.room.lastActive = time.Now() // Update the timestamp when character leaves
		c.room.mutex.Unlock()
	}

	// Remove character from game's active characters
	c.game.mutex.Lock()
	delete(c.game.characters, c.id)
	c.game.mutex.Unlock()

	// Save character state
	err := c.Save()
	if err != nil {
		Logger.Error("Error saving character during shutdown", "characterName", c.name, "error", err)
	}

	// Store a reference to the player before resetting
	player := c.player

	// Use a non-blocking send to avoid deadlocks
	select {
	case c.end <- true:
		Logger.Debug("End signal sent successfully", "characterName", c.name)
	default:
		Logger.Warn("End channel is full or closed", "characterName", c.name)
	}

	// If we have a valid player reference, inform them we're returning to console
	if player != nil {
		// Reset the player's character reference
		player.character = nil
	}
}

// GetCharacterInfo returns a formatted string with character information
func (c *Character) GetCharacterInfo() string {
	c.mutex.RLock()
	defer c.mutex.RUnlock()

	var info strings.Builder
	info.WriteString(fmt.Sprintf("\n\r%s\n\r", ApplyColor("bright_white", c.name)))
	info.WriteString("----------------\n\r")

	// Basic character information
	info.WriteString(fmt.Sprintf("Health: %d\n\r", int(c.health)))
	info.WriteString(fmt.Sprintf("Essence: %d\n\r", int(c.essence)))

	// Attributes
	if len(c.attributes) > 0 {
		info.WriteString("\n\rAttributes:\n\r")
		for attr, value := range c.attributes {
			info.WriteString(fmt.Sprintf("  %-12s: %d\n\r", attr, int(value)))
		}
	}

	// Abilities - only show those above zero
	var abilitiesAboveZero []string
	for ability, value := range c.abilities {
		if value > 0 {
			abilitiesAboveZero = append(abilitiesAboveZero, ability)
		}
	}

	if len(abilitiesAboveZero) > 0 {
		info.WriteString("\n\rAbilities:\n\r")
		// Sort abilities for consistent display
		sort.Strings(abilitiesAboveZero)

		// Display each ability with value > 0
		for _, ability := range abilitiesAboveZero {
			value := c.abilities[ability]
			info.WriteString(fmt.Sprintf("  %-12s: %d\n\r", ability, int(value)))
		}
	}

	// Inventory information
	if len(c.inventory) > 0 {
		info.WriteString("\n\rInventory:\n\r")
		for _, item := range c.inventory {
			if item != nil {
				if item.isWorn {
					info.WriteString(fmt.Sprintf("  %s (worn on %s)\n\r", item.name, strings.Join(item.wornOn, ", ")))
				} else {
					info.WriteString(fmt.Sprintf("  %s\n\r", item.name))
				}
			}
		}
	} else {
		info.WriteString("\n\rYou are not carrying anything.\n\r")
	}

	// Current location
	if c.room != nil {
		info.WriteString(fmt.Sprintf("\n\rCurrently in: %s\n\r", c.room.title))
	}

	return info.String()
}

// GetSkillInfo returns a formatted string with character abilities
func (c *Character) GetSkillInfo() string {
	c.mutex.RLock()
	defer c.mutex.RUnlock()

	var skillInfo strings.Builder
	skillInfo.WriteString(fmt.Sprintf("\n\r%s's Abilities\n\r", ApplyColor("bright_cyan", c.name)))
	skillInfo.WriteString("----------------\n\r")

	// Abilities - only show those above zero
	var abilitiesAboveZero []string
	for ability, value := range c.abilities {
		if value > 0 {
			abilitiesAboveZero = append(abilitiesAboveZero, ability)
		}
	}

	if len(abilitiesAboveZero) > 0 {
		// Sort abilities for consistent display
		sort.Strings(abilitiesAboveZero)

		// Display each ability with value > 0
		for _, ability := range abilitiesAboveZero {
			value := c.abilities[ability]
			skillInfo.WriteString(fmt.Sprintf("  %-15s: %d\n\r", ability, int(value)))
		}
	} else {
		skillInfo.WriteString("  You have not developed any abilities yet.\n\r")
	}

	return skillInfo.String()
}

// LookAtTarget handles examining specific targets
func (c *Character) LookAtTarget(target string) error {
	// First check if target is in the room
	desc := c.LookAtRoomTarget(target)
	if desc != fmt.Sprintf("\n\rYou don't see '%s' here.\n\r", target) {
		c.player.commandOut <- desc
		return nil
	}

	// Then check if it's in inventory
	desc = c.LookAtInventoryItem(target)
	if desc != fmt.Sprintf("\n\rYou don't see '%s' here.\n\r", target) {
		c.player.commandOut <- desc
		return nil
	}

	// Not found anywhere
	c.player.commandOut <- fmt.Sprintf("\n\rYou don't see '%s' here.\n\r", target)
	return nil
}

// LookAtRoomTarget looks for a target in the room (character or item)
func (c *Character) LookAtRoomTarget(target string) string {
	// Check if looking at a character in the room
	if c.room != nil {
		c.room.mutex.RLock()
		for _, char := range c.room.characters {
			if char != nil && strings.Contains(strings.ToLower(char.name), target) {
				c.room.mutex.RUnlock()
				return FormatCharacterDescription(char, c)
			}
		}

		// Check if looking at an item in the room
		for _, item := range c.room.items {
			if item != nil && strings.Contains(strings.ToLower(item.name), target) {
				c.room.mutex.RUnlock()
				return formatItemDescription(item)
			}
		}

		// Check for directions/exits
		for direction, exit := range c.room.exits {
			if strings.Contains(exit.direction, target) && exit != nil && exit.visible {
				c.room.mutex.RUnlock()
				if exit.description != "" {
					return fmt.Sprintf("\n\r%s\n\r", exit.description)
				}
				return fmt.Sprintf("\n\rYou see an exit leading %s.\n\r", direction)
			}
		}
		c.room.mutex.RUnlock()
	}

	return fmt.Sprintf("\n\rYou don't see '%s' here.\n\r", target)
}

// LookAtInventoryItem looks for an item in the character's inventory
func (c *Character) LookAtInventoryItem(target string) string {
	c.mutex.RLock()
	defer c.mutex.RUnlock()

	for _, item := range c.inventory {
		if item != nil && strings.Contains(strings.ToLower(item.name), target) {
			return formatItemDescription(item)
		}
	}

	return fmt.Sprintf("\n\rYou don't see '%s' here.\n\r", target)
}

// FormatCharacterDescription creates a description of a character for look command
func FormatCharacterDescription(target *Character, viewer *Character) string {
	target.mutex.RLock()
	defer target.mutex.RUnlock()

	var desc strings.Builder
	desc.WriteString(fmt.Sprintf("\n\r%s\n\r", target.name))

	// Basic appearance info
	desc.WriteString("You see a ")

	// Add more descriptive elements here based on character attributes, equipment, etc.
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
