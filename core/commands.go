package core

import (
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"time"
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

type CommandHandler func(character *Character, tokens []string) bool

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

func ExecuteCommand(character *Character, verb string, tokens []string) bool {
	if character == nil {
		Logger.Error("Attempted to execute command with nil character")
		return false
	}

	handler, ok := CommandHandlers[verb]
	if !ok {
		// This should never happen due to ValidateCommand, but we'll handle it gracefully
		Logger.Error("Command handler missing for validated command", "verb", verb)
		character.Player.ToPlayer <- "\n\rInternal error processing command.\n\r"
		return false
	}

	// Track command execution time
	start := time.Now()

	// Execute the command
	quit := handler(character, tokens)

	// Only log if command took longer than expected
	elapsed := time.Since(start)
	if elapsed > 100*time.Millisecond {
		Logger.Warn("Slow command execution",
			"verb", verb,
			"duration", elapsed,
			"character", character.Name)
	}

	// True indicates the player is quitting
	return quit
}

func ExecuteQuitCommand(character *Character, tokens []string) bool {
	if character == nil {
		Logger.Error("Attempted to quit with nil character")
		return true
	}

	if character.Player == nil || character.Room == nil || character.Server == nil {
		Logger.Error("Invalid character state during quit",
			"hasPlayer", character.Player != nil,
			"hasRoom", character.Room != nil,
			"hasServer", character.Server != nil)
		return true
	}

	playerID := character.Player.PlayerID
	characterName := character.Name
	currentRoom := character.Room

	Logger.Info("Player initiating quit", "playerName", playerID)

	// Send quit message to player before we start cleanup
	character.Player.ToPlayer <- "\n\rSaving character state...\n\r"

	// Save character state to database first
	err := character.Server.Database.WriteCharacter(character)
	if err != nil {
		Logger.Error("Failed to save character state on quit",
			"characterName", characterName,
			"error", err)
		character.Player.ToPlayer <- "\n\rWarning: Failed to save character state.\n\r"
	}

	// Save player data
	err = character.Server.Database.WritePlayer(character.Player)
	if err != nil {
		Logger.Error("Failed to save player data on quit",
			"playerName", playerID,
			"error", err)
		character.Player.ToPlayer <- "\n\rWarning: Failed to save player data.\n\r"
	}

	// Lock order: server -> room
	character.Server.Mutex.Lock()
	defer character.Server.Mutex.Unlock()

	currentRoom.Mutex.Lock()
	defer currentRoom.Mutex.Unlock()

	// Remove character from room and server
	delete(currentRoom.Characters, character.ID)
	delete(character.Server.Characters, character.ID)

	// Notify room of departure (while locks are held)
	for _, c := range currentRoom.Characters {
		if c.Player != nil {
			c.Player.ToPlayer <- fmt.Sprintf("\n\r%s has left.\n\r", characterName)
			c.Player.ToPlayer <- c.Player.Prompt
		}
	}

	// Final goodbye and cleanup
	character.Player.ToPlayer <- "\n\rGoodbye!\n\r"
	close(character.Player.FromPlayer) // Signal to input goroutine

	Logger.Info("Player quit successful",
		"playerName", playerID,
		"characterName", characterName,
		"savedState", err == nil)

	return true
}

func ExecuteSayCommand(character *Character, tokens []string) bool {
	if character == nil || character.Room == nil {
		Logger.Error("Invalid character or room state for say command")
		return false
	}

	Logger.Info("Player is saying something", "playerName", character.Player.PlayerID)

	if len(tokens) < 2 {
		character.Player.ToPlayer <- "\n\rWhat do you want to say?\n\r"
		return false
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
		c.Player.ToPlayer <- broadcastMessage
		c.Player.ToPlayer <- c.Player.Prompt
	}

	// Send to speaker
	character.Player.ToPlayer <- speakerMessage

	return false
}

func ExecuteLookCommand(character *Character, tokens []string) bool {
	if character == nil {
		Logger.Error("Attempted to look with nil character")
		return false
	}

	Logger.Info("Player is looking", "playerName", character.Player.PlayerID)

	// Handle looking at specific targets if provided
	if len(tokens) > 1 {
		target := strings.ToLower(strings.Join(tokens[1:], " "))
		desc := getLookTarget(character, target)
		character.Player.ToPlayer <- desc
		return false
	}

	// Look at room
	room := character.Room
	if room == nil {
		character.Player.ToPlayer <- "\n\rYou are floating in the void.\n\r"
		return false
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

	character.Player.ToPlayer <- roomInfo.String()
	return false
}

func ExecuteGoCommand(character *Character, tokens []string) bool {
	if character == nil {
		Logger.Error("Attempted to move with nil character")
		return false
	}

	// Check arguments
	if len(tokens) < 2 {
		character.Player.ToPlayer <- msgNoDirection
		return false
	}

	// Use the raw direction as provided - no normalization
	direction := strings.ToLower(strings.Join(tokens[1:], " "))

	// Check if character can move
	if !character.CanEscape() {
		character.Player.ToPlayer <- msgCantEscape
		return false
	}

	if err := moveCharacter(character, direction); err != nil {
		character.Player.ToPlayer <- err.Error()
		return false
	}

	// Clear combat state after successful move
	character.ExitCombat()

	return false
}

func ExecuteChallengeCommand(character *Character, tokens []string) bool {

	Logger.Info("Player is attempting a challenge", "playerName", character.Player.PlayerID)

	// Ensure the correct number of arguments are provided
	if len(tokens) < 3 {
		character.Player.ToPlayer <- "\n\rUsage: challenge <attackerScore> <defenderScore>\n\r"
		return false
	}

	// Parse attacker and defender scores from the command arguments
	attackerScore, err := strconv.ParseFloat(tokens[1], 64)
	if err != nil {
		character.Player.ToPlayer <- "\n\rInvalid attacker score format. Please enter a valid number.\n\r"
		return false
	}

	defenderScore, err := strconv.ParseFloat(tokens[2], 64)
	if err != nil {
		character.Player.ToPlayer <- "\n\rInvalid defender score format. Please enter a valid number.\n\r"
		return false
	}

	// Calculate the outcome using the Challenge function
	outcome := Challenge(attackerScore, defenderScore, character.Server.Balance)

	// Provide feedback to the player based on the challenge outcome
	feedbackMessage := fmt.Sprintf("\n\rChallenge outcome: %f\n\r", outcome)
	character.Player.ToPlayer <- feedbackMessage

	return false
}

func ExecuteWhoCommand(character *Character, tokens []string) bool {
	if character == nil || character.Server == nil {
		Logger.Error("Invalid character or server state in who command")
		return false
	}

	server := character.Server
	server.Mutex.Lock()

	// Early return if no one is online
	if len(server.Characters) == 0 {
		server.Mutex.Unlock()
		character.Player.ToPlayer <- whoEmpty
		return false
	}

	// Collect names while under lock
	names := make([]string, 0, len(server.Characters))
	for _, char := range server.Characters {
		if char != nil && char.Player != nil {
			names = append(names, char.Name)
		}
	}
	server.Mutex.Unlock()

	// Sort names
	sort.Strings(names)

	// Calculate column layout
	columnWidth := maxNameWidth + nameSpacing
	columns := character.Player.ConsoleWidth / columnWidth
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

	character.Player.ToPlayer <- sb.String()

	Logger.Info("Who list displayed",
		"player", character.Name,
		"online_count", len(names))

	return false
}

func ExecutePasswordCommand(character *Character, tokens []string) bool {

	Logger.Info("Player is attempting to change their password", "playerName", character.Player.PlayerID)

	if len(tokens) != 3 {
		character.Player.ToPlayer <- "\n\rUsage: password <oldPassword> <newPassword>\n\r"
		return false
	}

	oldPassword := tokens[1]
	newPassword := tokens[2]

	err := ChangePassword(character.Server, character.Player.PlayerID, oldPassword, newPassword)
	if err != nil {
		Logger.Error("Failed to change password for user", "playerName", character.Player.PlayerID, "error", err)
		character.Player.ToPlayer <- "\n\rFailed to change password. Please try again.\n\r"
		return false
	}

	character.Player.ToPlayer <- "\n\rPassword changed successfully.\n\r"
	return false // Keep the command loop running
}

func ExecuteShowCommand(character *Character, tokens []string) bool {

	Logger.Info("Player is displaying character information", "playerName", character.Player.PlayerID)

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
	player.ToPlayer <- output.String()

	return false // Keep the command loop running
}

func ExecuteTakeCommand(character *Character, tokens []string) bool {
	if len(tokens) < 2 {
		character.Player.ToPlayer <- "\n\rUsage: take <item name>\n\r"
		return false
	}

	itemName := strings.ToLower(strings.Join(tokens[1:], " "))
	var itemToTake *Item

	for _, item := range character.Room.Items {
		if strings.Contains(strings.ToLower(item.Name), itemName) && item.CanPickUp {
			itemToTake = item
			break
		}
	}

	if itemToTake == nil {
		character.Player.ToPlayer <- "\n\rYou can't find that item or it can't be picked up.\n\r"
		return false
	}

	if !character.CanCarryItem(itemToTake) {
		character.Player.ToPlayer <- "\n\rYou can't carry any more items.\n\r"
		return false
	}

	// Try to place the item in the right hand first, then the left hand if right is occupied
	var handSlot string
	if character.Inventory["right_hand"] == nil {
		handSlot = "right_hand"
	} else if character.Inventory["left_hand"] == nil {
		handSlot = "left_hand"
	}

	if handSlot == "" {
		character.Player.ToPlayer <- "\n\rYour hands are full. You need a free hand to pick up an item.\n\r"
		return false
	}

	character.Room.RemoveItem(itemToTake)
	character.Mutex.Lock()
	character.Inventory[handSlot] = itemToTake
	character.Mutex.Unlock()

	SendRoomMessage(character.Room, fmt.Sprintf("\n\r%s picks up %s.\n\r", character.Name, itemToTake.Name))
	character.Player.ToPlayer <- fmt.Sprintf("\n\rYou take %s and hold it in your %s.\n\r", itemToTake.Name, strings.Replace(handSlot, "_", " ", -1))
	return false
}

func ExecuteInventoryCommand(character *Character, tokens []string) bool {

	Logger.Info("Player is checking their inventory", "playerName", character.Player.PlayerID)

	inventoryList := character.ListInventory()
	character.Player.ToPlayer <- inventoryList
	return false
}

func ExecuteDropCommand(character *Character, tokens []string) bool {
	if len(tokens) < 2 {
		character.Player.ToPlayer <- "\n\rUsage: drop <item name>\n\r"
		return false
	}

	itemName := strings.ToLower(strings.Join(tokens[1:], " "))
	var itemToDrop *Item
	var handSlot string

	// Check if the item is in a hand slot
	for slot, item := range character.Inventory {
		if (slot == "left_hand" || slot == "right_hand") && strings.Contains(strings.ToLower(item.Name), itemName) {
			itemToDrop = item
			handSlot = slot
			break
		}
	}

	if itemToDrop == nil {
		character.Player.ToPlayer <- "\n\rYou're not holding that item.\n\r"
		return false
	}
	character.Mutex.Lock()
	delete(character.Inventory, handSlot)
	character.Mutex.Unlock()
	character.Room.Mutex.Lock()
	character.Room.AddItem(itemToDrop)
	character.Room.Mutex.Unlock()

	character.Player.ToPlayer <- fmt.Sprintf("\n\rYou drop %s.\n\r", itemToDrop.Name)
	SendRoomMessage(character.Room, fmt.Sprintf("\n\r%s drops %s.\n\r", character.Name, itemToDrop.Name))
	return false
}

func ExecuteWearCommand(character *Character, tokens []string) bool {

	Logger.Info("Player is attempting to wear an item", "playerName", character.Player.PlayerID)

	if len(tokens) < 2 {
		character.Player.ToPlayer <- "\n\rUsage: wear <item name>\n\r"
		return false
	}

	itemName := strings.ToLower(strings.Join(tokens[1:], " "))
	itemToWear := character.FindInInventory(itemName)

	if itemToWear == nil {
		character.Player.ToPlayer <- "\n\rYou don't have that item.\n\r"
		return false
	}

	if !itemToWear.Wearable {
		character.Player.ToPlayer <- "\n\rYou can't wear that.\n\r"
		return false
	}

	if itemToWear.IsWorn {
		character.Player.ToPlayer <- "\n\rYou're already wearing that.\n\r"
		return false
	}

	if err := character.WearItem(itemToWear); err != nil {
		character.Player.ToPlayer <- fmt.Sprintf("\n\r%s\n\r", err.Error())
		return false
	}

	character.Player.ToPlayer <- fmt.Sprintf("\n\rYou wear %s.\n\r", itemToWear.Name)
	SendRoomMessage(character.Room, fmt.Sprintf("\n\r%s wears %s.\n\r", character.Name, itemToWear.Name))
	return false
}

func ExecuteRemoveCommand(character *Character, tokens []string) bool {
	if len(tokens) < 2 {
		character.Player.ToPlayer <- "\n\rUsage: remove <item name>\n\r"
		return false
	}

	itemName := strings.ToLower(strings.Join(tokens[1:], " "))
	var itemToRemove *Item

	for _, item := range character.Inventory {
		if item != nil && item.IsWorn && strings.Contains(strings.ToLower(item.Name), itemName) {
			itemToRemove = item
			break
		}
	}

	if itemToRemove == nil {
		character.Player.ToPlayer <- "\n\rYou're not wearing that item.\n\r"
		return false
	}

	err := character.RemoveWornItem(itemToRemove)
	if err != nil {
		character.Player.ToPlayer <- fmt.Sprintf("\n\r%s\n\r", err.Error())
		return false
	}

	character.Player.ToPlayer <- fmt.Sprintf("\n\rYou remove %s.\n\r", itemToRemove.Name)
	SendRoomMessage(character.Room, fmt.Sprintf("\n\r%s removes %s.\n\r", character.Name, itemToRemove.Name))
	return false
}

func ExecuteExamineCommand(character *Character, tokens []string) bool {

	Logger.Info("Player is examining an item", "playerName", character.Player.PlayerID)

	if len(tokens) < 2 {
		character.Player.ToPlayer <- "\n\rUsage: examine <item name>\n\r"
		return false
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
		character.Player.ToPlayer <- "\n\rYou don't see that item here.\n\r"
		return false
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

	character.Player.ToPlayer <- description
	return false
}

func ExecuteAssessCommand(character *Character, tokens []string) bool {
	Logger.Info("Player is assessing combat situation", "playerName", character.Player.PlayerID)

	if !character.IsInCombat() {
		character.Player.ToPlayer <- "\n\rYou are not currently in combat.\n\r"
		return false
	}

	var assessment strings.Builder
	assessment.WriteString("\n\rCombat Assessment:\n\r")

	if len(character.CombatRange) == 0 {
		assessment.WriteString("You are in combat, but not engaged with any specific opponents.\n\r")
	} else {
		for targetID, distance := range character.CombatRange {
			targetCharacter := character.Server.Characters[targetID]
			if targetCharacter == nil {
				continue // Skip if the character is not found (should not happen in normal circumstances)
			}

			var rangeDescription string
			switch distance {
			case 0:
				rangeDescription = "far"
			case 1:
				rangeDescription = "pole"
			case 2:
				rangeDescription = "melee"
			default:
				rangeDescription = "unknown"
			}

			facingInfo := ""
			if targetCharacter.GetFacing() == character {
				facingInfo = " and is facing you"
			}

			assessment.WriteString(fmt.Sprintf("%s is at %s range%s.\n\r", targetCharacter.Name, rangeDescription, facingInfo))
		}
	}

	if character.CanEscape() {
		assessment.WriteString("You can attempt to escape from combat.\n\r")
	} else {
		assessment.WriteString("You cannot escape from combat at this time.\n\r")
	}

	character.Player.ToPlayer <- assessment.String()
	return false
}

func ExecuteFaceCommand(character *Character, tokens []string) bool {
	if len(tokens) < 2 {
		character.Player.ToPlayer <- "\n\rUsage: face <character name>\n\r"
		return false
	}

	targetName := strings.Join(tokens[1:], " ")
	var targetCharacter *Character

	// Find the target character in the same room
	for _, c := range character.Room.Characters {
		if strings.EqualFold(c.Name, targetName) {
			targetCharacter = c
			break
		}
	}

	if targetCharacter == nil {
		character.Player.ToPlayer <- fmt.Sprintf("\n\rYou don't see %s here.\n\r", targetName)
		return false
	}

	// Set facing for the character executing the command
	character.SetFacing(targetCharacter)

	// Enter combat and set range to far (0) for both characters
	character.EnterCombat()
	targetCharacter.EnterCombat()

	character.SetCombatRange(targetCharacter, 0) // 0 represents far range
	targetCharacter.SetCombatRange(character, 0) // Reciprocal setting

	character.Player.ToPlayer <- fmt.Sprintf("\n\rYou are now facing %s at far range.\n\r", targetCharacter.Name)

	// Notify the target character
	targetCharacter.Player.ToPlayer <- fmt.Sprintf("\n\r%s is now facing you at far range.\n\r", character.Name)
	targetCharacter.Player.ToPlayer <- targetCharacter.Player.Prompt

	return false
}

func ExecuteHelpCommand(character *Character, tokens []string) bool {

	Logger.Info("Player is requesting help", "playerName", character.Player.PlayerID)

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
		"\n\rwho - List all characters online" +
		"\n\rpassword <oldPassword> <newPassword> - Change your password" +
		"\n\rquit - Quit the game\n\r"

	character.Player.ToPlayer <- helpMessage
	return false
}
