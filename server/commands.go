package main

import (
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
)

const (
	msgNoExits     = "There are no visible exits.\n\r"
	msgAlone       = "You are alone.\n\r"
	msgAlsoHere    = "Also here: "
	msgItems       = "Items in the room:\n\r"
	msgNoDirection = "\n\rWhich direction do you want to go?\n\r"
	msgCantEscape  = "\n\rYou can't escape!\n\r"
	msgNoRoom      = "\n\rYou are not in any room to move from.\n\r"
	msgInvalidDir  = "\n\rYou cannot go that way.\n\r"
	msgPathNowhere = "\n\rThe path leads nowhere.\n\r"
	whoHeader      = "\n\rOnline Characters\n\r"
	whoEmpty       = "\n\rNo other players online.\n\r"
	maxNameWidth   = 15 // Width allocated per name
	nameSpacing    = 2  // Spaces between columns
)

type CommandHandler func(character *Character, tokens []string)

var CommandHandlers = map[string]CommandHandler{
	"quit":      ExecuteQuitCommand,
	"show":      ExecuteShowCommand,
	"look":      ExecuteLookCommand,
	"say":       ExecuteSayCommand,
	"go":        ExecuteGoCommand,
	"help":      ExecuteHelpCommand,
	"who":       ExecuteWhoCommand,
	"password":  ExecutePasswordCommand,
	"challenge": ExecuteChallengeCommand,
	"take":      ExecuteTakeCommand,
	"get":       ExecuteTakeCommand, // Alias for take command
	"drop":      ExecuteDropCommand,
	"inventory": ExecuteInventoryCommand,
	"wear":      ExecuteWearCommand,
	"remove":    ExecuteRemoveCommand,
	"examine":   ExecuteExamineCommand,
	"assess":    ExecuteAssessCommand,
	"face":      ExecuteFaceCommand,
	"advance":   ExecuteAdvanceCommand,
	"retreat":   ExecuteRetreatCommand,
	"i":         ExecuteInventoryCommand, // Alias for inventory command
	"inv":       ExecuteInventoryCommand, // Alias for inventory command
	"\"":        ExecuteSayCommand,       // Allow for double quotes to be used as a shortcut for the say command
	"'":         ExecuteSayCommand,       // Allow for single quotes to be used as a shortcut for the say command
	"q!":        ExecuteQuitCommand,      // Allow for q! to be used as a shortcut for the quit command
}

func ValidateCommand(command string) (string, []string, error) {
	// Early return for empty input
	if len(command) == 0 {
		return "", nil, errors.New("\n\rNo command entered.\n\r")
	}

	// Handle quoted strings and split into tokens
	var tokens []string
	var currentToken strings.Builder
	inQuotes := false

	// Single pass tokenization
	for i := 0; i < len(command); i++ {
		switch command[i] {
		case '"':
			inQuotes = !inQuotes
		case ' ', '\t':
			if !inQuotes {
				if currentToken.Len() > 0 {
					tokens = append(tokens, currentToken.String())
					currentToken.Reset()
				}
			} else {
				currentToken.WriteByte(command[i])
			}
		default:
			currentToken.WriteByte(command[i])
		}
	}

	// Add final token if exists
	if currentToken.Len() > 0 {
		tokens = append(tokens, currentToken.String())
	}

	// Validate tokens
	if len(tokens) == 0 {
		return "", nil, errors.New("\n\rNo command entered.\n\r")
	}

	// Convert first token to lowercase for command lookup
	verb := strings.ToLower(tokens[0])

	// Validate command exists
	if _, exists := CommandHandlers[verb]; !exists {
		return "", nil, fmt.Errorf("\n\rCommand '%s' not understood.\n\r", verb)
	}

	// Only log valid commands
	Logger.Debug("Valid command received", "verb", verb, "args", tokens[1:])

	return verb, tokens, nil
}

func ExecuteCommand(character *Character, verb string, tokens []string) {

	if character == nil {
		Logger.Error("Attempted to execute command with nil character")
		return
	}

	handler, ok := CommandHandlers[verb]
	if !ok {
		// This should never happen due to ValidateCommand, but we'll handle it gracefully
		Logger.Error("Command handler missing for validated command", "verb", verb)
		character.Player.toPlayer <- "\n\rInternal error processing command.\n\r"
		return
	}

	go func() {

		Logger.Debug("Executing command", "verb", verb, "character", character.Name)

		start := time.Now()

		// Execute the command
		handler(character, tokens)

		elapsed := time.Since(start)
		if elapsed > 100*time.Millisecond {
			Logger.Warn("Slow command execution", "verb", verb, "duration", elapsed, "character", character.Name)
		}

		Logger.Debug("Command execution complete", "verb", verb, "character", character.Name)

	}()

}

func ExecuteQuitCommand(character *Character, tokens []string) {

	if character == nil {
		Logger.Error("Attempted to quit with nil character")
		return
	}

	if character.Player == nil {
		Logger.Error("Character has no associated player")
		// Perform character-only cleanup if applicable
		character.Stop()
		return
	}

	Logger.Info("Player initiating quit", "playerName", character.Player.playerID)

	// Notify the player
	select {
	case character.Player.toPlayer <- "\n\rSaving character state...\n\r":
	default:
		Logger.Warn("Failed to notify player: ToPlayer channel is full or closed", "playerName", character.Player.playerID)
	}

	// Signal the end of character's lifecycle
	character.End <- true

	// Perform cleanup operations
	character.Stop()

}

func ExecuteHelpCommand(character *Character, tokens []string) {

	Logger.Debug("Player is requesting help", "playerName", character.Player.playerID)

	helpMessage := "\n\rAvailable Commands:" +
		"\n\rhelp - Display available commands" +
		"\n\rshow - Display character information" +
		"\n\rsay <message> - Say something to all players" +
		"\n\rlook - Look around the room" +
		"\n\rgo <direction> - Move in a direction" +
		"\n\rtake <item> - Take an item from the room" +
		"\n\rdrop <item> - Drop a held item" +
		"\n\rwear <item> - Wear an item from your inventory" +
		"\n\rremove <item> - Remove a worn item" +
		"\n\rexamine <item> - Get detailed information about an item" +
		"\n\rinventory (or i) - Check your inventory" +
		"\n\rassess - Assess your current combat situation" +
		"\n\rface <character> - Face a character in the room" +
		"\n\radvance <target> <range> - Advance towards a target. Range can be far, pole, or melee (default)" +
		"\n\rretreat - Retreat from the current combat" +
		"\n\rwho - List all characters online" +
		"\n\rpassword - Change your password" +
		"\n\rquit - Quit the game\n\r"

	character.Player.toPlayer <- helpMessage
}

func ExecuteSayCommand(character *Character, tokens []string) {
	if character == nil || character.Room == nil {
		Logger.Error("Invalid character or room state for say command")
		return
	}

	Logger.Debug("Player is saying something", "playerName", character.Player.playerID)

	if len(tokens) < 2 {
		character.Player.toPlayer <- "\n\rWhat do you want to say?\n\r"
		return
	}

	message := strings.Join(tokens[1:], " ")

	// Lock the room while we access its character list
	character.Room.Mutex.Lock()
	roomChars := make([]*Character, 0, len(character.Room.Characters))
	for _, c := range character.Room.Characters {
		if c != character {
			roomChars = append(roomChars, c)
		}
	}
	character.Room.Mutex.Unlock()

	// Construct messages once
	broadcastMessage := fmt.Sprintf("\n\r%s says %s\n\r", character.Name, message)
	speakerMessage := fmt.Sprintf("\n\rYou say %s\n\r", message)

	// Send to other characters without holding the lock
	for _, c := range roomChars {
		c.Player.toPlayer <- broadcastMessage
		c.Player.toPlayer <- c.Player.prompt
	}

	// Send to speaker
	character.Player.toPlayer <- speakerMessage

}

func ExecuteLookCommand(character *Character, tokens []string) {
	if character == nil {
		Logger.Error("Attempted to look with nil character")
		return
	}

	Logger.Debug("Player is looking", "playerName", character.Player.playerID)

	// Handle looking at specific targets if provided
	if len(tokens) > 1 {
		target := strings.ToLower(strings.Join(tokens[1:], " "))
		desc := getLookTarget(character, target)
		character.Player.toPlayer <- desc
		return
	}

	// Look at room
	room := character.Room
	if room == nil {
		character.Player.toPlayer <- "\n\rYou are floating in the void.\n\r"
		return
	}

	room.Mutex.Lock()
	defer room.Mutex.Unlock()

	var roomInfo strings.Builder
	roomInfo.Grow(1024) // Pre-allocate reasonable buffer

	// Room Title and Description
	roomInfo.WriteString("\n\r[")
	roomInfo.WriteString(ApplyColor("bright_white", room.Title))
	roomInfo.WriteString("]\n\r")
	roomInfo.WriteString(room.Description)
	roomInfo.WriteString("\n\r")

	// Exits - collect while under lock
	exits := make([]string, 0, len(room.Exits))
	for direction, exit := range room.Exits {
		if exit != nil && exit.Visible {
			exits = append(exits, direction)
		}
	}

	if len(exits) == 0 {
		roomInfo.WriteString(msgNoExits)
	} else {
		sort.Strings(exits)
		roomInfo.WriteString("Obvious exits: ")
		roomInfo.WriteString(strings.Join(exits, ", "))
		roomInfo.WriteString("\n\r")
	}

	// Characters - collect while under lock
	chars := make([]string, 0, len(room.Characters))
	for _, c := range room.Characters {
		if c != nil && c != character {
			chars = append(chars, c.Name)
		}
	}

	if len(chars) == 0 {
		roomInfo.WriteString(msgAlone)
	} else {
		roomInfo.WriteString(msgAlsoHere)
		roomInfo.WriteString(strings.Join(chars, ", "))
		roomInfo.WriteString("\n\r")
	}

	// Items - collect while under lock
	items := make([]string, 0, len(room.Items))
	for _, item := range room.Items {
		if item != nil && item.CanPickUp {
			items = append(items, item.Name)
		}
	}

	if len(items) > 0 {
		roomInfo.WriteString(msgItems)
		for _, item := range items {
			roomInfo.WriteString("- ")
			roomInfo.WriteString(item)
			roomInfo.WriteString("\n\r")
		}
	}

	character.Player.toPlayer <- roomInfo.String()
}

func ExecuteGoCommand(character *Character, tokens []string) {
	if character == nil {
		Logger.Error("Attempted to move with nil character")
		return
	}

	// Check arguments
	if len(tokens) < 2 {
		character.Player.toPlayer <- msgNoDirection
		return
	}

	// Use the raw direction as provided - no normalization
	direction := strings.ToLower(strings.Join(tokens[1:], " "))

	// Check if character can move
	if !character.CanEscape() {
		character.Player.toPlayer <- msgCantEscape
		return
	}

	if err := moveCharacter(character, direction); err != nil {
		character.Player.toPlayer <- err.Error()
		return
	}

	// Clear combat state after successful move
	character.ExitCombat()

}

func ExecuteChallengeCommand(character *Character, tokens []string) {

	Logger.Debug("Player is attempting a challenge", "playerName", character.Player.playerID)

	// Ensure the correct number of arguments are provided
	if len(tokens) < 3 {
		character.Player.toPlayer <- "\n\rUsage: challenge <attackerScore> <defenderScore>\n\r"
		return
	}

	// Parse attacker and defender scores from the command arguments
	attackerScore, err := strconv.ParseFloat(tokens[1], 64)
	if err != nil {
		character.Player.toPlayer <- "\n\rInvalid attacker score format. Please enter a valid number.\n\r"
		return
	}

	defenderScore, err := strconv.ParseFloat(tokens[2], 64)
	if err != nil {
		character.Player.toPlayer <- "\n\rInvalid defender score format. Please enter a valid number.\n\r"
		return
	}

	// Calculate the outcome using the Challenge function
	outcome := Challenge(attackerScore, defenderScore, character.Game.Balance)

	// Provide feedback to the player based on the challenge outcome
	feedbackMessage := fmt.Sprintf("\n\rChallenge outcome: %f\n\r", outcome)
	character.Player.toPlayer <- feedbackMessage

}

func ExecuteWhoCommand(character *Character, tokens []string) {
	if character == nil || character.Game == nil {
		Logger.Error("Invalid character or server state in who command")
		return
	}

	server := character.Game

	// Early return if no one is online
	if len(server.Characters) == 0 {
		character.Player.toPlayer <- whoEmpty
		return
	}

	// Collect names while under lock
	names := make([]string, 0, len(server.Characters))
	for _, char := range server.Characters {
		if char != nil && char.Player != nil {
			names = append(names, char.Name)
		}
	}

	// Sort names
	sort.Strings(names)

	// Calculate column layout
	columnWidth := maxNameWidth + nameSpacing
	columns := character.Player.consoleWidth / columnWidth
	if columns < 1 {
		columns = 1
	}

	rows := len(names) / columns
	if len(names)%columns != 0 {
		rows++
	}

	// Build the output
	var sb strings.Builder
	sb.WriteString(whoHeader)

	// Display names in columns
	for row := 0; row < rows; row++ {
		for col := 0; col < columns; col++ {
			index := row + (col * rows)
			if index < len(names) {
				name := ApplyColor("bright_white", names[index])
				sb.WriteString(fmt.Sprintf("%-*s", maxNameWidth+nameSpacing, name))
			}
		}
		sb.WriteString("\n\r")
	}

	sb.WriteString(fmt.Sprintf("Total Players Online: %d\n\r", len(names)))

	character.Player.toPlayer <- sb.String()

	Logger.Debug("Who list displayed", "player", character.Name, "online_count", len(names))

}

func ExecutePasswordCommand(character *Character, tokens []string) {
	player := character.Player

	// Disable echo to prevent password display
	player.echo = false
	defer func() {
		player.echo = true
	}()

	// Password policy message
	policy := "\n\rPassword must contain:\n\r" +
		"- At least 8 characters\n\r" +
		"- At least one uppercase letter\n\r" +
		"- At least one lowercase letter\n\r" +
		"- At least one number\n\r" +
		"- At least one special character\n\r"

	player.toPlayer <- "\n\rChanging password. " + policy

	// Get current password
	player.toPlayer <- "\n\rEnter current password: "
	currentPass, ok := <-player.fromPlayer
	if !ok {
		return
	}

	// Get new password
	player.toPlayer <- "\n\rEnter new password: "
	newPass, ok := <-player.fromPlayer
	if !ok {
		return
	}

	// Validate password complexity
	if !isValidPassword(newPass) {
		player.toPlayer <- "\n\rPassword does not meet requirements.\n\r"
		return
	}

	// Confirm new password
	player.toPlayer <- "\n\rConfirm new password: "
	confirmPass, ok := <-player.fromPlayer
	if !ok {
		return
	}

	// Check if passwords match
	if newPass != confirmPass {
		player.toPlayer <- "\n\rPasswords do not match.\n\r"
		return
	}

	// Attempt to change password
	err := player.server.ChangePassword(player, currentPass, newPass)
	if err != nil {
		Logger.Error("Password change failed",
			"playerName", player.playerID,
			"errorType", err.Error())

		switch {
		case strings.Contains(err.Error(), "incorrect username or password"):
			player.toPlayer <- "\n\rCurrent password is incorrect.\n\r"
		case strings.Contains(err.Error(), "password reset required"):
			player.toPlayer <- "\n\rPassword reset required. Please contact an administrator.\n\r"
		case strings.Contains(err.Error(), "authentication failed"):
			player.toPlayer <- "\n\rAuthentication failed. Please try again later.\n\r"
		default:
			player.toPlayer <- "\n\rFailed to change password. Please try again later.\n\r"
		}
		return
	}

	player.toPlayer <- "\n\rPassword changed successfully.\n\r"
}

func ExecuteShowCommand(character *Character, tokens []string) {

	Logger.Debug("Player is displaying character information", "playerName", character.Player.playerID)

	player := character.Player
	var output strings.Builder

	// First row: Character's Name
	output.WriteString(fmt.Sprintf("Name: %s\r\n", character.Name))

	// Health and Essence (integer component only)
	output.WriteString(fmt.Sprintf("Health: %d, Essence: %d\r\n", int(character.Health), int(character.Essence)))

	// Attributes
	output.WriteString("Attributes:\r\n")
	for attr, value := range character.Attributes {
		output.WriteString(fmt.Sprintf("%-15s: %2d\r\n", attr, int(value)))
	}

	// Abilities (only those with scores of 1 or greater)
	output.WriteString("Abilities:\r\n")
	for ability, score := range character.Abilities {
		if score >= 1 {
			output.WriteString(fmt.Sprintf("%-15s: %2d\r\n", ability, int(score)))
		}
	}

	// Send the composed information to the player
	player.toPlayer <- output.String()

}

func ExecuteTakeCommand(character *Character, tokens []string) {
	if len(tokens) < 2 {
		character.Player.toPlayer <- "\n\rUsage: take <item name>\n\r"
		return
	}

	itemName := strings.ToLower(strings.Join(tokens[1:], " "))

	// Lock room to check items
	character.Room.Mutex.RLock()
	var itemToTake *Item
	var itemID uuid.UUID

	for id, item := range character.Room.Items {
		if item != nil && strings.Contains(strings.ToLower(item.Name), itemName) && item.CanPickUp {
			itemToTake = item
			itemID = id
			break
		}
	}

	// Early unlock if item not found
	if itemToTake == nil {
		character.Room.Mutex.RUnlock()
		character.Player.toPlayer <- "\n\rYou can't find that item or it can't be picked up.\n\r"
		return
	}

	// Lock character to check inventory
	character.Mutex.RLock()

	// Check if character can carry the item
	if !character.CanCarryItem(itemToTake) {
		character.Room.Mutex.RUnlock()
		character.Mutex.RUnlock()
		character.Player.toPlayer <- "\n\rYou can't carry any more items.\n\r"
		return
	}

	// Determine available hand slot
	var handSlot string
	if character.Inventory["right_hand"] == nil {
		handSlot = "right_hand"
	} else if character.Inventory["left_hand"] == nil {
		handSlot = "left_hand"
	}

	if handSlot == "" {
		character.Room.Mutex.RUnlock()
		character.Mutex.RUnlock()
		character.Player.toPlayer <- "\n\rYour hands are full. You need a free hand to pick up an item.\n\r"
		return
	}

	// At this point we have both locks and can safely modify both structures
	delete(character.Room.Items, itemID)
	character.Inventory[handSlot] = itemToTake

	// Update timestamps
	itemToTake.LastEdited = time.Now()
	character.LastEdited = time.Now()
	character.Room.LastEdited = time.Now()

	// Store message before releasing locks
	roomMessage := fmt.Sprintf("\n\r%s picks up %s.\n\r", character.Name, itemToTake.Name)
	playerMessage := fmt.Sprintf("\n\rYou take %s and hold it in your %s.\n\r",
		itemToTake.Name, strings.Replace(handSlot, "_", " ", -1))

	// Release locks
	character.Room.Mutex.RUnlock()
	character.Mutex.RUnlock()

	// Send messages after releasing locks
	SendRoomMessageExcept(character.Room, roomMessage, character)
	character.Player.toPlayer <- playerMessage

	Logger.Debug("Item taken", "character", character.Name, "item", itemToTake.Name, "slot", handSlot)

}

func ExecuteInventoryCommand(character *Character, tokens []string) {

	Logger.Debug("Player is checking their inventory", "playerName", character.Player.playerID)

	inventoryList := character.ListInventory()
	character.Player.toPlayer <- inventoryList
}

func ExecuteDropCommand(character *Character, tokens []string) {
	if len(tokens) < 2 {
		character.Player.toPlayer <- "\n\rUsage: drop <item name>\n\r"
		return
	}

	itemName := strings.ToLower(strings.Join(tokens[1:], " "))

	// Lock character first to check inventory
	character.Mutex.Lock()

	// Find the item and its slot
	var itemToDrop *Item
	var itemSlot string
	var isWorn bool

	for slot, item := range character.Inventory {
		if item != nil && strings.Contains(strings.ToLower(item.Name), itemName) {
			itemToDrop = item
			itemSlot = slot
			isWorn = item.IsWorn
			break
		}
	}

	if itemToDrop == nil {
		character.Mutex.Unlock()
		character.Player.toPlayer <- "\n\rYou don't have that item.\n\r"
		return
	}

	// Can't drop worn items
	if isWorn {
		character.Mutex.Unlock()
		character.Player.toPlayer <- "\n\rYou must remove that item before dropping it.\n\r"
		return
	}

	// Lock room after character
	character.Room.Mutex.Lock()

	// Handle stackable items
	var quantity uint32 = 1
	var dropMessage string

	if itemToDrop.Stackable && itemToDrop.Quantity > 1 {
		// Only drop one from the stack
		itemToDrop.Quantity--

		// Create a new item for the dropped portion
		droppedItem := &Item{
			ID:          uuid.New(),
			PrototypeID: itemToDrop.PrototypeID,
			Name:        itemToDrop.Name,
			Description: itemToDrop.Description,
			Mass:        itemToDrop.Mass,
			Value:       itemToDrop.Value,
			Stackable:   true,
			MaxStack:    itemToDrop.MaxStack,
			Quantity:    1,
			CanPickUp:   itemToDrop.CanPickUp,
			Metadata:    make(map[string]string),
			LastEdited:  time.Now(),
		}

		character.Room.AddItem(droppedItem)
		dropMessage = fmt.Sprintf("one %s", itemToDrop.Name)
	} else {
		// Drop the entire item
		delete(character.Inventory, itemSlot)
		character.Room.AddItem(itemToDrop)
		dropMessage = itemToDrop.Name

		// If it was in a hand slot, update the message
		if itemSlot == "left_hand" || itemSlot == "right_hand" {
			dropMessage = fmt.Sprintf("%s from your %s", itemToDrop.Name,
				strings.Replace(itemSlot, "_", " ", -1))
		}
	}

	// Update timestamps
	character.LastEdited = time.Now()
	character.Room.LastEdited = time.Now()
	itemToDrop.LastEdited = time.Now()

	// Store messages before releasing locks
	playerMsg := fmt.Sprintf("\n\rYou drop %s.\n\r", dropMessage)
	roomMsg := fmt.Sprintf("\n\r%s drops %s.\n\r", character.Name, dropMessage)

	// Release locks in reverse order
	character.Room.Mutex.Unlock()
	character.Mutex.Unlock()

	// Send messages after releasing locks
	character.Player.toPlayer <- playerMsg
	SendRoomMessageExcept(character.Room, roomMsg, character)

	Logger.Debug("Item dropped",
		"character", character.Name,
		"item", itemToDrop.Name,
		"quantity", quantity,
		"slot", itemSlot)

}

func ExecuteWearCommand(character *Character, tokens []string) {
	if len(tokens) < 2 {
		character.Player.toPlayer <- "\n\rUsage: wear <item name>\n\r"
		return
	}

	itemName := strings.ToLower(strings.Join(tokens[1:], " "))

	// Lock character for inventory operations
	character.Mutex.Lock()
	defer character.Mutex.Unlock()

	// Find the item and its slot
	var itemToWear *Item
	var currentSlot string

	for slot, item := range character.Inventory {
		if item != nil && strings.Contains(strings.ToLower(item.Name), itemName) {
			itemToWear = item
			currentSlot = slot
			break
		}
	}

	if itemToWear == nil {
		character.Player.toPlayer <- "\n\rYou don't have that item.\n\r"
		return
	}

	// Validate item can be worn
	if !itemToWear.Wearable || len(itemToWear.WornOn) == 0 {
		character.Player.toPlayer <- "\n\rThat item cannot be worn.\n\r"
		return
	}

	if itemToWear.IsWorn {
		character.Player.toPlayer <- "\n\rYou're already wearing that.\n\r"
		return
	}

	// Verify item is in hand
	if currentSlot != "left_hand" && currentSlot != "right_hand" {
		character.Player.toPlayer <- "\n\rYou must be holding the item to wear it.\n\r"
		return
	}

	// Check if wearing locations are valid and available
	var blockedLocations []string
	for _, location := range itemToWear.WornOn {
		if !WearLocations[location] {
			character.Player.toPlayer <- fmt.Sprintf("\n\rInvalid wear location: %s\n\r", location)
			return
		}
		if existing := character.Inventory[location]; existing != nil {
			blockedLocations = append(blockedLocations, fmt.Sprintf("%s (%s)", location, existing.Name))
		}
	}

	if len(blockedLocations) > 0 {
		character.Player.toPlayer <- fmt.Sprintf("\n\rYou are already wearing something on your %s.\n\r",
			strings.Join(blockedLocations, ", "))
		return
	}

	// Handle stackable items
	if itemToWear.Stackable && itemToWear.Quantity > 1 {
		// Create a new item for the worn piece
		wornItem := &Item{
			ID:          uuid.New(),
			PrototypeID: itemToWear.PrototypeID,
			Name:        itemToWear.Name,
			Description: itemToWear.Description,
			Mass:        itemToWear.Mass,
			Value:       itemToWear.Value,
			Stackable:   true,
			MaxStack:    itemToWear.MaxStack,
			Quantity:    1,
			Wearable:    true,
			WornOn:      itemToWear.WornOn,
			IsWorn:      true,
			LastEdited:  time.Now(),
		}

		// Decrease the stack quantity
		itemToWear.Quantity--
		itemToWear.LastEdited = time.Now()

		// Add worn item to wear locations
		for _, location := range wornItem.WornOn {
			character.Inventory[location] = wornItem
		}
	} else {
		// Remove from hand slot
		delete(character.Inventory, currentSlot)

		// Add to wear locations
		for _, location := range itemToWear.WornOn {
			character.Inventory[location] = itemToWear
		}
		itemToWear.IsWorn = true
		itemToWear.LastEdited = time.Now()
	}

	character.LastEdited = time.Now()

	// Prepare messages
	var itemDesc string
	if len(itemToWear.WornOn) > 1 {
		itemDesc = fmt.Sprintf("%s on your %s", itemToWear.Name, strings.Join(itemToWear.WornOn, " and "))
	} else {
		itemDesc = fmt.Sprintf("%s on your %s", itemToWear.Name, itemToWear.WornOn[0])
	}

	character.Player.toPlayer <- fmt.Sprintf("\n\rYou wear %s.\n\r", itemDesc)
	SendRoomMessageExcept(character.Room, fmt.Sprintf("\n\r%s wears %s.\n\r", character.Name, itemToWear.Name), character)

	Logger.Debug("Item worn",
		"character", character.Name,
		"item", itemToWear.Name,
		"locations", itemToWear.WornOn)

}

func ExecuteRemoveCommand(character *Character, tokens []string) {
	if len(tokens) < 2 {
		character.Player.toPlayer <- "\n\rUsage: remove <item name>\n\r"
		return
	}

	itemName := strings.ToLower(strings.Join(tokens[1:], " "))

	character.Mutex.Lock()
	defer character.Mutex.Unlock()

	// Find the worn item and its locations
	var itemToRemove *Item
	wornLocations := make([]string, 0)

	for location, item := range character.Inventory {
		if item != nil && item.IsWorn && strings.Contains(strings.ToLower(item.Name), itemName) {
			itemToRemove = item
			wornLocations = append(wornLocations, location)
		}
	}

	if itemToRemove == nil {
		character.Player.toPlayer <- "\n\rYou're not wearing that item.\n\r"
		return
	}

	// Find an available hand
	var handSlot string
	switch {
	case character.Inventory["right_hand"] == nil:
		handSlot = "right_hand"
	case character.Inventory["left_hand"] == nil:
		handSlot = "left_hand"
	default:
		character.Player.toPlayer <- "\n\rYour hands are full. You need a free hand to remove that.\n\r"
		return
	}

	// Handle stackable items
	if itemToRemove.Stackable {
		// Create a new item for the removed piece
		removedItem := &Item{
			ID:          uuid.New(),
			PrototypeID: itemToRemove.PrototypeID,
			Name:        itemToRemove.Name,
			Description: itemToRemove.Description,
			Mass:        itemToRemove.Mass,
			Value:       itemToRemove.Value,
			Stackable:   true,
			MaxStack:    itemToRemove.MaxStack,
			Quantity:    1,
			Wearable:    true,
			WornOn:      itemToRemove.WornOn,
			IsWorn:      false,
			LastEdited:  time.Now(),
		}

		// Check for similar items in inventory to stack with
		var stackedWith *Item
		for _, item := range character.Inventory {
			if item != nil && !item.IsWorn && item.PrototypeID == removedItem.PrototypeID &&
				item.Quantity < item.MaxStack {
				stackedWith = item
				break
			}
		}

		if stackedWith != nil {
			// Add to existing stack
			stackedWith.Quantity++
			stackedWith.LastEdited = time.Now()
		} else {
			// Place in hand
			character.Inventory[handSlot] = removedItem
		}

	} else {
		// Remove from worn locations
		for _, location := range wornLocations {
			delete(character.Inventory, location)
		}

		// Place in hand
		character.Inventory[handSlot] = itemToRemove
		itemToRemove.IsWorn = false
	}

	character.LastEdited = time.Now()
	itemToRemove.LastEdited = time.Now()

	// Prepare descriptive messages
	var removeDesc string
	if len(wornLocations) > 1 {
		removeDesc = fmt.Sprintf("%s from your %s",
			itemToRemove.Name,
			strings.Join(wornLocations, " and "))
	} else {
		removeDesc = fmt.Sprintf("%s from your %s",
			itemToRemove.Name,
			wornLocations[0])
	}

	character.Player.toPlayer <- fmt.Sprintf("\n\rYou remove %s.\n\r", removeDesc)
	SendRoomMessageExcept(character.Room, fmt.Sprintf("\n\r%s removes %s.\n\r", character.Name, itemToRemove.Name), character)

	Logger.Debug("Item removed", "character", character.Name, "item", itemToRemove.Name, "from_locations", wornLocations, "to_hand", handSlot)

}

func ExecuteExamineCommand(character *Character, tokens []string) {
	Logger.Debug("Player is examining an item", "playerName", character.Player.playerID)

	if len(tokens) < 2 {
		character.Player.toPlayer <- "\n\rUsage: examine <item name>\n\r"
		return
	}

	itemName := strings.ToLower(strings.Join(tokens[1:], " "))

	// Check inventory first
	item := character.FindInInventory(itemName)

	// If not in inventory, check room
	if item == nil {
		for _, roomItem := range character.Room.Items {
			if strings.Contains(strings.ToLower(roomItem.Name), itemName) {
				item = roomItem
				break
			}
		}
	}

	if item == nil {
		character.Player.toPlayer <- "\n\rYou don't see that item here.\n\r"
		return
	}

	description := fmt.Sprintf("\n\rItem: %s (ID: %s)\n\r", item.Name, item.ID)
	description += fmt.Sprintf("Description: %s\n\r", item.Description)
	description += fmt.Sprintf("Mass: %.2f\n\r", item.Mass)
	description += fmt.Sprintf("Value: %d\n\r", item.Value)
	description += fmt.Sprintf("Stackable: %v\n\r", item.Stackable)
	if item.Stackable {
		description += fmt.Sprintf("Quantity: %d/%d\n\r", item.Quantity, item.MaxStack)
	}

	if item.Wearable {
		description += fmt.Sprintf("Wearable on: %s\n\r", strings.Join(item.WornOn, ", "))
		if item.IsWorn {
			description += "This item is currently being worn.\n\r"
		}
	}

	if item.Container {
		description += "This is a container.\n\r"
		if len(item.Contents) > 0 {
			description += "It contains:\n\r"
			for _, contentItem := range item.Contents {
				description += fmt.Sprintf("  - %s (ID: %s)\n\r", contentItem.Name, contentItem.ID)
			}
		} else {
			description += "It is empty.\n\r"
		}
	}

	if len(item.Verbs) > 0 {
		description += "Special actions:\n\r"
		for verb, action := range item.Verbs {
			description += fmt.Sprintf("  %s: %s\n\r", verb, action)
		}
	}

	if len(item.TraitMods) > 0 {
		description += "Trait Modifications:\n\r"
		for trait, mod := range item.TraitMods {
			description += fmt.Sprintf("  %s: %d\n\r", trait, mod)
		}
	}

	if len(item.Metadata) > 0 {
		description += "Additional Information:\n\r"
		for key, value := range item.Metadata {
			description += fmt.Sprintf("  %s: %s\n\r", key, value)
		}
	}

	character.Player.toPlayer <- description
}
