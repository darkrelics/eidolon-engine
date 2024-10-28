package core

import (
	"fmt"
	"strings"
)

func ExecuteAssessCommand(character *Character, tokens []string) bool {
	Logger.Debug("Player is assessing combat situation", "playerName", character.Player.PlayerID)

	if !character.IsInCombat() {
		// Add facing info even when not in combat
		if character.Facing != nil {
			character.Player.ToPlayer <- fmt.Sprintf("\n\rYou are facing %s but not in combat.\n\r", character.Facing.Name)
		} else {
			character.Player.ToPlayer <- "\n\rYou are not currently in combat.\n\r"
		}
		return false
	}

	var assessment strings.Builder
	assessment.WriteString("\n\rCombat Assessment:\n\r")

	if len(character.CombatRange) == 0 {
		// Add facing info even with no range information
		if character.Facing != nil {
			assessment.WriteString(fmt.Sprintf("You are facing %s but not engaged with any opponents.\n\r", character.Facing.Name))
		} else {
			assessment.WriteString("You are in combat, but not engaged with any specific opponents.\n\r")
		}
	} else {
		// Track who we're advancing towards
		var advanceTarget *Character
		if character.Advancing && character.Facing != nil {
			advanceTarget = character.Facing
		}

		// First assess our own situation with each combatant
		for targetID, distance := range character.CombatRange {
			targetCharacter := character.Server.Characters[targetID]
			if targetCharacter == nil {
				continue
			}

			// Build status line with precise distance
			statusLine := fmt.Sprintf("%s is at %s range (%.1f units)",
				targetCharacter.Name,
				getRangeDescription(distance),
				distance)

			// Add facing information
			if targetCharacter.GetFacing() == character {
				statusLine += " and is facing you"
			}

			// Note if this is who we're facing
			if targetCharacter == character.Facing {
				statusLine += " and you are facing them"
			}

			// Add advance information
			if targetCharacter == advanceTarget {
				statusLine += " and you are advancing"
			}
			if targetCharacter.Advancing && targetCharacter.Facing == character {
				statusLine += " and they are advancing towards you"
			}

			assessment.WriteString(statusLine + ".\n\r")
		}
	}

	// Add escape possibility
	if character.CanEscape() {
		assessment.WriteString("You can attempt to escape from combat.\n\r")
	} else {
		assessment.WriteString("You are engaged in melee combat!\n\r")
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

	// Initiating character enters combat and sets range
	character.EnterCombat()
	character.SetCombatRange(targetCharacter, DefaultDistance)

	// Target enters combat but doesn't change facing
	targetCharacter.EnterCombat()
	targetCharacter.SetCombatRange(character, DefaultDistance)

	character.Player.ToPlayer <- fmt.Sprintf("\n\rYou are now facing %s at a distance of %.1f units.\n\r",
		targetCharacter.Name, DefaultDistance)

	// Notify the target character with range information
	targetCharacter.Player.ToPlayer <- fmt.Sprintf("\n\r%s is now facing you at a distance of %.1f units.\n\r",
		character.Name, DefaultDistance)
	targetCharacter.Player.ToPlayer <- targetCharacter.Player.Prompt

	return false
}

func ExecuteAdvanceCommand(character *Character, tokens []string) bool {
	if character == nil {
		Logger.Error("Attempted to advance with nil character")
		return false
	}

	// Check if already advancing
	if character.Advancing {
		character.Player.ToPlayer <- "\n\rYou are already advancing.\n\r"
		return false
	}

	// Check if already in melee with someone
	for targetID, distance := range character.CombatRange {
		if distance <= MeleeRange {
			if target := character.Server.Characters[targetID]; target != nil {
				character.Player.ToPlayer <- fmt.Sprintf("\n\rYou are already in melee combat with %s.\n\r", target.Name)
				return false
			}
		}
	}

	// Default values
	desiredDistance := MeleeRange
	var target *Character

	if len(tokens) > 1 {
		// Handle the last token as the target name unless it's a range specification
		lastToken := strings.ToLower(tokens[len(tokens)-1])
		switch lastToken {
		case "far":
			desiredDistance = FarRange
		case "pole":
			desiredDistance = PoleRange
		case "melee":
			desiredDistance = MeleeRange
		default:
			// If not a range specification, use it as target name
			// Find target in room
			for _, c := range character.Room.Characters {
				if strings.EqualFold(c.Name, lastToken) {
					target = c
					break
				}
			}
		}

		// Check if second to last token is "very" for "very far"
		if len(tokens) > 2 && strings.ToLower(tokens[len(tokens)-2]) == "very" && lastToken == "far" {
			desiredDistance = VeryFarRange
		}
	}

	// If no target specified, use current facing
	if target == nil {
		target = character.Facing
	}

	if target == nil {
		character.Player.ToPlayer <- "\n\rAdvance towards whom?\n\r"
		return false
	}

	// Check for self-targeting
	if target == character {
		character.Player.ToPlayer <- "\n\rYou cannot advance towards yourself.\n\r"
		return false
	}

	character.Advancing = true
	// Launch performAdvance as non-blocking goroutine
	go performAdvance(character, target, desiredDistance)

	// Inform the character and room
	character.Player.ToPlayer <- fmt.Sprintf("\n\rYou begin advancing towards %s.\n\r", target.Name)
	SendRoomMessage(character.Room, fmt.Sprintf("\n\r%s begins advancing towards %s.\n\r",
		character.Name, target.Name))

	return false
}
func ExecuteRetreatCommand(character *Character, tokens []string) bool {
	if character == nil {
		Logger.Error("Attempted to retreat with nil character")
		return false
	}

	// Check if already advancing/retreating
	if character.Advancing {
		character.Player.ToPlayer <- "\n\rYou are already in motion.\n\r"
		return false
	}

	// Default values
	desiredDistance := FarRange
	var target *Character

	if len(tokens) > 1 {
		// Handle the last token as the target name unless it's a range specification
		lastToken := strings.ToLower(tokens[len(tokens)-1])
		switch lastToken {
		case "far":
			desiredDistance = FarRange
		case "pole":
			desiredDistance = PoleRange
		default:
			// If not a range specification, use it as target name
			// Find target in room
			for _, c := range character.Room.Characters {
				if strings.EqualFold(c.Name, lastToken) {
					target = c
					break
				}
			}
		}

		// Check if second to last token is "very" for "very far"
		if len(tokens) > 2 && strings.ToLower(tokens[len(tokens)-2]) == "very" && lastToken == "far" {
			desiredDistance = VeryFarRange
		}
	}

	// If no target specified, use current facing
	if target == nil {
		target = character.Facing
	}

	if target == nil {
		character.Player.ToPlayer <- "\n\rRetreat from whom?\n\r"
		return false
	}

	// Get current distance
	currentDistance := character.GetCombatRange(target)

	// If already at or beyond desired distance
	if currentDistance >= desiredDistance {
		character.Player.ToPlayer <- fmt.Sprintf("\n\rYou are already at %s range from %s.\n\r",
			getRangeDescription(desiredDistance), target.Name)
		return false
	}

	// Start the retreat
	character.Advancing = true // We reuse the advancing flag for any movement
	go performAdvance(character, target, desiredDistance)

	// Inform the character and room
	character.Player.ToPlayer <- fmt.Sprintf("\n\rYou begin retreating from %s.\n\r", target.Name)
	SendRoomMessage(character.Room, fmt.Sprintf("\n\r%s begins retreating from %s.\n\r",
		character.Name, target.Name))

	return false
}
