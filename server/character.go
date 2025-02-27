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

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/service/dynamodb"
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
		end:         make(chan bool),
		prompt:      "\n\r> ",
	}

	// Load character data from database
	cd := &CharacterData{}
	key := map[string]*dynamodb.AttributeValue{
		"CharacterID": {S: aws.String(characterID.String())},
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
	// for name, itemIDStr := range cd.Inventory {
	// 	itemID, err := uuid.Parse(itemIDStr)
	// 	if err != nil {
	// 		Logger.Error("Error parsing item UUID", "itemID", itemIDStr, "error", err)
	// 		continue
	// 	}
	// 	item, err := LoadItem(itemID.String(), game.database)
	// 	if err != nil {
	// 		Logger.Error("Error loading item for character", "itemID", itemID, "characterName", character.Name, "error", err)
	// 		continue
	// 	}
	// 	character.inventory[name] = item
	// }

	// Add character to game state
	game.mutex.Lock()
	game.characters[character.id] = character
	game.mutex.Unlock()

	return character, nil
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
		id:          uuid.New(),
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

// Run starts the character's main gameplay loop
func (c *Character) Run() {
	Logger.Info("Starting character session", "characterName", c.name)

	// Add character to the game's active characters
	c.game.mutex.Lock()
	c.game.characters[c.id] = c
	c.game.mutex.Unlock()

	// Add character to the room
	c.room.mutex.Lock()
	c.room.characters[c.id] = c
	c.room.mutex.Unlock()

	// Main input loop
	for {
		// Send prompt to player
		c.toPlayer <- c.prompt

		select {
		case <-c.end:
			Logger.Info("Character session ending via end channel", "characterName", c.name)
			return

		case input, ok := <-c.fromPlayer:
			if !ok {
				Logger.Info("Character input channel closed", "characterName", c.name)
				return
			}

			// Process the input
			cmd := strings.TrimSpace(strings.ToLower(input))

			if cmd == "quit" || cmd == "exit" {
				c.toPlayer <- "\nLeaving game...\n"
				close(c.end)
				return
			} else if cmd == "" {
				// Empty command, just send prompt again
				continue
			} else {
				c.toPlayer <- fmt.Sprintf("You entered: %s\n", cmd)
			}
		}
	}
}

// Stop cleanly shuts down the character session
func (c *Character) Stop() {
	Logger.Info("Stopping character session", "characterName", c.name)

	// Remove character from room
	if c.room != nil {
		c.room.mutex.Lock()
		delete(c.room.characters, c.id)
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

	// Signal the end channel if it hasn't been closed already
	select {
	case c.end <- true:
	default:
		// Channel might already be closed or full
	}
}
