package interface_ssh

import (
	"context"
	"net"
	"sync"
	"time"

	"golang.org/x/crypto/ssh"

	"github.com/robinje/multi-user-dungeon/core"
)

type SSH_Config struct {
	Context     context.Context
	Mutex       sync.RWMutex
	WaitGroup   sync.WaitGroup
	Database    *core.KeyPair
	StartTime   time.Time
	Port        uint16
	Listener    net.Listener
	SSHConfig   *ssh.ServerConfig
	PlayerCount uint64
	PlayerIndex *core.Index
	Players     map[uint64]*core.Player
	ActiveMotDs []*core.MOTD

	CognitoClientID     string
	CognitoClientSecret string
	Region              string
	LogLevel            int
	ApplicationName     string
	LogGroup            string
	LogStream           string
	MetricNamespace     string
	PrivateKeyPath      string
}
