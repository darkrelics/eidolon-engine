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
	"context"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/service/dynamodb"
	"github.com/google/uuid"
	"golang.org/x/crypto/ssh"
)

type Player struct {
	index         uint64
	id            string
	toPlayer      chan string
	fromPlayer    chan string
	playerError   chan error
	echo          bool
	prompt        string
	connection    ssh.Channel
	consoleWidth  int
	consoleHeight int
	characterList map[string]uuid.UUID
	seenMotD      []uuid.UUID
	character     *Character
	login         time.Time
	server        *Server
	mutex         sync.RWMutex
	interfaceCtx  context.Context
	ctx           context.Context
	cancel        context.CancelFunc
	shutdownOnce  sync.Once
}

type PlayerData struct {
	PlayerID      string            `json:"PlayerID" dynamodbav:"PlayerID"`
	CharacterList map[string]string `json:"characterList" dynamodbav:"CharacterList"`
	SeenMotDs     []string          `json:"seenMotD" dynamodbav:"SeenMotD"`
}

func (p *Player) LoadPlayer(playerName string) error {

	Logger.Debug("Loading player data", "player_name", playerName)

	database := p.server.database

	key := map[string]*dynamodb.AttributeValue{
		"PlayerID": {S: aws.String(playerName)},
	}

	var playerData PlayerData

	err := database.Get("players", key, &playerData)
	if err != nil {
		// Return an empty map for new players.

		// TODO: Build an initalization Lambda function for Cognito.
		Logger.Info("First time player", "playerName", playerName)
	}

	return nil

}

func NewPlayerSSH(server *Server, playerName string, conn ssh.Channel, interfaceCtx context.Context) (*Player, error) {

	ctx, cancel := context.WithCancel(server.globalContext)

	player := &Player{
		server:        server,
		id:            playerName,
		toPlayer:      make(chan string, 10),
		fromPlayer:    make(chan string, 10),
		playerError:   make(chan error, 1),
		echo:          true,
		connection:    conn,
		consoleWidth:  80,
		consoleHeight: 24,
		login:         time.Now(),
		interfaceCtx:  interfaceCtx,
		ctx:           ctx,
		cancel:        cancel,
		shutdownOnce:  sync.Once{},
	}

	return player, nil

}

func (p *Player) Run(requests <-chan *ssh.Request) {
	Logger.Info("Player connected", "player_name", p.id)
	defer func() {
		Logger.Info("Player disconnected", "player_name", p.id)
		p.shutdownOnce.Do(func() {
			p.cancel()
			close(p.toPlayer)
			close(p.fromPlayer)
			close(p.playerError)
			if p.character != nil {
				// Save character state
				if err := p.character.Save(); err != nil {
					Logger.Error("Error saving character on disconnect", "error", err)
				}
				p.character = nil
			}
			p.connection.Close()
		})
	}()

	// Wait for shutdown conditions
	select {
	case <-p.ctx.Done():
		return
	case <-p.interfaceCtx.Done():
		return
	case err := <-p.playerError:
		Logger.Error("Player error", "player_name", p.id, "error", err)
		return
	}
}
