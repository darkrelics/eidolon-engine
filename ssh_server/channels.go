package main

import (
	"context"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/robinje/multi-user-dungeon/core"
	"golang.org/x/crypto/ssh"
)

func handleChannels(server *core.Server, game *core.Game, sshConn *ssh.ServerConn, channels <-chan ssh.NewChannel) {

	core.Logger.Debug("Active Player Indeices:", "playerIndices", server.PlayerIndex)

	playerName := sshConn.User()

	core.Logger.Info("New connection", "address", sshConn.RemoteAddr().String(), "user", playerName)

	for newChannel := range channels {
		channel, requests, err := newChannel.Accept()
		if err != nil {
			core.Logger.Error("Could not accept channel", "error", err)
			continue
		}

		for index := range server.Players {
			if server.Players[index].PlayerID == playerName {
				core.Logger.Warn("Player already connected", "playerName", playerName)
				// Send a message to the player and close the connection
				channel.Write([]byte("You are already connected. Goodbye.\n\r"))
				sshConn.Close()
				return
			}
		}

		// Attempt to read the player from the database
		_, characterList, seenMotD, err := server.Database.ReadPlayer(playerName)
		if err != nil {
			if err.Error() == "player not found" {
				// Create a new player record if not found
				core.Logger.Info("Creating new player record", "player_name", playerName)
				characterList = make(map[string]uuid.UUID)
				seenMotD = []uuid.UUID{} // Initialize an empty slice for new players
				err = server.Database.WritePlayer(&core.Player{
					PlayerID:      playerName,
					CharacterList: characterList,
					SeenMotD:      seenMotD,
				})
				if err != nil {
					core.Logger.Error("Error creating player record", "error", err)
					continue
				}
			} else {
				core.Logger.Error("Error reading player from database", "error", err)
				continue
			}
		}

		// Simple player initialization
		ctx, cancel := context.WithCancel(context.Background())
		player := &core.Player{
			Server:        server,
			Index:         server.PlayerIndex.GetID(),
			PlayerID:      playerName,
			CharacterList: characterList,
			SeenMotD:      seenMotD,
			ToPlayer:      make(chan string, 10),
			FromPlayer:    make(chan string, 10),
			Echo:          true,
			Prompt:        "",
			Connection:    channel,
			ConsoleWidth:  80,
			ConsoleHeight: 24,
			LoginTime:     time.Now(),
			Mutex:         sync.Mutex{},
			CTX:           ctx,
			Cancel:        cancel,
		}

		server.Mutex.Lock()
		server.Players[player.Index] = player
		server.Mutex.Unlock()

		go handleSSHRequests(player, requests)
		go handlePlayerSession(server, game, player)

		core.Logger.Info("Player session started", "playerName", playerName)
	}
}

// handleSSHRequests handles SSH requests from the client.
func handleSSHRequests(player *core.Player, requests <-chan *ssh.Request) {

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
			core.Logger.Warn("Unsupported request", "request", req.Type, "player_name", player.PlayerID)
			req.Reply(false, nil)
		}
	}
}
