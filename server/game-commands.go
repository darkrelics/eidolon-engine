/*
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

*/

package main

import (
	"fmt"
	"time"
)

// ProcessGameCommand handles commands at the game level
func (g *Game) ProcessGameCommand(cmd *CommandRequest) *CommandResponse {
	if cmd == nil {
		Logger.Error("Received nil command for game processing")
		return &CommandResponse{
			Success:   false,
			Error:     fmt.Errorf("invalid command"),
			Timestamp: time.Now(),
		}
	}

	Logger.Debug("Processing game command",
		"verb", cmd.Verb,
		"character", cmd.Character.name)

	// Verb-based routing directs to appropriate handler
	switch cmd.Verb {
	default:
		// Command not understood by the engine - log it
		Logger.Info("Unknown command attempted", "verb", cmd.Verb, "character", cmd.Character.name)
		return &CommandResponse{
			RequestID: cmd.ID,
			Success:   false,
			Error:     fmt.Errorf("the engine doesn't understand that command"),
			Timestamp: time.Now(),
		}
	}
}
