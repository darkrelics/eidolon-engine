package interface_ssh

import (
	"context"
	"sync"
	"time"

	"github.com/robinje/multi-user-dungeon/core"
	"golang.org/x/crypto/ssh"
)

// handleChannels processes SSH channels for a connection
func handleChannels(ctx context.Context, server *core.Server, game *core.Game, sshConn *ssh.ServerConn, channels <-chan ssh.NewChannel) {
	core.Logger.Debug("Active Player Indices:", "playerIndices", server.PlayerIndex)
	playerName := sshConn.User()
	core.Logger.Info("New connection", "address", sshConn.RemoteAddr().String(), "user", playerName)

	for {
		select {
		case <-ctx.Done():
			core.Logger.Info("Closing connection due to context cancellation", "player", playerName)
			return

		case newChannel, ok := <-channels:
			if !ok {
				core.Logger.Info("Channel closed", "player", playerName)
				return
			}

			channel, requests, err := newChannel.Accept()
			if err != nil {
				core.Logger.Error("Could not accept channel", "error", err)
				continue
			}

			// Check for existing connection
			server.Mutex.RLock()
			for index := range server.Players {
				if server.Players[index].PlayerID == playerName {
					server.Mutex.RUnlock()
					core.Logger.Warn("Player already connected", "playerName", playerName)
					channel.Write([]byte("You are already connected. Goodbye.\n\r"))
					sshConn.Close()
					return
				}
			}
			server.Mutex.RUnlock()

			// Initialize or load player data
			characterList, seenMotD, err := core.InitializePlayerData(server, playerName)
			if err != nil {
				core.Logger.Error("Failed to initialize player data", "error", err, "player", playerName)
				continue
			}

			// Create player context as child of connection context
			playerCtx, playerCancel := context.WithCancel(ctx)
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
				Mutex:         sync.RWMutex{},
				Context:       playerCtx,
				Cancel:        playerCancel,
			}

			server.Mutex.Lock()
			server.Players[player.Index] = player
			server.Mutex.Unlock()

			// Start player handlers with context
			go handleSSHRequests(playerCtx, player, requests)
			go handlePlayerSession(playerCtx, server, game, player)

			core.Logger.Info("Player session started",
				"playerName", playerName,
				"index", player.Index)
		}
	}
}

// handleSSHRequests handles SSH requests from the client.
func handleSSHRequests(ctx context.Context, player *core.Player, requests <-chan *ssh.Request) {
	for {
		select {
		case <-ctx.Done():
			core.Logger.Info("Context cancelled, exiting handleSSHRequests loop",
				"player", player.PlayerID)
			return

		case req, ok := <-requests:
			if !ok {
				core.Logger.Info("Request channel closed, exiting handleSSHRequests loop",
					"player", player.PlayerID)
				return
			}

			player.Mutex.Lock()
			handleRequest(req, player)
			player.Mutex.Unlock()
		}
	}
}

// handleRequest processes individual SSH requests
func handleRequest(req *ssh.Request, player *core.Player) {
	switch req.Type {
	case "shell":
		core.Logger.Debug("Accepting shell request",
			"player", player.PlayerID)
		req.Reply(true, nil)

	case "pty-req":
		termLen := req.Payload[3]
		w, h := core.ParseDims(req.Payload[termLen+4:])
		player.ConsoleWidth = w
		player.ConsoleHeight = h
		core.Logger.Debug("Terminal size set",
			"player", player.PlayerID,
			"width", w,
			"height", h)
		req.Reply(true, nil)

	case "window-change":
		w, h := core.ParseDims(req.Payload)
		player.ConsoleWidth = w
		player.ConsoleHeight = h
		core.Logger.Debug("Window size changed",
			"player", player.PlayerID,
			"width", w,
			"height", h)

	default:
		core.Logger.Warn("Unsupported request",
			"type", req.Type,
			"player", player.PlayerID)
		req.Reply(false, nil)
	}
}
