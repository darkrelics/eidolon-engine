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
	"fmt"
	"time"
)

const (
	DamageTypeBashing    = "bashing"
	DamageTypeLethal     = "lethal"
	DamageTypeAggravated = "aggravated"
)

const (
	CharStateStanding    = "standing"
	CharStateUnconscious = "unconscious"
	CharStateDead        = "dead"
)

const (
	BashingHealTime    = 15 * time.Minute
	LethalHealTime     = 6 * time.Hour
	AggravatedHealTime = 7 * 24 * time.Hour // 7 days
)

// Wound represents a single point of damage with its heal time
type Wound struct {
	DamageType string    `json:"damage_type" dynamodbav:"damage_type"`
	HealAt     time.Time `json:"heal_at" dynamodbav:"heal_at"`
}

// GetHealingDuration returns the healing time for a damage type
func GetHealingDuration(damageType string) time.Duration {
	switch damageType {
	case DamageTypeBashing:
		return BashingHealTime
	case DamageTypeLethal:
		return LethalHealTime
	case DamageTypeAggravated:
		return AggravatedHealTime
	default:
		return BashingHealTime // Default to fastest healing
	}
}

// TakeDamage applies damage of the specified type to the character
func (c *Character) TakeDamage(damageType string, amount int) {
	c.mutex.Lock()
	defer c.mutex.Unlock()

	// Handle damage conversion for unconscious characters
	if c.charState == CharStateUnconscious {
		if damageType == DamageTypeBashing {
			// Bashing converts to lethal when unconscious
			damageType = DamageTypeLethal
		} else if damageType == DamageTypeLethal || damageType == DamageTypeAggravated {
			// Lethal/Aggravated replaces bashing wounds first
			bashingCount := 0
			for _, wound := range c.wounds {
				if wound.DamageType == DamageTypeBashing {
					bashingCount++
				}
			}
			
			// Replace bashing wounds with new damage type
			replacements := min(amount, bashingCount)
			if replacements > 0 {
				newWounds := []Wound{}
				replaced := 0
				now := time.Now()
				healDuration := GetHealingDuration(damageType)
				
				// Keep non-bashing wounds and replace bashing with new damage type
				for _, wound := range c.wounds {
					if wound.DamageType == DamageTypeBashing && replaced < replacements {
						// Replace this bashing wound with the new damage type
						newWounds = append(newWounds, Wound{
							DamageType: damageType,
							HealAt:     now.Add(healDuration),
						})
						replaced++
					} else {
						newWounds = append(newWounds, wound)
					}
				}
				
				c.wounds = newWounds
				amount -= replacements
			}
		}
	}

	now := time.Now()
	healDuration := GetHealingDuration(damageType)

	// Add remaining wounds
	for i := 0; i < amount; i++ {
		wound := Wound{
			DamageType: damageType,
			HealAt:     now.Add(healDuration),
		}
		c.wounds = append(c.wounds, wound)
	}

	// Update current health
	c.health = c.maxHealth - len(c.wounds)

	// Notify the player
	damageMsg := fmt.Sprintf("You take %d %s damage! Health: %d/%d\n\r", 
		amount, damageType, c.health, c.maxHealth)
	c.playerCommandOut <- damageMsg

	// Check for unconscious or death
	if c.health <= 0 {
		// Check if any bashing wounds remain
		hasBashing := false
		for _, wound := range c.wounds {
			if wound.DamageType == DamageTypeBashing {
				hasBashing = true
				break
			}
		}

		if hasBashing && c.charState != CharStateDead {
			c.charState = CharStateUnconscious
			c.playerCommandOut <- ApplyColor("yellow", "You fall unconscious!\n\r")
		} else {
			c.charState = CharStateDead
			c.playerCommandOut <- ApplyColor("red", "You have died!\n\r")
		}
	}
}

// Helper function for min value
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// CalculateCurrentHealth recalculates health based on wounds that have healed
func (c *Character) CalculateCurrentHealth() {
	c.mutex.Lock()
	defer c.mutex.Unlock()

	now := time.Now()
	activeWounds := []Wound{}

	// Keep only wounds that haven't healed yet
	for _, wound := range c.wounds {
		if wound.HealAt.After(now) {
			activeWounds = append(activeWounds, wound)
		}
	}

	// Update wounds and health if any healing occurred
	if len(activeWounds) != len(c.wounds) {
		healed := len(c.wounds) - len(activeWounds)
		c.wounds = activeWounds
		oldHealth := c.health
		c.health = c.maxHealth - len(c.wounds)
		
		// Check for state transitions
		if oldHealth <= 0 && c.health > 0 {
			// Regaining consciousness
			if c.charState == CharStateUnconscious {
				c.charState = CharStateStanding
				if c.player != nil {
					c.playerCommandOut <- ApplyColor("green", "You regain consciousness!\n\r")
				}
			}
		}
		
		if healed > 0 && c.player != nil {
			c.playerCommandOut <- fmt.Sprintf("You heal %d wound%s. Health: %d/%d\n\r",
				healed, pluralize(healed), c.health, c.maxHealth)
		}
	}
}

// GetWoundsByType returns count of wounds by damage type
func (c *Character) GetWoundsByType() map[string]int {
	c.mutex.RLock()
	defer c.mutex.RUnlock()

	counts := make(map[string]int)
	for _, wound := range c.wounds {
		counts[wound.DamageType]++
	}
	return counts
}

// Helper function for pluralization
func pluralize(count int) string {
	if count == 1 {
		return ""
	}
	return "s"
}