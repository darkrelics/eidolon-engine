/*
Eidolon Engine

Copyright 2024-2026 Jason E. Robinson

*/

package main

import (
	"fmt"
	"time"

	"github.com/gofrs/uuid/v5"
)

type MOTD struct {
	MotdID    uuid.UUID
	Active    bool
	Message   string
	CreatedAt time.Time
}

type MOTDData struct {
	MotdID    string `json:"MotdID" dynamodbav:"MotdID"`
	Active    bool   `json:"Active" dynamodbav:"Active"`
	Message   string `json:"Message" dynamodbav:"Message"`
	CreatedAt string `json:"CreatedAt" dynamodbav:"CreatedAt"`
}

/*

Areas for Improvement

Error Handling:

When saving player data after displaying MOTDs fails, it returns the error but continues execution
Consider adding retry logic or more graceful degradation


Default Message Management:

The default welcome message is hard-coded
Could be moved to a configuration file or database record for easier customization


Pagination:

No pagination mechanism for a large number of MOTDs
Could implement pagination if many MOTDs need to be displayed


Message Categorization:

No categorization of messages (e.g., system announcements, events, maintenance)
Adding categories could improve organization and allow filtering


Efficiency:

The code loads all MOTDs and then filters for active ones
Could optimize the database query to only return active MOTDs


Formatting and Styling:

Basic text formatting with line breaks
Could extend to support richer formatting or ANSI color codes for better visual presentation


Time-Based Messages:

No expiration date for messages
Could add start/end dates to automatically activate/deactivate messages


Caching:

No caching mechanism for frequently accessed MOTDs
Implementing a cache could reduce database load


*/

// LoadMOTDs retrieves all active MOTDs from the database
func (s *Server) LoadMOTDs() error {
	Logger.Info("Loading active MOTDs")

	var motdDataList []MOTDData

	err := s.database.Scan(s.ctx, s.database.tableNames["motd"], &motdDataList)
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

		motdID, err := uuid.FromString(motdData.MotdID)
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
	defaultMOTDID, _ := uuid.FromString("00000000-0000-0000-0000-000000000000")
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
	defaultMOTDID, _ := uuid.FromString("00000000-0000-0000-0000-000000000000")
	welcomeDisplayed := false

	player.mutex.RLock()
	activeMotDs := player.server.activeMotDs
	player.mutex.RUnlock()

	for _, motd := range activeMotDs {
		if motd != nil && motd.MotdID == defaultMOTDID {
			player.commandOut <- fmt.Sprintf("\n\r%s\n\r", motd.Message)
			welcomeDisplayed = true
			break
		}
	}

	// If no welcome message was found, display a generic one
	if !welcomeDisplayed {
		player.commandOut <- "\n\rWelcome to Eidolon Engine!\n\r"
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

	defaultMOTDID, _ := uuid.FromString("00000000-0000-0000-0000-000000000000")
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
			player.commandOut <- fmt.Sprintf("\n\r--- News ---\n\r%s\n\r", motd.Message)

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
