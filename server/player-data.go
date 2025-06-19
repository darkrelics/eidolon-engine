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
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/gofrs/uuid/v5"
)

type PlayerData struct {
	PlayerID      string            `json:"PlayerID" dynamodbav:"PlayerID"` // Store UUID as string in DynamoDB
	Email         string            `json:"Email" dynamodbav:"Email"`       // Store email
	CharacterList map[string]string `json:"CharacterList" dynamodbav:"CharacterList"`
	SeenMotDs     []string          `json:"SeenMotD" dynamodbav:"SeenMotD"`
}

func (p *Player) Load(playerID uuid.UUID) error {
	Logger.Debug("Loading player data", "player_id", playerID.String())

	database := p.server.database

	key := map[string]types.AttributeValue{
		"PlayerID": &types.AttributeValueMemberS{Value: playerID.String()},
	}

	var playerData PlayerData

	p.characterList = make(map[string]uuid.UUID)
	p.seenMotD = make([]uuid.UUID, 0)

	err := database.Get(p.server.ctx, "players", key, &playerData)
	if err != nil {
		if strings.Contains(err.Error(), "item not found") {
			Logger.Info("New player", "player_id", playerID.String(), "email", p.email)
			p.Save()
			return nil
		}
		Logger.Error("Error loading player data", "error", err)
		return err
	}

	Logger.Info("Player data loaded", "player_id", playerID.String(), "email", playerData.Email)

	p.mutex.Lock()
	defer p.mutex.Unlock()

	// Update email from database
	p.email = playerData.Email

	for characterName, characterID := range playerData.CharacterList {
		parsedUUID, err := uuid.FromString(characterID)
		if err != nil {
			Logger.Error("Error parsing character ID", "character_id", characterID)
			continue
		}
		p.characterList[characterName] = parsedUUID
	}

	for _, motdID := range playerData.SeenMotDs {
		motdUUID, err := uuid.FromString(motdID)
		if err != nil {
			Logger.Error("Error parsing MOTD ID", "motd_id", motdID)
			continue
		}
		p.seenMotD = append(p.seenMotD, motdUUID)
	}

	p.lastEdited = time.Now()
	p.lastSaved = time.Now()

	return nil
}

func (p *Player) Save() error {
	return p.SaveWithContext(p.server.ctx)
}

// SaveWithContext saves the player data with a specific context
// This is used during shutdown to ensure saves complete even after server context is cancelled
func (p *Player) SaveWithContext(ctx context.Context) error {
	Logger.Info("Saving player data", "player_id", p.id.String(), "email", p.email)

	database := p.server.database

	playerData := PlayerData{
		PlayerID:      p.id.String(),
		Email:         p.email,
		CharacterList: make(map[string]string),
		SeenMotDs:     make([]string, len(p.seenMotD)),
	}

	// Convert character IDs to strings
	for characterName, characterID := range p.characterList {
		playerData.CharacterList[characterName] = characterID.String()
	}

	// Convert MOTD IDs to strings
	for i, motdID := range p.seenMotD {
		playerData.SeenMotDs[i] = motdID.String()
	}

	err := database.Put(ctx, "players", playerData)
	if err != nil {
		Logger.Error("Error saving player data", "error", err)
		SafeSendString(p.commandOut, "Error saving player data. Please contact an administrator.\n", p.id.String())
		return fmt.Errorf("error saving player data: %w", err)
	}

	p.mutex.Lock()
	p.lastSaved = time.Now()
	p.mutex.Unlock()

	return nil
}
