package core

import (
	"context"
	"log/slog"
	"net"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs"
	"github.com/aws/aws-sdk-go/service/dynamodb"
	"github.com/bits-and-blooms/bloom/v3"
	"github.com/google/uuid"
	"golang.org/x/crypto/ssh"
)

// The Index struct is to be depricated in favor of UUIDs
type Index struct {
	IndexID uint64
	mu      sync.RWMutex
}

type Configuration struct {
	Server struct {
		Port           uint16 `yaml:"Port"`
		PrivateKeyPath string `yaml:"PrivateKeyPath"`
	} `yaml:"Server"`
	Aws struct {
		Region string `yaml:"Region"`
	} `yaml:"Aws"`
	Cognito struct {
		UserPoolID     string `yaml:"UserPoolId"`
		ClientSecret   string `yaml:"UserPoolClientSecret"`
		ClientID       string `yaml:"UserPoolClientId"`
		UserPoolDomain string `yaml:"UserPoolDomain"`
		UserPoolArn    string `yaml:"UserPoolArn"`
	} `yaml:"Cognito"`
	Game struct {
		Balance         float64 `yaml:"Balance"`
		AutoSave        uint16  `yaml:"AutoSave"`
		StartingEssence uint16  `yaml:"StartingEssence"`
		StartingHealth  uint16  `yaml:"StartingHealth"`
	} `yaml:"Game"`
	Logging struct {
		ApplicationName string `yaml:"ApplicationName"`
		LogLevel        int    `yaml:"LogLevel"`
		LogGroup        string `yaml:"LogGroup"`
		LogStream       string `yaml:"LogStream"`
		MetricNamespace string `yaml:"MetricNamespace"`
	} `yaml:"Logging"`
}

type KeyPair struct {
	db *dynamodb.DynamoDB
}

type Server struct {
	Config      *Configuration
	Context     context.Context
	Mutex       sync.RWMutex
	WaitGroup   sync.WaitGroup
	Database    *KeyPair
	StartTime   time.Time
	Port        uint16
	Listener    net.Listener
	SSHConfig   *ssh.ServerConfig
	PlayerCount uint64
	PlayerIndex *Index
	Players     map[uint64]*Player
	ActiveMotDs []*MOTD
}

type Game struct {
	Config               *Configuration
	Context              context.Context
	Mutex                sync.RWMutex
	WaitGroup            sync.WaitGroup
	Ticker               *time.Ticker
	Database             *KeyPair
	ArcheTypes           map[string]*Archetype
	CharacterBloomFilter *bloom.BloomFilter
	Characters           map[uuid.UUID]*Character
	Rooms                map[int64]*Room
	Prototypes           map[uuid.UUID]*Prototype
	Items                map[uuid.UUID]*Item
}

type Player struct {
	Server        *Server
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
	CTX           context.Context
	Cancel        context.CancelFunc
}

type PlayerData struct {
	PlayerID      string            `json:"PlayerID" dynamodbav:"PlayerID"`
	CharacterList map[string]string `json:"characterList" dynamodbav:"CharacterList"`
	SeenMotDs     []string          `json:"seenMotD" dynamodbav:"SeenMotD"`
}

// Room represents the in-memory structure for a room
type Room struct {
	RoomID      int64
	Area        string
	Title       string
	Description string
	Exits       map[string]*Exit
	Characters  map[uuid.UUID]*Character
	Items       map[uuid.UUID]*Item
	Mutex       sync.RWMutex
	LastEdited  time.Time
	LastSaved   time.Time
}

// RoomData represents the structure for storing room data in DynamoDB
type RoomData struct {
	RoomID      int64    `json:"roomID" dynamodbav:"RoomID"`
	Area        string   `json:"area" dynamodbav:"Area"`
	Title       string   `json:"title" dynamodbav:"Title"`
	Description string   `json:"description" dynamodbav:"Description"`
	ExitIDs     []string `json:"exitID" dynamodbav:"ExitID"`
	ItemIDs     []string `json:"itemID" dynamodbav:"ItemID"`
}

// Exit represents the in-memory structure for an exit
type Exit struct {
	ExitID     uuid.UUID
	Direction  string
	TargetRoom *Room
	Visible    bool
	LastEdited time.Time
	LastSaved  time.Time
}

// ExitData represents the structure for storing exit data in DynamoDB
type ExitData struct {
	ExitID     string `json:"ExitID" dynamodbav:"ExitID"`
	Direction  string `json:"Direction" dynamodbav:"Direction"`
	TargetRoom int64  `json:"TargetRoom" dynamodbav:"TargetRoom"`
	Visible    bool   `json:"Visible" dynamodbav:"Visible"`
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

type CloudWatchHandler struct {
	client      *cloudwatchlogs.Client
	logGroup    string
	logStream   string
	attrs       []slog.Attr
	mutex       sync.RWMutex
	initialized bool
}

type MultiHandler struct {
	handlers []slog.Handler
}

type MOTD struct {
	MotdID    uuid.UUID
	Active    bool
	Message   string
	CreatedAt time.Time
}

type MOTDData struct {
	MotdID    string `json:"MotdID" dynamodbav:"MotdID"`
	Active    bool   `json:"active" dynamodbav:"Active"`
	Message   string `json:"message" dynamodbav:"Message"`
	CreatedAt string `json:"createdAt" dynamodbav:"CreatedAt"`
}
