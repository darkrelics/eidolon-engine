package core

import (
	"fmt"
	"sort"
	"strconv"
	"strings"

	"github.com/google/uuid"
)

// SelectCharacter handles the character selection process for a player.
// It presents the player with options to select or create a character.
func SelectCharacter(game *Game, player *Player) (*Character, error) {
	Logger.Debug("Player is selecting a character", "playerName", player.PlayerID)

	var options []string

	sendCharacterOptions := func() {
		player.ToPlayer <- "Select a character:\n\r"
		player.ToPlayer <- "0: Create a new character\n\r"

		if len(player.CharacterList) > 0 {
			i := 1
			for name := range player.CharacterList {
				player.ToPlayer <- fmt.Sprintf("%d: %s\n\r", i, name)
				options = append(options, name)
				i++
			}
			player.ToPlayer <- "X: Delete a character\n\r"
		} else {
			player.ToPlayer <- "No existing characters found.\n\r"
		}
		player.ToPlayer <- "Enter the number of your choice or 'X' to delete: "
	}

	for {
		options = []string{} // Reset options for each iteration
		sendCharacterOptions()

		input, ok := <-player.FromPlayer
		if !ok {
			Logger.Error("Failed to receive input from player", "playerName", player.PlayerID)
			return nil, fmt.Errorf("failed to receive input")
		}

		input = strings.TrimSpace(strings.ToUpper(input))

		if input == "X" && len(player.CharacterList) > 0 {
			// Handle character deletion
			player.ToPlayer <- "Select a character to delete: \n\r"
			for i, name := range options {
				player.ToPlayer <- fmt.Sprintf("%d: %s\n\r", i+1, name)
			}
			player.ToPlayer <- "Enter the number of the character to delete: "

			deleteChoice, ok := <-player.FromPlayer
			if !ok {
				Logger.Error("Failed to receive delete choice from player", "playerName", player.PlayerID)
				return nil, fmt.Errorf("failed to receive delete choice")
			}

			deleteIndex, err := strconv.Atoi(strings.TrimSpace(deleteChoice))
			if err != nil || deleteIndex < 1 || deleteIndex > len(options) {
				player.ToPlayer <- "Invalid choice. Returning to character selection.\n\r"
				continue
			}

			characterToDelete := options[deleteIndex-1]
			err = game.Database.DeleteCharacter(player, characterToDelete)
			if err != nil {
				Logger.Error("Failed to delete character", "characterName", characterToDelete, "error", err)
				player.ToPlayer <- fmt.Sprintf("Failed to delete character: %v\n\r", err)
			} else {
				player.ToPlayer <- fmt.Sprintf("\n\rCharacter '%s' has been deleted.\n\r", characterToDelete)
			}
			continue
		}

		choice, err := strconv.Atoi(input)
		if err != nil || choice < 0 || choice > len(options) {
			player.ToPlayer <- "Invalid choice. Please select a valid option.\n\r"
			continue
		}

		var character *Character
		if choice == 0 {
			character, err = game.CreateCharacter(player)
			if err != nil {
				player.ToPlayer <- fmt.Sprintf("\n\rError creating character: %v\n\r", err)
				continue
			}
		} else if choice <= len(options) {
			characterName := options[choice-1]
			characterID := player.CharacterList[characterName]
			character, err = game.Database.LoadCharacter(characterID, player, game)
			if err != nil {
				Logger.Error("Error loading character for player", "characterName", characterName, "playerName", player.PlayerID, "error", err)
				player.ToPlayer <- fmt.Sprintf("Error loading character: %v\n\r", err)
				continue
			}
		}

		if character == nil {
			player.ToPlayer <- "Failed to create or load character. Please try again.\n\r"
			continue
		}

		// Ensure the character is added to the server's character list
		game.Mutex.Lock()
		game.Characters[character.ID] = character
		game.Mutex.Unlock()

		// Add character to the room and notify other players
		if character.Room != nil {
			// Notify the room that the character has entered
			character.Room.Mutex.Lock()
			character.Room.Characters[character.ID] = character
			character.Room.Mutex.Unlock()
		}

		Logger.Debug("Character selected and added to server", "characterName", character.Name, "characterID", character.ID)

		return character, nil
	}
}

// CreateCharacter handles the character creation process for a player.
// It prompts the player for a character name and archetype, and initializes the character.
func (g *Game) CreateCharacter(player *Player) (*Character, error) {
	Logger.Info("Player is creating a new character", "playerName", player.PlayerID)

	player.ToPlayer <- "\n\rEnter your character name: "

	charName, ok := <-player.FromPlayer
	if !ok {
		Logger.Error("Failed to receive character name input", "playerName", player.PlayerID)
		return nil, fmt.Errorf("failed to receive character name input")
	}

	// Consider title case for the character name
	charName = strings.TrimSpace(charName)

	// Validate character name
	if len(charName) == 0 {
		player.ToPlayer <- "Character name cannot be empty.\n\r"
		return nil, fmt.Errorf("character name cannot be empty")
	}

	if len(charName) > 15 {
		player.ToPlayer <- "Character name must be 15 characters or fewer.\n\r"
		return nil, fmt.Errorf("character name must be 15 characters or fewer")
	}

	// Check if name exists
	if g.CharacterBloomFilter.Test([]byte(charName)) {
		player.ToPlayer <- "Character name already exists. Please choose another name.\n\r"
		return nil, fmt.Errorf("character name already exists")
	}

	var selectedArchetype string

	// Get archetypes list

	archetypeCount := len(g.ArcheTypes)
	archetypeOptions := make([]string, 0, archetypeCount)
	for name, archetype := range g.ArcheTypes {
		archetypeOptions = append(archetypeOptions, name+" - "+archetype.Description)
	}

	sort.Strings(archetypeOptions)

	// If archetypes are available, prompt the player to select one
	if archetypeCount > 0 {
		for {
			selectionMsg := "\n\rSelect a character archetype.\n\r"
			for i, option := range archetypeOptions {
				selectionMsg += fmt.Sprintf("%d: %s\n\r", i+1, option)
			}
			selectionMsg += "Enter the number of your choice: "
			player.ToPlayer <- selectionMsg

			selection, ok := <-player.FromPlayer
			if !ok {
				Logger.Error("Failed to receive archetype selection", "playerName", player.PlayerID)
				return nil, fmt.Errorf("failed to receive archetype selection")
			}

			selectionNum, err := strconv.Atoi(strings.TrimSpace(selection))
			if err == nil && selectionNum >= 1 && selectionNum <= len(archetypeOptions) {
				selectedOption := archetypeOptions[selectionNum-1]
				selectedArchetype = strings.Split(selectedOption, " - ")[0]
				break
			} else {
				player.ToPlayer <- "Invalid selection. Please select a valid archetype number.\n\r"
			}
		}
	}

	Logger.Debug("Creating character", "characterName", charName)

	// Find starting room
	room, ok := g.Rooms[1] // This should be pulled from the Archetype
	if !ok {
		Logger.Warn("Starting room not found, using default room", "startingRoomID", 1)
		room, ok = g.Rooms[0]
		if !ok {
			Logger.Error("No default room found", "defaultRoomID", 0)
			player.ToPlayer <- "No starting or default room found. Please contact the administrator.\n\r"
			return nil, fmt.Errorf("no starting or default room found")
		}
	}

	// Create the new character
	character, err := g.NewCharacter(charName, player, room, selectedArchetype)
	if err != nil {
		Logger.Error("Error creating character", "characterName", charName, "error", err)
		player.ToPlayer <- "Error creating character. Please try again later.\n\r"
		return nil, fmt.Errorf("failed to create character: %w", err)
	}

	player.Mutex.Lock()
	if player.CharacterList == nil {
		player.CharacterList = make(map[string]uuid.UUID)
	}
	player.CharacterList[charName] = character.ID
	player.Mutex.Unlock()

	Logger.Debug("Added character to player's character list", "characterName", charName, "characterID", character.ID)

	// Save character to database
	if err := g.Database.WriteCharacter(character); err != nil {
		Logger.Error("Error saving character to database", "characterName", charName, "error", err)
		player.ToPlayer <- "Error saving character to database. Please try again later.\n\r"
		return nil, fmt.Errorf("failed to save character to database: %w", err)
	}

	// Save updated player data
	if err := g.Database.WritePlayer(player); err != nil {
		Logger.Error("Error saving player data", "playerName", player.PlayerID, "error", err)
		player.ToPlayer <- "Error saving player data. Please try again later.\n\r"
		return nil, fmt.Errorf("failed to save player data: %w", err)
	}

	Logger.Debug("Successfully created and saved character for player",
		"characterName", charName,
		"characterID", character.ID,
		"playerName", player.PlayerID)

	return character, nil
}
