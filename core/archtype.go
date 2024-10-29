package core

import (
	"fmt"
	"strings"
)

// DisplayArchetypes logs the loaded archetypes for debugging purposes.
func DisplayArchetypes(s *Server) {
	for key, archtype := range s.ArcheTypes {
		Logger.Debug("Archetype", "name", key, "description", archtype.Description)
	}
}

// LoadArchetypes retrieves all archetypes from the DynamoDB table and stores them in the Server's ArcheTypes map.
func (s *Server) LoadArchetypes() error {
	s.Mutex.Lock()
	defer s.Mutex.Unlock()

	var archetypes []Archetype
	err := s.Database.Scan("archetypes", &archetypes)
	if err != nil {
		return fmt.Errorf("error scanning archetypes table: %w", err)
	}

	s.ArcheTypes = make(map[string]*Archetype)
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

		s.ArcheTypes[archetype.ArchetypeName] = &archetypeCopy
		Logger.Debug("Loaded archetype",
			"name", archetype.ArchetypeName,
			"description", archetype.Description)
	}

	return nil
}

// StoreArchetypes stores all archetypes from the Server's ArcheTypes map into the DynamoDB table.
func (s *Server) StoreArchetypes() error {
	s.Mutex.Lock()
	defer s.Mutex.Unlock()

	for _, archetype := range s.ArcheTypes {
		err := s.Database.Put("archetypes", *archetype)
		if err != nil {
			return fmt.Errorf("error storing archetype %s: %w", archetype.ArchetypeName, err)
		}

		Logger.Debug("Stored archetype", "name", archetype.ArchetypeName)
	}

	return nil
}
