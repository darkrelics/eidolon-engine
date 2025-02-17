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
	"regexp"
	"strings"
)

func (p *Player) Console() {
	for {
		select {
		case <-p.ctx.Done():
			return
		default:
			characterCount := len(p.characterList)

			p.toPlayer <- "\n=====Console=====\n"
			if characterCount == 0 {
				p.toPlayer <- "1) Change Password\n"
				p.toPlayer <- "2) Create Character\n"
				p.toPlayer <- "9) Quit\n"
			} else {
				p.toPlayer <- "1) Change Password\n"
				p.toPlayer <- "2) Create Character\n"
				p.toPlayer <- "3) Select Character\n"
				p.toPlayer <- "4) Delete Character\n"
				p.toPlayer <- "9) Quit\n"
			}
			p.toPlayer <- "\nEnter your choice: "

			select {
			case <-p.ctx.Done():
				return
			case choice := <-p.fromPlayer:
				switch strings.TrimSpace(choice) {
				case "1":
					p.HandlePasswordChange()

				case "2":
					p.toPlayer <- "Character creation not yet implemented\n"

				case "3":
					if characterCount > 0 {
						p.toPlayer <- "Character selection not yet implemented\n"
					} else {
						p.toPlayer <- "No characters available\n"
					}

				case "4":
					if characterCount > 0 {
						p.toPlayer <- "Character deletion not yet implemented\n"
					} else {
						p.toPlayer <- "No characters available\n"
					}

				case "9":
					p.toPlayer <- "\nGoodbye!\n"
					p.Stop()
					return

				default:
					p.toPlayer <- "Invalid choice. Please try again.\n"
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

	p.toPlayer <- "\nPassword must:\n" +
		"- Be at least 8 characters long\n" +
		"- Contain at least one uppercase letter\n" +
		"- Contain at least one lowercase letter\n" +
		"- Contain at least one number\n" +
		"- Contain at least one special character\n\n"

	p.toPlayer <- "Enter your current password (or 'exit' to cancel): "
	currentPassword := <-p.fromPlayer
	p.toPlayer <- "\n"

	if strings.ToLower(strings.TrimSpace(currentPassword)) == "exit" {
		p.toPlayer <- "Password change cancelled.\n"
		return
	}

	for {
		p.toPlayer <- "Enter your new password (or 'exit' to cancel): "
		newPassword := <-p.fromPlayer
		p.toPlayer <- "\n"

		if strings.ToLower(strings.TrimSpace(newPassword)) == "exit" {
			p.toPlayer <- "Password change cancelled.\n"
			return
		}

		if len(newPassword) < 8 {
			p.toPlayer <- "Password must be at least 8 characters long. Please try again.\n"
			continue
		}

		if !hasUpperCase.MatchString(newPassword) {
			p.toPlayer <- "Password must contain at least one uppercase letter. Please try again.\n"
			continue
		}

		if !hasLowerCase.MatchString(newPassword) {
			p.toPlayer <- "Password must contain at least one lowercase letter. Please try again.\n"
			continue
		}

		if !hasNumber.MatchString(newPassword) {
			p.toPlayer <- "Password must contain at least one number. Please try again.\n"
			continue
		}

		if !hasSpecialChar.MatchString(newPassword) {
			p.toPlayer <- "Password must contain at least one special character. Please try again.\n"
			continue
		}

		p.toPlayer <- "Confirm your new password: "
		confirmPassword := <-p.fromPlayer
		p.toPlayer <- "\n"

		if strings.ToLower(strings.TrimSpace(confirmPassword)) == "exit" {
			p.toPlayer <- "Password change cancelled.\n"
			return
		}

		if newPassword != confirmPassword {
			p.toPlayer <- "Passwords do not match. Please try again.\n"
			continue
		}

		err := p.server.ChangePassword(p, currentPassword, newPassword)
		if err != nil {
			// TODO: Provide more verbose feedback based on the error
			p.toPlayer <- "Password change failed. Please try again.\n"
			continue
		}

		p.toPlayer <- "Password successfully changed.\n"
		return
	}
}
