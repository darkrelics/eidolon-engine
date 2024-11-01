package core

import (
	"fmt"
	"strconv"
	"strings"
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
