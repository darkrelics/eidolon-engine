/*
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

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
	CharStateGhost       = "ghost"
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

func GetHealingDuration(damageType string) time.Duration {
	switch damageType {
	case DamageTypeBashing:
		return BashingHealTime
	case DamageTypeLethal:
		return LethalHealTime
	case DamageTypeAggravated:
		return AggravatedHealTime
	default:
		return BashingHealTime
	}
}

func (c *Character) TakeDamage(damageType string, amount int) {
	c.mutex.Lock()
	defer c.mutex.Unlock()

	originalAmount := amount

	if c.charState == CharStateUnconscious {
		amount = c.handleUnconsciousDamage(damageType, amount)
		damageType = c.convertUnconsciousDamageType(damageType)
	}

	c.addWounds(damageType, amount)
	c.health = c.maxHealth - len(c.wounds)

	damageMsg := fmt.Sprintf("You take %d %s damage! Health: %d/%d\n\r",
		originalAmount, damageType, c.health, c.maxHealth)
	c.playerCommandOut <- damageMsg

	if c.health <= 0 {
		c.updateStateWhenHealthZero()
	}
}

func (c *Character) handleUnconsciousDamage(damageType string, amount int) int {
	if damageType != DamageTypeLethal && damageType != DamageTypeAggravated {
		return amount
	}

	bashingCount := c.countWoundType(DamageTypeBashing)
	replacements := min(amount, bashingCount)

	if replacements > 0 {
		c.replaceBashingWounds(replacements, damageType)
		return amount - replacements
	}

	return amount
}

func (c *Character) convertUnconsciousDamageType(damageType string) string {
	if damageType == DamageTypeBashing {
		return DamageTypeLethal
	}
	return damageType
}

func (c *Character) countWoundType(woundType string) int {
	count := 0
	for _, wound := range c.wounds {
		if wound.DamageType == woundType {
			count++
		}
	}
	return count
}

func (c *Character) replaceBashingWounds(amount int, newType string) {
	newWounds := []Wound{}
	replaced := 0
	now := time.Now()
	healDuration := GetHealingDuration(newType)

	for _, wound := range c.wounds {
		if wound.DamageType == DamageTypeBashing && replaced < amount {
			newWounds = append(newWounds, Wound{
				DamageType: newType,
				HealAt:     now.Add(healDuration),
			})
			replaced++
		} else {
			newWounds = append(newWounds, wound)
		}
	}

	c.wounds = newWounds
}

func (c *Character) addWounds(damageType string, amount int) {
	now := time.Now()
	healDuration := GetHealingDuration(damageType)

	for i := 0; i < amount; i++ {
		c.wounds = append(c.wounds, Wound{
			DamageType: damageType,
			HealAt:     now.Add(healDuration),
		})
	}
}

func (c *Character) updateStateWhenHealthZero() {
	if c.countWoundType(DamageTypeBashing) > 0 && c.charState != CharStateDead {
		c.charState = CharStateUnconscious
		c.playerCommandOut <- ApplyColor("yellow", "You fall unconscious!\n\r")
	} else {
		previousState := c.charState
		c.charState = CharStateDead
		c.playerCommandOut <- ApplyColor("red", "You have died!\n\r")

		// Update the player's character list to mark this character as dead
		if previousState != CharStateDead && c.player != nil {
			c.player.MarkCharacterDead(c.name)
		}
	}
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func (c *Character) CalculateCurrentHealth() {
	c.mutex.Lock()
	defer c.mutex.Unlock()

	if c.charState == CharStateDead {
		return
	}

	now := time.Now()
	activeWounds := []Wound{}

	for _, wound := range c.wounds {
		if wound.HealAt.After(now) {
			activeWounds = append(activeWounds, wound)
		}
	}

	if len(activeWounds) != len(c.wounds) {
		healed := len(c.wounds) - len(activeWounds)
		c.wounds = activeWounds
		oldHealth := c.health
		c.health = c.maxHealth - len(c.wounds)

		if oldHealth <= 0 && c.health > 0 && c.charState == CharStateUnconscious {
			c.charState = CharStateStanding
			if c.player != nil {
				c.playerCommandOut <- ApplyColor("green", "You regain consciousness!\n\r")
			}
		}

		if healed > 0 && c.player != nil {
			c.playerCommandOut <- fmt.Sprintf("You heal %d wound%s. Health: %d/%d\n\r",
				healed, pluralize(healed), c.health, c.maxHealth)
		}
	}
}

func (c *Character) GetWoundsByType() map[string]int {
	c.mutex.RLock()
	defer c.mutex.RUnlock()

	counts := make(map[string]int)
	for _, wound := range c.wounds {
		counts[wound.DamageType]++
	}
	return counts
}

func pluralize(count int) string {
	if count == 1 {
		return ""
	}
	return "s"
}
