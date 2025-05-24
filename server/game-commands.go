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

	// Process command based on verb
	switch cmd.Verb {
	case "weather", "time":
		// Global environmental commands
		return g.handleEnvironmentCommand(cmd)
	case "shout", "announce":
		// Global communication commands
		return g.handleGlobalCommunicationCommand(cmd)
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
