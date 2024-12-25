package main

import (
	"fmt"
	"math"

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
	return c.CombatRange != nil
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
	defer func() {
		character.Mutex.Lock()
		character.Advancing = false
		character.Mutex.Unlock()
	}()

	character.Mutex.Lock()
	agility := character.Attributes["agility"]
	if agility < 0.1 {
		agility = 0.1
	}
	startingRoom := character.Room
	currentDistance := character.GetCombatRange(target)
	characterName := character.Name
	character.Mutex.Unlock()

	moveRate := 1.0 * agility
	isRetreat := desiredDistance > currentDistance
	if isRetreat {
		moveRate *= 1.05
		if desiredDistance > VeryFarRange {
			desiredDistance = VeryFarRange
		}
	}

	for {
		select {
		case <-character.End:
			character.Player.toPlayer <- "\n\rMovement interrupted.\n\r"
			return

		case <-target.End:
			character.Player.toPlayer <- "\n\rMovement interrupted.\n\r"
			return

		case <-character.Game.ticker.C:
			character.Mutex.Lock()
			if !character.Advancing || character.Room != startingRoom {
				character.Mutex.Unlock()
				character.Player.toPlayer <- "\n\rMovement interrupted.\n\r"
				return
			}
			curDistance := character.GetCombatRange(target)
			character.Mutex.Unlock()

			var newDistance float64
			if isRetreat {
				newDistance = math.Min(desiredDistance, math.Min(curDistance+moveRate, VeryFarRange))
			} else {
				newDistance = math.Max(desiredDistance, curDistance-moveRate)
			}

			character.Mutex.Lock()
			character.SetCombatRange(target, newDistance)
			character.Mutex.Unlock()

			target.Mutex.Lock()
			target.SetCombatRange(character, newDistance)
			target.Mutex.Unlock()

			rangeDesc := getRangeDescription(newDistance)
			if isRetreat {
				character.Player.toPlayer <- fmt.Sprintf("\n\rYou retreat to %s range (%.1f units) from %s.\n\r",
					rangeDesc, newDistance, target.Name)
				SendRoomMessageExcept(startingRoom,
					fmt.Sprintf("\n\r%s retreats to %s range (%.1f units) from %s.\n\r",
						characterName, rangeDesc, newDistance, target.Name), character)
			} else {
				character.Player.toPlayer <- fmt.Sprintf("\n\rYou advance to %s range (%.1f units) with %s.\n\r",
					rangeDesc, newDistance, target.Name)
				SendRoomMessageExcept(startingRoom,
					fmt.Sprintf("\n\r%s advances to %s range (%.1f units) with %s.\n\r",
						characterName, rangeDesc, newDistance, target.Name), character)
			}

			if (!isRetreat && newDistance <= desiredDistance) ||
				(isRetreat && newDistance >= desiredDistance) {
				return
			}
		}
	}
}
