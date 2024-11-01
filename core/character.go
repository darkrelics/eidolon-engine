package core

import (
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/service/dynamodb"
	"github.com/bits-and-blooms/bloom/v3"
	"github.com/google/uuid"
)

const FalsePositiveRate = 0.01 // 1% bloom filter false positive rate

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
	"left_finger":  true,
	"right_finger": true,
	"left_wrist":   true,
	"right_wrist":  true,
}

// NewCharacter creates a new character with the specified name and archetype.
func (g *Game) NewCharacter(name string, player *Player, room *Room, archetypeName string) (*Character, error) {

	// Check if the character name already exists
	if g.CharacterBloomFilter.Test([]byte(name)) {
		return nil, fmt.Errorf("character name '%s' already exists", name)
	}

	// Add character name to bloom filter
	g.CharacterBloomFilter.Add([]byte(name))

	character := &Character{
		Game:        g,
		ID:          uuid.New(),
		Room:        room,
		Name:        name,
		Player:      player,
		Health:      float64(g.Config.Game.StartingHealth),
		Essence:     float64(g.Config.Game.StartingEssence),
		Attributes:  make(map[string]float64),
		Abilities:   make(map[string]float64),
		Inventory:   make(map[string]*Item),
		Mutex:       sync.Mutex{},
		CombatRange: nil,
		Facing:      nil,
		LastSaved:   time.Now(),
		LastEdited:  time.Now(),
	}

	// Apply archetype attributes and abilities
	if archetypeName != "" {
		if archetype, ok := g.ArcheTypes[archetypeName]; ok {
			for attr, value := range archetype.Attributes {
				character.Attributes[attr] = value
			}
			for ability, value := range archetype.Abilities {
				character.Abilities[ability] = value
			}
			// Set the start room if it's defined in the archetype
			if archetype.StartRoom != 0 {
				if startRoom, ok := g.Rooms[archetype.StartRoom]; ok {
					character.Room = startRoom
				}
			}
		} else {
			return nil, fmt.Errorf("archetype '%s' not found", archetypeName)
		}
	}

	// Add the character to the server's Characters map
	g.Mutex.Lock()
	g.Characters[character.ID] = character
	g.Mutex.Unlock()

	SendRoomMessageExcept(character.Room, fmt.Sprintf("\n\r%s has arrived.\n\r", character.Name), character)

	return character, nil
}

// ToData converts a Character object into a CharacterData struct for database storage.
func (c *Character) ToData() *CharacterData {
	inventoryIDs := make(map[string]string)
	for name, item := range c.Inventory {
		inventoryIDs[name] = item.ID.String()
	}

	return &CharacterData{
		CharacterID:   c.ID.String(),
		PlayerID:      c.Player.PlayerID,
		CharacterName: c.Name,
		Attributes:    c.Attributes,
		Abilities:     c.Abilities,
		Essence:       c.Essence,
		Health:        c.Health,
		RoomID:        c.Room.RoomID,
		Inventory:     inventoryIDs,
	}
}

// FromData populates a Character object from a CharacterData struct retrieved from the database.
func (c *Character) FromData(cd *CharacterData, game *Game) error {
	var err error
	c.ID, err = uuid.Parse(cd.CharacterID)
	if err != nil {
		return fmt.Errorf("parse character ID: %w", err)
	}
	c.Name = cd.CharacterName
	c.Attributes = cd.Attributes
	c.Abilities = cd.Abilities
	c.Essence = cd.Essence
	c.Health = cd.Health

	// Retrieve the room; if not found, default to room ID 0
	room, exists := game.Rooms[cd.RoomID]
	if !exists {
		Logger.Warn("Room not found, defaulting to room ID 0", "roomID", cd.RoomID)
		room, exists = game.Rooms[0]
		if !exists {
			return fmt.Errorf("default room not found")
		}
	}
	c.Room = room

	// Initialize inventory
	c.Inventory = make(map[string]*Item)
	for name, itemIDStr := range cd.Inventory {
		itemID, err := uuid.Parse(itemIDStr)
		if err != nil {
			Logger.Error("Error parsing item UUID", "itemID", itemIDStr, "error", err)
			continue
		}
		item, err := game.Database.LoadItem(itemID.String())
		if err != nil {
			Logger.Error("Error loading item for character", "itemID", itemID, "characterName", c.Name, "error", err)
			continue
		}
		c.Inventory[name] = item
	}

	return nil
}

// WriteCharacter saves the character to the DynamoDB database.
func (kp *KeyPair) WriteCharacter(character *Character) error {

	characterData := character.ToData()

	err := kp.Put("characters", characterData)
	if err != nil {
		Logger.Error("Error writing character data", "characterName", character.Name, "error", err)
		return fmt.Errorf("error writing character data: %w", err)
	}

	Logger.Debug("Successfully wrote character to database", "characterName", character.Name, "characterID", character.ID)

	character.LastSaved = time.Now()

	return nil
}

// LoadCharacter retrieves a character from the DynamoDB database and reconstructs the Character object.
func (kp *KeyPair) LoadCharacter(characterID uuid.UUID, player *Player, game *Game) (*Character, error) {

	key := map[string]*dynamodb.AttributeValue{
		"CharacterID": {S: aws.String(characterID.String())},
	}

	var cd CharacterData
	err := kp.Get("characters", key, &cd)
	if err != nil {
		Logger.Error("Error loading character data", "characterID", characterID, "error", err)
		return nil, fmt.Errorf("error loading character data: %w", err)
	}

	character := &Character{
		Game:        game,
		ID:          characterID,
		Player:      player,
		Mutex:       sync.Mutex{},
		Facing:      nil,
		Advancing:   false,
		CombatRange: nil,
		LastSaved:   time.Now(),
	}

	if err := character.FromData(&cd, game); err != nil {
		Logger.Error("Error reconstructing character from data", "characterID", characterID, "error", err)
		return nil, fmt.Errorf("error loading character from data: %w", err)
	}

	// Ensure the character is added to the room's character list
	if character.Room != nil {

		SendRoomMessageExcept(character.Room, fmt.Sprintf("\n\r%s has arrived.\n\r", character.Name), character)

		character.Room.Mutex.Lock()
		if character.Room.Characters == nil {
			character.Room.Characters = make(map[uuid.UUID]*Character)
		}
		character.Room.Characters[character.ID] = character
		character.Room.Mutex.Unlock()
		Logger.Debug("Added character to room", "characterName", character.Name, "characterID", character.ID, "roomID", character.Room.RoomID)
	} else {
		Logger.Warn("Character loaded without a valid room", "characterName", character.Name, "characterID", character.ID)
	}

	Logger.Debug("Loaded character", "characterName", character.Name, "characterID", character.ID)

	character.LastSaved = time.Now()

	return character, nil
}

// DeleteCharacter removes a character from the player's character list and the database.
func (kp *KeyPair) DeleteCharacter(player *Player, characterName string) error {
	Logger.Debug("Attempting to delete character", "playerName", player.PlayerID, "characterName", characterName)

	// Check if the character exists in the player's character list
	characterID, exists := player.CharacterList[characterName]
	if !exists {
		return fmt.Errorf("character %s not found for player %s", characterName, player.PlayerID)
	}

	// Remove the character from the player's character list
	delete(player.CharacterList, characterName)

	// Update the player data in the database
	err := kp.WritePlayer(player)
	if err != nil {
		Logger.Error("Failed to update player data after character deletion", "playerName", player.PlayerID, "error", err)
		return fmt.Errorf("failed to update player data: %w", err)
	}

	// Delete the character from the database
	key := map[string]*dynamodb.AttributeValue{
		"CharacterID": {S: aws.String(characterID.String())},
	}
	err = kp.Delete("characters", key)
	if err != nil {
		Logger.Error("Failed to delete character from database", "characterName", characterName, "characterID", characterID, "error", err)
		return fmt.Errorf("failed to delete character from database: %w", err)
	}

	Logger.Info("Successfully deleted character", "playerName", player.PlayerID, "characterName", characterName, "characterID", characterID)
	return nil
}

// LoadCharacterNames loads all character names from the database to initialize the bloom filter.
func (kp *KeyPair) LoadCharacterNames() (map[string]bool, error) {
	names := make(map[string]bool)

	var characters []struct {
		CharacterName string `dynamodbav:"Name"`
	}

	err := kp.Scan("characters", &characters)
	if err != nil {
		Logger.Error("Error scanning characters table", "error", err)
		return nil, fmt.Errorf("error scanning characters: %w", err)
	}

	for _, character := range characters {
		names[strings.ToLower(character.CharacterName)] = true
	}

	if len(names) == 0 {
		Logger.Warn("No characters found in the database")
		return names, nil // Return empty map without error
	}

	return names, nil
}

// InitializeBloomFilter initializes the bloom filter with existing character names,
// as well as names from ../data/names.txt and ../data/obscenity.txt.
func InitializeBloomFilter(game *Game) error {
	// Load character names from the database
	characterNames, err := game.Database.LoadCharacterNames()
	if err != nil {
		return fmt.Errorf("failed to load character names: %w", err)
	}

	// Load additional names from names.txt
	namesFilePath := "../data/names.txt"
	namesFromFile, err := loadNamesFromFile(namesFilePath)
	if err != nil {
		return fmt.Errorf("failed to load names from %s: %w", namesFilePath, err)
	}

	// Load obscenity words from obscenity.txt
	obscenityFilePath := "../data/obscenity.txt"
	obscenities, err := loadNamesFromFile(obscenityFilePath)
	if err != nil {
		return fmt.Errorf("failed to load obscenities from %s: %w", obscenityFilePath, err)
	}

	// Calculate total number of items to add to the bloom filter
	totalItems := len(characterNames)
	for range characterNames { // Assuming characterNames is a map; adjust if it's a slice
		// Counting items in characterNames
	}
	totalItems += len(namesFromFile)
	totalItems += len(obscenities)

	// Ensure a minimum size
	if totalItems < 100 {
		totalItems = 100
	}

	fpRate := FalsePositiveRate

	// Initialize the bloom filter with the estimated number of items and false positive rate
	game.CharacterBloomFilter = bloom.NewWithEstimates(uint(totalItems), fpRate)

	// Add character names to the bloom filter
	for name := range characterNames {
		game.CharacterBloomFilter.AddString(strings.ToLower(name))
	}

	// Add names from names.txt to the bloom filter
	for _, name := range namesFromFile {
		game.CharacterBloomFilter.AddString(name)
	}

	// Add obscenities to the bloom filter
	for _, word := range obscenities {
		game.CharacterBloomFilter.AddString(word)
	}

	Logger.Debug("Bloom filter initialized",
		"estimatedSize", totalItems,
		"falsePositiveRate", fpRate,
		"totalItemsAdded", totalItems,
	)

	return nil
}

// AddCharacterName adds a character name to the bloom filter to prevent duplicates.
func (game *Game) AddCharacterName(name string) {

	game.CharacterBloomFilter.AddString(strings.ToLower(name))
	Logger.Debug("Added character name to bloom filter", "characterName", name)

}

// CharacterNameExists checks if a character name already exists using the bloom filter.
func (game *Game) CharacterNameExists(name string) bool {
	exists := game.CharacterBloomFilter.TestString(strings.ToLower(name))
	if exists {
		Logger.Info("Character name exists", "characterName", name)
	}
	return exists
}

// SaveActiveCharacters saves all active characters to the database if they have been edited since the last save.
func (g *Game) SaveActiveCharacters() error {

	Logger.Debug("Saving active characters...")

	for _, character := range g.Characters {
		// Check if the character's LastEdited is before LastSaved
		if !character.LastEdited.After(character.LastSaved) {
			Logger.Debug("Character not edited since last save, skipping", "characterName", character.Name)
			continue // Skip writing this character
		}

		character.Mutex.Lock()
		// Attempt to write the character to the database
		err := g.Database.WriteCharacter(character)
		if err != nil {
			Logger.Error("Error saving character", "characterName", character.Name, "error", err)
			continue // Continue saving other characters even if one fails
		}

		// Update LastSaved after a successful write
		character.LastSaved = time.Now()
		Logger.Debug("Character saved successfully", "characterName", character.Name)
		character.Mutex.Unlock()
	}

	Logger.Info("Active characters saved successfully.")
	return nil
}

// WearItem allows a character to wear an item from their inventory.
func (c *Character) WearItem(item *Item) error {
	c.Mutex.Lock()
	defer c.Mutex.Unlock()

	// Check if the item is in a hand slot
	inHand := false
	var handSlot string
	for slot, handItem := range c.Inventory {
		if (slot == "left_hand" || slot == "right_hand") && handItem == item {
			inHand = true
			handSlot = slot
			break
		}
	}

	if !inHand {
		return fmt.Errorf("you need to be holding the item to wear it")
	}

	if !item.Wearable {
		return fmt.Errorf("this item cannot be worn")
	}

	for _, location := range item.WornOn {
		if !WearLocations[location] {
			return fmt.Errorf("invalid wear location: %s", location)
		}
		if c.Inventory[location] != nil {
			return fmt.Errorf("you are already wearing something on your %s", location)
		}
	}

	for _, location := range item.WornOn {
		c.Inventory[location] = item
	}

	item.IsWorn = true
	delete(c.Inventory, handSlot) // Remove from hand slot

	Logger.Debug("Item worn", "characterName", c.Name, "itemName", item.Name, "wornOn", item.WornOn)

	c.LastEdited = time.Now()

	return nil
}

// ListInventory lists the items in a character's inventory.
func (c *Character) ListInventory() string {
	Logger.Debug("Character is listing inventory", "characterName", c.Name)

	c.Mutex.Lock()
	defer c.Mutex.Unlock()

	var output strings.Builder
	output.WriteString("\n\r")
	output.WriteString(ApplyColor("bright_white", "=== Inventory ===\n\r"))

	// Hands section
	output.WriteString(ApplyColor("white", "\nHands:\n\r"))
	leftItem := c.Inventory["left_hand"]
	rightItem := c.Inventory["right_hand"]

	output.WriteString(formatHandSlot("Left Hand", leftItem))
	output.WriteString(formatHandSlot("Right Hand", rightItem))

	// Worn items section
	var wornItems []*Item
	wornMap := make(map[string]bool)

	for _, item := range c.Inventory {
		if item.IsWorn && !wornMap[item.Name] {
			wornItems = append(wornItems, item)
			wornMap[item.Name] = true
		}
	}

	if len(wornItems) > 0 {
		output.WriteString(ApplyColor("white", "\nWorn Items:\n\r"))
		sort.Slice(wornItems, func(i, j int) bool {
			return wornItems[i].Name < wornItems[j].Name
		})

		for _, item := range wornItems {
			output.WriteString(formatWornItem(item))
		}
	}

	// Carried items section (items not in hands or worn)
	var carriedItems []*Item
	carriedMap := make(map[string]*Item) // For stacking similar items

	for slot, item := range c.Inventory {
		if slot != "left_hand" && slot != "right_hand" && !item.IsWorn {
			if item.Stackable {
				if existing, found := carriedMap[item.Name]; found {
					existing.Quantity += item.Quantity
				} else {
					carriedMap[item.Name] = item
					carriedItems = append(carriedItems, item)
				}
			} else {
				carriedItems = append(carriedItems, item)
			}
		}
	}

	if len(carriedItems) > 0 {
		output.WriteString(ApplyColor("white", "\nCarried Items:\n\r"))
		sort.Slice(carriedItems, func(i, j int) bool {
			return carriedItems[i].Name < carriedItems[j].Name
		})

		for _, item := range carriedItems {
			output.WriteString(formatCarriedItem(item))
		}
	}

	if len(c.Inventory) == 0 {
		output.WriteString("\n\rYour inventory is empty.\n\r")
	}

	return output.String()
}

// AddToInventory adds an item to the character's inventory.
func (c *Character) AddToInventory(item *Item) {
	Logger.Debug("Character is adding item to inventory", "characterName", c.Name, "itemName", item.Name)

	c.Mutex.Lock()
	defer c.Mutex.Unlock()

	if item.Wearable && len(item.WornOn) > 0 {
		for _, location := range item.WornOn {
			c.Inventory[location] = item
		}
		item.IsWorn = true
	} else {
		// Place in the first available hand slot
		if c.Inventory["right_hand"] == nil {
			c.Inventory["right_hand"] = item
		} else if c.Inventory["left_hand"] == nil {
			c.Inventory["left_hand"] = item
		} else {
			// If both hands are full, add to general inventory
			c.Inventory[item.Name] = item
		}
	}

	c.LastEdited = time.Now()

	Logger.Debug("Item added to inventory", "characterName", c.Name, "itemName", item.Name)
}

// FindInInventory searches for an item in the character's inventory by name.
func (c *Character) FindInInventory(itemName string) *Item {
	Logger.Debug("Character is searching inventory for item", "characterName", c.Name, "itemName", itemName)

	c.Mutex.Lock()
	defer c.Mutex.Unlock()

	lowercaseName := strings.ToLower(itemName)

	for _, item := range c.Inventory {
		if strings.Contains(strings.ToLower(item.Name), lowercaseName) {
			return item
		}
	}

	return nil
}

// RemoveFromInventory removes an item from the character's inventory.
func (c *Character) RemoveFromInventory(item *Item) {
	Logger.Debug("Character is removing item from inventory", "characterName", c.Name, "itemName", item.Name)

	c.Mutex.Lock()
	defer c.Mutex.Unlock()

	if item.IsWorn {
		for _, location := range item.WornOn {
			delete(c.Inventory, location)
		}
		item.IsWorn = false
	} else {
		// Remove from hand slots or general inventory
		for slot, invItem := range c.Inventory {
			if invItem == item {
				delete(c.Inventory, slot)
				break
			}
		}
	}

	c.LastEdited = time.Now()

	Logger.Debug("Item removed from inventory", "characterName", c.Name, "itemName", item.Name)
}

// CanCarryItem checks if the character can carry the specified item.
// This is a placeholder for future weight and capacity checks.
func (c *Character) CanCarryItem(item *Item) bool {
	Logger.Debug("Character is checking if they can carry item", "characterName", c.Name, "itemName", item.Name)

	// Placeholder implementation; always returns true for now
	return true
}

// RemoveWornItem allows a character to remove a worn item.
func (c *Character) RemoveWornItem(item *Item) error {
	c.Mutex.Lock()
	defer c.Mutex.Unlock()

	if item == nil {
		return fmt.Errorf("no item specified")
	}

	// Check if the item is worn
	isWorn := false
	for _, invItem := range c.Inventory {
		if invItem == item && item.IsWorn {
			isWorn = true
			break
		}
	}

	if !isWorn {
		return fmt.Errorf("you are not wearing that item")
	}

	// Try to place the item in the right hand first, then the left hand if right is occupied
	var handSlot string
	if c.Inventory["right_hand"] == nil {
		handSlot = "right_hand"
	} else if c.Inventory["left_hand"] == nil {
		handSlot = "left_hand"
	}

	if handSlot == "" {
		return fmt.Errorf("your hands are full. You need a free hand to remove an item")
	}

	// Remove item from worn locations
	for _, location := range item.WornOn {
		delete(c.Inventory, location)
	}
	item.IsWorn = false

	// Place item in hand slot
	c.Inventory[handSlot] = item

	c.LastEdited = time.Now()

	Logger.Debug("Item removed from worn location and placed in hand", "characterName", c.Name, "itemName", item.Name, "handSlot", handSlot)
	return nil
}

// getOtherCharacters returns a list of character names in the room, excluding the current character.
func getOtherCharacters(r *Room, currentCharacter *Character) []string {
	if r == nil || r.Characters == nil {
		Logger.Warn("Room or Characters map is nil in getOtherCharacters")
		return []string{}
	}

	otherCharacters := make([]string, 0)
	for _, c := range r.Characters {
		if c != nil && c != currentCharacter {
			otherCharacters = append(otherCharacters, c.Name)
		}
	}

	Logger.Debug("Found other characters in room", "count", len(otherCharacters), "room_id", r.RoomID)
	return otherCharacters
}

func moveCharacter(character *Character, direction string) error {
	character.Mutex.Lock()
	defer character.Mutex.Unlock()

	if character.Room == nil {
		return fmt.Errorf(msgNoRoom)
	}

	// Lock current room to check exit
	character.Room.Mutex.Lock()
	selectedExit, exists := character.Room.Exits[direction]
	if !exists || selectedExit == nil {
		character.Room.Mutex.Unlock()
		return fmt.Errorf(msgInvalidDir)
	}

	targetRoom := selectedExit.TargetRoom
	if targetRoom == nil {
		character.Room.Mutex.Unlock()
		return fmt.Errorf(msgPathNowhere)
	}

	// Lock target room
	targetRoom.Mutex.Lock()

	// Now we have all necessary locks to perform the move
	// Remove from old room
	oldRoom := character.Room
	delete(oldRoom.Characters, character.ID)

	// Prepare messages while we have locks
	oldRoomMsg := fmt.Sprintf("\n\r%s has left going %s.\n\r", character.Name, direction)
	newRoomMsg := fmt.Sprintf("\n\r%s has arrived.\n\r", character.Name)

	// Send message to old room while locked
	for _, c := range oldRoom.Characters {
		if c.Player != nil {
			c.Player.ToPlayer <- oldRoomMsg
			c.Player.ToPlayer <- c.Player.Prompt
		}
	}

	// Update character's room
	character.Room = targetRoom

	// Initialize character map if needed
	if targetRoom.Characters == nil {
		targetRoom.Characters = make(map[uuid.UUID]*Character)
	}

	// Add to new room
	targetRoom.Characters[character.ID] = character

	// Send message to new room while locked
	for _, c := range targetRoom.Characters {
		if c != character && c.Player != nil {
			c.Player.ToPlayer <- newRoomMsg
			c.Player.ToPlayer <- c.Player.Prompt
		}
	}

	// Update timestamps
	character.LastEdited = time.Now()
	oldRoom.LastEdited = time.Now()
	targetRoom.LastEdited = time.Now()

	// Release locks in reverse order
	targetRoom.Mutex.Unlock()
	oldRoom.Mutex.Unlock()

	// Show the new room to the character
	ExecuteLookCommand(character, []string{})

	Logger.Debug("Character moved successfully",
		"character", character.Name,
		"from", oldRoom.RoomID,
		"to", targetRoom.RoomID,
		"direction", direction)

	return nil
}

func (c *Character) Cleanup() {

	Logger.Debug("Cleaning up character", "characterName", c.Name, "characterID", c.ID)

	// Check if the Game exists.

	if c.Game == nil {
		Logger.Error("Game is nil in character cleanup", "characterName", c.Name)
		return
	}

	// Check if Character map exists in the Game.
	if c.Game.Characters == nil {
		Logger.Error("Game.Characters is nil in character cleanup", "characterName", c.Name)
		return
	}

	// Check if Character exists in the Game's Character map.
	if _, exists := c.Game.Characters[c.ID]; !exists {
		Logger.Error("Character not found in Game's Characters map during cleanup", "characterName", c.Name)
		return
	}

	c.Mutex.Lock()
	defer c.Mutex.Unlock()

	err := c.Game.Database.WriteCharacter(c)
	if err != nil {
		Logger.Error("Error saving character data during cleanup", "characterName", c.Name, "error", err)
	}

	// Remove character from room

	Logger.Debug("Characters in room before cleanup", "roomID", c.Room.RoomID, "characters", c.Room.Characters)

	if c.Room != nil {

		SendRoomMessageExcept(c.Room, fmt.Sprintf("\n\r%s has arrived.\n\r", c.Name), c)

		c.Room.Mutex.Lock()
		delete(c.Room.Characters, c.ID)
		c.Room.Mutex.Unlock()
	}

	Logger.Debug("Characters in room before cleanup", "roomID", c.Room.RoomID, "characters", c.Room.Characters)

	// Remove character from server's character list
	c.Game.Mutex.Lock()
	delete(c.Game.Characters, c.ID)
	c.Game.Mutex.Unlock()

	Logger.Debug("Character cleaned up", "characterName", c.Name, "characterID", c.ID)

	// c = nil

}
