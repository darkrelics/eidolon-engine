/*
Eidolon Engine

Copyright 2024-2025 Jason Robinson

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package main

import (
	"context"
	"fmt"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
)

func (p *Player) Console(done chan bool) {
	for {
		select {
		case <-p.ctx.Done():
			done <- true
			return
		default:
			characterCount := len(p.characterList)

			p.commandOut <- "\n=====Console=====\n"
			p.commandOut <- "1) Change Password\n"
			p.commandOut <- "2) View Messages\n"
			p.commandOut <- "3) Create Character\n"

			if characterCount == 0 {
				p.commandOut <- "9) Quit\n"
			} else {
				p.commandOut <- "4) Select Character\n"
				p.commandOut <- "5) Delete Character\n"
				p.commandOut <- "9) Quit\n"
			}
			p.commandOut <- "\nEnter your choice: "

			select {
			case <-p.ctx.Done():
				done <- true
				return
			case choice := <-p.commandIn:
				switch strings.TrimSpace(choice) {
				case "1":
					p.HandlePasswordChange()

				case "2":
					p.HandleViewMOTDs()

				case "3":
					p.HandleCharacterCreation()

				case "4":
					if characterCount > 0 {
						p.HandleCharacterSelection()
					} else {
						p.commandOut <- "Invalid choice. Please try again.\n"
					}

				case "5":
					if characterCount > 0 {
						p.HandleCharacterDeletion()
					} else {
						p.commandOut <- "Invalid choice. Please try again.\n"
					}

				case "9":
					p.commandOut <- "\nGoodbye!\n"
					p.Stop()
					done <- true
					return

				default:
					p.commandOut <- "Invalid choice. Please try again.\n"
				}
			}
		}
	}
}

func (p *Player) HandlePasswordChange() {
	p.mutex.Lock()
	originalEcho := p.echo
	p.echo = false
	p.mutex.Unlock()

	defer func() {
		p.mutex.Lock()
		p.echo = originalEcho
		p.mutex.Unlock()
	}()

	hasUpperCase := regexp.MustCompile(`[A-Z]`)
	hasLowerCase := regexp.MustCompile(`[a-z]`)
	hasNumber := regexp.MustCompile(`[0-9]`)
	hasSpecialChar := regexp.MustCompile(`[!@#$%^&*(),.?":{}|<>]`)

	p.commandOut <- "\nPassword must:\n" +
		"- Be at least 8 characters long\n" +
		"- Contain at least one uppercase letter\n" +
		"- Contain at least one lowercase letter\n" +
		"- Contain at least one number\n" +
		"- Contain at least one special character\n\n"

	p.commandOut <- "Enter your current password (or 'exit' to cancel): "
	currentPassword := <-p.commandIn
	p.commandOut <- "\n"

	if strings.ToLower(strings.TrimSpace(currentPassword)) == "exit" {
		p.commandOut <- "Password change cancelled.\n"
		return
	}

	for {
		p.commandOut <- "Enter your new password (or 'exit' to cancel): "
		newPassword := <-p.commandIn
		p.commandOut <- "\n"

		if strings.ToLower(strings.TrimSpace(newPassword)) == "exit" {
			p.commandOut <- "Password change cancelled.\n"
			return
		}

		if len(newPassword) < 8 {
			p.commandOut <- "Password must be at least 8 characters long. Please try again.\n"
			continue
		}

		if !hasUpperCase.MatchString(newPassword) {
			p.commandOut <- "Password must contain at least one uppercase letter. Please try again.\n"
			continue
		}

		if !hasLowerCase.MatchString(newPassword) {
			p.commandOut <- "Password must contain at least one lowercase letter. Please try again.\n"
			continue
		}

		if !hasNumber.MatchString(newPassword) {
			p.commandOut <- "Password must contain at least one number. Please try again.\n"
			continue
		}

		if !hasSpecialChar.MatchString(newPassword) {
			p.commandOut <- "Password must contain at least one special character. Please try again.\n"
			continue
		}

		p.commandOut <- "Confirm your new password: "
		confirmPassword := <-p.commandIn
		p.commandOut <- "\n"

		if strings.ToLower(strings.TrimSpace(confirmPassword)) == "exit" {
			p.commandOut <- "Password change cancelled.\n"
			return
		}

		if newPassword != confirmPassword {
			p.commandOut <- "Passwords do not match. Please try again.\n"
			continue
		}

		err := p.server.ChangePassword(p, currentPassword, newPassword)
		if err != nil {
			// TODO: Provide more verbose feedback based on the error
			p.commandOut <- "Password change failed. Please try again.\n"
			continue
		}

		p.commandOut <- "Password successfully changed.\n"
		return
	}
}

func (p *Player) HandleCharacterCreation() {
	// Get character name
	p.commandOut <- "\nEnter character name (3-15 letters only): "
	name, ok := <-p.commandIn
	if !ok {
		Logger.Warn("Player input channel closed")
		return
	}

	name = strings.TrimSpace(name)

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
		p.characterList = make(map[string]uuid.UUID)
	}
	p.characterList[name] = character.id
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
	if len(name) < 3 {
		return fmt.Errorf("name must be at least 3 characters")
	}
	if len(name) > 15 {
		return fmt.Errorf("name must be 15 characters or fewer")
	}

	// Check if name contains only letters
	if !regexp.MustCompile(`^[a-zA-Z]+$`).MatchString(name) {
		return fmt.Errorf("name must contain only letters")
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

	// Create a character instance to use SelectArchetype method
	tempChar := &Character{
		game: p.server.game,
	}

	// Create adapter channels to convert between string and structured commands
	commandInAdapter := make(chan *CommandResponse, 10)
	commandOutAdapter := make(chan *CommandRequest, 10)

	// Set up the character channels
	tempChar.gameCommandIn = commandInAdapter
	tempChar.gameCommandOut = commandOutAdapter

	// Start goroutines to handle channel adaptation
	go func() {
		// Forward string messages to player
		for resp := range commandInAdapter {
			if resp != nil && resp.Message != "" {
				p.commandOut <- resp.Message
			}
		}
	}()

	go func() {
		// Convert player input to command requests
		for input := range p.commandIn {
			commandOutAdapter <- &CommandRequest{
				ID:        uuid.New(),
				Character: tempChar,
				Args:      []string{input},
				Timestamp: time.Now(),
			}
		}
	}()

	return tempChar.SelectArchetype()
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
	if err != nil || num < 1 || num > len(options) {
		p.commandOut <- "Invalid selection.\n"
		return
	}

	// Get character ID from player's character list
	characterName := options[num-1]
	p.mutex.RLock()
	characterID := p.characterList[characterName]
	p.mutex.RUnlock()

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
	for name := range p.characterList {
		options = append(options, name)
	}
	sort.Strings(options)
	return options
}

func (p *Player) displayCharacterOptions(options []string) {
	p.commandOut <- "\nSelect a character:\n"
	for i, name := range options {
		p.commandOut <- fmt.Sprintf("%d) %s\n", i+1, name)
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
	for i, name := range options {
		p.commandOut <- fmt.Sprintf("%d) %s\n", i+1, name)
	}
	p.commandOut <- "\nEnter your choice (or 0 to cancel): "

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
	characterID := p.characterList[characterName]
	p.mutex.RUnlock()

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

func (p *Player) PlayCharacter() {
	if p.character == nil {
		p.commandOut <- "No character selected.\n"
		return
	}

	// Create a new end channel if needed
	if p.character.end == nil {
		p.character.end = make(chan bool, 5)
	}

	// Create a context for the forwarding goroutine
	ctx, cancel := context.WithCancel(p.ctx)
	defer cancel()

	// Start a goroutine to forward player input to character
	inputForwarder := make(chan bool, 1)
	go func() {
		defer func() {
			if r := recover(); r != nil {
				Logger.Warn("Recovered in command forwarding", "player", p.id, "recover", r)
			}
			close(inputForwarder)
		}()

		Logger.Debug("Starting input forwarding for character", "characterName", p.character.name)
		for {
			select {
			case input, ok := <-p.commandIn:
				if !ok {
					Logger.Warn("Player command input channel closed unexpectedly")
					return
				}
				Logger.Debug("Forwarding input to character", "input", input, "characterName", p.character.name)
				// Forward the input to character
				select {
				case p.character.playerCommandIn <- input:
					Logger.Debug("Successfully forwarded input to character", "characterName", p.character.name)
				case <-ctx.Done():
					Logger.Debug("Context cancelled during input forwarding", "characterName", p.character.name)
					return
				}
			case <-p.character.end:
				Logger.Debug("Character end signal received, stopping input forwarding", "characterName", p.character.name)
				return
			case <-ctx.Done():
				Logger.Debug("Context cancelled, stopping input forwarding", "characterName", p.character.name)
				return
			}
		}
	}()

	// Run the character's lifecycle (blocks until character session ends)
	Logger.Info("Starting character session", "characterName", p.character.name)
	p.character.Run(p.character.end)
	Logger.Info("Character session ended", "characterName", p.character.name)

	// Signal input forwarder to stop
	cancel()
	
	// Wait for input forwarder to complete
	<-inputForwarder

	// Character Run has completed
	p.character = nil

	// Ensure we're fully back to console mode
	p.commandOut <- "\n\rReturning to console.\n\r"
}

func (p *Player) HandleViewMOTDs() {
	p.commandOut <- "\n\r=== Active Messages ===\n\r"

	p.mutex.RLock()
	activeMotDs := p.server.activeMotDs
	p.mutex.RUnlock()

	if len(activeMotDs) == 0 {
		p.commandOut <- "No messages to display.\n\r"
		return
	}

	// Display messages with creation date, sorted newest first
	for _, motd := range activeMotDs {
		if motd == nil || !motd.Active {
			continue
		}

		// Format the creation date
		dateStr := motd.CreatedAt.Format("Jan 02, 2006")

		// Default MOTD has no date displayed
		defaultMOTDID, _ := uuid.Parse("00000000-0000-0000-0000-000000000000")
		if motd.MotdID == defaultMOTDID {
			p.commandOut <- fmt.Sprintf("\n\r%s\n\r", motd.Message)
		} else {
			p.commandOut <- fmt.Sprintf("\n\r[%s]\n\r%s\n\r", dateStr, motd.Message)
		}
	}
}
