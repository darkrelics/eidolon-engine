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
	skills           map[string]float64
	essence          float64
	health           float64
	room             *Room
	inventory        map[string]*Item
	leftHand         *Item // Item held in left hand
	rightHand        *Item // Item held in right hand
	mutex            sync.RWMutex
	facing           *Character
	advancing        bool
	combatRange      map[uuid.UUID]float64
	lastEdited       time.Time
	lastSaved        time.Time
	waitUntil        time.Time             // Time when the character can execute the next command
	charState        string                // Current character state (standing, sitting, etc.)
	hidden           bool                  // Whether the character is hidden
	lastHideAttempt  time.Time             // Time of last hide attempt for rate limiting
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
	Skills        map[string]float64 `json:"Skills" dynamodbav:"Skills"`
	Essence       float64            `json:"Essence" dynamodbav:"Essence"`
	Health        float64            `json:"Health" dynamodbav:"Health"`
	RoomID        int64              `json:"RoomID" dynamodbav:"RoomID"`
	Inventory     map[string]string  `json:"Inventory" dynamodbav:"Inventory"`
	LeftHandID    string             `json:"LeftHandID,omitempty" dynamodbav:"LeftHandID,omitempty"`
	RightHandID   string             `json:"RightHandID,omitempty" dynamodbav:"RightHandID,omitempty"`
	Hidden        bool               `json:"Hidden" dynamodbav:"Hidden"`
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
		skills:           make(map[string]float64),
		inventory:        make(map[string]*Item),
		leftHand:         nil,
		rightHand:        nil,
		mutex:            sync.RWMutex{},
		facing:           nil,
		advancing:        false,
		combatRange:      make(map[uuid.UUID]float64),
		lastEdited:       time.Now(),
		charState:        "standing",
		hidden:           false,
		waitUntil:        time.Now(),
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

	if err := game.database.Get(game.ctx, "characters", key, cd); err != nil {
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
	character.skills = cd.Skills
	character.essence = cd.Essence
	character.health = cd.Health
	character.hidden = cd.Hidden

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
	inventory, err := LoadItemsForCharacter(game.ctx, cd.Inventory, game.database)
	if err != nil {
		Logger.Warn("Error loading character inventory", "characterID", characterID, "error", err)
	}
	character.inventory = inventory

	// Load hand items
	if cd.LeftHandID != "" {
		leftHandID, err := uuid.FromString(cd.LeftHandID)
		if err == nil {
			leftItem, err := LoadItem(game.ctx, leftHandID.String(), game.database)
			if err != nil {
				Logger.Warn("Error loading left hand item", "itemID", cd.LeftHandID, "error", err)
			} else {
				character.leftHand = leftItem
			}
		}
	}

	if cd.RightHandID != "" {
		rightHandID, err := uuid.FromString(cd.RightHandID)
		if err == nil {
			rightItem, err := LoadItem(game.ctx, rightHandID.String(), game.database)
			if err != nil {
				Logger.Warn("Error loading right hand item", "itemID", cd.RightHandID, "error", err)
			} else {
				character.rightHand = rightItem
			}
		}
	}

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
	// Also add hand items to game tracking
	if character.leftHand != nil {
		game.items[character.leftHand.id] = character.leftHand
	}
	if character.rightHand != nil {
		game.items[character.rightHand.id] = character.rightHand
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
		activeChar.Stop()
	}

	// Load character data to get inventory and hand items if character is not active
	var inventoryItems map[string]string
	var handItemIDs []string
	if !isActive {
		// Load character data to get inventory and hands
		charKey := map[string]types.AttributeValue{
			"CharacterID": &types.AttributeValueMemberS{Value: characterID.String()},
		}
		var charData CharacterData
		err := p.server.database.Get(p.server.ctx, "characters", charKey, &charData)
		if err == nil {
			inventoryItems = charData.Inventory
			if charData.LeftHandID != "" {
				handItemIDs = append(handItemIDs, charData.LeftHandID)
			}
			if charData.RightHandID != "" {
				handItemIDs = append(handItemIDs, charData.RightHandID)
			}
		} else {
			Logger.Warn("Could not load character data for inventory cleanup", "characterID", characterID, "error", err)
		}
	} else if activeChar != nil {
		// Get inventory and hands from active character
		activeChar.mutex.RLock()
		inventoryItems = make(map[string]string)
		for slot, item := range activeChar.inventory {
			if item != nil {
				inventoryItems[slot] = item.id.String()
			}
		}
		if activeChar.leftHand != nil {
			handItemIDs = append(handItemIDs, activeChar.leftHand.id.String())
		}
		if activeChar.rightHand != nil {
			handItemIDs = append(handItemIDs, activeChar.rightHand.id.String())
		}
		activeChar.mutex.RUnlock()
	}

	// Clean up inventory and hand items from game.items map
	totalItems := len(inventoryItems) + len(handItemIDs)
	if totalItems > 0 {
		p.server.game.mutex.Lock()
		// Clean up inventory items
		for _, itemIDStr := range inventoryItems {
			itemID, err := uuid.FromString(itemIDStr)
			if err != nil {
				Logger.Warn("Invalid item ID in character inventory", "itemID", itemIDStr, "error", err)
				continue
			}
			delete(p.server.game.items, itemID)
			Logger.Debug("Removed item from game.items", "itemID", itemID, "characterID", characterID)
		}
		// Clean up hand items
		for _, itemIDStr := range handItemIDs {
			itemID, err := uuid.FromString(itemIDStr)
			if err != nil {
				Logger.Warn("Invalid item ID in character hands", "itemID", itemIDStr, "error", err)
				continue
			}
			delete(p.server.game.items, itemID)
			Logger.Debug("Removed hand item from game.items", "itemID", itemID, "characterID", characterID)
		}
		p.server.game.mutex.Unlock()
		Logger.Info("Cleaned up character items", "characterID", characterID, "itemCount", totalItems)
	}

	// Create the key for DynamoDB deletion
	key := map[string]types.AttributeValue{
		"CharacterID": &types.AttributeValueMemberS{Value: characterID.String()},
	}

	// Delete the character from the database
	err := p.server.database.Delete(p.server.ctx, "characters", key)
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
		// For skills
		if _, exists := c.skills[trait]; exists {
			c.skills[trait] += float64(mod)
			Logger.Debug("Applied skill mod",
				"character", c.name,
				"skill", trait,
				"mod", mod,
				"newValue", c.skills[trait])
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
		// For skills
		if _, exists := c.skills[trait]; exists {
			c.skills[trait] -= float64(mod)
			Logger.Debug("Removed skill mod",
				"character", c.name,
				"skill", trait,
				"mod", -mod,
				"newValue", c.skills[trait])
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

// GetSkill safely retrieves a skill value, returning 0 if not found
func (c *Character) GetSkill(skillName string) float64 {
	c.mutex.RLock()
	defer c.mutex.RUnlock()
	
	if value, exists := c.skills[skillName]; exists {
		return value
	}
	return 0.0
}

// GetAttribute safely retrieves an attribute value, returning 0 if not found
func (c *Character) GetAttribute(attrName string) float64 {
	c.mutex.RLock()
	defer c.mutex.RUnlock()
	
	if value, exists := c.attributes[attrName]; exists {
		return value
	}
	return 0.0
}

// IsHidden returns whether the character is currently hidden
func (c *Character) IsHidden() bool {
	c.mutex.RLock()
	defer c.mutex.RUnlock()
	return c.hidden
}

// SetHidden sets the character's hidden state
func (c *Character) SetHidden(hidden bool) {
	c.mutex.Lock()
	defer c.mutex.Unlock()
	c.hidden = hidden
	c.lastEdited = time.Now()
}

// IsVisibleTo checks if this character is visible to another character
func (c *Character) IsVisibleTo(observer *Character) bool {
	c.mutex.RLock()
	defer c.mutex.RUnlock()
	
	if c == observer {
		return true // Always visible to self
	}
	
	return !c.hidden
}
