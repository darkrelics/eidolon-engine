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

	"github.com/google/uuid"
)

type MOTD struct {
	MotdID    uuid.UUID
	Active    bool
	Message   string
	CreatedAt time.Time
}

type MOTDData struct {
	MotdID    string `json:"MotdID" dynamodbav:"MotdID"`
	Active    bool   `json:"active" dynamodbav:"Active"`
	Message   string `json:"message" dynamodbav:"Message"`
	CreatedAt string `json:"createdAt" dynamodbav:"CreatedAt"`
}

// LoadMOTDs retrieves all active MOTDs from the database
func (s *Server) LoadMOTDs() error {
	Logger.Info("Loading active MOTDs")

	var motdDataList []MOTDData

	err := s.database.Scan("motd", &motdDataList)
	if err != nil {
		Logger.Error("Error scanning MOTDs table", "error", err)
		return fmt.Errorf("error scanning MOTDs: %w", err)
	}

	s.mutex.Lock()
	defer s.mutex.Unlock()

	s.activeMotDs = make([]*MOTD, 0, len(motdDataList))

	for _, motdData := range motdDataList {
		// Only load active MOTDs
		if !motdData.Active {
			continue
		}

		motdID, err := uuid.Parse(motdData.MotdID)
		if err != nil {
			Logger.Warn("Error parsing MOTD ID", "motdID", motdData.MotdID, "error", err)
			continue
		}

		createdAt, err := time.Parse(time.RFC3339, motdData.CreatedAt)
		if err != nil {
			// Default to current time if parsing fails
			Logger.Warn("Error parsing MOTD creation time", "motdID", motdData.MotdID, "error", err)
			createdAt = time.Now()
		}

		motd := &MOTD{
			MotdID:    motdID,
			Active:    motdData.Active,
			Message:   motdData.Message,
			CreatedAt: createdAt,
		}

		s.activeMotDs = append(s.activeMotDs, motd)
	}

	// Create a default welcome message if none exists
	defaultMOTDID, _ := uuid.Parse("00000000-0000-0000-0000-000000000000")
	foundDefault := false

	for _, motd := range s.activeMotDs {
		if motd.MotdID == defaultMOTDID {
			foundDefault = true
			break
		}
	}

	if !foundDefault {
		defaultMOTD := &MOTD{
			MotdID:    defaultMOTDID,
			Active:    true,
			Message:   "Welcome to Eidolon Engine! May your adventures be legendary.",
			CreatedAt: time.Now(),
		}
		s.activeMotDs = append(s.activeMotDs, defaultMOTD)
	}

	Logger.Info("Successfully loaded MOTDs", "count", len(s.activeMotDs))
	return nil
}

// DisplayMOTDs sends all active MOTDs to the player
func DisplayMOTDs(player *Player) error {
	if player == nil || player.server == nil {
		Logger.Error("Invalid player or server object")
		return fmt.Errorf("invalid player or server object")
	}

	Logger.Debug("Displaying MOTDs for player", "playerID", player.id)

	// Find and display the welcome message first
	defaultMOTDID, _ := uuid.Parse("00000000-0000-0000-0000-000000000000")
	welcomeDisplayed := false

	player.mutex.RLock()
	activeMotDs := player.server.activeMotDs
	player.mutex.RUnlock()

	for _, motd := range activeMotDs {
		if motd != nil && motd.MotdID == defaultMOTDID {
			player.toPlayer <- fmt.Sprintf("\n\r%s\n\r", motd.Message)
			welcomeDisplayed = true
			break
		}
	}

	// If no welcome message was found, display a generic one
	if !welcomeDisplayed {
		player.toPlayer <- "\n\rWelcome to Eidolon Engine!\n\r"
	}

	return nil
}

// DisplayUnseenMOTDs shows only the MOTDs the player hasn't seen yet
func DisplayUnseenMOTDs(player *Player) error {
	if player == nil || player.server == nil {
		Logger.Error("Invalid player or server object")
		return fmt.Errorf("invalid player or server object")
	}

	Logger.Debug("Displaying unseen MOTDs for player", "playerID", player.id)

	// Display welcome message
	if err := DisplayMOTDs(player); err != nil {
		return err
	}

	player.mutex.Lock()
	defer player.mutex.Unlock()

	// Display other unseen MOTDs
	var newlySeen []uuid.UUID

	defaultMOTDID, _ := uuid.Parse("00000000-0000-0000-0000-000000000000")
	for _, motd := range player.server.activeMotDs {
		if motd == nil || motd.MotdID == defaultMOTDID {
			continue
		}

		// Check if the player has already seen this MOTD
		seenMOTD := false
		for _, seenID := range player.seenMotD {
			if seenID == motd.MotdID {
				seenMOTD = true
				break
			}
		}

		if !seenMOTD {
			// Display the MOTD to the player
			player.toPlayer <- fmt.Sprintf("\n\r--- News ---\n\r%s\n\r", motd.Message)

			// Add to the list of newly seen MOTDs
			newlySeen = append(newlySeen, motd.MotdID)
		}
	}

	// Update player's seen MOTD list
	if len(newlySeen) > 0 {
		player.seenMotD = append(player.seenMotD, newlySeen...)

		// Save the updated player data
		err := player.Save()
		if err != nil {
			Logger.Error("Error saving player data after displaying MOTDs", "playerID", player.id, "error", err)
			return fmt.Errorf("error saving player data after displaying MOTDs: %w", err)
		}
	}

	return nil
}
