package main

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/service/dynamodb"
	"github.com/google/uuid"
)

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

type Character struct {
	Game        *Game
	ID          uuid.UUID
	Player      *Player
	Name        string
	Attributes  map[string]float64
	Abilities   map[string]float64
	Essence     float64
	Health      float64
	Room        *Room
	Inventory   map[string]*Item
	Mutex       sync.RWMutex
	Facing      *Character
	Advancing   bool
	CombatRange map[uuid.UUID]float64
	LastEdited  time.Time
	LastSaved   time.Time
	inputChan   chan string
	outputChan  chan string
	prompt      string
	End         chan bool
}

// CharacterData for unmarshalling character.
type CharacterData struct {
	CharacterID   string             `json:"CharacterID" dynamodbav:"CharacterID"`
	PlayerID      string             `json:"PlayerID" dynamodbav:"PlayerID"`
	CharacterName string             `json:"Name" dynamodbav:"Name"`
	Attributes    map[string]float64 `json:"Attributes" dynamodbav:"Attributes"`
	Abilities     map[string]float64 `json:"Abilities" dynamodbav:"Abilities"`
	Essence       float64            `json:"Essence" dynamodbav:"Essence"`
	Health        float64            `json:"Health" dynamodbav:"Health"`
	RoomID        int64              `json:"RoomID" dynamodbav:"RoomID"`
	Inventory     map[string]string  `json:"Inventory" dynamodbav:"Inventory"`
}

func NewCharacter() *Character {
	return &Character{
		Attributes:  make(map[string]float64),
		Abilities:   make(map[string]float64),
		Inventory:   make(map[string]*Item),
		CombatRange: make(map[uuid.UUID]float64),
		inputChan:   make(chan string, 10),
		outputChan:  make(chan string, 10),
		End:         make(chan bool),
		Mutex:       sync.RWMutex{},
		prompt:      "\n\r> ",
	}
}

func (c *Character) Run() error {
	if c == nil || c.Player == nil {
		return fmt.Errorf("invalid character or player")
	}

	if c.Player.ctx == nil {
		return fmt.Errorf("player context is nil")
	}

	Logger.Debug("Starting character run", "characterName", c.Name)

	if err := c.initializeCharacter(); err != nil {
		return fmt.Errorf("character initialization failed: %w", err)
	}

	return c.InputLoop()
}

func (c *Character) initializeCharacter() error {
	// Execute initial look command
	ExecuteLookCommand(c, []string{})

	// Send initial prompt
	select {
	case c.outputChan <- c.prompt:
		return nil
	case <-c.Player.ctx.Done():
		return fmt.Errorf("context cancelled before prompt")
	}
}

func (c *Character) Stop() error {
	Logger.Debug("Stopping character", "characterName", c.Name, "characterID", c.ID)

	if c.Game == nil {
		return fmt.Errorf("game is nil")
	}

	select {
	case c.End <- true:
	default:
		// Channel already closed or full
	}

	c.Mutex.Lock()
	defer c.Mutex.Unlock()

	if err := c.cleanupRoom(); err != nil {
		return err
	}

	if err := WriteCharacter(c, c.Game.Database); err != nil {
		Logger.Error("Error saving character data",
			"characterName", c.Name,
			"characterID", c.ID,
			"error", err)
		return fmt.Errorf("failed to save character: %w", err)
	}

	c.Game.Mutex.Lock()
	delete(c.Game.Characters, c.ID)
	c.Game.Mutex.Unlock()

	Logger.Debug("Character stopped successfully",
		"characterName", c.Name,
		"characterID", c.ID)
	return nil
}

func (c *Character) cleanupRoom() error {
	if c.Room != nil {
		SendRoomMessageExcept(c.Room,
			fmt.Sprintf("\n\r%s has left the room.\n\r", c.Name), c)

		c.Room.Mutex.Lock()
		delete(c.Room.Characters, c.ID)
		c.Room.Mutex.Unlock()
	}
	return nil
}

func CreateCharacter(name string, player *Player, room *Room, archetypeName string, game *Game) (*Character, error) {
	// Validate character name
	if game.CharacterBloomFilter.Test([]byte(name)) {
		return nil, fmt.Errorf("character name '%s' already exists", name)
	}

	character := NewCharacter()
	character.ID = uuid.New()
	character.Name = name
	character.Player = player
	character.Room = room
	character.Game = game
	character.Health = float64(game.StartingHealth)
	character.Essence = float64(game.StartingEssence)
	character.LastEdited = time.Now()
	character.LastSaved = time.Now()

	if archetypeName != "" {
		if archetype, ok := game.ArcheTypes[archetypeName]; ok {
			for attr, value := range archetype.Attributes {
				character.Attributes[attr] = value
			}
			for ability, value := range archetype.Abilities {
				character.Abilities[ability] = value
			}
			if archetype.StartRoom != 0 {
				if startRoom, ok := game.Rooms[archetype.StartRoom]; ok {
					character.Room = startRoom
				}
			}
		} else {
			return nil, fmt.Errorf("archetype '%s' not found", archetypeName)
		}
	}

	// Save character to database
	if err := WriteCharacter(character, game.Database); err != nil {
		return nil, fmt.Errorf("failed to save character: %w", err)
	}

	// Update player's character list
	player.mutex.Lock()
	if player.characterList == nil {
		player.characterList = make(map[string]uuid.UUID)
	}
	player.characterList[name] = character.ID
	player.mutex.Unlock()

	// Save updated player data
	if err := player.WritePlayer(); err != nil {
		return nil, fmt.Errorf("failed to save player data: %w", err)
	}

	game.Mutex.Lock()
	game.Characters[character.ID] = character
	game.Mutex.Unlock()

	game.CharacterBloomFilter.Add([]byte(name))
	SendRoomMessageExcept(character.Room, fmt.Sprintf("\n\r%s has arrived.\n\r", character.Name), character)

	return character, nil
}

func LoadCharacter(characterID uuid.UUID, player *Player, game *Game) (*Character, error) {
	character := NewCharacter()
	character.ID = characterID
	character.Player = player
	character.Game = game

	cd := &CharacterData{}
	key := map[string]*dynamodb.AttributeValue{
		"CharacterID": {S: aws.String(characterID.String())},
	}

	if err := game.Database.Get("characters", key, cd); err != nil {
		return nil, fmt.Errorf("error loading character data: %w", err)
	}

	if err := character.FromData(cd, game); err != nil {
		return nil, fmt.Errorf("error reconstructing character: %w", err)
	}

	game.Mutex.Lock()
	game.Characters[character.ID] = character
	game.Mutex.Unlock()

	SendRoomMessageExcept(character.Room, fmt.Sprintf("\n\r%s has arrived.\n\r", character.Name), character)
	character.LastSaved = time.Now()

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
		PlayerID:      c.Player.playerID,
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
func (c *Character) FromData(cd *CharacterData, Game *Game) error {
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
	room, exists := Game.Rooms[cd.RoomID]
	if !exists {
		Logger.Warn("Room not found, defaulting to room ID 0", "roomID", cd.RoomID)
		room, exists = Game.Rooms[0]
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
		item, err := LoadItem(itemID.String(), Game.Database)
		if err != nil {
			Logger.Error("Error loading item for character", "itemID", itemID, "characterName", c.Name, "error", err)
			continue
		}
		c.Inventory[name] = item
	}

	return nil
}

// WriteCharacter saves the character to the DynamoDB database.
func WriteCharacter(character *Character, kp *KeyPair) error {

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

// DeleteCharacter removes a character from the player's character list and the database.
func (kp *KeyPair) DeleteCharacter(Player *Player, characterName string) error {
	Logger.Debug("Attempting to delete character", "playerName", Player.playerID, "characterName", characterName)

	// Check if the character exists in the player's character list
	characterID, exists := Player.characterList[characterName]
	if !exists {
		return fmt.Errorf("character %s not found for player %s", characterName, Player.playerID)
	}

	// Remove the character from the player's character list
	delete(Player.characterList, characterName)

	// Update the player data in the database
	err := Player.WritePlayer()
	if err != nil {
		Logger.Error("Failed to update player data after character deletion", "playerName", Player.playerID, "error", err)
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

	Logger.Info("Successfully deleted character", "playerName", Player.playerID, "characterName", characterName, "characterID", characterID)
	return nil
}

// AddCharacterName adds a character name to the bloom filter to prevent duplicates.
func AddCharacterName(name string, game *Game) {

	game.CharacterBloomFilter.AddString(strings.ToLower(name))
	Logger.Debug("Added character name to bloom filter", "characterName", name)

}

// CharacterNameExists checks if a character name already exists using the bloom filter.
func CharacterNameExists(name string, game *Game) bool {
	exists := game.CharacterBloomFilter.TestString(strings.ToLower(name))
	if exists {
		Logger.Info("Character name exists", "characterName", name)
	}
	return exists
}

// WearItem allows a character to wear an item from their inventory.
func WearItem(item *Item, c *Character) error {
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

	c.Mutex.RLock()
	defer c.Mutex.RUnlock()

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
func AddToInventory(item *Item, c *Character) {
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

	c.Mutex.RLock()
	defer c.Mutex.RUnlock()

	lowercaseName := strings.ToLower(itemName)

	for _, item := range c.Inventory {
		if strings.Contains(strings.ToLower(item.Name), lowercaseName) {
			return item
		}
	}

	return nil
}

// RemoveFromInventory removes an item from the character's inventory.
func RemoveFromInventory(item *Item, c *Character) {
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
func RemoveWornItem(item *Item, c *Character) error {
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

func moveCharacter(character *Character, direction string) error {
	// Check if the character is in a room
	if character.Room == nil {
		return errors.New(msgNoRoom)
	}

	// Lock current room to check exit
	character.Room.Mutex.Lock()

	selectedExit, exists := character.Room.Exits[direction]
	if !exists || selectedExit == nil {
		character.Room.Mutex.Unlock()
		return errors.New(msgInvalidDir)
	}

	targetRoom := selectedExit.TargetRoom
	if targetRoom == nil {
		character.Room.Mutex.Unlock()
		return errors.New(msgPathNowhere)
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
	SendRoomMessageExcept(oldRoom, oldRoomMsg, character)

	// Update character's room
	character.Room = targetRoom

	// Initialize character map if needed
	if targetRoom.Characters == nil {
		targetRoom.Characters = make(map[uuid.UUID]*Character)
	}

	// Add to new room
	targetRoom.Characters[character.ID] = character

	// Send message to new room while locked
	SendRoomMessageExcept(targetRoom, newRoomMsg, character)

	// Update timestamps
	character.LastEdited = time.Now()
	oldRoom.LastEdited = time.Now()
	targetRoom.LastEdited = time.Now()

	// Release locks in reverse order
	targetRoom.Mutex.Unlock()
	character.Room.Mutex.Unlock()
	character.Mutex.Lock()

	// Show the new room to the character
	ExecuteLookCommand(character, []string{})

	Logger.Debug("Character moved successfully", "character", character.Name, "from", oldRoom.RoomID, "to", targetRoom.RoomID, "direction", direction)

	return nil
}

// InputLoop is the main loop that handles player commands.
// It reads commands from the player's input and executes them accordingly.
func (c *Character) InputLoop() error {
	var lastCommand string
	shouldQuit := false
	const commandTimeout = 5 * time.Second

	for !shouldQuit {
		select {
		case <-c.Player.ctx.Done():
			return fmt.Errorf("player context cancelled")

		case inputLine, ok := <-c.inputChan:
			if !ok {
				return fmt.Errorf("input channel closed")
			}
			if lastCommand == "" {
				lastCommand = strings.Replace(inputLine, "\n", "\n\r", -1)
			}

		case <-c.Game.ticker.C:
			if lastCommand != "" {
				cmdCtx, cancel := context.WithTimeout(c.Player.ctx, commandTimeout)
				defer cancel()

				verb, tokens, err := ValidateCommand(strings.TrimSpace(lastCommand))
				if err != nil {
					select {
					case c.outputChan <- err.Error() + "\n\r":
					case <-cmdCtx.Done():
						return fmt.Errorf("command context cancelled")
					}
				} else {
					shouldQuit = ExecuteCommand(c, verb, tokens)
					Logger.Debug("Command executed",
						"character", c.Name,
						"command", strings.Join(tokens, " "))
				}

				if !shouldQuit {
					select {
					case c.outputChan <- c.prompt:
					case <-cmdCtx.Done():
						return fmt.Errorf("prompt context cancelled")
					default:
						Logger.Warn("Unable to send prompt", "characterName", c.Name)
					}
				}

				lastCommand = ""
			}
		}
	}

	return nil
}
