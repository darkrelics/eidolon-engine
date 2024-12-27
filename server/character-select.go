package main

import (
	"context"
	"fmt"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"github.com/google/uuid"
)

func SelectCharacter(ctx context.Context, player *Player) (*Character, error) {
	options := buildCharacterOptions(player)

	for {
		if err := sendOptions(ctx, player, options); err != nil {
			return nil, err
		}

		input, err := receiveInput(ctx, player)
		if err != nil {
			return nil, err
		}

		if input == "X" && len(options) > 0 {
			if err := handleCharacterDeletion(ctx, options, player); err != nil {
				player.toPlayer <- fmt.Sprintf("Error deleting character: %v\n\r", err)
				continue
			}
			options = buildCharacterOptions(player)
			continue
		}

		choice, err := strconv.Atoi(input)
		if err != nil || choice < 0 || choice > len(options) {
			player.toPlayer <- "Invalid choice. Please select a valid option.\n\r"
			continue
		}

		if choice == 0 {
			return createNewCharacter(player)
		}

		if choice <= len(options) {
			player.mutex.RLock()
			characterID := player.characterList[options[choice-1]]
			player.mutex.RUnlock()
			return LoadCharacter(characterID, player, player.server.game)
		}
	}
}

func createNewCharacter(player *Player) (*Character, error) {
	name, err := getValidCharacterName(player)
	if err != nil {
		return nil, err
	}

	archetype, err := selectArchetype(player)
	if err != nil {
		Logger.Warn("Error selecting archetype", "error", err)
		archetype = ""
	}

	room, err := getStartingRoom(player.server.game, archetype)
	if err != nil {
		Logger.Warn("Error getting starting room", "error", err)
		room = player.server.game.Rooms[0]
	}

	character, err := CreateCharacter(name, player, room, archetype, player.server.game)
	if err != nil {
		Logger.Warn("Error creating character", "error", err)
		return nil, err
	}

	err = WriteCharacter(character, player.server.database)
	if err != nil {
		Logger.Warn("Error writing character", "error", err)
		return nil, err
	}

	player.mutex.Lock()
	if player.characterList == nil {
		player.characterList = make(map[string]uuid.UUID)
	}
	player.characterList[name] = character.ID
	player.mutex.Unlock()

	if err := player.WritePlayer(); err != nil {
		Logger.Warn("Error writing player", "error", err)
		return nil, err
	}

	return character, nil
}

func getValidCharacterName(player *Player) (string, error) {
	player.toPlayer <- "\n\rEnter your character name: "
	name, ok := <-player.fromPlayer
	if !ok {
		return "", fmt.Errorf("player input channel closed")
	}

	name = strings.TrimSpace(name)

	// Name validation rules
	if len(name) < 2 {
		return "", fmt.Errorf("character mame must be at least 3 characters")
	}
	if len(name) > 15 {
		return "", fmt.Errorf("character name must be 15 characters or fewer")
	}
	if !regexp.MustCompile(`^[a-zA-Z]+$`).MatchString(name) {
		return "", fmt.Errorf("character name must contain only letters")
	}
	if player.server.game.CharacterBloomFilter.Test([]byte(name)) {
		return "", fmt.Errorf("character name already exists")
	}

	return name, nil
}

func buildCharacterOptions(player *Player) []string {
	player.mutex.RLock()
	defer player.mutex.RUnlock()

	options := make([]string, 0, len(player.characterList))
	for name := range player.characterList {
		options = append(options, name)
	}
	sort.Strings(options)
	return options
}

func sendOptions(ctx context.Context, player *Player, options []string) error {
	select {
	case <-ctx.Done():
		return ctx.Err()
	case player.toPlayer <- "Select a character:\n\r":
		player.toPlayer <- "0: Create a new character\n\r"
		for i, name := range options {
			player.toPlayer <- fmt.Sprintf("%d: %s\n\r", i+1, name)
		}
		if len(options) > 0 {
			player.toPlayer <- "X: Delete a character\n\r"
		} else {
			player.toPlayer <- "No existing characters found.\n\r"
		}
		player.toPlayer <- "Enter the number of your choice or 'X' to delete: "
		return nil
	}
}

func receiveInput(ctx context.Context, player *Player) (string, error) {
	select {
	case <-ctx.Done():
		return "", ctx.Err()
	case input, ok := <-player.fromPlayer:
		if !ok {
			return "", fmt.Errorf("player input channel closed")
		}
		return strings.TrimSpace(strings.ToUpper(input)), nil
	}
}

func handleCharacterSelection(ctx context.Context, input string, options []string, player *Player) (*Character, bool) {

	if input == "X" && len(options) > 0 {
		if err := handleCharacterDeletion(ctx, options, player); err != nil {
			player.toPlayer <- fmt.Sprintf("Error deleting character: %v\n\r", err)
		}
		return nil, true
	}

	choice, err := strconv.Atoi(input)
	if err != nil || choice < 0 || choice > len(options) {
		player.toPlayer <- "Invalid choice. Please select a valid option.\n\r"
		return nil, true
	}

	character, err := loadOrCreateCharacter(choice, options, player)
	if err != nil {
		player.toPlayer <- fmt.Sprintf("Error: %v\n\r", err)
		return nil, true
	}

	if err := addCharacterToRoom(character); err != nil {
		player.toPlayer <- fmt.Sprintf("Error adding character to room: %v\n\r", err)
		return nil, true
	}

	return character, false
}

func loadOrCreateCharacter(choice int, options []string, player *Player) (*Character, error) {
	game := player.server.game

	if choice == 0 {
		name, err := getValidCharacterName(player)
		if err != nil {
			return nil, fmt.Errorf("name validation: %w", err)
		}

		archetype, err := selectArchetype(player)
		if err != nil {
			return nil, fmt.Errorf("archetype selection: %w", err)
		}

		room, err := getStartingRoom(game, archetype)
		if err != nil {
			return nil, fmt.Errorf("starting room: %w", err)
		}

		character, err := CreateCharacter(name, player, room, archetype, game)
		if err != nil {
			return nil, fmt.Errorf("character creation: %w", err)
		}

		if err := WriteCharacter(character, player.server.database); err != nil {
			return nil, fmt.Errorf("character save: %w", err)
		}

		player.mutex.Lock()
		if player.characterList == nil {
			player.characterList = make(map[string]uuid.UUID)
		}
		player.characterList[name] = character.ID
		player.mutex.Unlock()

		if err := player.WritePlayer(); err != nil {
			return nil, fmt.Errorf("player save: %w", err)
		}

		return character, nil
	}

	if choice <= len(options) {
		player.mutex.RLock()
		characterID := player.characterList[options[choice-1]]
		player.mutex.RUnlock()
		return LoadCharacter(characterID, player, game)
	}

	return nil, fmt.Errorf("invalid choice")
}

func addCharacterToRoom(character *Character) error {
	if character.Room == nil {
		return fmt.Errorf("character has no assigned room")
	}

	character.Room.Mutex.Lock()
	defer character.Room.Mutex.Unlock()
	character.Room.Characters[character.ID] = character
	return nil
}

func validateCharacterName(name string, g *Game) error {
	if len(name) == 0 {
		return fmt.Errorf("character name cannot be empty")
	}

	if len(name) > 15 {
		return fmt.Errorf("character name must be 15 characters or fewer")
	}

	if g.CharacterBloomFilter.Test([]byte(name)) {
		return fmt.Errorf("character name already exists")
	}

	return nil
}

func getStartingRoom(g *Game, archetype string) (*Room, error) {
	g.Mutex.RLock()
	defer g.Mutex.RUnlock()

	startRoomID := int64(1)
	if arch, ok := g.ArcheTypes[archetype]; ok {
		startRoomID = arch.StartRoom
	}

	room, ok := g.Rooms[startRoomID]
	if !ok {
		room, ok = g.Rooms[0]
		if !ok {
			return nil, fmt.Errorf("no starting or default room found")
		}
	}

	return room, nil
}

func promptArchetypeSelection(player *Player, options []string) (int, error) {
	msg := "\n\rSelect a character archetype.\n\r"
	for i, option := range options {
		msg += fmt.Sprintf("%d: %s\n\r", i+1, option)
	}
	msg += "Enter the number of your choice: "

	select {
	case player.toPlayer <- msg:
	default:
		return 0, fmt.Errorf("player output channel blocked")
	}

	selection, ok := <-player.fromPlayer
	if !ok {
		return 0, fmt.Errorf("player input channel closed")
	}

	num, err := strconv.Atoi(strings.TrimSpace(selection))
	if err != nil || num < 1 || num > len(options) {
		return 0, fmt.Errorf("invalid archetype selection")
	}

	return num, nil
}

func handleCharacterDeletion(ctx context.Context, options []string, player *Player) error {
	if err := sendDeletionOptions(ctx, options, player); err != nil {
		return err
	}

	deleteChoice, err := receiveInput(ctx, player)
	if err != nil {
		return err
	}

	deleteIndex, err := strconv.Atoi(strings.TrimSpace(deleteChoice))
	if err != nil || deleteIndex < 1 || deleteIndex > len(options) {
		return fmt.Errorf("invalid deletion choice")
	}

	characterToDelete := options[deleteIndex-1]
	if err := player.server.database.DeleteCharacter(player, characterToDelete); err != nil {
		return err
	}

	player.toPlayer <- fmt.Sprintf("\n\rCharacter '%s' has been deleted.\n\r", characterToDelete)
	return nil
}

func sendDeletionOptions(ctx context.Context, options []string, player *Player) error {
	select {
	case <-ctx.Done():
		return ctx.Err()
	case player.toPlayer <- "Select a character to delete: \n\r":
		for i, name := range options {
			player.toPlayer <- fmt.Sprintf("%d: %s\n\r", i+1, name)
		}
		player.toPlayer <- "Enter the number of the character to delete: "
		return nil
	}
}
