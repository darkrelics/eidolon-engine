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

	"github.com/gofrs/uuid/v5"
)

// Exit represents the in-memory structure for an exit
type Exit struct {
	exitID       uuid.UUID
	direction    string
	description  string
	targetRoom   *Room
	targetRoomID int64
	arrivalText  string
	visible      bool
	scriptID     string
	lastEdited   time.Time
	lastSaved    time.Time
}

// ExitData represents the structure for storing exit data in DynamoDB
type ExitData struct {
	ExitID      string `json:"ExitID" dynamodbav:"ExitID"`
	Direction   string `json:"Direction" dynamodbav:"Direction"`
	Description string `json:"Description" dynamodbav:"Description"`
	TargetRoom  int64  `json:"TargetRoom" dynamodbav:"TargetRoom"`
	ArrivalText string `json:"ArrivalText" dynamodbav:"ArrivalText"`
	Visible     bool   `json:"Visible" dynamodbav:"Visible"`
	ScriptID    string `json:"ScriptID" dynamodbav:"ScriptID"`
}

// NewExit initializes a new exit
func NewExit(exitID uuid.UUID, direction string, description string, targetRoom *Room, targetRoomID int64, arrivalText string, visible bool, scriptID string) *Exit {
	Logger.Info("New Exit...Initializing Exit...")

	return &Exit{
		exitID:       exitID,
		direction:    direction,
		description:  description,
		targetRoom:   targetRoom,
		targetRoomID: targetRoomID,
		arrivalText:  arrivalText,
		visible:      visible,
		scriptID:     scriptID,
		lastEdited:   time.Now(),
		lastSaved:    time.Now(),
	}
}

// LoadExits loads exit data from DynamoDB
func (g *Game) LoadExits() error {
	Logger.Info("Load Exits...Loading Exits...")

	var exitsData []ExitData

	err := g.database.Scan("exits", &exitsData)
	if err != nil {
		Logger.Error("Error scanning exits table", "error", err)
		return nil
	}

	for _, exitData := range exitsData {
		exitID, err := uuid.FromString(exitData.ExitID)
		if err != nil {
			Logger.Warn("Error parsing exit ID", "error", err)
			continue
		}

		// Default arrival text if not provided
		arrivalText := exitData.ArrivalText
		if arrivalText == "" {
			// Generate default arrival text based on direction
			arrivalText = fmt.Sprintf("arrives from the %s", exitData.Direction)
		}

		g.exits[exitID] = NewExit(
			exitID,
			exitData.Direction,
			exitData.Description,
			g.rooms[exitData.TargetRoom],
			exitData.TargetRoom,
			arrivalText,
			exitData.Visible,
			exitData.ScriptID,
		)
	}

	return nil
}

// SendArrivalMessage notifies characters in the destination room that a character has arrived
func SendArrivalMessage(character *Character, exitUsed *Exit, destinationRoom *Room) {
	if character == nil || exitUsed == nil || destinationRoom == nil {
		return
	}

	var message string
	if exitUsed.arrivalText != "" {
		// Use custom arrival text if provided
		message = fmt.Sprintf("\n\r%s %s.\n\r", character.name, exitUsed.arrivalText)
	} else {
		// Use default arrival text with direction
		message = fmt.Sprintf("\n\r%s arrives from the %s.\n\r", character.name, exitUsed.direction)
	}

	// Send message to all characters in destination room except the arriving character
	SendRoomMessageExcept(destinationRoom, message, character)
}
