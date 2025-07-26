/*
Eidolon Engine

Copyright 2024-2025 Jason Robinson

*/

package main

import (
	"time"

	"github.com/gofrs/uuid/v5"
)

// CommandTier represents the level at which a command will be processed
type CommandTier int

const (
	// CharacterTier commands are processed by the character immediately
	CharacterTier CommandTier = iota
	// RoomTier commands are processed by the room
	RoomTier
	// GameTier commands are processed by the game
	GameTier
)

// CommandState represents the current state of a command
type CommandState int

const (
	// CommandPending indicates the command is waiting to be processed
	CommandPending CommandState = iota
	// CommandProcessing indicates the command is being processed
	CommandProcessing
	// CommandCompleted indicates the command has completed successfully
	CommandCompleted
	// CommandFailed indicates the command failed
	CommandFailed
	// CommandRejected indicates the command was rejected
	CommandRejected
)

// CommandRequest encapsulates a command request sent between components
type CommandRequest struct {
	ID        uuid.UUID             // Unique ID for the command
	Character *Character            // Character issuing the command
	Verb      string                // Command verb
	Args      []string              // Command arguments
	Tier      CommandTier           // Which tier should process this command
	State     CommandState          // Current state of the command
	Timestamp time.Time             // When the command was created
	Response  chan *CommandResponse // Channel for direct response
}

// CommandResponse encapsulates a response to a command
type CommandResponse struct {
	RequestID uuid.UUID // ID of the original request
	Success   bool      // Whether the command succeeded
	Message   string    // Response message
	Error     error     // Error, if any
	Timestamp time.Time // When the response was created
}
