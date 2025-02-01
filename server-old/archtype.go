package main

import (
	"fmt"
	"sort"
	"strconv"
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
	Logger.Debug("Archetypes:" + fmt.Sprint(len(g.ArcheTypes)))
	for key, archetype := range g.ArcheTypes {
		Logger.Debug("Archetype", "name", key, "description", archetype.Description)
	}
}

// LoadArchetypes retrieves all archetypes from the DynamoDB table and stores them in the Server's ArcheTypes map.
func LoadArchetypes(g *Game) error {
	DisplayArchetypes(g)
	var archetypes []Archetype
	err := g.Database.Scan("archetypes", &archetypes)
	if err != nil {
		return fmt.Errorf("error scanning archetypes table: %w", err)
	}

	g.ArcheTypes = make(map[string]*Archetype)

	for _, archetype := range archetypes {
		archetypeCopy := archetype

		// Normalize map keys once during load
		for k, v := range archetypeCopy.Attributes {
			lowerKey := strings.ToLower(k)
			if lowerKey != k {
				archetypeCopy.Attributes[lowerKey] = v
				delete(archetypeCopy.Attributes, k)
			}
		}

		for k, v := range archetypeCopy.Abilities {
			lowerKey := strings.ToLower(k)
			if lowerKey != k {
				archetypeCopy.Abilities[lowerKey] = v
				delete(archetypeCopy.Abilities, k)
			}
		}

		g.ArcheTypes[archetype.ArchetypeName] = &archetypeCopy
		Logger.Debug("Loaded archetype", "name", archetype.ArchetypeName)
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

func selectArchetype(player *Player) (string, error) {
	options := buildArchetypeOptions(player.server.game)
	if len(options) == 0 {
		return "", nil // No archetypes available
	}

	msg := "\n\rSelect a character archetype.\n\r"
	for i, option := range options {
		msg += fmt.Sprintf("%d: %s\n\r", i+1, option)
	}
	msg += "Enter the number of your choice: "

	player.toPlayer <- msg
	selection, ok := <-player.fromPlayer
	if !ok {
		return "", fmt.Errorf("player input channel closed")
	}

	num, err := strconv.Atoi(strings.TrimSpace(selection))
	if err != nil || num < 1 || num > len(options) {
		return "", fmt.Errorf("invalid archetype selection")
	}

	return strings.Split(options[num-1], " - ")[0], nil
}

func buildArchetypeOptions(g *Game) []string {
	options := make([]string, 0, len(g.ArcheTypes))
	for name, archetype := range g.ArcheTypes {
		options = append(options, name+" - "+archetype.Description)
	}
	sort.Strings(options)
	return options
}
