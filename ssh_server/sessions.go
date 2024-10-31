package main

import (
	"github.com/robinje/multi-user-dungeon/core"
)

func handlePlayerSession(server *core.Server, game *core.Game, player *core.Player) {
	// Ensure connection cleanup even on panic
	defer func() {
		if r := recover(); r != nil {
			core.Logger.Error("Panic in player session", "playerName", player.PlayerID, "panic", r)
		}
		if player != nil && player.Connection != nil {
			player.Cleanup()
		}
	}()

	go core.PlayerInput(player)
	go core.PlayerOutput(player)

	core.Logger.Info("Starting player session", "playerName", player.PlayerID, "playerIndex", player.Index)

	// Send welcome message and MOTDs
	core.Logger.Debug("Displaying welcome messages", "playerName", player.PlayerID)
	core.DisplayUnseenMOTDs(server, player)

	// Character Selection Dialog
	core.Logger.Debug("Starting character selection", "playerName", player.PlayerID)
	character, err := core.SelectCharacter(game, player)
	if err != nil {
		core.Logger.Error("Character selection failed", "playerName", player.PlayerID, "error", err)
		return
	}

	if character == nil {
		core.Logger.Error("No character selected", "playerName", player.PlayerID)
		return
	}

	core.Logger.Info("Character selected for player", "playerName", player.PlayerID, "characterName", character.Name, "characterID", character.ID)

	// Set the selected character in the player struct
	player.Character = character

	// Create a done channel to signal when the input loop is complete
	done := make(chan struct{})

	// Start the input loop in a goroutine
	go func() {
		defer close(done)
		core.Logger.Debug("Starting input loop", "playerName", player.PlayerID, "characterName", character.Name)
		core.InputLoop(character)
	}()

	// Wait for either context cancellation or input loop completion
	select {
	case <-player.CTX.Done():
		core.Logger.Info("Player session context cancelled", "playerName", player.PlayerID, "characterName", character.Name)
	case <-done:
		core.Logger.Info("Player input loop completed normally", "playerName", player.PlayerID, "characterName", character.Name)
	}

	// Save character data
	if character != nil {
		core.Logger.Debug("Saving character data", "playerName", player.PlayerID, "characterName", character.Name)
		err = server.Database.WriteCharacter(character)
		if err != nil {
			core.Logger.Error("Failed to save character data", "playerName", player.PlayerID, "characterName", character.Name, "error", err)
		}
	}

	// Save player data
	if player != nil {
		core.Logger.Debug("Saving player data", "playerName", player.PlayerID)
		err = server.Database.WritePlayer(player)
		if err != nil {
			core.Logger.Error("Failed to save player data", "playerName", player.PlayerID, "error", err)
		}

		core.Logger.Debug("Initiating player cleanup", "playerName", player.PlayerID)
		player.Cleanup()
	}

	core.Logger.Info("Player session ended", "playerName", player.PlayerID)
}
