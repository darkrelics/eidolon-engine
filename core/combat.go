package core

import (
	"fmt"

	"github.com/google/uuid"
)

const (
	DefaultDistance = 30.0 // Default starting distance
	MeleeRange      = 5.0  // Distance for melee combat
	PoleRange       = 10.0 // Distance for pole weapons
	FarRange        = 30.0 // Distance for far range
	VeryFarRange    = 50.0 // Maximum combat distance
)

// EnterCombat initializes the CombatRange map when a character enters combat
func (c *Character) EnterCombat() {
	c.Mutex.Lock()
	defer c.Mutex.Unlock()
	if c.CombatRange == nil {
		c.CombatRange = make(map[uuid.UUID]float64)
	}
}

// ExitCombat clears the CombatRange map when a character exits combat
func (c *Character) ExitCombat() {
	c.Mutex.Lock()
	defer c.Mutex.Unlock()
	c.CombatRange = nil
	c.Advancing = false
}

// SetCombatRange sets the distance to a target character, initializing the map if necessary
func (c *Character) SetCombatRange(target *Character, distance float64) {
	c.Mutex.Lock()
	defer c.Mutex.Unlock()
	if c.CombatRange == nil {
		c.CombatRange = make(map[uuid.UUID]float64)
	}
	c.CombatRange[target.ID] = distance
}

// GetCombatRange gets the distance to a target character, returning DefaultDistance if not in combat
func (c *Character) GetCombatRange(target *Character) float64 {
	if c.CombatRange == nil {
		return DefaultDistance
	}
	if distance, exists := c.CombatRange[target.ID]; exists {
		return distance
	}
	return DefaultDistance
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
		if distance <= MeleeRange {
			return false
		}
	}
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

// Helper function to get range description based on distance
func getRangeDescription(distance float64) string {
	switch {
	case distance <= MeleeRange:
		return "melee"
	case distance <= PoleRange:
		return "pole"
	case distance <= FarRange:
		return "far"
	default:
		return "very far"
	}
}

func performAdvance(character *Character, target *Character, desiredDistance float64) {
	Logger.Debug("Starting performAdvance", "character", character.Name, "target", target.Name, "desiredDistance", desiredDistance)

	// Clear advancing state when done
	defer func() {
		Logger.Debug("Clearing advancing state", "character", character.Name)
		character.Mutex.Lock()
		character.Advancing = false
		character.Mutex.Unlock()
		Logger.Debug("Advancing state cleared", "character", character.Name)
	}()

	// Get initial state under a single lock
	Logger.Debug("Acquiring character lock for initial state", "character", character.Name)
	character.Mutex.Lock()
	agility, exists := character.Attributes["agility"]
	characterName := character.Name
	startingRoom := character.Room
	currentDistance := character.GetCombatRange(target)
	character.Mutex.Unlock()
	Logger.Debug("Released initial state lock", "character", characterName)

	if !exists || agility < 0.1 {
		Logger.Debug("Adjusting minimum agility", "character", characterName, "defaultAgility", 0.1)
		agility = 0.1
	}

	moveRate := 1.0 * agility
	isRetreat := desiredDistance > currentDistance
	if isRetreat {
		moveRate *= 1.05
	}

	distanceToMove := currentDistance - desiredDistance
	if isRetreat {
		distanceToMove = desiredDistance - currentDistance
		if desiredDistance > VeryFarRange {
			desiredDistance = VeryFarRange
		}
	}

	if distanceToMove <= 0 {
		Logger.Debug("No movement needed", "character", characterName)
		character.Player.ToPlayer <- "\n\rYou are already at the desired distance.\n\r"
		return
	}

	for {
		<-character.Game.Ticker.C

		// Get states before acquiring locks
		Logger.Debug("Pre-lock state check", "character", characterName)

		// First check character's state with minimal lock time
		character.Mutex.Lock()
		if !character.Advancing || character.Room != startingRoom {
			character.Mutex.Unlock()
			Logger.Debug("Character state invalid, ending movement", "character", characterName)
			character.Player.ToPlayer <- "\n\rMovement interrupted.\n\r"
			return
		}
		curDistance := character.GetCombatRange(target)
		character.Mutex.Unlock()

		// Then check target's state with minimal lock time
		target.Mutex.Lock()
		targetInRoom := target.Room == startingRoom
		target.Mutex.Unlock()

		if !targetInRoom {
			Logger.Debug("Target left room, ending movement", "character", characterName)
			character.Player.ToPlayer <- "\n\rMovement interrupted.\n\r"
			return
		}

		// Calculate new distance before acquiring locks
		var newDistance float64
		if isRetreat {
			newDistance = curDistance + moveRate
			if newDistance > desiredDistance {
				newDistance = desiredDistance
			}
			if newDistance > VeryFarRange {
				newDistance = VeryFarRange
			}
		} else {
			newDistance = curDistance - moveRate
			if newDistance < desiredDistance {
				newDistance = desiredDistance
			}
		}

		// Update distances with minimal lock time
		Logger.Debug("Acquiring locks for distance update", "character", characterName, "currentDistance", curDistance, "newDistance", newDistance)

		character.Mutex.Lock()
		character.SetCombatRange(target, newDistance)
		character.Mutex.Unlock()

		target.Mutex.Lock()
		target.SetCombatRange(character, newDistance)
		target.Mutex.Unlock()

		Logger.Debug("Released locks after distance update", "character", characterName, "newDistance", newDistance)

		rangeDesc := getRangeDescription(newDistance)

		// Send movement notifications using SendRoomMessageExcept
		if isRetreat {
			character.Player.ToPlayer <- fmt.Sprintf("\n\rYou retreat to %s range (%.1f units) from %s.\n\r",
				rangeDesc, newDistance, target.Name)

			roomMessage := fmt.Sprintf("\n\r%s retreats to %s range (%.1f units) from %s.\n\r",
				characterName, rangeDesc, newDistance, target.Name)
			SendRoomMessageExcept(startingRoom, roomMessage, character)
		} else {
			character.Player.ToPlayer <- fmt.Sprintf("\n\rYou advance to %s range (%.1f units) with %s.\n\r",
				rangeDesc, newDistance, target.Name)

			roomMessage := fmt.Sprintf("\n\r%s advances to %s range (%.1f units) with %s.\n\r",
				characterName, rangeDesc, newDistance, target.Name)
			SendRoomMessageExcept(startingRoom, roomMessage, character)
		}

		if (isRetreat && newDistance >= desiredDistance) ||
			(!isRetreat && newDistance <= desiredDistance) {
			Logger.Debug("Movement complete",
				"character", characterName,
				"finalDistance", newDistance)
			return
		}
	}
}
