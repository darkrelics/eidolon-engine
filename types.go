package main

import (
	"context"
	"net"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go/service/dynamodb"

	"github.com/google/uuid"
	"golang.org/x/crypto/ssh"
)

type Interface_SSH struct {
	Config         *Configuration
	GlobalContext  context.Context
	ServerContext  context.Context
	Context        context.Context
	Cancel         context.CancelFunc
	Mutex          sync.RWMutex
	StartTime      time.Time
	Port           uint16
	PrivateKeyPath string
	Listener       net.Listener
	Connections    uint64
	Database       *KeyPair
	SSHConfig      *ssh.ServerConfig
}

// The Index struct is to be depricated in favor of UUIDs

type KeyPair struct {
	db *dynamodb.DynamoDB
}

type Player struct {
	Index         uint64
	PlayerID      string
	ToPlayer      chan string
	FromPlayer    chan string
	PlayerError   chan error
	Echo          bool
	Prompt        string
	Connection    ssh.Channel
	ConsoleWidth  int
	ConsoleHeight int
	SeenMotD      []uuid.UUID
	CharacterList map[string]uuid.UUID
	Character     *Character
	LoginTime     time.Time
	Mutex         sync.RWMutex
	Context       context.Context
	Cancel        context.CancelFunc
}

type PlayerData struct {
	PlayerID      string            `json:"PlayerID" dynamodbav:"PlayerID"`
	CharacterList map[string]string `json:"characterList" dynamodbav:"CharacterList"`
	SeenMotDs     []string          `json:"seenMotD" dynamodbav:"SeenMotD"`
}

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

type Archetype struct {
	ArchetypeName string             `json:"ArchetypeName" dynamodbav:"ArchetypeName"`
	Description   string             `json:"Description" dynamodbav:"Description"`
	Attributes    map[string]float64 `json:"Attributes" dynamodbav:"Attributes"`
	Abilities     map[string]float64 `json:"Abilities" dynamodbav:"Abilities"`
	StartRoom     int64              `json:"StartRoom" dynamodbav:"StartRoom"`
}

type Item struct {
	ID          uuid.UUID
	PrototypeID uuid.UUID
	Name        string
	Description string
	Mass        float64
	Value       uint64
	Stackable   bool
	MaxStack    uint32
	Quantity    uint32
	Wearable    bool
	WornOn      []string
	Verbs       map[string]string
	Overrides   map[string]string
	TraitMods   map[string]int8
	Container   bool
	Contents    []*Item
	IsWorn      bool
	CanPickUp   bool
	Metadata    map[string]string
	Mutex       sync.RWMutex
	LastEdited  time.Time
	LastSaved   time.Time
}

type ItemData struct {
	ItemID      string            `json:"itemId" dynamodbav:"ItemID"`
	PrototypeID string            `json:"prototypeID" dynamodbav:"PrototypeID"`
	Name        string            `json:"name" dynamodbav:"Name"`
	Description string            `json:"description" dynamodbav:"Description"`
	Mass        float64           `json:"mass" dynamodbav:"Mass"`
	Value       uint64            `json:"value" dynamodbav:"Value"`
	Stackable   bool              `json:"stackable" dynamodbav:"Stackable"`
	MaxStack    uint32            `json:"max_stack" dynamodbav:"MaxStack"`
	Quantity    uint32            `json:"quantity" dynamodbav:"Quantity"`
	Wearable    bool              `json:"wearable" dynamodbav:"Wearable"`
	WornOn      []string          `json:"worn_on" dynamodbav:"WornOn"`
	Verbs       map[string]string `json:"verbs" dynamodbav:"Verbs"`
	Overrides   map[string]string `json:"overrides" dynamodbav:"Overrides"`
	TraitMods   map[string]int8   `json:"trait_mods" dynamodbav:"TraitMods"`
	Container   bool              `json:"container" dynamodbav:"Container"`
	Contents    []string          `json:"contents" dynamodbav:"Contents"`
	IsWorn      bool              `json:"is_worn" dynamodbav:"IsWorn"`
	CanPickUp   bool              `json:"can_pick_up" dynamodbav:"CanPickUp"`
	Metadata    map[string]string `json:"metadata" dynamodbav:"Metadata"`
}

type Prototype struct {
	ID          uuid.UUID
	Name        string
	Description string
	Mass        float64
	Value       uint64
	Stackable   bool
	MaxStack    uint32
	Quantity    uint32
	Wearable    bool
	WornOn      []string
	Verbs       map[string]string
	Overrides   map[string]string
	TraitMods   map[string]int8
	Container   bool
	Contents    []uuid.UUID
	CanPickUp   bool
	Metadata    map[string]string
	Mutex       sync.RWMutex
	LastEdited  time.Time
	LastSaved   time.Time
}

type PrototypeData struct {
	PrototypeID string            `json:"id" dynamodbav:"prototypeID"`
	Name        string            `json:"name" dynamodbav:"name"`
	Description string            `json:"description" dynamodbav:"description"`
	Mass        float64           `json:"mass" dynamodbav:"mass"`
	Value       uint64            `json:"value" dynamodbav:"value"`
	Stackable   bool              `json:"stackable" dynamodbav:"stackable"`
	MaxStack    uint32            `json:"max_stack" dynamodbav:"max_stack"`
	Quantity    uint32            `json:"quantity" dynamodbav:"quantity"`
	Wearable    bool              `json:"wearable" dynamodbav:"wearable"`
	WornOn      []string          `json:"worn_on" dynamodbav:"worn_on"`
	Verbs       map[string]string `json:"verbs" dynamodbav:"verbs"`
	Overrides   map[string]string `json:"overrides" dynamodbav:"overrides"`
	TraitMods   map[string]int8   `json:"trait_mods" dynamodbav:"trait_mods"`
	Container   bool              `json:"container" dynamodbav:"container"`
	Contents    []string          `json:"contents" dynamodbav:"contents"`
	CanPickUp   bool              `json:"can_pick_up" dynamodbav:"can_pick_up"`
	Metadata    map[string]string `json:"metadata" dynamodbav:"metadata"`
}
