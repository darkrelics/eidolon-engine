package core

import (
	"fmt"
)

// StoreArchetypes stores all archetypes from the Server's ArcheTypes map into the DynamoDB table.
func (g *Game) StoreArchetypes() error {

	for _, archetype := range g.ArcheTypes {
		err := g.Database.Put("archetypes", *archetype)
		if err != nil {
			return fmt.Errorf("error storing archetype %s: %w", archetype.ArchetypeName, err)
		}

		Logger.Debug("Stored archetype", "name", archetype.ArchetypeName)
	}

	return nil
}
