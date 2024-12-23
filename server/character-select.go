package main

import (
	"context"
	"fmt"
	"sort"
	"strconv"
	"strings"

	"github.com/google/uuid"
)

func SelectCharacter(ctx context.Context, player *Player) (*Character, error) {
	Logger.Debug("Player is selecting a character", "playerName", player.playerID)

	for {
		options := buildCharacterOptions(player)
		if err := sendOptions(ctx, player, options); err != nil {
			return nil, fmt.Errorf("failed to send options: %w", err)
		}

		input, err := receiveInput(ctx, player)
		if err != nil {
			return nil, fmt.Errorf("failed to receive input: %w", err)
		}

		if character, shouldContinue := handleCharacterSelection(ctx, input, options, player); !shouldContinue {
			return character, nil
		}
	}
}

func CreateCharacter(player *Player, g *Game) (*Character, error) {
	Logger.Info("Player is creating a new character", "playerName", player.playerID)

	charName, err := getValidCharacterName(player, g)
	if err != nil {
		return nil, err
	}

	selectedArchetype, err := selectArchetype(player, g)
	if err != nil {
		return nil, err
	}

	room, err := getStartingRoom(g, selectedArchetype)
	if err != nil {
		return nil, err
	}

	character, err := createAndSaveCharacter(charName, player, room, selectedArchetype, g)
	if err != nil {
		return nil, err
	}

	return character, nil
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

	game := player.server.game

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

	character, err := loadOrCreateCharacter(ctx, choice, options, player)
	if err != nil {
		player.toPlayer <- fmt.Sprintf("Error: %v\n\r", err)
		return nil, true
	}

	if err := addCharacterToRoom(character, game); err != nil {
		player.toPlayer <- fmt.Sprintf("Error adding character to room: %v\n\r", err)
		return nil, true
	}

	return character, false
}

func loadOrCreateCharacter(ctx context.Context, choice int, options []string, player *Player) (*Character, error) {

	game := player.server.game

	game.Mutex.Lock()
	defer game.Mutex.Unlock()

	var character *Character
	var err error

	if choice == 0 {
		character, err = CreateCharacter(player, game)
	} else if choice <= len(options) {
		player.mutex.RLock()
		characterID := player.characterList[options[choice-1]]
		player.mutex.RUnlock()
		character, err = player.server.database.LoadCharacter(characterID, player, game)
	}

	if err != nil {
		return nil, err
	}

	if character == nil {
		return nil, fmt.Errorf("failed to create or load character")
	}

	game.Characters[character.ID] = character
	return character, nil
}

func addCharacterToRoom(character *Character, game *Game) error {
	if character.Room == nil {
		return fmt.Errorf("character has no assigned room")
	}

	character.Room.Mutex.Lock()
	defer character.Room.Mutex.Unlock()
	character.Room.Characters[character.ID] = character
	return nil
}

func getValidCharacterName(player *Player, g *Game) (string, error) {
	select {
	case player.toPlayer <- "\n\rEnter your character name: ":
	default:
		return "", fmt.Errorf("player output channel blocked")
	}

	charName, ok := <-player.fromPlayer
	if !ok {
		return "", fmt.Errorf("player input channel closed")
	}

	charName = strings.TrimSpace(charName)

	if err := validateCharacterName(charName, g); err != nil {
		return "", err
	}

	return charName, nil
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

func selectArchetype(player *Player, g *Game) (string, error) {
	archetypeOptions := buildArchetypeOptions(g)
	if len(archetypeOptions) == 0 {
		return "", fmt.Errorf("no archetypes available")
	}

	selection, err := promptArchetypeSelection(player, archetypeOptions)
	if err != nil {
		return "", err
	}

	return strings.Split(archetypeOptions[selection-1], " - ")[0], nil
}

func buildArchetypeOptions(g *Game) []string {
	options := make([]string, 0, len(g.ArcheTypes))
	for name, archetype := range g.ArcheTypes {
		options = append(options, name+" - "+archetype.Description)
	}
	sort.Strings(options)
	return options
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

func createAndSaveCharacter(name string, player *Player, room *Room, archetype string, g *Game) (*Character, error) {
	character, err := NewCharacter(name, player, room, archetype, g)
	if err != nil {
		return nil, fmt.Errorf("failed to create character: %w", err)
	}

	player.mutex.Lock()
	if player.characterList == nil {
		player.characterList = make(map[string]uuid.UUID)
	}
	player.characterList[name] = character.ID
	player.mutex.Unlock()

	if err := WriteCharacter(character, g.Database); err != nil {
		return nil, fmt.Errorf("failed to save character to database: %w", err)
	}

	if err := player.WritePlayer(); err != nil {
		return nil, fmt.Errorf("failed to save player data: %w", err)
	}

	return character, nil
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
