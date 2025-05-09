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
	"strings"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/google/uuid"
)

// WearLocations defines all possible locations where an item can be worn
var WearLocations = map[string]bool{
	"head":         true,
	"neck":         true,
	"shoulders":    true,
	"chest":        true,
	"back":         true,
	"arms":         true,
	"hands":        true,
	"waist":        true,
	"legs":         true,
	"feet":         true,
	"left_finger":  true,
	"right_finger": true,
	"left_wrist":   true,
	"right_wrist":  true,
}

type Character struct {
	game        *Game
	id          uuid.UUID
	player      *Player
	name        string
	attributes  map[string]float64
	abilities   map[string]float64
	essence     float64
	health      float64
	room        *Room
	inventory   map[string]*Item
	mutex       sync.RWMutex
	facing      *Character
	advancing   bool
	combatRange map[uuid.UUID]float64
	lastEdited  time.Time
	lastSaved   time.Time
	toGame      chan string
	fromGame    chan string
	toPlayer    chan string
	fromPlayer  chan string
	end         chan bool
	prompt      string
}

// CharacterData for unmarshalling character.
type CharacterData struct {
	CharacterID   string             `json:"CharacterID" dynamodbav:"CharacterID"`
	PlayerID      string             `json:"PlayerID" dynamodbav:"PlayerID"`
	CharacterName string             `json:"Name" dynamodbav:"Name"`
	Attributes    map[string]float64 `json:"Attributes" dynamodbav:"Attributes"`
	Abilities     map[string]float64 `json:"Abilities" dynamodbav:"Abilities"`
	Essence       float64            `json:"Essence" dynamodbav:"Essence"`
	Health        float64            `json:"Health" dynamodbav:"Health"`
	RoomID        int64              `json:"RoomID" dynamodbav:"RoomID"`
	Inventory     map[string]string  `json:"Inventory" dynamodbav:"Inventory"`
}

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

func LoadCharacter(player *Player, characterID uuid.UUID) (*Character, error) {
	Logger.Debug("Loading character", "characterID", characterID)

	game := player.server.game

	// Initialize new character with default values
	character := &Character{
		game:        game,
		id:          characterID,
		player:      player,
		attributes:  make(map[string]float64),
		abilities:   make(map[string]float64),
		inventory:   make(map[string]*Item),
		mutex:       sync.RWMutex{},
		facing:      nil,
		advancing:   false,
		combatRange: make(map[uuid.UUID]float64),
		lastEdited:  time.Now(),
		toGame:      make(chan string, 10),
		fromGame:    make(chan string, 10),
		toPlayer:    make(chan string, 10),
		fromPlayer:  make(chan string, 10),
		end:         make(chan bool, 5),
		prompt:      "\n\r> ",
	}

	// Load character data from database
	cd := &CharacterData{}
	key := map[string]types.AttributeValue{
		"CharacterID": &types.AttributeValueMemberS{Value: characterID.String()},
	}

	if err := game.database.Get("characters", key, cd); err != nil {
		return nil, fmt.Errorf("error loading character data: %w", err)
	}

	// Populate character from data
	var err error
	character.id, err = uuid.Parse(cd.CharacterID)
	if err != nil {
		return nil, fmt.Errorf("parse character ID: %w", err)
	}
	character.name = cd.CharacterName
	character.attributes = cd.Attributes
	character.abilities = cd.Abilities
	character.essence = cd.Essence
	character.health = cd.Health

	// Set character room
	room, exists := game.rooms[cd.RoomID]
	if !exists {
		Logger.Warn("Room not found, defaulting to room ID 0", "roomID", cd.RoomID)
		room, exists = game.rooms[0]
		if !exists {
			return nil, fmt.Errorf("default room not found")
		}
	}
	character.room = room

	// Load inventory items
	for name, itemIDStr := range cd.Inventory {
		itemID, err := uuid.Parse(itemIDStr)
		if err != nil {
			Logger.Error("Error parsing item UUID", "itemID", itemIDStr, "error", err)
			continue
		}
		item, err := LoadItem(itemID.String(), game.database)
		if err != nil {
			Logger.Error("Error loading item for character", "itemID", itemID, "characterName", character.name, "error", err)
			continue
		}
		character.inventory[name] = item
	}

	// Add character to game state
	game.mutex.Lock()
	game.characters[character.id] = character
	game.mutex.Unlock()

	return character, nil
}

// Removes a character from the database by its ID
func (p *Player) DeleteCharacter(characterID uuid.UUID) error {
	Logger.Info("Deleting character from database", "characterID", characterID)

	// Check if character is currently active in the game
	p.server.game.mutex.RLock()
	activeChar, isActive := p.server.game.characters[characterID]
	p.server.game.mutex.RUnlock()

	// If character is active, stop it first
	if isActive && activeChar != nil {
		Logger.Info("Stopping active character before deletion", "characterName", activeChar.name)
		activeChar.Stop(activeChar.end)
	}

	// Create the key for DynamoDB deletion
	key := map[string]types.AttributeValue{
		"CharacterID": &types.AttributeValueMemberS{Value: characterID.String()},
	}

	// Delete the character from the database
	err := p.server.database.Delete("characters", key)
	if err != nil {
		Logger.Error("Failed to delete character", "characterID", characterID, "error", err)
		return fmt.Errorf("failed to delete character: %w", err)
	}

	Logger.Info("Character deleted successfully", "characterID", characterID)
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
		game:        p.server.game,
		id:          GenerateUUIDv7(),
		player:      p,
		name:        name,
		attributes:  make(map[string]float64),
		abilities:   make(map[string]float64),
		essence:     float64(p.server.game.startingEssence),
		health:      float64(p.server.game.startingHealth),
		inventory:   make(map[string]*Item),
		mutex:       sync.RWMutex{},
		advancing:   false,
		facing:      nil,
		combatRange: make(map[uuid.UUID]float64),
		lastEdited:  time.Now(),
		toGame:      make(chan string, 10),
		fromGame:    make(chan string, 10),
		end:         make(chan bool, 1),
		prompt:      "> ",
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

	// Notify room of arrival (without holding locks)
	SendRoomMessageExcept(c.room, fmt.Sprintf("\n\r%s has arrived.\n\r", c.name), c)

	// Show initial room description
	if err := executeLookCommand(c, []string{"look"}); err != nil {
		Logger.Warn("Failed to show initial room", "characterName", c.name, "error", err)
	}

	// Send initial prompt
	c.player.toPlayer <- c.prompt

	const idleTimeout = 30 * time.Second
	timer := time.NewTimer(idleTimeout)
	defer timer.Stop()

	// Channel to track when a command is processing
	commandProcessing := make(chan struct{}, 1)

	for {
		timer.Reset(idleTimeout)

		select {
		case inputLine, ok := <-c.player.fromPlayer:
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
				c.player.toPlayer <- err.Error() + "\n\r"
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
			c.player.toPlayer <- c.prompt

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

// formatCharacterDescription creates a description of a character
func formatCharacterDescription(target *Character, _ *Character) string {
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

func GenerateUUIDv7() uuid.UUID {

	uuid_type_7, err := uuid.NewV7()
	if err != nil {
		Logger.Error("Error generating UUIDv7", "error", err)
		return uuid.Nil
	}
	return uuid_type_7
}
