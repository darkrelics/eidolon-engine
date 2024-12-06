package character

import (
	"fmt"
	"strings"

	"github.com/robinje/multi-user-dungeon/core"
)

// DisplayArchetypes logs the loaded archetypes for debugging purposes.
func DisplayArchetypes(g *core.Game) {
	for key, archtype := range g.ArcheTypes {
		core.Logger.Debug("Archetype", "name", key, "description", archtype.Description)
	}
}

// LoadArchetypes retrieves all archetypes from the DynamoDB table and stores them in the Server's ArcheTypes map.
func LoadArchetypes(g *core.Game) error {
	g.Mutex.Lock()
	defer g.Mutex.Unlock()

	var archetypes []core.Archetype
	err := g.Database.Scan("archetypes", &archetypes)
	if err != nil {
		return fmt.Errorf("error scanning archetypes table: %w", err)
	}

	if g.ArcheTypes == nil {
		g.ArcheTypes = make(map[string]*core.Archetype)
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
		core.Logger.Debug("Loaded archetype", "name", archetype.ArchetypeName, "description", archetype.Description)
	}

	return nil
}

// StoreArchetypes stores all archetypes from the Server's ArcheTypes map into the DynamoDB table.
func StoreArchetypes(g *core.Game) error {

	for _, archetype := range g.ArcheTypes {
		err := g.Database.Put("archetypes", *archetype)
		if err != nil {
			return fmt.Errorf("error storing archetype %s: %w", archetype.ArchetypeName, err)
		}

		core.Logger.Debug("Stored archetype", "name", archetype.ArchetypeName)
	}

	return nil
}
