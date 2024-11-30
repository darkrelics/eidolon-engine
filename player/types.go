package player

import (
	"context"
	"sync"
	"time"

	"github.com/google/uuid"
	"golang.org/x/crypto/ssh"
)

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
