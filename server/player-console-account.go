/*
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

*/

package main

import (
	"fmt"
	"regexp"
	"strings"

	"github.com/gofrs/uuid/v5"
)

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

	p.commandOut <- "Enter your current password (or '0' to cancel): "
	currentPassword := <-p.commandIn
	p.commandOut <- "\n"

	if strings.TrimSpace(currentPassword) == "0" {
		p.commandOut <- "Password change cancelled.\n"
		return
	}

	for {
		p.commandOut <- "Enter your new password (or '0' to cancel): "
		newPassword := <-p.commandIn
		p.commandOut <- "\n"

		if strings.TrimSpace(newPassword) == "0" {
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

		if strings.TrimSpace(confirmPassword) == "0" {
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
		defaultMOTDID, _ := uuid.FromString("00000000-0000-0000-0000-000000000000")
		if motd.MotdID == defaultMOTDID {
			p.commandOut <- fmt.Sprintf("\n\r%s\n\r", motd.Message)
		} else {
			p.commandOut <- fmt.Sprintf("\n\r[%s]\n\r%s\n\r", dateStr, motd.Message)
		}
	}
}
