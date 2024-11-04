package core

import (
	"fmt"
	"sort"
	"strconv"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/service/dynamodb"
	"github.com/google/uuid"
)

// NewRoom creates a new Room instance with initialized fields.
func NewRoom(roomID int64, area string, title string, description string) *Room {
	room := &Room{
		RoomID:      roomID,
		Area:        area,
		Title:       title,
		Description: description,
		Exits:       make(map[string]*Exit),
		Characters:  make(map[uuid.UUID]*Character),
		Items:       make(map[uuid.UUID]*Item),
		Mutex:       sync.RWMutex{},
		LastSaved:   time.Now(),
		LastEdited:  time.Now(),
	}
	Logger.Debug("Created room", "room_title", room.Title, "room_id", room.RoomID)
	return room
}

// StoreRooms stores all rooms into the DynamoDB database.
func (kp *KeyPair) StoreRooms(rooms map[int64]*Room) error {

	for _, room := range rooms {
		room.Mutex.Lock()

		// Cleanup nil items before saving
		room.CleanupNilItems()

		err := kp.WriteRoom(room)
		if err != nil {
			Logger.Error("Error storing room", "room_id", room.RoomID, "error", err)
			return fmt.Errorf("error storing room %d: %w", room.RoomID, err)
		}

		room.LastSaved = time.Now()

		room.Mutex.Unlock()

	}
	Logger.Debug("Successfully stored all rooms")
	return nil
}

// LoadRooms retrieves all rooms from the DynamoDB database and returns them as a map of Room instances.
func (kp *KeyPair) LoadRooms() (map[int64]*Room, error) {
	rooms := make(map[int64]*Room)

	var roomsData []RoomData
	err := kp.Scan("rooms", &roomsData)
	if err != nil {
		Logger.Error("Error scanning rooms", "error", err)
		return nil, fmt.Errorf("error scanning rooms: %w", err)
	}

	// First pass: create all rooms without exits or items
	for _, roomData := range roomsData {
		room := NewRoom(roomData.RoomID, roomData.Area, roomData.Title, roomData.Description)
		rooms[room.RoomID] = room
	}

	// Load all exits
	allExits, err := kp.LoadAllExits()
	if err != nil {
		Logger.Error("Error loading exits", "error", err)
		return nil, fmt.Errorf("error loading exits: %w", err)
	}

	// Load all items
	allItems, err := kp.LoadAllItems()
	if err != nil {
		Logger.Error("Error loading items", "error", err)
		return nil, fmt.Errorf("error loading items: %w", err)
	}

	// Second pass: add exits and items to rooms, and resolve target rooms
	for _, room := range rooms {
		roomData, exists := findRoomData(roomsData, room.RoomID)
		if !exists {
			Logger.Warn("Room data not found", "room_id", room.RoomID)
			continue
		}

		// Add exits to the room
		room.Exits = make(map[string]*Exit)
		for _, exitID := range roomData.ExitIDs {
			if exit, exists := allExits[exitID]; exists {
				room.Exits[exit.Direction] = exit
				// Resolve TargetRoom pointer
				if targetRoom, exists := rooms[exit.TargetRoom.RoomID]; exists {
					exit.TargetRoom = targetRoom
				} else {
					Logger.Warn("Target room not found for exit", "room_id", room.RoomID, "direction", exit.Direction, "target_room_id", exit.TargetRoom.RoomID)
				}
			}
		}

		// Add items to the room
		room.Items = make(map[uuid.UUID]*Item)
		for _, itemID := range roomData.ItemIDs {
			itemUUID, err := uuid.Parse(itemID)
			if err != nil {
				Logger.Error("Invalid item UUID", "item_id", itemID, "error", err)
				continue
			}
			if item, exists := allItems[itemID]; exists {
				room.Items[itemUUID] = item
			} else {
				Logger.Warn("Item not found for room", "room_id", room.RoomID, "item_id", itemID)
			}
		}
	}

	Logger.Debug("Successfully loaded rooms from database", "count", len(rooms))
	return rooms, nil
}

// Helper function to find room data by ID
func findRoomData(roomsData []RoomData, roomID int64) (RoomData, bool) {
	for _, data := range roomsData {
		if data.RoomID == roomID {
			return data, true
		}
	}
	return RoomData{}, false
}

// LoadAllExits loads all exits for all rooms.
func (kp *KeyPair) LoadAllExits() (map[string]*Exit, error) {
	var exitsData []ExitData

	err := kp.Scan("exits", &exitsData)
	if err != nil {
		Logger.Error("Error scanning exits", "error", err)
		return nil, fmt.Errorf("error scanning exits: %w", err)
	}

	exits := make(map[string]*Exit)
	for _, exitData := range exitsData {
		exitID, err := uuid.Parse(exitData.ExitID)
		if err != nil {
			Logger.Error("Invalid exit UUID", "exit_id", exitData.ExitID, "error", err)
			continue
		}

		exits[exitData.ExitID] = &Exit{
			ExitID:     exitID,
			Direction:  exitData.Direction,
			TargetRoom: &Room{RoomID: exitData.TargetRoom}, // Temporary Room object, will be resolved later
			Visible:    exitData.Visible,
			LastSaved:  time.Now(),
			LastEdited: time.Now(),
		}
	}

	Logger.Debug("Loaded all exits", "total_exits", len(exits))
	return exits, nil
}

// DisplayRooms logs information about all rooms, useful for debugging.
func DisplayRooms(rooms map[int64]*Room) {
	Logger.Info("Displaying rooms")
	for _, room := range rooms {
		Logger.Info("Room", "room_id", room.RoomID, "title", room.Title)
		for _, exit := range room.Exits {
			Logger.Info("  Exit", "direction", exit.Direction, "target_room", exit.TargetRoom)
		}
	}
}

// WriteRoom stores a single room into the DynamoDB database.
func (kp *KeyPair) WriteRoom(room *Room) error {
	if room == nil {
		return fmt.Errorf("cannot write nil room")
	}

	room.Mutex.Lock()
	defer room.Mutex.Unlock()

	// Write exits separately
	for _, exit := range room.Exits {
		exitData := ExitData{
			ExitID:     exit.ExitID.String(),
			Direction:  exit.Direction,
			TargetRoom: exit.TargetRoom.RoomID,
			Visible:    exit.Visible,
		}
		err := kp.Put("exits", exitData)
		if err != nil {
			Logger.Error("Error writing exit data", "room_id", room.RoomID, "direction", exit.Direction, "error", err)
			return fmt.Errorf("error writing exit data: %w", err)
		}

		exit.LastSaved = time.Now()
	}

	roomData := room.ToData()
	err := kp.Put("rooms", roomData)
	if err != nil {
		Logger.Error("Error writing room data", "room_id", room.RoomID, "error", err)
		return fmt.Errorf("error writing room data: %w", err)
	}

	room.LastSaved = time.Now()

	Logger.Info("Successfully wrote room and exits to database", "room_id", room.RoomID)
	return nil
}

// SaveActiveRooms saves all active rooms to the database if they have been edited since the last save.
func (g *Game) SaveActiveRooms() error {
	if g == nil {
		return fmt.Errorf("server is nil")
	}

	g.Mutex.Lock()
	defer g.Mutex.Unlock()

	Logger.Debug("Starting to save active rooms...")

	for roomID, room := range g.Rooms {
		if room == nil {
			Logger.Debug("Skipping nil room", "room_id", roomID)
			continue
		}

		// Check if LastEdited is after LastSaved, skip if it is not
		if !room.LastEdited.After(room.LastSaved) {
			Logger.Debug("Room not edited since last save, skipping", "room_id", roomID)
			continue
		}

		// Attempt to write the room to the database
		if err := g.Database.WriteRoom(room); err != nil {
			Logger.Error("Error saving room", "room_id", roomID, "error", err)
			// Continue saving other rooms even if one fails
		} else {
			// Update LastSaved after successful save
			room.LastSaved = time.Now()
			Logger.Debug("Successfully saved room", "room_id", roomID)
		}
	}

	Logger.Info("Finished saving active rooms")
	return nil
}

// AddExit adds an exit to the room's exits map.
func (r *Room) AddExit(exit *Exit) {
	r.Mutex.Lock()
	defer r.Mutex.Unlock()

	if exit == nil {
		Logger.Warn("Attempted to add nil exit to room", "room_id", r.RoomID)
		return
	}

	r.Exits[exit.Direction] = exit

	r.LastEdited = time.Now()

	Logger.Debug("Added exit to room", "room_id", r.RoomID, "direction", exit.Direction)
}

// SendRoomMessage sends a message to all characters in the room.
func SendRoomMessage(r *Room, message string) {
	Logger.Debug("Sending message to room", "room_id", r.RoomID, "message", message)

	for _, character := range r.Characters {

		if character.Player == nil || character.Player.ToPlayer == nil {
			Logger.Warn("Player or ToPlayer channel is nil", "playerID", character.Player.PlayerID, "room_id", r.RoomID)
			continue
		}

		character.Player.ToPlayer <- message
		character.Player.ToPlayer <- character.Player.Prompt
	}
}

// SendRoomMessageExcept sends a message to all characters in the room except for the specified character.
func SendRoomMessageExcept(r *Room, message string, character *Character) {
	Logger.Debug("Sending message to room except for character", "room_id", r.RoomID, "message", message, "character_id", character.ID)

	for _, c := range r.Characters {
		if c == character {
			continue
		}

		if c.Player == nil || c.Player.ToPlayer == nil {
			Logger.Warn("Player or ToPlayer channel is nil", "playerID", c.Player.PlayerID, "room_id", r.RoomID)
			continue
		}

		c.Player.ToPlayer <- message
		c.Player.ToPlayer <- c.Player.Prompt
	}
}

// getVisibleExits returns a sorted list of visible exit directions from the room.
func getVisibleExits(r *Room) []string {
	Logger.Debug("Getting visible exits for room", "room_id", r.RoomID)

	if r.Exits == nil {
		Logger.Debug("Exits map is nil for room", "room_id", r.RoomID)
		return []string{}
	}

	visibleExits := make([]string, 0, len(r.Exits))
	for direction, exit := range r.Exits {
		if exit.Visible {
			visibleExits = append(visibleExits, direction)
		}
	}
	sort.Strings(visibleExits)
	return visibleExits
}

// ToData converts a Room to RoomData for database storage.
func (r *Room) ToData() *RoomData {
	r.Mutex.Lock()
	defer r.Mutex.Unlock()

	exitIDs := make([]string, 0, len(r.Exits))
	for _, exit := range r.Exits {
		exitIDs = append(exitIDs, exit.ExitID.String())
	}

	itemIDs := make([]string, 0, len(r.Items))
	for itemID := range r.Items {
		itemIDs = append(itemIDs, itemID.String())
	}

	return &RoomData{
		RoomID:      r.RoomID,
		Area:        r.Area,
		Title:       r.Title,
		Description: r.Description,
		ExitIDs:     exitIDs,
		ItemIDs:     itemIDs,
	}
}

// FromData populates a Room from RoomData.
func (r *Room) FromData(data *RoomData, exits map[string]*Exit, items map[string]*Item) {
	r.Mutex.Lock()
	defer r.Mutex.Unlock()

	r.RoomID = data.RoomID
	r.Area = data.Area
	r.Title = data.Title
	r.Description = data.Description

	r.Exits = make(map[string]*Exit)
	for _, direction := range data.ExitIDs {
		if exit, ok := exits[direction]; ok {
			r.Exits[direction] = exit
		}
	}

	r.Items = make(map[uuid.UUID]*Item)
	for _, itemIDStr := range data.ItemIDs {
		if itemID, err := uuid.Parse(itemIDStr); err == nil {
			if item, ok := items[itemIDStr]; ok {
				r.Items[itemID] = item
			}
		}
	}
}

// LoadItemsForRoom loads all items for a specific room
func (kp *KeyPair) LoadItemsForRoom(roomID int64) (map[uuid.UUID]*Item, error) {
	items := make(map[uuid.UUID]*Item)

	var itemsData []ItemData
	// Assume we have a way to query items by room ID
	err := kp.Query("items", "RoomID = :roomID", map[string]*dynamodb.AttributeValue{
		":roomID": {N: aws.String(strconv.FormatInt(roomID, 10))},
	}, &itemsData)

	if err != nil {
		return nil, fmt.Errorf("error querying items for room %d: %w", roomID, err)
	}

	for _, itemData := range itemsData {
		item, err := kp.itemFromData(&itemData)
		if err != nil {
			Logger.Error("Error creating item from data", "item_id", itemData.ItemID, "error", err)
			continue
		}
		items[item.ID] = item
	}

	return items, nil
}

// CleanupNilItems removes any nil items from the room's item list.
func (r *Room) CleanupNilItems() {
	r.Mutex.Lock()
	defer r.Mutex.Unlock()

	for id, item := range r.Items {
		if item == nil {
			delete(r.Items, id)
			Logger.Info("Removed nil item from room", "itemID", id, "roomID", r.RoomID)
		}
	}

	r.LastEdited = time.Now()
}
