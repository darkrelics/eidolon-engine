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

func (c *Character) CharacterToData() *CharacterData {

	Logger.Info("CharacterToData", "CharacterID", c.id.String())

	inventory := make(map[string]string)
	for name, item := range c.inventory {
		inventory[name] = item.id.String()
	}

	return &CharacterData{
		CharacterID:   c.id.String(),
		PlayerID:      c.player.id,
		CharacterName: c.name,
		Attributes:    c.attributes,
		Abilities:     c.abilities,
		Essence:       c.essence,
		Health:        c.health,
		RoomID:        c.room.roomID,
		Inventory:     inventory,
	}
}

func (p *Player) CharacterFromData(characterData *CharacterData) (*Character, error) {

	Logger.Info("CharacterFromData", "CharacterID", characterData.CharacterID)

	character := &Character{
		game:        p.server.game,
		id:          uuid.MustParse(characterData.CharacterID),
		player:      p,
		name:        characterData.CharacterName,
		attributes:  characterData.Attributes,
		abilities:   characterData.Abilities,
		essence:     characterData.Essence,
		health:      characterData.Health,
		inventory:   make(map[string]*Item),
		mutex:       sync.RWMutex{},
		facing:      nil,
		advancing:   false,
		combatRange: make(map[uuid.UUID]float64),
		lastEdited:  time.Now(),
		lastSaved:   time.Now(),
		toGame:      make(chan string, 10),
		fromGame:    make(chan string, 10),
		toPlayer:    make(chan string, 10),
		fromPlayer:  make(chan string, 10),
		end:         make(chan bool, 1),
		prompt:      "> ",
	}

	// Place character in room
	room, exists := p.server.game.rooms[characterData.RoomID]
	if !exists {
		Logger.Warn("Room does not exist", "roomID", characterData.RoomID)
		room, exists = p.server.game.rooms[0]
		if !exists {
			Logger.Error("Starting room does not exist")
			return nil, fmt.Errorf("starting room does not exist")
		}
	}

	character.room = room

	// initialize inventory

	return character, nil
}

// Save the character to the database

func (c *Character) Save() error {

	Logger.Info("Saving Character", "CharacterID", c.id.String())

	characterData := c.CharacterToData()

	err := c.game.database.Put("characters", *characterData)
	if err != nil {
		Logger.Error("Error saving character", "error", err)
		return fmt.Errorf("error saving character: %w", err)
	}

	Logger.Debug("Character saved", "character", c.id.String())

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

func (p *Player) LoadCharacter(characterID uuid.UUID) (*Character, error) {

	Logger.Info("Loading Character", "CharacterID", characterID.String())

	characterData := &CharacterData{}
	key := map[string]*dynamodb.AttributeValue{
		"CharacterID": {S: aws.String(characterID.String())},
	}

	if err := p.server.database.Get("characters", key, characterData); err != nil {
		Logger.Error("Error loading character", "error", err)
		return nil, fmt.Errorf("error loading character: %w", err)
	}

	character, err := p.CharacterFromData(characterData)
	if err != nil {
		Logger.Error("Error creating character from data", "error", err)
		return nil, fmt.Errorf("error creating character from data: %w", err)
	}

	game := p.server.game
	game.mutex.Lock()
	game.characters[character.id] = character
	game.mutex.Unlock()

	return character, nil

}
