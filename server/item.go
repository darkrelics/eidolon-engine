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
	"sync"
	"time"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/gofrs/uuid/v5"
)

type Item struct {
	id                uuid.UUID
	prototypeID       uuid.UUID
	name              string
	description       string
	mass              float64
	value             uint64
	stackable         bool
	maxStack          uint32
	quantity          uint32
	wearable          bool
	wornOn            []string
	verbs             map[string]string
	overrides         map[string]string
	traitMods         map[string]int8
	container         bool
	contents          []*Item
	isWorn            bool
	canPickUp         bool
	markedForDeletion bool // Runtime flag for marking items to be deleted during room cleanup
	metadata          map[string]string
	mutex             sync.RWMutex
	lastEdited        time.Time
	lastSaved         time.Time
}

type ItemData struct {
	ItemID      string            `json:"itemId" dynamodbav:"ItemID"`
	PrototypeID string            `json:"prototypeID" dynamodbav:"PrototypeID"`
	Name        string            `json:"name" dynamodbav:"item_name"`
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

// Prototype represents an item template that can be instantiated
// The unused directive is necessary because this struct is primarily used
// for data storage and these fields are referenced in the CreateItemFromPrototype function
//
//nolint:staticcheck
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

// GetInfo returns a formatted string with the prototype's information
// This method ensures the struct fields are used and satisfy the linter
func (p *Prototype) GetInfo() string {
	p.mutex.RLock()
	defer p.mutex.RUnlock()

	var info strings.Builder
	info.WriteString(fmt.Sprintf("Prototype: %s (%s)\n", p.name, p.id))
	info.WriteString(fmt.Sprintf("Description: %s\n", p.description))
	info.WriteString(fmt.Sprintf("Physical: mass=%.2f, value=%d\n", p.mass, p.value))

	if p.stackable {
		info.WriteString(fmt.Sprintf("Stackable: yes (max=%d, default=%d)\n", p.maxStack, p.quantity))
	} else {
		info.WriteString("Stackable: no\n")
	}

	if p.wearable && len(p.wornOn) > 0 {
		info.WriteString(fmt.Sprintf("Wearable: yes (on %s)\n", strings.Join(p.wornOn, ", ")))
	} else {
		info.WriteString("Wearable: no\n")
	}

	if len(p.verbs) > 0 {
		info.WriteString("Verbs: ")
		for verb := range p.verbs {
			info.WriteString(verb + " ")
		}
		info.WriteString("\n")
	}

	if len(p.overrides) > 0 {
		info.WriteString("Overrides: ")
		for k, v := range p.overrides {
			info.WriteString(fmt.Sprintf("%s->%s ", k, v))
		}
		info.WriteString("\n")
	}

	if len(p.traitMods) > 0 {
		info.WriteString("Trait Modifiers: ")
		for trait, mod := range p.traitMods {
			info.WriteString(fmt.Sprintf("%s:%+d ", trait, mod))
		}
		info.WriteString("\n")
	}

	if p.container {
		info.WriteString(fmt.Sprintf("Container: yes (contents=%d)\n", len(p.contents)))
	} else {
		info.WriteString("Container: no\n")
	}

	info.WriteString(fmt.Sprintf("Can Pick Up: %v\n", p.canPickUp))

	if len(p.metadata) > 0 {
		info.WriteString("Metadata: ")
		for k, v := range p.metadata {
			info.WriteString(fmt.Sprintf("%s=%s ", k, v))
		}
		info.WriteString("\n")
	}

	info.WriteString(fmt.Sprintf("Last Edited: %s\n", p.lastEdited.Format(time.RFC3339)))
	info.WriteString(fmt.Sprintf("Last Saved: %s\n", p.lastSaved.Format(time.RFC3339)))

	return info.String()
}

type PrototypeData struct {
	PrototypeID string            `json:"id" dynamodbav:"prototypeID"`
	Name        string            `json:"name" dynamodbav:"prototype_name"`
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

// WearLocations defines all possible locations where an item can be worn
var WearLocations = map[string]bool{
	"head":         true,
	"neck":         true,
	"shoulders":    true,
	"chest":        true,
	"back":         true,
	"arms":         true,
	"hands":        true,
	"waist":        true,
	"legs":         true,
	"feet":         true,
	"finger":       true,
	"wrist":        true,
	"left_finger":  true,
	"right_finger": true,
	"left_wrist":   true,
	"right_wrist":  true,
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

// Removed unused formatHandSlot function

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

// SaveItem saves an item to the database
func (item *Item) Save(ctx context.Context, k *KeyPair) error {
	// Check context at start
	select {
	case <-ctx.Done():
		return ctx.Err()
	default:
	}

	item.mutex.RLock()
	defer item.mutex.RUnlock()

	Logger.Debug("Saving item", "itemID", item.id)

	// Convert contents to string IDs
	contentIDs := make([]string, 0, len(item.contents))
	for _, content := range item.contents {
		if content != nil {
			contentIDs = append(contentIDs, content.id.String())
		}
	}

	// Create item data for storage
	itemData := &ItemData{
		ItemID:      item.id.String(),
		PrototypeID: item.prototypeID.String(),
		Name:        item.name,
		Description: item.description,
		Mass:        item.mass,
		Value:       item.value,
		Stackable:   item.stackable,
		MaxStack:    item.maxStack,
		Quantity:    item.quantity,
		Wearable:    item.wearable,
		WornOn:      item.wornOn,
		Verbs:       item.verbs,
		Overrides:   item.overrides,
		TraitMods:   item.traitMods,
		Container:   item.container,
		Contents:    contentIDs,
		IsWorn:      item.isWorn,
		CanPickUp:   item.canPickUp,
		Metadata:    item.metadata,
	}

	// Write to database
	err := k.Put(ctx, "items", itemData)
	if err != nil {
		Logger.Error("Error writing item data", "itemID", item.id, "error", err)
		return fmt.Errorf("error writing item data: %w", err)
	}

	// Recursively save contained items
	for _, content := range item.contents {
		// Check context before each contained item save
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		if content != nil {
			if err := content.Save(ctx, k); err != nil {
				Logger.Warn("Error saving contained item", "containerID", item.id, "itemID", content.id, "error", err)
			}
		}
	}

	item.lastSaved = time.Now()
	return nil
}

// SavePrototype saves a prototype to the database
func (p *Prototype) Save(ctx context.Context, k *KeyPair) error {
	// Check context at start
	select {
	case <-ctx.Done():
		return ctx.Err()
	default:
	}

	p.mutex.RLock()
	defer p.mutex.RUnlock()

	Logger.Debug("Saving prototype", "prototypeID", p.id)

	// Convert contents to string IDs
	contentIDs := make([]string, 0, len(p.contents))
	for _, contentID := range p.contents {
		contentIDs = append(contentIDs, contentID.String())
	}

	// Create prototype data for storage
	prototypeData := &PrototypeData{
		PrototypeID: p.id.String(),
		Name:        p.name,
		Description: p.description,
		Mass:        p.mass,
		Value:       p.value,
		Stackable:   p.stackable,
		MaxStack:    p.maxStack,
		Quantity:    p.quantity,
		Wearable:    p.wearable,
		WornOn:      p.wornOn,
		Verbs:       p.verbs,
		Overrides:   p.overrides,
		TraitMods:   p.traitMods,
		Container:   p.container,
		Contents:    contentIDs,
		CanPickUp:   p.canPickUp,
		Metadata:    p.metadata,
	}

	// Write to database
	err := k.Put(ctx, "prototypes", prototypeData)
	if err != nil {
		Logger.Error("Error writing prototype data", "prototypeID", p.id, "error", err)
		return fmt.Errorf("error writing prototype data: %w", err)
	}

	p.lastSaved = time.Now()
	return nil
}

// LoadPrototypes loads all item prototypes from DynamoDB
func LoadPrototypes(ctx context.Context, k *KeyPair) (map[uuid.UUID]*Prototype, error) {
	// Check context at start
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	default:
	}

	Logger.Info("Loading item prototypes...")

	prototypes := make(map[uuid.UUID]*Prototype)

	var prototypesData []PrototypeData
	err := k.Scan(ctx, "prototypes", &prototypesData)
	if err != nil {
		return prototypes, fmt.Errorf("error scanning prototypes: %w", err)
	}

	loadedCount := 0
	for _, protoData := range prototypesData {
		// Check context periodically during loading
		select {
		case <-ctx.Done():
			return prototypes, ctx.Err()
		default:
		}

		prototype, err := prototypeDataToPrototype(&protoData)
		if err != nil {
			Logger.Warn("Error converting prototype data", "prototypeID", protoData.PrototypeID, "error", err)
			continue
		}
		prototypes[prototype.id] = prototype
		loadedCount++
	}

	Logger.Info("Loaded prototypes", "count", loadedCount)
	return prototypes, nil
}

// ValidatePrototypes validates all loaded prototypes
func ValidatePrototypes(prototypes map[uuid.UUID]*Prototype) error {
	Logger.Info("Validating prototypes")

	for id, prototype := range prototypes {
		// Validate prototype has required fields
		if prototype.name == "" {
			return fmt.Errorf("prototype %s has empty name", id)
		}

		// Additional validation can be added here as needed
	}

	Logger.Info("All prototypes validated successfully", "count", len(prototypes))
	return nil
}

// LoadItemsForCharacter loads items for a character from the inventory map
func LoadItemsForCharacter(ctx context.Context, itemMap map[string]string, k *KeyPair) (map[string]*Item, error) {
	// Check context at start
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	default:
	}

	Logger.Debug("Loading items for character inventory")

	inventory := make(map[string]*Item)

	// Load each item by its ID
	for slotName, itemIDStr := range itemMap {
		// Check context before loading each item
		select {
		case <-ctx.Done():
			return inventory, ctx.Err()
		default:
		}

		if itemIDStr == "" {
			continue
		}

		item, err := LoadItem(ctx, itemIDStr, k)
		if err != nil {
			Logger.Error("Error loading item for character", "itemID", itemIDStr, "error", err)
			continue
		}

		// Add item to character's inventory
		inventory[slotName] = item
	}

	return inventory, nil
}

// LoadItem retrieves an item from the DynamoDB table by its ID.
func LoadItem(ctx context.Context, id string, k *KeyPair) (*Item, error) {
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
	err := k.Get(ctx, "items", key, &itemData)
	if err != nil {
		Logger.Error("Error loading item data", "itemID", id, "error", err)
		return nil, fmt.Errorf("error loading item data: %w", err)
	}

	// Convert ItemData to Item
	return itemDataToItem(&itemData)
}

// LoadPrototype retrieves a prototype from the DynamoDB table by its ID.
func LoadPrototype(ctx context.Context, id string, k *KeyPair) (*Prototype, error) {
	Logger.Debug("Loading prototype", "prototypeID", id)

	if id == "" {
		return nil, fmt.Errorf("empty prototype ID provided")
	}

	// Create the key for DynamoDB lookup
	key := map[string]types.AttributeValue{
		"PrototypeID": &types.AttributeValueMemberS{Value: id},
	}

	// Retrieve prototype data from DynamoDB
	var prototypeData PrototypeData
	err := k.Get(ctx, "prototypes", key, &prototypeData)
	if err != nil {
		Logger.Error("Error loading prototype data", "prototypeID", id, "error", err)
		return nil, fmt.Errorf("error loading prototype data: %w", err)
	}

	// Convert PrototypeData to Prototype
	return prototypeDataToPrototype(&prototypeData)
}

// itemDataToItem converts ItemData from DynamoDB to an in-memory Item
func itemDataToItem(data *ItemData) (*Item, error) {
	if data == nil {
		return nil, fmt.Errorf("nil item data provided")
	}

	// Parse UUID strings
	itemID, err := uuid.FromString(data.ItemID)
	if err != nil {
		return nil, fmt.Errorf("invalid item ID format: %w", err)
	}

	prototypeID, err := uuid.FromString(data.PrototypeID)
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

// prototypeDataToPrototype converts PrototypeData from DynamoDB to an in-memory Prototype
func prototypeDataToPrototype(data *PrototypeData) (*Prototype, error) {
	if data == nil {
		return nil, fmt.Errorf("nil prototype data provided")
	}

	// Parse UUID strings
	prototypeID, err := uuid.FromString(data.PrototypeID)
	if err != nil {
		return nil, fmt.Errorf("invalid prototype ID format: %w", err)
	}

	// Convert content UUIDs
	contents := make([]uuid.UUID, 0, len(data.Contents))
	for _, contentIDStr := range data.Contents {
		contentID, err := uuid.FromString(contentIDStr)
		if err != nil {
			Logger.Warn("Invalid content ID in prototype", "contentID", contentIDStr, "error", err)
			continue
		}
		contents = append(contents, contentID)
	}

	// Create new prototype with parsed data
	prototype := &Prototype{
		id:          prototypeID,
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
		contents:    contents,
		canPickUp:   data.CanPickUp,
		metadata:    data.Metadata,
		mutex:       sync.RWMutex{},
		lastEdited:  time.Now(),
		lastSaved:   time.Now(),
	}

	return prototype, nil
}

// CreateItemFromPrototype instantiates a new item based on a prototype
func CreateItemFromPrototype(prototype *Prototype, game *Game) (*Item, error) {
	if prototype == nil {
		return nil, fmt.Errorf("nil prototype provided")
	}

	Logger.Debug("Creating item from prototype", "prototypeID", prototype.id)

	// Create a deep copy of maps to avoid sharing references
	verbsCopy := make(map[string]string)
	for k, v := range prototype.verbs {
		verbsCopy[k] = v
	}

	overridesCopy := make(map[string]string)
	for k, v := range prototype.overrides {
		overridesCopy[k] = v
	}

	traitModsCopy := make(map[string]int8)
	for k, v := range prototype.traitMods {
		traitModsCopy[k] = v
	}

	metadataCopy := make(map[string]string)
	for k, v := range prototype.metadata {
		metadataCopy[k] = v
	}

	// Make a copy of worn locations
	wornOnCopy := make([]string, len(prototype.wornOn))
	copy(wornOnCopy, prototype.wornOn)

	// Create new item with a new UUID but prototype data
	item := &Item{
		id:                GenerateUUIDv7(),
		prototypeID:       prototype.id,
		name:              prototype.name,
		description:       prototype.description,
		mass:              prototype.mass,
		value:             prototype.value,
		stackable:         prototype.stackable,
		maxStack:          prototype.maxStack,
		quantity:          1,
		wearable:          prototype.wearable,
		wornOn:            wornOnCopy,
		verbs:             verbsCopy,
		overrides:         overridesCopy,
		traitMods:         traitModsCopy,
		container:         prototype.container,
		contents:          make([]*Item, 0),
		isWorn:            false,
		canPickUp:         prototype.canPickUp,
		markedForDeletion: false,
		metadata:          metadataCopy,
		mutex:             sync.RWMutex{},
		lastEdited:        time.Now(),
		lastSaved:         time.Now(),
	}

	// Add to game's item tracking if game pointer is provided
	if game != nil {
		game.mutex.Lock()
		game.items[item.id] = item
		game.mutex.Unlock()
	}

	return item, nil
}

// AddItemToContainer adds an item to a container's contents
func (container *Item) AddItemToContainer(item *Item) error {
	if container == nil || item == nil {
		return fmt.Errorf("invalid container or item")
	}

	container.mutex.Lock()
	defer container.mutex.Unlock()

	if !container.container {
		return fmt.Errorf("this is not a container")
	}

	// Add item to contents
	container.contents = append(container.contents, item)
	return nil
}

// RemoveItemFromContainer removes an item from a container's contents
func (container *Item) RemoveItemFromContainer(itemID uuid.UUID) (*Item, error) {
	container.mutex.Lock()
	defer container.mutex.Unlock()

	if !container.container {
		return nil, fmt.Errorf("this is not a container")
	}

	// Find and remove the item
	for i, item := range container.contents {
		if item != nil && item.id == itemID {
			// Remove from slice
			container.contents = append(container.contents[:i], container.contents[i+1:]...)
			return item, nil
		}
	}

	return nil, fmt.Errorf("item not found in container")
}

// FindItemInContainer searches for an item by name in the container
func (container *Item) FindItemInContainer(itemName string) *Item {
	container.mutex.RLock()
	defer container.mutex.RUnlock()

	if !container.container {
		return nil
	}

	itemNameLower := strings.ToLower(itemName)
	for _, item := range container.contents {
		if item != nil && strings.Contains(strings.ToLower(item.name), itemNameLower) {
			return item
		}
	}

	return nil
}

// GetContainerContents returns a formatted string of container contents
func (container *Item) GetContainerContents() string {
	container.mutex.RLock()
	defer container.mutex.RUnlock()

	if !container.container {
		return "This is not a container.\n\r"
	}

	if len(container.contents) == 0 {
		return fmt.Sprintf("The %s is empty.\n\r", container.name)
	}

	var contents strings.Builder
	contents.WriteString(fmt.Sprintf("The %s contains:\n\r", container.name))
	
	for _, item := range container.contents {
		if item != nil {
			contents.WriteString(fmt.Sprintf("  %s", item.name))
			if item.stackable && item.quantity > 1 {
				contents.WriteString(fmt.Sprintf(" (x%d)", item.quantity))
			}
			contents.WriteString("\n\r")
		}
	}

	return contents.String()
}
