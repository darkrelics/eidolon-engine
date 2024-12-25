package main

import (
	"fmt"
	"strings"
)

type Archetype struct {
	ArchetypeName string             `json:"ArchetypeName" dynamodbav:"ArchetypeName"`
	Description   string             `json:"Description" dynamodbav:"Description"`
	Attributes    map[string]float64 `json:"Attributes" dynamodbav:"Attributes"`
	Abilities     map[string]float64 `json:"Abilities" dynamodbav:"Abilities"`
	StartRoom     int64              `json:"StartRoom" dynamodbav:"StartRoom"`
}

// DisplayArchetypes logs the loaded archetypes for debugging purposes.
func DisplayArchetypes(g *Game) {
	for key, archtype := range g.ArcheTypes {
		Logger.Debug("Archetype", "name", key, "description", archtype.Description)
	}
}

// LoadArchetypes retrieves all archetypes from the DynamoDB table and stores them in the Server's ArcheTypes map.
func LoadArchetypes(g *Game) error {
	g.Mutex.Lock()
	defer g.Mutex.Unlock()

	var archetypes []Archetype
	err := g.Database.Scan("archetypes", &archetypes)
	if err != nil {
		return fmt.Errorf("error scanning archetypes table: %w", err)
	}

	if g.ArcheTypes == nil {
		g.ArcheTypes = make(map[string]*Archetype)
	}

	for _, archetype := range archetypes {
		// Create a copy of the archetype to store in the map
		archetypeCopy := archetype

		// Convert attribute keys to lowercase
		lowerAttributes := make(map[string]float64)
		for key, value := range archetypeCopy.Attributes {
			lowerAttributes[strings.ToLower(key)] = value
		}
		archetypeCopy.Attributes = lowerAttributes

		// Convert ability keys to lowercase
		lowerAbilities := make(map[string]float64)
		for key, value := range archetypeCopy.Abilities {
			lowerAbilities[strings.ToLower(key)] = value
		}
		archetypeCopy.Abilities = lowerAbilities

		g.ArcheTypes[archetype.ArchetypeName] = &archetypeCopy
		Logger.Debug("Loaded archetype", "name", archetype.ArchetypeName, "description", archetype.Description)
	}

	return nil
}

// StoreArchetypes stores all archetypes from the Server's ArcheTypes map into the DynamoDB table.
func StoreArchetypes(g *Game) error {

	for _, archetype := range g.ArcheTypes {
		err := g.Database.Put("archetypes", *archetype)
		if err != nil {
			return fmt.Errorf("error storing archetype %s: %w", archetype.ArchetypeName, err)
		}

		Logger.Debug("Stored archetype", "name", archetype.ArchetypeName)
	}

	return nil
}
