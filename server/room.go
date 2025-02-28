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
	"sync"
	"time"

	"github.com/google/uuid"
)

// Room represents the in-memory structure for a room
type Room struct {
	roomID      int64
	area        string
	title       string
	description string
	exits       map[uuid.UUID]*Exit
	characters  map[uuid.UUID]*Character
	items       map[uuid.UUID]*Item
	mutex       sync.RWMutex
	lastEdited  time.Time
	lastSaved   time.Time
}

// RoomData represents the structure for storing room data in DynamoDB
type RoomData struct {
	RoomID      int64    `json:"roomID" dynamodbav:"RoomID"`
	Area        string   `json:"area" dynamodbav:"Area"`
	Title       string   `json:"title" dynamodbav:"Title"`
	Description string   `json:"description" dynamodbav:"Description"`
	ExitIDs     []string `json:"exitID" dynamodbav:"ExitID"`
	ItemIDs     []string `json:"itemID" dynamodbav:"ItemID"`
}

// Exit represents the in-memory structure for an exit
type Exit struct {
	exitID      uuid.UUID
	direction   string
	description string
	targetRoom  *Room
	visible     bool
	lastEdited  time.Time
	lastSaved   time.Time
}

// ExitData represents the structure for storing exit data in DynamoDB
type ExitData struct {
	ExitID      string `json:"ExitID" dynamodbav:"ExitID"`
	Direction   string `json:"Direction" dynamodbav:"Direction"`
	Description string `json:"Description" dynamodbav:"Description"`
	TargetRoom  int64  `json:"TargetRoom" dynamodbav:"TargetRoom"`
	Visible     bool   `json:"Visible" dynamodbav:"Visible"`
}

// Initialize a new room

func NewRoom(roomID int64, area, title, description string) *Room {

	Logger.Info("New Room...Initalizing Room...")

	return &Room{
		roomID:      roomID,
		area:        area,
		title:       title,
		description: description,
		exits:       make(map[uuid.UUID]*Exit),
		characters:  make(map[uuid.UUID]*Character),
		items:       make(map[uuid.UUID]*Item),
		mutex:       sync.RWMutex{},
		lastEdited:  time.Now(),
		lastSaved:   time.Now(),
	}
}

// Initialize a new exit

func NewExit(exitID uuid.UUID, direction string, description string, targetRoom *Room, visible bool) *Exit {

	Logger.Info("New Exit...Initalizing Exit...")

	return &Exit{
		exitID:      exitID,
		direction:   direction,
		description: description,
		targetRoom:  targetRoom,
		visible:     visible,
		lastEdited:  time.Now(),
		lastSaved:   time.Now(),
	}
}

// Load exit data from DynamoDB

func (g *Game) LoadExits() error {

	Logger.Info("Load Exits...Loading Exits...")

	var exitsData []ExitData

	err := g.database.Scan("exits", &exitsData)
	if err != nil {
		Logger.Error("Error scanning exits table", "error", err)
		return nil
	}

	for _, exitData := range exitsData {
		exitID, err := uuid.Parse(exitData.ExitID)
		if err != nil {
			Logger.Warn("Error parsing exit ID", "error", err)
		}

		g.exits[exitID] = NewExit(exitID, exitData.Direction, exitData.Description, g.rooms[exitData.TargetRoom], exitData.Visible)
	}

	return nil
}

// Load room data from DynamoDB

func (g *Game) LoadRooms() error {

	Logger.Info("Load Rooms...Loading Rooms...")

	// Load room data from DynamoDB
	var roomsData []RoomData
	err := g.database.Scan("rooms", &roomsData)
	if err != nil {
		Logger.Error("Error scanning rooms table", "error", err)
		return fmt.Errorf("error scanning rooms: %w", err)
	}

	// Populate all rooms

	for _, roomData := range roomsData {
		g.rooms[roomData.RoomID] = NewRoom(roomData.RoomID, roomData.Area, roomData.Title, roomData.Description)

	}

	// Load exit data

	err = g.LoadExits()
	if err != nil {
		Logger.Warn("Error loading exits", "error", err)
	}

	// Assocate exits with rooms

	for _, roomData := range roomsData {
		for _, exitID := range roomData.ExitIDs {
			exitUUID, err := uuid.Parse(exitID)
			if err != nil {
				Logger.Warn("Error parsing exit ID", "error", err)
				continue
			}
			g.rooms[roomData.RoomID].exits[exitUUID] = g.exits[exitUUID]
		}
	}

	// Load item data

	return nil

}

// SendRoomMessageExcept sends a message to all characters in a room except one
func SendRoomMessageExcept(room *Room, message string, except *Character) {
	if room == nil {
		return
	}

	room.mutex.RLock()
	defer room.mutex.RUnlock()

	for _, c := range room.characters {
		if c != nil && c != except && c.player != nil {
			select {
			case c.player.toPlayer <- message:
				// Message sent successfully
			default:
				Logger.Warn("Failed to send room message to player",
					"recipient", c.name,
					"message", message)
			}
		}
	}
}
