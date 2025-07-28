/*
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

*/

package main

import (
	"context"
	"strings"
)

func (p *Player) Console(done chan bool) {
	RunWithPanicRecoveryCallback("player.Console", func() {
		p.consoleInternal(done)
	}, func(err error) {
		select {
		case done <- true:
		default:
		}
	}, "playerID", p.id)
}

// consoleInternal contains the actual console logic
func (p *Player) consoleInternal(done chan bool) {
	for {
		select {
		case <-p.ctx.Done():
			done <- true
			return
		default:
			characterCount := len(p.characterList)

			// Safe channel operations prevent panic on disconnect
			menuMessages := []string{
				"\n=====Console=====\n",
				"0) Quit\n",
				"1) Change Password\n",
				"2) View Messages\n",
				"3) Create Character\n",
			}

			for _, msg := range menuMessages {
				select {
				case <-p.ctx.Done():
					done <- true
					return
				case p.commandOut <- msg:
				}
			}

			if characterCount > 0 {
				additionalMessages := []string{
					"4) Select Character\n",
					"5) Delete Character\n",
				}
				for _, msg := range additionalMessages {
					select {
					case <-p.ctx.Done():
						done <- true
						return
					case p.commandOut <- msg:
					}
				}
			}

			select {
			case <-p.ctx.Done():
				done <- true
				return
			case p.commandOut <- "\nEnter your choice: ":
			}

			select {
			case <-p.ctx.Done():
				done <- true
				return
			case choice := <-p.commandIn:
				switch strings.TrimSpace(choice) {
				case "0":
					select {
					case <-p.ctx.Done():
						return
					case p.commandOut <- "\nGoodbye!\n":
					}
					p.Stop()
					done <- true
					return

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
						select {
						case <-p.ctx.Done():
							return
						case p.commandOut <- "Invalid choice. Please try again.\n":
						}
					}

				case "5":
					if characterCount > 0 {
						p.HandleCharacterDeletion()
					} else {
						select {
						case <-p.ctx.Done():
							return
						case p.commandOut <- "Invalid choice. Please try again.\n":
						}
					}

				default:
					select {
					case <-p.ctx.Done():
						return
					case p.commandOut <- "Invalid choice. Please try again.\n":
					}
				}
			}
		}
	}
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

	// Store character references to prevent race conditions
	characterName := p.character.name
	characterPlayerCommandIn := p.character.playerCommandIn
	characterEnd := p.character.end

	// Start a goroutine to forward player input to character
	inputForwarder := make(chan bool, 1)
	go p.forwardInputToCharacter(ctx, characterName, characterPlayerCommandIn, characterEnd, inputForwarder)

	// Run the character's lifecycle (blocks until character session ends)
	Logger.Info("Starting character session", "characterName", characterName)
	p.character.Run(characterEnd)
	Logger.Info("Character session ended", "characterName", characterName)

	// Signal input forwarder to stop
	cancel()

	// Wait for input forwarder to complete
	<-inputForwarder

	// Character Run has completed
	p.character = nil

	// Ensure we're fully back to console mode
	p.commandOut <- "\n\rReturning to console.\n\r"
}

// forwardInputToCharacter forwards player input to the character
func (p *Player) forwardInputToCharacter(ctx context.Context, characterName string, characterPlayerCommandIn chan<- string, characterEnd <-chan bool, inputForwarder chan bool) {
	defer func() {
		if r := recover(); r != nil {
			Logger.Warn("Recovered in command forwarding", "player", p.id, "recover", r)
		}
		close(inputForwarder)
	}()

	Logger.Debug("Starting input forwarding for character", "characterName", characterName)
	for {
		select {
		case input, ok := <-p.commandIn:
			if !ok {
				Logger.Warn("Player command input channel closed unexpectedly")
				return
			}
			Logger.Debug("Forwarding input to character", "input", input, "characterName", characterName)
			// Forward the input to character
			select {
			case characterPlayerCommandIn <- input:
				Logger.Debug("Successfully forwarded input to character", "characterName", characterName)
			case <-ctx.Done():
				Logger.Debug("Context cancelled during input forwarding", "characterName", characterName)
				return
			}
		case _, ok := <-characterEnd:
			if !ok {
				Logger.Debug("Character end channel closed, stopping input forwarding", "characterName", characterName)
			} else {
				Logger.Debug("Character end signal received, stopping input forwarding", "characterName", characterName)
			}
			return
		case <-ctx.Done():
			Logger.Debug("Context cancelled, stopping input forwarding", "characterName", characterName)
			return
		}
	}
}
