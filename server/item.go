/*
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

*/

package main

import (
	"fmt"
	"strings"
	"sync"
	"time"

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

// AddItemToContainer adds an item to a container's contents with stacking support
func (container *Item) AddItemToContainer(item *Item) error {
	if container == nil || item == nil {
		return fmt.Errorf("invalid container or item")
	}

	container.mutex.Lock()
	defer container.mutex.Unlock()

	if !container.container {
		return fmt.Errorf("this is not a container")
	}

	// Check if item is stackable and try to merge with existing stacks
	if item.stackable {
		for _, existingItem := range container.contents {
			if existingItem != nil && existingItem.prototypeID == item.prototypeID {
				// Same prototype, try to merge stacks
				existingItem.mutex.Lock()
				if existingItem.quantity < existingItem.maxStack {
					// Calculate how many can be added
					spaceAvailable := existingItem.maxStack - existingItem.quantity
					item.mutex.Lock()
					if item.quantity <= spaceAvailable {
						// All items fit in existing stack
						existingItem.quantity += item.quantity
						item.mutex.Unlock()
						existingItem.mutex.Unlock()
						// Item fully merged, no need to add separately
						return nil
					} else {
						// Partial merge
						existingItem.quantity = existingItem.maxStack
						item.quantity -= spaceAvailable
						item.mutex.Unlock()
						existingItem.mutex.Unlock()
						// Continue to add remaining as new stack
					}
				} else {
					existingItem.mutex.Unlock()
				}
			}
		}
	}

	// Add item to contents (either non-stackable or remaining stackable quantity)
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
