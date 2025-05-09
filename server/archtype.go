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
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
)

type Archetype struct {
	ArchetypeName string             `json:"ArchetypeName" dynamodbav:"archetypeName"`
	Description   string             `json:"Description" dynamodbav:"description"`
	Attributes    map[string]float64 `json:"Attributes" dynamodbav:"attributes"`
	Abilities     map[string]float64 `json:"Abilities" dynamodbav:"abilities"`
	StartRoom     int64              `json:"StartRoom" dynamodbav:"startRoom"`
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

		// Normalize map keys once during load
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

func (c *Character) SelectArchetype() (string, error) {

	if len(c.game.archetypeOptions) == 0 {
		return "", nil // No archetypes available.
	}

	options := c.game.archetypeOptions

	msg := "\n\rSelect a character archetype.\n\r"
	for i, option := range options {
		msg += fmt.Sprintf("%d: %s\n\r", i+1, option)
	}
	msg += "Enter the number of your choice: "

	c.gameCommandIn <- &CommandResponse{
		RequestID: uuid.New(),
		Success:   true,
		Message:   msg,
		Timestamp: time.Now(),
	}

	// Wait for response
	var selection string
	var ok bool

	// Create a channel for the response
	respChan := make(chan string, 1)

	// Start a goroutine to wait for a command
	go func() {
		select {
		case cmd, cmdOk := <-c.gameCommandOut:
			if cmdOk && cmd != nil {
				// Extract the first argument as the selection
				if len(cmd.Args) > 0 {
					respChan <- cmd.Args[0]
				} else {
					respChan <- ""
				}
			} else {
				respChan <- ""
			}
		case <-time.After(5 * time.Minute): // Add a timeout
			respChan <- ""
		}
	}()

	// Wait for the response
	selection, ok = <-respChan
	if !ok {
		Logger.Warn("Character input channel closed")
		return "", fmt.Errorf("character input channel closed")
	}

	num, err := strconv.Atoi(strings.TrimSpace(selection))
	if err != nil || num < 1 || num > len(options) {
		return "", fmt.Errorf("invalid archetype selection")
	}

	return strings.Split(options[num-1], " - ")[0], nil
}
