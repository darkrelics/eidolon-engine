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
	"strings"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/google/uuid"
)

type Item struct {
	id          uuid.UUID
	prototypeID uuid.UUID
	name        string
	description string
	mass        float64
	value       uint64
	stackable   bool
	maxStack    uint32
	quantity    uint32
	wearable    bool
	wornOn      []string
	verbs       map[string]string
	overrides   map[string]string
	traitMods   map[string]int8
	container   bool
	contents    []*Item
	isWorn      bool
	canPickUp   bool
	markedForDeletion bool // Runtime flag for marking items to be deleted during room cleanup
	metadata    map[string]string
	mutex       sync.RWMutex
	lastEdited  time.Time
	lastSaved   time.Time
}

type ItemData struct {
	ItemID      string            `json:"itemId" dynamodbav:"ItemID"`
	PrototypeID string            `json:"prototypeID" dynamodbav:"PrototypeID"`
	Name        string            `json:"name" dynamodbav:"Name"`
	Description string            `json:"description" dynamodbav:"Description"`
	Mass        float64           `json:"mass" dynamodbav:"Mass"`
	Value       uint64            `json:"value" dynamodbav:"Value"`
	Stackable   bool              `json:"stackable" dynamodbav:"Stackable"`
	MaxStack    uint32            `json:"max_stack" dynamodbav:"MaxStack"`
	Quantity    uint32            `json:"quantity" dynamodbav:"Quantity"`
	Wearable    bool              `json:"wearable" dynamodbav:"Wearable"`
	WornOn      []string          `json:"worn_on" dynamodbav:"WornOn"`
	Verbs       map[string]string `json:"verbs" dynamodbav:"Verbs"`
	Overrides   map[string]string `json:"overrides" dynamodbav:"Overrides"`
	TraitMods   map[string]int8   `json:"trait_mods" dynamodbav:"TraitMods"`
	Container   bool              `json:"container" dynamodbav:"Container"`
	Contents    []string          `json:"contents" dynamodbav:"Contents"`
	IsWorn      bool              `json:"is_worn" dynamodbav:"IsWorn"`
	CanPickUp   bool              `json:"can_pick_up" dynamodbav:"CanPickUp"`
	Metadata    map[string]string `json:"metadata" dynamodbav:"Metadata"`
}

type Prototype struct {
	id          uuid.UUID
	name        string
	description string
	mass        float64
	value       uint64
	stackable   bool
	maxStack    uint32
	quantity    uint32
	wearable    bool
	wornOn      []string
	verbs       map[string]string
	overrides   map[string]string
	traitMods   map[string]int8
	container   bool
	contents    []uuid.UUID
	canPickUp   bool
	metadata    map[string]string
	mutex       sync.RWMutex
	lastEdited  time.Time
	lastSaved   time.Time
}

type PrototypeData struct {
	PrototypeID string            `json:"id" dynamodbav:"prototypeID"`
	Name        string            `json:"name" dynamodbav:"name"`
	Description string            `json:"description" dynamodbav:"description"`
	Mass        float64           `json:"mass" dynamodbav:"mass"`
	Value       uint64            `json:"value" dynamodbav:"value"`
	Stackable   bool              `json:"stackable" dynamodbav:"stackable"`
	MaxStack    uint32            `json:"max_stack" dynamodbav:"max_stack"`
	Quantity    uint32            `json:"quantity" dynamodbav:"quantity"`
	Wearable    bool              `json:"wearable" dynamodbav:"wearable"`
	WornOn      []string          `json:"worn_on" dynamodbav:"worn_on"`
	Verbs       map[string]string `json:"verbs" dynamodbav:"verbs"`
	Overrides   map[string]string `json:"overrides" dynamodbav:"overrides"`
	TraitMods   map[string]int8   `json:"trait_mods" dynamodbav:"trait_mods"`
	Container   bool              `json:"container" dynamodbav:"container"`
	Contents    []string          `json:"contents" dynamodbav:"contents"`
	CanPickUp   bool              `json:"can_pick_up" dynamodbav:"can_pick_up"`
	Metadata    map[string]string `json:"metadata" dynamodbav:"metadata"`
}

// formatItemDescription creates a description of an item
func formatItemDescription(item *Item) string {
	var desc strings.Builder
	desc.WriteString(fmt.Sprintf("\n\r%s\n\r", item.name))
	desc.WriteString(item.description)
	desc.WriteString("\n\r")

	if item.wearable && len(item.wornOn) > 0 {
		desc.WriteString(fmt.Sprintf("It can be worn on: %s\n\r", strings.Join(item.wornOn, ", ")))
	}

	return desc.String()
}

// formatHandSlot formats a hand slot for inventory display
func formatHandSlot(slotName string, item *Item) string {
	if item == nil {
		return fmt.Sprintf("  %s: empty\n\r", slotName)
	}

	description := fmt.Sprintf("  %s: %s", slotName, item.name)
	if item.stackable && item.quantity > 1 {
		description += fmt.Sprintf(" (x%d)", item.quantity)
	}
	description += "\n\r"

	return description
}

// formatWornItem formats a worn item for inventory display
func formatWornItem(item *Item) string {
	description := fmt.Sprintf("  %s", item.name)
	if len(item.wornOn) > 0 {
		description += fmt.Sprintf(" (worn on %s)", strings.Join(item.wornOn, ", "))
	}
	description += "\n\r"

	return description
}

// formatCarriedItem formats a carried item for inventory display
func formatCarriedItem(item *Item) string {
	description := fmt.Sprintf("  %s", item.name)
	if item.stackable && item.quantity > 1 {
		description += fmt.Sprintf(" (x%d)", item.quantity)
	}
	description += "\n\r"

	return description
}

// LoadItem retrieves an item from the DynamoDB table by its ID.
func LoadItem(id string, k *KeyPair) (*Item, error) {
	Logger.Debug("Loading item", "itemID", id)

	if id == "" {
		return nil, fmt.Errorf("empty item ID provided")
	}

	// Create the key for DynamoDB lookup
	key := map[string]types.AttributeValue{
		"ItemID": &types.AttributeValueMemberS{Value: id},
	}

	// Retrieve item data from DynamoDB
	var itemData ItemData
	err := k.Get("items", key, &itemData)
	if err != nil {
		Logger.Error("Error loading item data", "itemID", id, "error", err)
		return nil, fmt.Errorf("error loading item data: %w", err)
	}

	// Convert ItemData to Item
	return itemDataToItem(&itemData)
}

// itemDataToItem converts ItemData from DynamoDB to an in-memory Item
func itemDataToItem(data *ItemData) (*Item, error) {
	if data == nil {
		return nil, fmt.Errorf("nil item data provided")
	}

	// Parse UUID strings
	itemID, err := uuid.Parse(data.ItemID)
	if err != nil {
		return nil, fmt.Errorf("invalid item ID format: %w", err)
	}

	prototypeID, err := uuid.Parse(data.PrototypeID)
	if err != nil {
		return nil, fmt.Errorf("invalid prototype ID format: %w", err)
	}

	// Create new item with parsed data
	item := &Item{
		id:          itemID,
		prototypeID: prototypeID,
		name:        data.Name,
		description: data.Description,
		mass:        data.Mass,
		value:       data.Value,
		stackable:   data.Stackable,
		maxStack:    data.MaxStack,
		quantity:    data.Quantity,
		wearable:    data.Wearable,
		wornOn:      data.WornOn,
		verbs:       data.Verbs,
		overrides:   data.Overrides,
		traitMods:   data.TraitMods,
		container:   data.Container,
		isWorn:      data.IsWorn,
		canPickUp:   data.CanPickUp,
		metadata:    data.Metadata,
		mutex:       sync.RWMutex{},
		lastEdited:  time.Now(),
		lastSaved:   time.Now(),
	}

	// If this is a container, we need to parse its contents
	if data.Container && len(data.Contents) > 0 {
		item.contents = make([]*Item, 0, len(data.Contents))
		// We'll leave the contents as an empty slice for now
		// The actual loading of contained items would need to be
		// done separately to avoid circular references
	} else {
		item.contents = make([]*Item, 0)
	}

	return item, nil
}
