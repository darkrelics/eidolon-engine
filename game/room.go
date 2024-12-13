package game

import (
	"fmt"
	"strconv"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/service/dynamodb"
	"github.com/google/uuid"

	"github.com/robinje/multi-user-dungeon/core"
)

// NewRoom creates a new Room instance with initialized fields.
func NewRoom(roomID int64, area string, title string, description string) *core.Room {
	room := &core.Room{
		RoomID:      roomID,
		Area:        area,
		Title:       title,
		Description: description,
		Exits:       make(map[string]*core.Exit),
		Characters:  make(map[uuid.UUID]*core.Character),
		Items:       make(map[uuid.UUID]*core.Item),
		Mutex:       sync.RWMutex{},
		LastSaved:   time.Now(),
		LastEdited:  time.Now(),
	}
	core.Logger.Debug("Created room", "room_title", room.Title, "room_id", room.RoomID)
	return room
}

// StoreRooms stores all rooms into the DynamoDB database.
func StoreRooms(rooms map[int64]*core.Room, kp *core.KeyPair) error {

	for _, room := range rooms {
		room.Mutex.Lock()

		// Cleanup nil items before saving
		CleanupNilItems(room)

		err := WriteRoom(room, kp)
		if err != nil {
			core.Logger.Error("Error storing room", "room_id", room.RoomID, "error", err)
			return fmt.Errorf("error storing room %d: %w", room.RoomID, err)
		}

		room.LastSaved = time.Now()

		room.Mutex.Unlock()

	}
	core.Logger.Debug("Successfully stored all rooms")
	return nil
}

// LoadRooms retrieves all rooms from the DynamoDB database and returns them as a map of Room instances.
func LoadRooms(kp *core.KeyPair) (map[int64]*core.Room, error) {
	rooms := make(map[int64]*core.Room)

	var roomsData []core.RoomData
	err := kp.Scan("rooms", &roomsData)
	if err != nil {
		core.Logger.Error("Error scanning rooms", "error", err)
		return nil, fmt.Errorf("error scanning rooms: %w", err)
	}

	// First pass: create all rooms without exits or items
	for _, roomData := range roomsData {
		room := NewRoom(roomData.RoomID, roomData.Area, roomData.Title, roomData.Description)
		rooms[room.RoomID] = room
	}

	// Load all exits
	allExits, err := LoadAllExits(kp)
	if err != nil {
		core.Logger.Error("Error loading exits", "error", err)
		return nil, fmt.Errorf("error loading exits: %w", err)
	}

	// Load all items
	allItems, err := LoadAllItems(kp)
	if err != nil {
		core.Logger.Error("Error loading items", "error", err)
		return nil, fmt.Errorf("error loading items: %w", err)
	}

	// Second pass: add exits and items to rooms, and resolve target rooms
	for _, room := range rooms {
		roomData, exists := findRoomData(roomsData, room.RoomID)
		if !exists {
			core.Logger.Warn("Room data not found", "room_id", room.RoomID)
			continue
		}

		// Add exits to the room
		room.Exits = make(map[string]*core.Exit)
		for _, exitID := range roomData.ExitIDs {
			if exit, exists := allExits[exitID]; exists {
				room.Exits[exit.Direction] = exit
				// Resolve TargetRoom pointer
				if targetRoom, exists := rooms[exit.TargetRoom.RoomID]; exists {
					exit.TargetRoom = targetRoom
				} else {
					core.Logger.Warn("Target room not found for exit", "room_id", room.RoomID, "direction", exit.Direction, "target_room_id", exit.TargetRoom.RoomID)
				}
			}
		}

		// Add items to the room
		room.Items = make(map[uuid.UUID]*core.Item)
		for _, itemID := range roomData.ItemIDs {
			itemUUID, err := uuid.Parse(itemID)
			if err != nil {
				core.Logger.Error("Invalid item UUID", "item_id", itemID, "error", err)
				continue
			}
			if item, exists := allItems[itemID]; exists {
				room.Items[itemUUID] = item
			} else {
				core.Logger.Warn("Item not found for room", "room_id", room.RoomID, "item_id", itemID)
			}
		}
	}

	core.Logger.Debug("Successfully loaded rooms from database", "count", len(rooms))
	return rooms, nil
}

// Helper function to find room data by ID
func findRoomData(roomsData []core.RoomData, roomID int64) (core.RoomData, bool) {
	for _, data := range roomsData {
		if data.RoomID == roomID {
			return data, true
		}
	}
	return core.RoomData{}, false
}

// LoadAllExits loads all exits for all rooms.
func LoadAllExits(kp *core.KeyPair) (map[string]*core.Exit, error) {
	var exitsData []core.ExitData

	err := kp.Scan("exits", &exitsData)
	if err != nil {
		core.Logger.Error("Error scanning exits", "error", err)
		return nil, fmt.Errorf("error scanning exits: %w", err)
	}

	exits := make(map[string]*core.Exit)
	for _, exitData := range exitsData {
		exitID, err := uuid.Parse(exitData.ExitID)
		if err != nil {
			core.Logger.Error("Invalid exit UUID", "exit_id", exitData.ExitID, "error", err)
			continue
		}

		exits[exitData.ExitID] = &core.Exit{
			ExitID:     exitID,
			Direction:  exitData.Direction,
			TargetRoom: &core.Room{RoomID: exitData.TargetRoom}, // Temporary Room object, will be resolved later
			Visible:    exitData.Visible,
			LastSaved:  time.Now(),
			LastEdited: time.Now(),
		}
	}

	core.Logger.Debug("Loaded all exits", "total_exits", len(exits))
	return exits, nil
}

// DisplayRooms logs information about all rooms, useful for debugging.
func DisplayRooms(rooms map[int64]*core.Room) {
	core.Logger.Info("Displaying rooms")
	for _, room := range rooms {
		core.Logger.Info("Room", "room_id", room.RoomID, "title", room.Title)
		for _, exit := range room.Exits {
			core.Logger.Info("  Exit", "direction", exit.Direction, "target_room", exit.TargetRoom)
		}
	}
}

// WriteRoom stores a single room into the DynamoDB database.
func WriteRoom(room *core.Room, kp *core.KeyPair) error {
	if room == nil {
		return fmt.Errorf("cannot write nil room")
	}

	room.Mutex.Lock()
	defer room.Mutex.Unlock()

	// Write exits separately
	for _, exit := range room.Exits {
		exitData := core.ExitData{
			ExitID:     exit.ExitID.String(),
			Direction:  exit.Direction,
			TargetRoom: exit.TargetRoom.RoomID,
			Visible:    exit.Visible,
		}
		err := kp.Put("exits", exitData)
		if err != nil {
			core.Logger.Error("Error writing exit data", "room_id", room.RoomID, "direction", exit.Direction, "error", err)
			return fmt.Errorf("error writing exit data: %w", err)
		}

		exit.LastSaved = time.Now()
	}

	roomData := ToData(room)
	err := kp.Put("rooms", roomData)
	if err != nil {
		core.Logger.Error("Error writing room data", "room_id", room.RoomID, "error", err)
		return fmt.Errorf("error writing room data: %w", err)
	}

	room.LastSaved = time.Now()

	core.Logger.Info("Successfully wrote room and exits to database", "room_id", room.RoomID)
	return nil
}

// SaveActiveRooms saves all active rooms to the database if they have been edited since the last save.
func SaveActiveRooms(g *core.Game) error {
	if g == nil {
		return fmt.Errorf("server is nil")
	}

	g.Mutex.RLock()
	defer g.Mutex.RUnlock()

	core.Logger.Debug("Starting to save active rooms...")

	for roomID, room := range g.Rooms {
		if room == nil {
			core.Logger.Debug("Skipping nil room", "room_id", roomID)
			continue
		}

		// Check if LastEdited is after LastSaved, skip if it is not
		if !room.LastEdited.After(room.LastSaved) {
			core.Logger.Debug("Room not edited since last save, skipping", "room_id", roomID)
			continue
		}

		// Attempt to write the room to the database
		if err := WriteRoom(room, g.Database); err != nil {
			core.Logger.Error("Error saving room", "room_id", roomID, "error", err)
			// Continue saving other rooms even if one fails
		} else {
			// Update LastSaved after successful save
			room.LastSaved = time.Now()
			core.Logger.Debug("Successfully saved room", "room_id", roomID)
		}
	}

	core.Logger.Info("Finished saving active rooms")
	return nil
}

// AddExit adds an exit to the room's exits map.
func AddExit(exit *core.Exit, r *core.Room) {
	r.Mutex.Lock()
	defer r.Mutex.Unlock()

	if exit == nil {
		core.Logger.Warn("Attempted to add nil exit to room", "room_id", r.RoomID)
		return
	}

	r.Exits[exit.Direction] = exit

	r.LastEdited = time.Now()

	core.Logger.Debug("Added exit to room", "room_id", r.RoomID, "direction", exit.Direction)
}

// SendRoomMessage sends a message to all characters in the room.
func SendRoomMessage(r *core.Room, message string) {
	core.Logger.Debug("Sending message to room", "room_id", r.RoomID, "message", message)

	for _, character := range r.Characters {

		if character.Player == nil || character.Player.ToPlayer == nil {
			core.Logger.Warn("Player or ToPlayer channel is nil", "playerID", character.Player.PlayerID, "room_id", r.RoomID)
			continue
		}

		character.Player.ToPlayer <- message
		character.Player.ToPlayer <- character.Player.Prompt
	}
}

// SendRoomMessageExcept sends a message to all characters in the room except for the specified character.
func SendRoomMessageExcept(r *core.Room, message string, character *core.Character) {
	core.Logger.Debug("Sending message to room except for character", "room_id", r.RoomID, "message", message, "character_id", character.ID)

	for _, c := range r.Characters {
		if c == character {
			continue
		}

		if c.Player == nil || c.Player.ToPlayer == nil {
			core.Logger.Warn("Player or ToPlayer channel is nil", "playerID", c.Player.PlayerID, "room_id", r.RoomID)
			continue
		}

		c.Player.ToPlayer <- message
		c.Player.ToPlayer <- c.Player.Prompt
	}
}

// ToData converts a Room to RoomData for database storage.
func ToData(r *core.Room) *core.RoomData {
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

	return &core.RoomData{
		RoomID:      r.RoomID,
		Area:        r.Area,
		Title:       r.Title,
		Description: r.Description,
		ExitIDs:     exitIDs,
		ItemIDs:     itemIDs,
	}
}

// FromData populates a Room from RoomData.
func FromData(data *core.RoomData, exits map[string]*core.Exit, items map[string]*core.Item, r *core.Room) {
	r.Mutex.Lock()
	defer r.Mutex.Unlock()

	r.RoomID = data.RoomID
	r.Area = data.Area
	r.Title = data.Title
	r.Description = data.Description

	r.Exits = make(map[string]*core.Exit)
	for _, direction := range data.ExitIDs {
		if exit, ok := exits[direction]; ok {
			r.Exits[direction] = exit
		}
	}

	r.Items = make(map[uuid.UUID]*core.Item)
	for _, itemIDStr := range data.ItemIDs {
		if itemID, err := uuid.Parse(itemIDStr); err == nil {
			if item, ok := items[itemIDStr]; ok {
				r.Items[itemID] = item
			}
		}
	}
}

// LoadItemsForRoom loads all items for a specific room
func LoadItemsForRoom(roomID int64, kp *core.KeyPair) (map[uuid.UUID]*core.Item, error) {
	items := make(map[uuid.UUID]*core.Item)

	var itemsData []core.ItemData
	// Assume we have a way to query items by room ID
	err := kp.Query("items", "RoomID = :roomID", map[string]*dynamodb.AttributeValue{
		":roomID": {N: aws.String(strconv.FormatInt(roomID, 10))},
	}, &itemsData)

	if err != nil {
		return nil, fmt.Errorf("error querying items for room %d: %w", roomID, err)
	}

	for _, itemData := range itemsData {
		item, err := itemFromData(&itemData, kp)
		if err != nil {
			core.Logger.Error("Error creating item from data", "item_id", itemData.ItemID, "error", err)
			continue
		}
		items[item.ID] = item
	}

	return items, nil
}

// CleanupNilItems removes any nil items from the room's item list.
func CleanupNilItems(r *core.Room) {
	r.Mutex.Lock()
	defer r.Mutex.Unlock()

	for id, item := range r.Items {
		if item == nil {
			delete(r.Items, id)
			core.Logger.Info("Removed nil item from room", "itemID", id, "roomID", r.RoomID)
		}
	}

	r.LastEdited = time.Now()
}
