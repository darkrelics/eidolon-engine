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
	"sort"
	"strings"

	"github.com/gofrs/uuid/v5"
)

// slotMappings defines semantic equivalents for archetype slots
var slotMappings = map[string][]string{
	"weapon": {"weapon", "waist", "hands"},
	"armor":  {"armor", "chest", "body"},
	"back":   {"back", "shoulders"},
	"finger": {"finger", "left_finger", "right_finger"},
	"wrist":  {"wrist", "left_wrist", "right_wrist"},
}

type ArchetypeItem struct {
	PrototypeID string `json:"PrototypeID" dynamodbav:"prototypeID"`
	Slot        string `json:"Slot" dynamodbav:"slot"`
	IsWorn      bool   `json:"IsWorn" dynamodbav:"isWorn"`
}

type Archetype struct {
	ArchetypeName string             `json:"ArchetypeName" dynamodbav:"archetypeName"`
	Description   string             `json:"Description" dynamodbav:"description"`
	Attributes    map[string]float64 `json:"Attributes" dynamodbav:"attributes"`
	Abilities     map[string]float64 `json:"Abilities" dynamodbav:"abilities"`
	StartRoom     int64              `json:"StartRoom" dynamodbav:"startRoom"`
	StartingItems []ArchetypeItem    `json:"StartingItems" dynamodbav:"startingItems"`
	Health        uint16             `json:"Health,omitempty" dynamodbav:"health,omitempty"`
	Essence       uint16             `json:"Essence,omitempty" dynamodbav:"essence,omitempty"`
}

// Display Archetypes for debugging purposes.
func (g *Game) DisplayArchetypes() {
	Logger.Info("Display Archetypes")

	Logger.Debug("Archetypes:" + fmt.Sprint(len(g.archetypes)))
	for key, archetype := range g.archetypes {
		Logger.Debug("Archetype", "name", key, "description", archetype.Description)
	}
}

// normalizeMapKeys converts all keys in a map to lowercase
func normalizeMapKeys(m map[string]float64) {
	for k, v := range m {
		lowerKey := strings.ToLower(k)
		if lowerKey != k {
			m[lowerKey] = v
			delete(m, k)
		}
	}
}

// LoadArchetypes retrieves all archetypes from the DynamoDB table and stores them in the Games's ArcheTypes map.
func (g *Game) LoadArchetypes() error {
	Logger.Info("Load Archetypes")

	var archetypes []Archetype

	err := g.database.Scan(g.ctx, "archetypes", &archetypes)
	if err != nil {
		Logger.Error("Load Archetypes: Error Scanning Archetypes Table", "error", err)
		return fmt.Errorf("error scanning archetypes table: %w", err)
	}

	g.archetypes = make(map[string]*Archetype)

	for i := range archetypes {
		archetype := &archetypes[i]

		normalizeMapKeys(archetype.Attributes)
		normalizeMapKeys(archetype.Abilities)

		// Validate archetype data consistency
		if err := g.ValidateArchetype(archetype); err != nil {
			Logger.Warn("Skipping invalid archetype", "name", archetype.ArchetypeName, "error", err)
			continue
		}

		g.archetypes[archetype.ArchetypeName] = archetype
		Logger.Info("Loaded archetype", "name", archetype.ArchetypeName)
	}

	g.DisplayArchetypes()

	return nil
}

func (g *Game) BuildArchetypeOptions() {

	Logger.Info("Building Archetype Options")

	options := make([]string, 0, len(g.archetypes))

	for name, archetype := range g.archetypes {
		options = append(options, name+" - "+archetype.Description)
	}

	sort.Strings(options)

	g.archetypeOptions = options
}

// ValidateArchetype checks archetype data for consistency and completeness
func (g *Game) ValidateArchetype(archetype *Archetype) error {
	if archetype == nil {
		return fmt.Errorf("archetype cannot be nil")
	}

	if archetype.ArchetypeName == "" {
		return fmt.Errorf("archetype name cannot be empty")
	}

	if archetype.Description == "" {
		return fmt.Errorf("archetype '%s' description cannot be empty", archetype.ArchetypeName)
	}

	if len(archetype.Attributes) == 0 {
		return fmt.Errorf("archetype '%s' must have at least one attribute", archetype.ArchetypeName)
	}

	if len(archetype.Abilities) == 0 {
		return fmt.Errorf("archetype '%s' must have at least one ability", archetype.ArchetypeName)
	}

	// Validate starting items
	for i, startingItem := range archetype.StartingItems {
		if startingItem.PrototypeID == "" {
			return fmt.Errorf("archetype '%s' starting item %d has empty prototype ID", archetype.ArchetypeName, i)
		}

		if startingItem.Slot == "" {
			return fmt.Errorf("archetype '%s' starting item %d has empty slot", archetype.ArchetypeName, i)
		}

		// Validate prototype ID format and parse UUID
		prototypeIDUUID, err := uuid.FromString(startingItem.PrototypeID)
		if err != nil {
			return fmt.Errorf("archetype '%s' starting item %d has invalid prototype ID: %w", archetype.ArchetypeName, i, err)
		}

		// Validate prototype exists
		g.mutex.RLock()
		var prototype *Prototype
		var exists bool
		if g.prototypes != nil {
			prototype, exists = g.prototypes[prototypeIDUUID]
		}
		g.mutex.RUnlock()

		if !exists {
			return fmt.Errorf("archetype '%s' starting item %d references non-existent prototype '%s'", archetype.ArchetypeName, i, startingItem.PrototypeID)
		}

		// Validate slot compatibility with prototype wearable locations
		if startingItem.IsWorn && prototype.wearable {
			// Check if the archetype slot is compatible with the prototype's wearable locations
			slotCompatible := false
			for _, wearableLocation := range prototype.wornOn {
				if isSlotCompatible(startingItem.Slot, wearableLocation) {
					slotCompatible = true
					break
				}
			}

			if !slotCompatible {
				Logger.Warn("Archetype slot incompatible with prototype wearable locations",
					"archetype", archetype.ArchetypeName,
					"slot", startingItem.Slot,
					"wearableLocations", prototype.wornOn,
					"prototypeID", startingItem.PrototypeID)
			}
		}
	}

	return nil
}

// isSlotCompatible checks if an archetype slot is compatible with a prototype wearable location
func isSlotCompatible(slot, wearableLocation string) bool {
	// Direct match
	if slot == wearableLocation {
		return true
	}

	// Check if the wearable location is in the allowed locations for this slot
	if allowedLocations, exists := slotMappings[slot]; exists {
		for _, allowed := range allowedLocations {
			if allowed == wearableLocation {
				return true
			}
		}
	}

	// Fallback to substring matching for backwards compatibility
	return strings.Contains(wearableLocation, slot) || strings.Contains(slot, wearableLocation)
}
