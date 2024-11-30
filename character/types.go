package character

import (
	"sync"
	"time"

	"github.com/google/uuid"
)

type Character struct {
	Game        *Game
	ID          uuid.UUID
	Player      *Player
	Name        string
	Attributes  map[string]float64
	Abilities   map[string]float64
	Essence     float64
	Health      float64
	Room        *Room
	Inventory   map[string]*Item
	Mutex       sync.RWMutex
	Facing      *Character
	Advancing   bool // true when character is advancing towards their facing target
	CombatRange map[uuid.UUID]float64
	LastEdited  time.Time
	LastSaved   time.Time
	End         chan bool
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
