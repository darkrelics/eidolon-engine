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
}

// Display Archetypes for debugging purposes.
func (g *Game) DisplayArchetypes() error {
	Logger.Info("Display Archetypes")

	Logger.Debug("Archetypes:" + fmt.Sprint(len(g.archetypes)))
	for key, archetype := range g.archetypes {
		Logger.Debug("Archetype", "name", key, "description", archetype.Description)
	}

	return nil
}

// LoadArchetypes retrieves all archetypes from the DynamoDB table and stores them in the Games's ArcheTypes map.
func (g *Game) LoadArchetypes() error {
	Logger.Info("Load Archetypes")

	var archetypes []Archetype

	err := g.database.Scan("archetypes", &archetypes)
	if err != nil {
		Logger.Error("Load Archetypes: Error Scanning Archetypes Table", "error", err)
		return fmt.Errorf("error scanning archetypes table: %w", err)
	}

	g.archetypes = make(map[string]*Archetype)

	for _, archetype := range archetypes {

		for k, v := range archetype.Attributes {
			lowerKey := strings.ToLower(k)
			if lowerKey != k {
				archetype.Attributes[lowerKey] = v
				delete(archetype.Attributes, k)
			}
		}

		for k, v := range archetype.Abilities {
			lowerKey := strings.ToLower(k)
			if lowerKey != k {
				archetype.Abilities[lowerKey] = v
				delete(archetype.Abilities, k)
			}
		}

		// Validate archetype data consistency
		if err := g.ValidateArchetype(&archetype); err != nil {
			Logger.Warn("Skipping invalid archetype", "name", archetype.ArchetypeName, "error", err)
			continue
		}

		g.archetypes[archetype.ArchetypeName] = &archetype
		Logger.Info("Loaded archetype", "name", archetype.ArchetypeName)
	}

	g.DisplayArchetypes()

	return nil
}

func (g *Game) BuildArchetypeOptions() error {

	Logger.Info("Building Archetype Options")

	options := make([]string, 0, len(g.archetypes))

	for name, archetype := range g.archetypes {
		options = append(options, name+" - "+archetype.Description)
	}

	sort.Strings(options)

	g.archetypeOptions = options

	return nil
}

// ValidateArchetype checks archetype data for consistency and completeness
func (g *Game) ValidateArchetype(archetype *Archetype) error {
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

		// Validate prototype ID format
		_, err := uuid.FromString(startingItem.PrototypeID)
		if err != nil {
			return fmt.Errorf("archetype '%s' starting item %d has invalid prototype ID: %w", archetype.ArchetypeName, i, err)
		}

		// Skip prototype existence check during initial load - will be validated later
		
		// Validate prototype ID format
		prototypeIDUUID, err := uuid.FromString(startingItem.PrototypeID)
		if err != nil {
			return fmt.Errorf("archetype '%s' starting item %d has invalid prototype ID format: %v", archetype.ArchetypeName, i, err)
		}

		// Validate prototype exists
		if _, exists := g.prototypes[prototypeIDUUID]; !exists {
			return fmt.Errorf("archetype '%s' starting item %d references non-existent prototype '%s'", archetype.ArchetypeName, i, startingItem.PrototypeID)
		}
	}

	return nil
}

// ValidateArchetypePrototypes validates that all prototype IDs in archetypes exist in the prototypes map
func (g *Game) ValidateArchetypePrototypes() error {
	Logger.Info("Validating archetype prototype references")

	for archetypeName, archetype := range g.archetypes {
		for i, startingItem := range archetype.StartingItems {
			prototypeIDUUID, err := uuid.FromString(startingItem.PrototypeID)
			if err != nil {
				return fmt.Errorf("archetype '%s' starting item %d has invalid prototype ID: %w", archetypeName, i, err)
			}

			prototype, exists := g.prototypes[prototypeIDUUID]
			if !exists {
				return fmt.Errorf("archetype '%s' starting item %d prototype '%s' does not exist", archetypeName, i, startingItem.PrototypeID)
			}

			// Validate slot compatibility with prototype wearable locations
			if startingItem.IsWorn && prototype.wearable {
				// Check if the archetype slot is compatible with the prototype's wearable locations
				slotCompatible := false
				for _, wearableLocation := range prototype.wornOn {
					if strings.Contains(wearableLocation, startingItem.Slot) || 
					   strings.Contains(startingItem.Slot, wearableLocation) ||
					   startingItem.Slot == "finger" && (wearableLocation == "left_finger" || wearableLocation == "right_finger") {
						slotCompatible = true
						break
					}
				}
				
				if !slotCompatible {
					Logger.Warn("Archetype slot incompatible with prototype wearable locations",
						"archetype", archetypeName,
						"slot", startingItem.Slot,
						"wearableLocations", prototype.wornOn,
						"prototypeID", startingItem.PrototypeID)
				}
			}
		}
	}

	Logger.Info("All archetype prototype references validated successfully")
	return nil
}

