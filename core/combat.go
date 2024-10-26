package core

import (
	"fmt"
	"time"

	"github.com/google/uuid"
)

// EnterCombat initializes the CombatRange map when a character enters combat
func (c *Character) EnterCombat() {
	c.Mutex.Lock()
	defer c.Mutex.Unlock()
	if c.CombatRange == nil {
		c.CombatRange = make(map[uuid.UUID]int)
	}
}

// ExitCombat clears the CombatRange map when a character exits combat
func (c *Character) ExitCombat() {
	c.Mutex.Lock()
	defer c.Mutex.Unlock()
	c.CombatRange = nil
}

// SetCombatRange sets the range to a target character, initializing the map if necessary
func (c *Character) SetCombatRange(target *Character, CombatRange int) {
	c.Mutex.Lock()
	defer c.Mutex.Unlock()
	if c.CombatRange == nil {
		c.CombatRange = make(map[uuid.UUID]int)
	}
	c.CombatRange[target.ID] = CombatRange
}

// GetCombatRange gets the range to a target character, returning RangeFar if not in combat
func (c *Character) GetCombatRange(target *Character) int {
	if c.CombatRange == nil {
		return 0 // RangeFar
	}
	if CombatRange, exists := c.CombatRange[target.ID]; exists {
		return CombatRange
	}
	return 0 // RangeFar
}

// IsInCombat checks if the character is currently in combat
func (c *Character) IsInCombat() bool {
	return c.CombatRange != nil && len(c.CombatRange) > 0
}

// CanEscape checks if the character can escape from combat
// Returns true if no other characters are at melee range
func (c *Character) CanEscape() bool {
	c.Mutex.Lock()
	defer c.Mutex.Unlock()

	// If not in combat, can always escape
	if c.CombatRange == nil {
		return true
	}

	// Check if any character is at melee range
	for _, distance := range c.CombatRange {
		if distance == 2 { // RangeMelee
			return false
		}
	}
	// No characters at melee range, can escape
	return true
}

// SetFacing sets the character's facing to the target character
func (c *Character) SetFacing(target *Character) {
	c.Mutex.Lock()
	defer c.Mutex.Unlock()
	c.Facing = target
}

// GetFacing returns the character that this character is facing
func (c *Character) GetFacing() *Character {
	return c.Facing
}

// ClearFacing clears the character's facing
func (c *Character) ClearFacing() {
	c.Mutex.Lock()
	defer c.Mutex.Unlock()
	c.Facing = nil
}

// Helper function to convert range int to string
func getRangeName(r int) string {
	switch r {
	case 0:
		return "far"
	case 1:
		return "pole"
	case 2:
		return "melee"
	default:
		return "unknown"
	}
}

func performAdvance(character *Character, target *Character, desiredRange int) {
	defer func() {
		character.Mutex.Lock()
		character.Advancing = false
		character.Mutex.Unlock()
	}()

	// Get base times in seconds
	farToPole := 8.0
	poleToMelee := 2.0

	// Calculate agility modifier (minimum of 1 to prevent division by zero)
	agility := character.Attributes["agility"]
	if agility < 1 {
		agility = 1
	}

	// Modify times based on agility
	farToPole = farToPole / agility
	poleToMelee = poleToMelee / agility

	for {
		character.Mutex.Lock()
		if !character.Advancing {
			// Advance was interrupted
			character.Mutex.Unlock()
			return
		}

		currentRange := character.GetCombatRange(target)

		// Check if target is still valid
		if target.Room != character.Room {
			character.Player.ToPlayer <- fmt.Sprintf("\n\r%s is no longer in the room.\n\r", target.Name)
			character.Mutex.Unlock()
			return
		}

		// If we've reached desired range, stop
		if currentRange >= desiredRange {
			character.Player.ToPlayer <- fmt.Sprintf("\n\rYou have reached %s range with %s.\n\r",
				getRangeName(currentRange), target.Name)
			character.Mutex.Unlock()
			return
		}

		// Determine next range and delay
		nextRange := currentRange + 1
		var delay float64
		if currentRange == 0 { // far to pole
			delay = farToPole
		} else { // pole to melee
			delay = poleToMelee
		}
		character.Mutex.Unlock()

		// Wait for the calculated time
		time.Sleep(time.Duration(delay * float64(time.Second)))

		// Check again if we should continue
		character.Mutex.Lock()
		if !character.Advancing || target.Room != character.Room {
			character.Mutex.Unlock()
			return
		}

		// Update the range
		character.SetCombatRange(target, nextRange)
		target.SetCombatRange(character, nextRange)

		// Notify both parties of the range change
		character.Player.ToPlayer <- fmt.Sprintf("\n\rYou advance to %s range with %s.\n\r",
			getRangeName(nextRange), target.Name)
		target.Player.ToPlayer <- fmt.Sprintf("\n\r%s advances to %s range with you.\n\r",
			character.Name, getRangeName(nextRange))
		target.Player.ToPlayer <- target.Player.Prompt

		// If we've reached the desired range, we're done
		if nextRange == desiredRange {
			character.Mutex.Unlock()
			return
		}
		character.Mutex.Unlock()
	}
}
