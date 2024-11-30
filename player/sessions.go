package player

import (
	"context"
	"runtime/debug"

	"golang.org/x/sync/errgroup"

	"github.com/robinje/multi-user-dungeon/core"
)

// handlePlayerSession manages a player's game session
func handlePlayerSession(ctx context.Context, server *Server, game *core.Game, player *core.Player) {
	// Ensure connection cleanup even on panic
	defer func() {
		if r := recover(); r != nil {
			stack := debug.Stack()
			core.Logger.Error("Panic in player session", "playerName", player.PlayerID, "panic", r, "stack", string(stack))
		}
		if player != nil && player.Connection != nil {
			if player.Character != nil {
				player.Character.Cleanup()
			}
			player.Cleanup()
		}
	}()

	// Create session-specific context
	sessionCtx, cancel := context.WithCancel(ctx)
	defer cancel()

	// Start I/O handlers
	ioGroup, ioCtx := errgroup.WithContext(sessionCtx)
	ioGroup.Go(func() error {
		core.PlayerInput(ioCtx, player)
		return nil
	})
	ioGroup.Go(func() error {
		core.PlayerOutput(ioCtx, player)
		return nil
	})

	core.Logger.Info("Starting player session",
		"playerName", player.PlayerID,
		"playerIndex", player.Index)

	// Display welcome messages and MOTDs
	core.Logger.Debug("Displaying welcome messages", "playerName", player.PlayerID)
	if err := core.DisplayUnseenMOTDs(server, player); err != nil {
		core.Logger.Error("Failed to display MOTDs", "playerName", player.PlayerID, "error", err)
		return
	}

	// Character Selection
	core.Logger.Debug("Starting character selection", "playerName", player.PlayerID)
	character, err := core.SelectCharacter(sessionCtx, game, player)
	if err != nil {
		core.Logger.Error("Character selection failed", "playerName", player.PlayerID, "error", err)
		return
	}

	if character == nil {
		core.Logger.Error("No character selected", "playerName", player.PlayerID)
		return
	}

	core.Logger.Info("Character selected for player", "playerName", player.PlayerID, "characterName", character.Name, "characterID", character.ID)

	// Update player with selected character
	player.Mutex.Lock()
	player.Prompt = "> "
	player.Character = character
	player.Mutex.Unlock()

	// Create a channel for input loop completion
	inputDone := make(chan struct{})

	// Start the input loop
	go func() {
		defer close(inputDone)
		core.Logger.Debug("Starting input loop", "playerName", player.PlayerID, "characterName", character.Name)
		core.InputLoop(sessionCtx, character)
	}()

	// Wait for session end conditions
	select {
	case <-sessionCtx.Done():
		core.Logger.Info("Session context cancelled",
			"playerName", player.PlayerID,
			"characterName", character.Name)

	case <-ctx.Done():
		core.Logger.Info("Parent context cancelled",
			"playerName", player.PlayerID,
			"characterName", character.Name)

	case <-inputDone:
		core.Logger.Info("Input loop completed normally",
			"playerName", player.PlayerID,
			"characterName", character.Name)
	}

	// Cleanup
	cancel() // Ensure all child goroutines are cancelled
	if err := ioGroup.Wait(); err != nil {
		core.Logger.Error("Error in I/O handlers",
			"playerName", player.PlayerID,
			"error", err)
	}

	if character != nil {
		character.Cleanup()
	}
	player.Cleanup()

	core.Logger.Info("Player session ended", "playerName", player.PlayerID)
}
