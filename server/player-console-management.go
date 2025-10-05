/*
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

*/

package main

import (
	"fmt"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"unicode"

	"github.com/gofrs/uuid/v5"
)

func (p *Player) HandleCharacterCreation() {
	// Get character name
	p.commandOut <- "\nEnter character name (4-20 letters only, or '0' to cancel): "
	name, ok := <-p.commandIn
	if !ok {
		Logger.Warn("Player input channel closed")
		return
	}

	name = strings.TrimSpace(name)

	// Check for cancel
	if name == "0" {
		p.commandOut <- "Character creation cancelled.\n"
		return
	}

	// Validate character name
	if err := p.validateCharacterName(name); err != nil {
		p.commandOut <- fmt.Sprintf("Invalid name: %s\n", err.Error())
		return
	}

	// Select archetype
	archetypeName, err := p.selectArchetype()
	if err != nil {
		p.commandOut <- fmt.Sprintf("Archetype selection failed: %s\n", err.Error())
		return
	}

	// Validate archetype exists before character creation
	if archetypeName != "" {
		p.server.game.mutex.RLock()
		_, exists := p.server.game.archetypes[archetypeName]
		p.server.game.mutex.RUnlock()
		if !exists {
			p.commandOut <- fmt.Sprintf("Error: Selected archetype '%s' does not exist\n", archetypeName)
			return
		}
	}

	// Create character
	character, err := p.CreateCharacter(name, archetypeName)
	if err != nil {
		p.commandOut <- fmt.Sprintf("Character creation failed: %s\n", err.Error())
		return
	}

	p.commandOut <- fmt.Sprintf("\nCharacter '%s' created successfully!\n", name)

	// Save the character to the player's character list
	p.mutex.Lock()
	if p.characterList == nil {
		p.characterList = make(map[string]*PlayerCharacterInfo)
	}
	p.characterList[name] = &PlayerCharacterInfo{
		UUID:     character.id.String(),
		Dead:     false,
		GameMode: "MUD",
	}
	p.mutex.Unlock()

	// Save player data
	err = p.Save()
	if err != nil {
		p.commandOut <- "Warning: Failed to save player data. Your character may not appear in your character list next time you log in.\n"
		Logger.Error("Failed to save player data after character creation", "player", p.id, "error", err)
	}
}

func (p *Player) validateCharacterName(name string) error {
	// Check if name is empty
	if len(name) == 0 {
		return fmt.Errorf("name cannot be empty")
	}

	// Check name length
	if len(name) < 4 {
		return fmt.Errorf("name must be at least 4 characters")
	}
	if len(name) > 20 {
		return fmt.Errorf("name must be 20 characters or fewer")
	}

	// Check if name contains only letters, hyphens, and apostrophes
	if !regexp.MustCompile(`^[a-zA-Z'-]+$`).MatchString(name) {
		return fmt.Errorf("name must contain only letters, hyphens, and apostrophes")
	}

	// Prevent names starting or ending with special characters
	if name[0] == '-' || name[0] == '\'' || name[len(name)-1] == '-' || name[len(name)-1] == '\'' {
		return fmt.Errorf("name cannot start or end with special characters")
	}

	// Prevent consecutive special characters
	if regexp.MustCompile(`[-']{2,}`).MatchString(name) {
		return fmt.Errorf("name cannot have consecutive special characters")
	}

	// Prevent excessive repetition (more than 2 consecutive identical characters)
	for i := 0; i < len(name)-2; i++ {
		if name[i] == name[i+1] && name[i+1] == name[i+2] {
			return fmt.Errorf("name cannot have more than 2 consecutive identical characters")
		}
	}

	// Prevent single-letter names with special characters
	if len(name) <= 3 && (strings.Contains(name, "-") || strings.Contains(name, "'")) {
		return fmt.Errorf("short names cannot contain special characters")
	}

	// Ensure reasonable letter-to-special-character ratio
	letterCount := 0
	for _, r := range name {
		if unicode.IsLetter(r) {
			letterCount++
		}
	}
	if float64(letterCount)/float64(len(name)) < 0.5 {
		return fmt.Errorf("name must be primarily letters")
	}

	// Check reserved prefixes
	nameLower := strings.ToLower(name)
	reservedPrefixes := []string{"gm_", "admin_", "mod_", "system_", "server_", "npc_"}
	for _, prefix := range reservedPrefixes {
		if strings.HasPrefix(nameLower, prefix) {
			return fmt.Errorf("name uses reserved prefix")
		}
	}

	// Check reserved exact names
	reservedNames := []string{"admin", "administrator", "moderator", "gamemaster", "system"}
	for _, reserved := range reservedNames {
		if nameLower == reserved {
			return fmt.Errorf("name is reserved")
		}
	}

	// Check if name already exists
	if p.server.game.characterBloomFilter.TestString(strings.ToLower(name)) {
		return fmt.Errorf("name already exists")
	}

	return nil
}

func (p *Player) selectArchetype() (string, error) {
	if len(p.server.game.archetypeOptions) == 0 {
		return "", nil // No archetypes available
	}

	options := p.server.game.archetypeOptions

	// Display archetype selection menu
	msg := "\n\rSelect a character archetype.\n\r"
	msg += "0: Cancel\n\r"
	for i, option := range options {
		msg += fmt.Sprintf("%d: %s\n\r", i+1, option)
	}
	msg += "Enter the number of your choice: "

	p.commandOut <- msg

	// Wait for player input
	selection, ok := <-p.commandIn
	if !ok {
		return "", fmt.Errorf("player input channel closed")
	}

	// Parse selection
	num, err := strconv.Atoi(strings.TrimSpace(selection))
	if err != nil || num < 0 || num > len(options) {
		return "", fmt.Errorf("invalid archetype selection")
	}

	// Check for cancel
	if num == 0 {
		return "", fmt.Errorf("archetype selection cancelled")
	}

	// Extract archetype name from option (format: "Name - Description")
	return strings.Split(options[num-1], " - ")[0], nil
}

func (p *Player) HandleCharacterSelection() {
	options := p.buildCharacterOptions()
	if len(options) == 0 {
		p.commandOut <- "No characters available.\n"
		return
	}

	p.displayCharacterOptions(options)

	choice, ok := <-p.commandIn
	if !ok {
		Logger.Warn("Player input channel closed")
		return
	}

	num, err := strconv.Atoi(strings.TrimSpace(choice))
	if err != nil {
		p.commandOut <- "Invalid selection.\n"
		return
	}

	// Check for return to menu option
	if num == 0 {
		p.commandOut <- "Returning to menu.\n"
		return
	}

	// Validate selection
	if num < 1 || num > len(options) {
		p.commandOut <- "Invalid selection.\n"
		return
	}

	// Get character ID from player's character list
	characterName := options[num-1]
	p.mutex.RLock()
	characterInfo := p.characterList[characterName]
	p.mutex.RUnlock()

	// Parse UUID
	characterID, err := uuid.FromString(characterInfo.UUID)
	if err != nil {
		p.commandOut <- fmt.Sprintf("Failed to parse character ID: %s\n", err.Error())
		return
	}

	// Load the character
	character, err := LoadCharacter(p, characterID)
	if err != nil {
		p.commandOut <- fmt.Sprintf("Failed to load character: %s\n", err.Error())
		return
	}

	p.character = character
	p.commandOut <- fmt.Sprintf("\nYou are now playing as %s.\n", characterName)

	p.PlayCharacter()
}

func (p *Player) buildCharacterOptions() []string {
	p.mutex.RLock()
	defer p.mutex.RUnlock()

	options := make([]string, 0, len(p.characterList))
	for name, charInfo := range p.characterList {
		// Only include MUD characters
		if charInfo.GameMode == "MUD" || charInfo.GameMode == "" {
			options = append(options, name)
		}
	}
	sort.Strings(options)
	return options
}

func (p *Player) displayCharacterOptions(options []string) {
	p.commandOut <- "\nSelect a character:\n"
	p.commandOut <- "0) Return to menu\n"

	p.mutex.RLock()
	defer p.mutex.RUnlock()

	for i, name := range options {
		characterInfo := p.characterList[name]
		if characterInfo.Dead {
			p.commandOut <- fmt.Sprintf("%d) %s (DEAD)\n", i+1, name)
		} else {
			p.commandOut <- fmt.Sprintf("%d) %s\n", i+1, name)
		}
	}
	p.commandOut <- "\nEnter your choice: "
}

func (p *Player) HandleCharacterDeletion() {
	options := p.buildCharacterOptions()
	if len(options) == 0 {
		p.commandOut <- "No characters available to delete.\n"
		return
	}

	p.commandOut <- "\nSelect a character to delete:\n"
	p.commandOut <- "0) Cancel\n"

	p.mutex.RLock()
	for i, name := range options {
		characterInfo := p.characterList[name]
		if characterInfo.Dead {
			p.commandOut <- fmt.Sprintf("%d) %s (DEAD)\n", i+1, name)
		} else {
			p.commandOut <- fmt.Sprintf("%d) %s\n", i+1, name)
		}
	}
	p.mutex.RUnlock()

	p.commandOut <- "\nEnter your choice: "

	choice, ok := <-p.commandIn
	if !ok {
		Logger.Warn("Player input channel closed")
		return
	}

	num, err := strconv.Atoi(strings.TrimSpace(choice))
	if err != nil {
		p.commandOut <- "Invalid selection.\n"
		return
	}

	// Check for cancel option
	if num == 0 {
		p.commandOut <- "Character deletion cancelled.\n"
		return
	}

	// Validate selection
	if num < 1 || num > len(options) {
		p.commandOut <- "Invalid selection.\n"
		return
	}

	// Get character info
	characterName := options[num-1]
	p.mutex.RLock()
	characterInfo := p.characterList[characterName]
	p.mutex.RUnlock()

	// Parse UUID
	characterID, err := uuid.FromString(characterInfo.UUID)
	if err != nil {
		p.commandOut <- fmt.Sprintf("Failed to parse character ID: %s\n", err.Error())
		return
	}

	// Confirm deletion
	p.commandOut <- fmt.Sprintf("\nAre you sure you want to delete '%s'? This cannot be undone.\nType 'DELETE' to confirm: ", characterName)

	confirmation, ok := <-p.commandIn
	if !ok {
		Logger.Warn("Player input channel closed")
		return
	}

	if strings.TrimSpace(confirmation) != "DELETE" {
		p.commandOut <- "Character deletion cancelled.\n"
		return
	}

	// Delete the character from database
	err = p.DeleteCharacter(characterID)
	if err != nil {
		p.commandOut <- fmt.Sprintf("Failed to delete character: %s\n", err.Error())
		return
	}

	// Remove character from player's list
	p.mutex.Lock()
	delete(p.characterList, characterName)
	p.mutex.Unlock()

	// Save player data
	err = p.Save()
	if err != nil {
		p.commandOut <- "Warning: Failed to update player data after character deletion.\n"
		Logger.Error("Failed to save player data after character deletion", "player", p.id, "error", err)
	}

	p.commandOut <- fmt.Sprintf("\nCharacter '%s' has been deleted.\n", characterName)
}
