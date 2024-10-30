package main

import (
	"context"

	"github.com/robinje/multi-user-dungeon/core"
	"golang.org/x/crypto/ssh"
)

func handleChannels(server *core.Server, game *core.Game, sshConn *ssh.ServerConn, channels <-chan ssh.NewChannel) {
	playerName := sshConn.User()
	core.Logger.Info("New connection", "address", sshConn.RemoteAddr().String(), "user", playerName)

	for newChannel := range channels {
		channel, requests, err := newChannel.Accept()
		if err != nil {
			core.Logger.Error("Could not accept channel", "error", err)
			continue
		}

		// Simple player initialization
		ctx, cancel := context.WithCancel(context.Background())
		player := &core.Player{
			PlayerID:   playerName,
			Index:      server.PlayerIndex.GetID(),
			ToPlayer:   make(chan string, 100),
			FromPlayer: make(chan string, 10),
			Connection: channel,
			Game:       game,
			CTX:        ctx,
			Cancel:     cancel,
		}

		server.Mutex.Lock()
		game.Server.Players[player.Index] = player
		game.Server.Mutex.Unlock()

		go HandleSSHRequests(player, requests)
		go handlePlayerSession(server, game, player)

		core.Logger.Info("Player session started", "playerName", playerName)
	}
}

// HandleSSHRequests handles SSH requests from the client.
func HandleSSHRequests(player *core.Player, requests <-chan *ssh.Request) {
	core.Logger.Debug("Handling SSH requests for player", "player_name", player.PlayerID)

	for req := range requests {
		switch req.Type {
		case "shell":
			// Accept the shell request
			req.Reply(true, nil)
		case "pty-req":
			// Parse terminal dimensions
			termLen := req.Payload[3]
			w, h := core.ParseDims(req.Payload[termLen+4:])
			player.ConsoleWidth, player.ConsoleHeight = w, h
			req.Reply(true, nil)
		case "window-change":
			// Update terminal dimensions
			w, h := core.ParseDims(req.Payload)
			player.ConsoleWidth, player.ConsoleHeight = w, h
		default:
			// Reject unsupported requests
			req.Reply(false, nil)
		}
	}
}
