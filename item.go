package main

import (
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/service/dynamodb"
	"github.com/google/uuid"
)

// DisplayPrototypes logs the details of each prototype for debugging purposes.
func DisplayPrototypes(prototypes map[uuid.UUID]*Prototype) {
	for _, prototype := range prototypes {
		Logger.Debug("Prototype", "id", prototype.ID, "name", prototype.Name, "description", prototype.Description)
	}
}

// StorePrototypes stores item prototypes into the DynamoDB table.
func StorePrototypes(prototypes map[uuid.UUID]*Prototype, kp *KeyPair) error {
	for _, prototype := range prototypes {
		prototypeData := PrototypeData{
			PrototypeID: prototype.ID.String(),
			Name:        prototype.Name,
			Description: prototype.Description,
			Mass:        prototype.Mass,
			Value:       prototype.Value,
			Stackable:   prototype.Stackable,
			MaxStack:    prototype.MaxStack,
			Quantity:    prototype.Quantity,
			Wearable:    prototype.Wearable,
			WornOn:      prototype.WornOn,
			Verbs:       prototype.Verbs,
			Overrides:   prototype.Overrides,
			TraitMods:   prototype.TraitMods,
			Container:   prototype.Container,
			CanPickUp:   prototype.CanPickUp,
			Metadata:    prototype.Metadata,
		}

		err := kp.Put("prototypes", prototypeData)
		if err != nil {
			Logger.Error("Error storing prototype", "name", prototype.Name, "error", err)
			return fmt.Errorf("error storing prototype %s: %w", prototype.Name, err)
		}

		prototype.LastSaved = time.Now()

		Logger.Info("Stored prototype", "name", prototype.Name, "prototypeID", prototype.ID)
	}

	return nil
}

// LoadPrototypes retrieves all item prototypes from the DynamoDB table.
func LoadPrototypes(kp *KeyPair) (map[uuid.UUID]*Prototype, error) {
	var prototypeDataList []PrototypeData
	err := kp.Scan("prototypes", &prototypeDataList)
	if err != nil {
		Logger.Error("Error scanning prototypes table", "error", err)
		return nil, fmt.Errorf("error scanning prototypes: %w", err)
	}

	prototypes := make(map[uuid.UUID]*Prototype)
	for _, prototypeData := range prototypeDataList {
		id, err := uuid.Parse(prototypeData.PrototypeID)
		if err != nil {
			Logger.Error("Error parsing prototype UUID", "id", prototypeData.PrototypeID, "error", err)
			continue
		}
		prototype := &Prototype{
			ID:          id,
			Name:        prototypeData.Name,
			Description: prototypeData.Description,
			Mass:        prototypeData.Mass,
			Value:       prototypeData.Value,
			Stackable:   prototypeData.Stackable,
			MaxStack:    prototypeData.MaxStack,
			Quantity:    prototypeData.Quantity,
			Wearable:    prototypeData.Wearable,
			WornOn:      prototypeData.WornOn,
			Verbs:       prototypeData.Verbs,
			Overrides:   prototypeData.Overrides,
			TraitMods:   prototypeData.TraitMods,
			Container:   prototypeData.Container,
			CanPickUp:   prototypeData.CanPickUp,
			Metadata:    prototypeData.Metadata,
			Mutex:       sync.RWMutex{},
			LastEdited:  time.Now(),
			LastSaved:   time.Now(),
		}
		prototypes[id] = prototype
		Logger.Debug("Loaded prototype from database", "id", id, "name", prototype.Name)
	}

	return prototypes, nil
}

// LoadItem retrieves an item from the DynamoDB table.
func LoadItem(id string, k *KeyPair) (*Item, error) {
	if id == "" {
		return nil, fmt.Errorf("empty item ID provided")
	}

	key := map[string]*dynamodb.AttributeValue{
		"ItemID": {
			S: aws.String(id),
		},
	}

	var itemData ItemData
	err := k.Get("items", key, &itemData)
	if err != nil {
		Logger.Error("Error loading item data", "itemID", id, "error", err)
		return nil, fmt.Errorf("error loading item data: %w", err)
	}

	return itemFromData(&itemData, k)
}

// WriteItem stores an item into the DynamoDB table, handling nested contents if it's a container.
func WriteItem(obj *Item, k *KeyPair) error {
	// Recursively write contained items if the item is a container
	if obj.Container {
		for _, contentItem := range obj.Contents {
			if err := WriteItem(contentItem, k); err != nil {
				Logger.Error("Error writing content item", "contentItemID", contentItem.ID, "parentItemID", obj.ID, "error", err)
				return fmt.Errorf("error writing content item %s: %w", contentItem.ID, err)
			}
		}
	}

	// Prepare the list of content IDs
	contentIDs := make([]string, 0, len(obj.Contents))
	for _, contentItem := range obj.Contents {
		contentIDs = append(contentIDs, contentItem.ID.String())
	}

	// Create the ItemData struct to store in DynamoDB
	itemData := ItemData{
		ItemID:      obj.ID.String(),
		PrototypeID: obj.PrototypeID.String(),
		Name:        obj.Name,
		Description: obj.Description,
		Mass:        obj.Mass,
		Value:       obj.Value,
		Stackable:   obj.Stackable,
		MaxStack:    obj.MaxStack,
		Quantity:    obj.Quantity,
		Wearable:    obj.Wearable,
		WornOn:      obj.WornOn,
		Verbs:       obj.Verbs,
		Overrides:   obj.Overrides,
		TraitMods:   obj.TraitMods,
		Container:   obj.Container,
		Contents:    contentIDs,
		IsWorn:      obj.IsWorn,
		CanPickUp:   obj.CanPickUp,
		Metadata:    obj.Metadata,
	}

	// Write the item data to the DynamoDB table
	err := k.Put("items", itemData)
	if err != nil {
		Logger.Error("Error writing item data", "itemName", obj.Name, "itemID", obj.ID, "error", err)
		return fmt.Errorf("error writing item data: %w", err)
	}

	obj.LastSaved = time.Now()

	Logger.Info("Successfully wrote item", "itemName", obj.Name, "itemID", obj.ID)
	return nil
}

// SaveActiveItems saves all active items from rooms and characters to the database.
func SaveActiveItems(g *Game) error {
	if g == nil {
		return fmt.Errorf("server is nil")
	}

	Logger.Debug("Starting to save active items...")

	// Collect all items from rooms and characters
	itemsToSave := make(map[uuid.UUID]*Item)

	// Items in rooms
	if g.Rooms != nil {
		for roomID, room := range g.Rooms {
			if room == nil {
				Logger.Warn("Nil room found", "roomID", roomID)
				continue
			}
			room.Mutex.RLock()
			for _, item := range room.Items {
				if item == nil {
					Logger.Warn("Nil item found in room", "roomID", roomID)
					continue
				}
				itemsToSave[item.ID] = item
			}
			room.Mutex.RUnlock()
		}
	} else {
		Logger.Warn("Server Rooms map is nil")
	}

	// Items in character inventories
	if g.Characters != nil {
		for charID, character := range g.Characters {
			if character == nil {
				Logger.Warn("Nil character found", "characterID", charID)
				continue
			}
			character.Mutex.RLock()
			for _, item := range character.Inventory {
				if item == nil {
					Logger.Warn("Nil item found in inventory", "characterID", charID)
					continue
				}
				itemsToSave[item.ID] = item
			}
			character.Mutex.RUnlock()
		}
	} else {
		Logger.Warn("Server Characters map is nil")
	}

	// Save all collected items
	if g.Database == nil {
		return fmt.Errorf("server database is nil")
	}

	for _, item := range itemsToSave {
		if item == nil {
			Logger.Warn("Attempting to save a nil item, skipping")
			continue
		}

		// Check if LastEdited is after LastSaved, skip if it is not
		if !item.LastEdited.After(item.LastSaved) {
			Logger.Debug("Item not edited since last save, skipping", "itemName", item.Name, "itemID", item.ID)
			continue
		}

		// Attempt to write the item to the database
		if err := WriteItem(item, g.Database); err != nil {
			Logger.Error("Error saving item", "itemName", item.Name, "itemID", item.ID, "error", err)
			// Continue saving other items even if one fails
		} else {
			// Update LastSaved after successful save
			item.LastSaved = time.Now()
			Logger.Debug("Successfully saved item", "itemName", item.Name, "itemID", item.ID)
		}
	}

	Logger.Info("Finished saving active items")
	return nil
}

func CreateItemFromPrototype(prototypeID uuid.UUID, g *Game) (*Item, error) {
	prototype, exists := g.Prototypes[prototypeID]
	if !exists {
		Logger.Error("Prototype not found", "prototypeID", prototypeID)
		return nil, fmt.Errorf("prototype with ID %s not found", prototypeID)
	}

	newItem := &Item{
		ID:          uuid.New(),
		PrototypeID: prototypeID,
		Name:        prototype.Name,
		Description: prototype.Description,
		Mass:        prototype.Mass,
		Value:       prototype.Value,
		Stackable:   prototype.Stackable,
		MaxStack:    prototype.MaxStack,
		Quantity:    prototype.Quantity,
		Wearable:    prototype.Wearable,
		WornOn:      prototype.WornOn,
		Verbs:       prototype.Verbs,
		Overrides:   prototype.Overrides,
		TraitMods:   make(map[string]int8),
		Container:   prototype.Container,
		IsWorn:      false,
		CanPickUp:   prototype.CanPickUp,
		Metadata:    make(map[string]string),
		Mutex:       sync.RWMutex{},
		LastEdited:  time.Now(),
	}

	// Copy trait modifications and metadata
	for k, v := range prototype.TraitMods {
		newItem.TraitMods[k] = v
	}

	for k, v := range prototype.Metadata {
		newItem.Metadata[k] = v
	}

	// Recursively create contents if the item is a container
	if newItem.Container {
		newItem.Contents = make([]*Item, 0, len(prototype.Contents))
		for _, contentProtoID := range prototype.Contents {
			newContentItem, err := CreateItemFromPrototype(contentProtoID, g)
			if err != nil {
				Logger.Error("Error creating content item from prototype", "prototypeID", contentProtoID, "error", err)
				continue // Skip this content item but continue with others
			}
			newItem.Contents = append(newItem.Contents, newContentItem)
		}
	}

	// Save the new item to the database
	if err := WriteItem(newItem, g.Database); err != nil {
		Logger.Error("Failed to write new item to database", "itemName", newItem.Name, "itemID", newItem.ID, "error", err)
		return nil, fmt.Errorf("failed to write new item to database: %w", err)
	}

	newItem.LastSaved = time.Now()

	Logger.Debug("Created new item from prototype", "itemName", newItem.Name, "itemID", newItem.ID, "prototypeID", prototypeID)
	return newItem, nil
}

// itemFromData creates an Item from ItemData
func itemFromData(itemData *ItemData, kp *KeyPair) (*Item, error) {
	if itemData == nil {
		return nil, fmt.Errorf("itemData is nil")
	}

	itemID, err := uuid.Parse(itemData.ItemID)
	if err != nil {
		return nil, fmt.Errorf("error parsing item UUID: %w", err)
	}

	prototypeID, err := uuid.Parse(itemData.PrototypeID)
	if err != nil {
		return nil, fmt.Errorf("error parsing prototype UUID: %w", err)
	}

	item := &Item{
		ID:          itemID,
		PrototypeID: prototypeID,
		Name:        itemData.Name,
		Description: itemData.Description,
		Mass:        itemData.Mass,
		Value:       itemData.Value,
		Stackable:   itemData.Stackable,
		MaxStack:    itemData.MaxStack,
		Quantity:    itemData.Quantity,
		Wearable:    itemData.Wearable,
		WornOn:      itemData.WornOn,
		Verbs:       itemData.Verbs,
		Overrides:   itemData.Overrides,
		TraitMods:   itemData.TraitMods,
		Container:   itemData.Container,
		IsWorn:      itemData.IsWorn,
		CanPickUp:   itemData.CanPickUp,
		Metadata:    itemData.Metadata,
		Mutex:       sync.RWMutex{},
		LastEdited:  time.Now(),
		LastSaved:   time.Now(),
	}

	// Handle Contents if the item is a container
	if item.Container {
		item.Contents = make([]*Item, 0, len(itemData.Contents))
		for _, contentID := range itemData.Contents {
			contentItem, err := LoadItem(contentID, kp)
			if err != nil {
				Logger.Error("Error loading content item", "contentID", contentID, "parentItemID", item.ID, "error", err)
				continue // Skip this content item but continue with others
			}
			item.Contents = append(item.Contents, contentItem)
		}
	}

	return item, nil
}

// LoadAllItems loads all items for all rooms.
func LoadAllItems(kp *KeyPair) (map[string]*Item, error) {
	var itemsData []ItemData
	err := kp.Scan("items", &itemsData)
	if err != nil {
		Logger.Error("Error scanning items", "error", err)
		return nil, fmt.Errorf("error scanning items: %w", err)
	}

	items := make(map[string]*Item)
	for _, itemData := range itemsData {
		if itemData.ItemID == "" {
			Logger.Warn("Skipping item with empty ID")
			continue
		}
		item, err := itemFromData(&itemData, kp)
		if err != nil {
			Logger.Error("Error creating item from data", "item_id", itemData.ItemID, "error", err)
			continue
		}
		items[itemData.ItemID] = item
	}

	return items, nil
}

// AddItem adds an item to the room's item list.
func AddItem(item *Item, r *Room) {
	r.Mutex.Lock()
	defer r.Mutex.Unlock()

	if item == nil {
		Logger.Warn("Attempted to add nil item to room", "roomID", r.RoomID)
		return
	}

	if r.Items == nil {
		r.Items = make(map[uuid.UUID]*Item)
	}

	item.LastEdited = time.Now()

	r.Items[item.ID] = item

	Logger.Debug("Added item to room", "itemName", item.Name, "itemID", item.ID, "roomID", r.RoomID)
}

// RemoveItem removes an item from the room's item list.
func RemoveItem(item *Item, r *Room) {
	r.Mutex.Lock()
	defer r.Mutex.Unlock()

	if item == nil {
		Logger.Warn("Attempted to remove nil item from room", "roomID", r.RoomID)
		return
	}

	item.LastEdited = time.Now()

	delete(r.Items, item.ID)

	Logger.Debug("Removed item from room", "itemName", item.Name, "itemID", item.ID, "roomID", r.RoomID)
}

func formatHandSlot(slotName string, item *Item) string {
	if item == nil {
		return fmt.Sprintf("  %-10s: %s\n\r", slotName, ApplyColor("bright_black", "empty"))
	}

	details := item.Name
	if item.Container && len(item.Contents) > 0 {
		details += fmt.Sprintf(" (%d items inside)", len(item.Contents))
	} else if item.Stackable && item.Quantity > 1 {
		details += fmt.Sprintf(" (x%d)", item.Quantity)
	}

	return fmt.Sprintf("  %-10s: %s\n\r", slotName, ApplyColor("green", details))
}

func formatWornItem(item *Item) string {
	if item == nil {
		return ""
	}

	details := fmt.Sprintf("  %s (worn on %s)",
		ApplyColor("yellow", item.Name),
		ApplyColor("cyan", strings.Join(item.WornOn, ", ")))

	if item.Container && len(item.Contents) > 0 {
		details += ApplyColor("bright_black", fmt.Sprintf(" [%d items inside]", len(item.Contents)))
	}

	return details + "\n\r"
}

func formatCarriedItem(item *Item) string {
	if item == nil {
		return ""
	}

	details := fmt.Sprintf("  %s", ApplyColor("white", item.Name))

	if item.Stackable && item.Quantity > 1 {
		details += ApplyColor("bright_black", fmt.Sprintf(" (x%d)", item.Quantity))
	}
	if item.Container && len(item.Contents) > 0 {
		details += ApplyColor("bright_black", fmt.Sprintf(" [%d items inside]", len(item.Contents)))
	}

	return details + "\n\r"
}
