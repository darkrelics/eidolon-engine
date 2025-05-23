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
	"sync"
	"time"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/gofrs/uuid/v5"
)

type Character struct {
	game             *Game
	id               uuid.UUID
	player           *Player
	name             string
	attributes       map[string]float64
	abilities        map[string]float64
	essence          float64
	health           float64
	room             *Room
	inventory        map[string]*Item
	mutex            sync.RWMutex
	facing           *Character
	advancing        bool
	combatRange      map[uuid.UUID]float64
	lastEdited       time.Time
	lastSaved        time.Time
	waitUntil        time.Time             // Time when the character can execute the next command
	charState        string                // Current character state (standing, sitting, etc.)
	roomCommandOut   chan *CommandRequest  // Commands sent from character to room
	roomCommandIn    chan *CommandResponse // Responses from room to character
	gameCommandOut   chan *CommandRequest  // Commands escalated directly to game
	gameCommandIn    chan *CommandResponse // Responses from game to character
	playerCommandOut chan string           // Messages sent to player
	playerCommandIn  chan string           // Messages from player
	end              chan bool             // Channel for shutdown signaling
	prompt           string                // Character prompt
	stopped          bool                  // Flag to ensure Stop is only executed once
}

// CharacterData for unmarshalling character.
type CharacterData struct {
	CharacterID   string             `json:"CharacterID" dynamodbav:"CharacterID"`
	PlayerID      string             `json:"PlayerID" dynamodbav:"PlayerID"`
	CharacterName string             `json:"Name" dynamodbav:"character_name"`
	Attributes    map[string]float64 `json:"Attributes" dynamodbav:"Attributes"`
	Abilities     map[string]float64 `json:"Abilities" dynamodbav:"Abilities"`
	Essence       float64            `json:"Essence" dynamodbav:"Essence"`
	Health        float64            `json:"Health" dynamodbav:"Health"`
	RoomID        int64              `json:"RoomID" dynamodbav:"RoomID"`
	Inventory     map[string]string  `json:"Inventory" dynamodbav:"Inventory"`
}

func LoadCharacter(player *Player, characterID uuid.UUID) (*Character, error) {
	Logger.Debug("Loading character", "characterID", characterID)

	game := player.server.game

	// Initialize new character with default values
	character := &Character{
		game:             game,
		id:               characterID,
		player:           player,
		attributes:       make(map[string]float64),
		abilities:        make(map[string]float64),
		inventory:        make(map[string]*Item),
		mutex:            sync.RWMutex{},
		facing:           nil,
		advancing:        false,
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
		end:              make(chan bool, 5),
		prompt:           "\n\r> ",
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
	character.id, err = uuid.FromString(cd.CharacterID)
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
	inventory, err := LoadItemsForCharacter(cd.Inventory, game.database)
	if err != nil {
		Logger.Warn("Error loading character inventory", "characterID", characterID, "error", err)
	}
	character.inventory = inventory

	// Add loaded items to game's item tracking and apply trait mods for worn items
	game.mutex.Lock()
	for _, item := range character.inventory {
		if item != nil {
			game.items[item.id] = item

			// Apply trait modifications for worn items
			if item.isWorn && len(item.traitMods) > 0 {
				character.ApplyItemTraitMods(item)
			}
		}
	}
	game.mutex.Unlock()

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

// ApplyItemTraitMods applies trait modifications from an item to the character
func (c *Character) ApplyItemTraitMods(item *Item) {
	if item == nil || len(item.traitMods) == 0 {
		return
	}

	c.mutex.Lock()
	defer c.mutex.Unlock()

	Logger.Debug("Applying trait mods to character",
		"characterName", c.name,
		"itemName", item.name,
		"mods", item.traitMods)

	// Apply each trait modification
	for trait, mod := range item.traitMods {
		// For attributes
		if _, exists := c.attributes[trait]; exists {
			c.attributes[trait] += float64(mod)
			Logger.Debug("Applied attribute mod",
				"character", c.name,
				"attribute", trait,
				"mod", mod,
				"newValue", c.attributes[trait])
		}
		// For abilities
		if _, exists := c.abilities[trait]; exists {
			c.abilities[trait] += float64(mod)
			Logger.Debug("Applied ability mod",
				"character", c.name,
				"ability", trait,
				"mod", mod,
				"newValue", c.abilities[trait])
		}
		// Special case handling
		switch trait {
		case "health":
			c.health += float64(mod)
		case "essence":
			c.essence += float64(mod)
		}
	}
}

// RemoveItemTraitMods removes trait modifications from an item from the character
func (c *Character) RemoveItemTraitMods(item *Item) {
	if item == nil || len(item.traitMods) == 0 {
		return
	}

	c.mutex.Lock()
	defer c.mutex.Unlock()

	Logger.Debug("Removing trait mods from character",
		"characterName", c.name,
		"itemName", item.name,
		"mods", item.traitMods)

	// Remove each trait modification (apply the inverse)
	for trait, mod := range item.traitMods {
		// For attributes
		if _, exists := c.attributes[trait]; exists {
			c.attributes[trait] -= float64(mod)
			Logger.Debug("Removed attribute mod",
				"character", c.name,
				"attribute", trait,
				"mod", -mod,
				"newValue", c.attributes[trait])
		}
		// For abilities
		if _, exists := c.abilities[trait]; exists {
			c.abilities[trait] -= float64(mod)
			Logger.Debug("Removed ability mod",
				"character", c.name,
				"ability", trait,
				"mod", -mod,
				"newValue", c.abilities[trait])
		}
		// Special case handling
		switch trait {
		case "health":
			c.health -= float64(mod)
		case "essence":
			c.essence -= float64(mod)
		}
	}
}
