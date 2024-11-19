package main

import (
	"context"
	"net"
	"sync"
	"time"

	"golang.org/x/crypto/ssh"

	"github.com/robinje/multi-user-dungeon/core"
)

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

type Server struct {
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
