/*
Eidolon Engine

Copyright 2024-2026 Jason E. Robinson

*/

package main

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/gofrs/uuid/v5"
)

type ItemData struct {
	ItemID      string            `json:"ItemID" dynamodbav:"ItemID"`
	PrototypeID string            `json:"PrototypeID" dynamodbav:"PrototypeID"`
	Name        string            `json:"Name" dynamodbav:"item_name"`
	Description string            `json:"Description" dynamodbav:"Description"`
	Mass        float64           `json:"Mass" dynamodbav:"Mass"`
	Value       uint64            `json:"Value" dynamodbav:"Value"`
	Stackable   bool              `json:"Stackable" dynamodbav:"Stackable"`
	MaxStack    uint32            `json:"MaxStack" dynamodbav:"MaxStack"`
	Quantity    uint32            `json:"Quantity" dynamodbav:"Quantity"`
	Wearable    bool              `json:"Wearable" dynamodbav:"Wearable"`
	WornOn      []string          `json:"WornOn" dynamodbav:"WornOn"`
	Verbs       map[string]string `json:"Verbs" dynamodbav:"Verbs"`
	Overrides   map[string]string `json:"Overrides" dynamodbav:"Overrides"`
	TraitMods   map[string]int8   `json:"TraitMods" dynamodbav:"TraitMods"`
	Container   bool              `json:"Container" dynamodbav:"Container"`
	Contents    []string          `json:"Contents" dynamodbav:"Contents"`
	IsWorn      bool              `json:"IsWorn" dynamodbav:"IsWorn"`
	CanPickUp   bool              `json:"CanPickUp" dynamodbav:"CanPickUp"`
	Metadata    map[string]string `json:"Metadata" dynamodbav:"Metadata"`
}

type PrototypeData struct {
	PrototypeID string            `json:"PrototypeID" dynamodbav:"prototypeID"`
	Name        string            `json:"Name" dynamodbav:"prototype_name"`
	Description string            `json:"Description" dynamodbav:"description"`
	Mass        float64           `json:"Mass" dynamodbav:"mass"`
	Value       uint64            `json:"Value" dynamodbav:"value"`
	Stackable   bool              `json:"Stackable" dynamodbav:"stackable"`
	MaxStack    uint32            `json:"MaxStack" dynamodbav:"max_stack"`
	Quantity    uint32            `json:"Quantity" dynamodbav:"quantity"`
	Wearable    bool              `json:"Wearable" dynamodbav:"wearable"`
	WornOn      []string          `json:"WornOn" dynamodbav:"worn_on"`
	Verbs       map[string]string `json:"Verbs" dynamodbav:"verbs"`
	Overrides   map[string]string `json:"Overrides" dynamodbav:"overrides"`
	TraitMods   map[string]int8   `json:"TraitMods" dynamodbav:"trait_mods"`
	Container   bool              `json:"Container" dynamodbav:"container"`
	Contents    []string          `json:"Contents" dynamodbav:"contents"`
	CanPickUp   bool              `json:"CanPickUp" dynamodbav:"can_pick_up"`
	Metadata    map[string]string `json:"Metadata" dynamodbav:"metadata"`
}

func (item *Item) SaveItemTree(ctx context.Context, k *KeyPair) error {
	// Save this item first
	err := item.Save(ctx, k)
	if err != nil {
		return err
	}

	// If this is a container, recursively save all contained items
	if item.container && len(item.contents) > 0 {
		item.mutex.RLock()
		contents := make([]*Item, len(item.contents))
		copy(contents, item.contents)
		item.mutex.RUnlock()

		for _, contentItem := range contents {
			if contentItem != nil {
				// Check context before saving each contained item
				select {
				case <-ctx.Done():
					return ctx.Err()
				default:
				}

				err := contentItem.SaveItemTree(ctx, k)
				if err != nil {
					Logger.Warn("Failed to save contained item", "containerID", item.id, "contentID", contentItem.id, "error", err)
					// Continue saving other items rather than failing completely
				}
			}
		}
	}

	return nil
}

func (item *Item) Save(ctx context.Context, k *KeyPair) error {
	// Check context at start
	select {
	case <-ctx.Done():
		return ctx.Err()
	default:
	}

	item.mutex.RLock()

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
	err := k.Put(ctx, k.tableNames["items"], itemData)
	if err != nil {
		Logger.Error("Error writing item data", "itemID", item.id, "error", err)
		return fmt.Errorf("error writing item data: %w", err)
	}

	// Need to save contents without holding lock to avoid potential deadlocks
	contentsToSave := make([]*Item, len(item.contents))
	copy(contentsToSave, item.contents)
	item.mutex.RUnlock()

	// Recursively save contained items
	for _, content := range contentsToSave {
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

	// Update lastSaved with write lock
	item.mutex.Lock()
	item.lastSaved = time.Now()
	item.mutex.Unlock()

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
	err := k.Put(ctx, k.tableNames["prototypes"], prototypeData)
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
	err := k.Scan(ctx, k.tableNames["prototypes"], &prototypesData)
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

	// Create a shared map to track loaded items across all inventory slots
	// This prevents duplicate loading of the same item and handles circular references
	loadedItems := make(map[string]*Item)

	// Load each item by its ID with full container hierarchies
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

		// Load the item with all its container contents
		item, err := LoadItemWithContents(ctx, itemIDStr, k, loadedItems)
		if err != nil {
			Logger.Error("Error loading item with contents for character", "itemID", itemIDStr, "error", err)
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
	err := k.Get(ctx, k.tableNames["items"], key, &itemData)
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
	err := k.Get(ctx, k.tableNames["prototypes"], key, &prototypeData)
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

	// Initialize contents slice - actual loading will be done separately
	item.contents = make([]*Item, 0)

	return item, nil
}

// LoadItemWithContents loads an item and recursively loads all its container contents
// Uses a map to track loaded items and prevent infinite loops
func LoadItemWithContents(ctx context.Context, id string, k *KeyPair, loadedItems map[string]*Item) (*Item, error) {
	// Check if item is already loaded (prevents circular references)
	if existingItem, exists := loadedItems[id]; exists {
		return existingItem, nil
	}

	// Load the base item first
	item, err := LoadItem(ctx, id, k)
	if err != nil {
		return nil, err
	}

	// Add to loaded items map immediately to prevent circular loading
	loadedItems[id] = item

	// If this is a container, load its contents recursively
	if item.container {
		// Get the raw item data again to access the Contents field
		key := map[string]types.AttributeValue{
			"ItemID": &types.AttributeValueMemberS{Value: id},
		}

		var itemData ItemData
		err := k.Get(ctx, k.tableNames["items"], key, &itemData)
		if err != nil {
			Logger.Warn("Failed to reload item data for container contents", "itemID", id, "error", err)
			return item, nil // Return item without contents rather than failing completely
		}

		// Load each contained item recursively
		if len(itemData.Contents) > 0 {
			item.contents = make([]*Item, 0, len(itemData.Contents))

			for _, contentIDStr := range itemData.Contents {
				// Check context before loading each contained item
				select {
				case <-ctx.Done():
					Logger.Warn("Context cancelled while loading container contents", "containerID", id)
					return item, ctx.Err()
				default:
				}

				contentItem, err := LoadItemWithContents(ctx, contentIDStr, k, loadedItems)
				if err != nil {
					Logger.Warn("Failed to load contained item", "containerID", id, "contentID", contentIDStr, "error", err)
					// Continue loading other items rather than failing completely
					continue
				}

				if contentItem != nil {
					item.contents = append(item.contents, contentItem)
				}
			}
		}
	}

	return item, nil
}

// LoadItemTree loads an item and all its nested container contents
// This is the public interface for loading items with full container hierarchies
func LoadItemTree(ctx context.Context, id string, k *KeyPair) (*Item, error) {
	loadedItems := make(map[string]*Item)
	return LoadItemWithContents(ctx, id, k, loadedItems)
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
