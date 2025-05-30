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
	"math"
	"time"
)

// Experience system constants
const (
	baseXP             = 0.25 // base experience award per action
	varianceExponent   = 2.0  // k value for variance modifier sharpening
	xpProgressionBase  = 10.0 // base multiplier for XP requirements
	xpProgressionRatio = 3.5  // exponential ratio for XP requirements
	attributeXPRatio   = 0.1  // attributes gain 10% of skill XP
	failurePenalty     = 0.5  // failure gives 50% XP
	maxScore           = 10.0 // maximum skill/attribute score
)

// ExperienceContext holds information about a contested action for experience calculation
type ExperienceContext struct {
	AggressorSkill     string
	AggressorAttr      string
	DefenderSkill      string
	DefenderAttr       string
	AggressorSuccess   bool
	DefenderSuccess    bool
	AggressorEffective int
	DefenderEffective  int
}

// CalculateXPRequirement returns the XP required to advance from current score to score+1
func CalculateXPRequirement(currentScore float64) float64 {
	return xpProgressionBase * math.Pow(xpProgressionRatio, currentScore)
}

// CalculateVarianceModifier calculates the variance modifier based on effective scores
func CalculateVarianceModifier(myEffective, opponentEffective int) float64 {
	if myEffective == 0 && opponentEffective == 0 {
		return 1.0
	}

	minScore := float64(min(myEffective, opponentEffective))
	maxScore := float64(max(myEffective, opponentEffective))

	if maxScore == 0 {
		return 1.0
	}

	ratio := minScore / maxScore
	return math.Pow(ratio, varianceExponent)
}

// CalculateBaseXP calculates the raw XP before modifiers
func CalculateBaseXP() float64 {
	return baseXP
}

// CalculateFinalXP calculates the final XP award for a participant
func CalculateFinalXP(baseXP float64, varianceModifier float64, success bool) float64 {
	xpVar := baseXP * varianceModifier
	if success {
		return xpVar
	}
	return xpVar * failurePenalty
}

// CalculateScoreIncrement calculates how much to increment a score based on XP gained
func CalculateScoreIncrement(xpGained float64, currentScore float64) float64 {
	if currentScore >= maxScore {
		return 0.0
	}

	// Calculate remaining distance to max score
	remainingToMax := maxScore - currentScore

	// Calculate the XP required to advance from current score
	xpRequired := CalculateXPRequirement(currentScore)

	// Calculate the raw increment based on XP gained
	increment := xpGained / xpRequired

	// Cap the increment to not exceed max score
	if increment > remainingToMax {
		return remainingToMax
	}

	return increment
}

// ResolveOpposedCheckWithXP performs an opposed check and awards experience
func ResolveOpposedCheckWithXP(aggressor, defender *Character, aggressorSkill, aggressorAttr, defenderSkill, defenderAttr string) Outcome {
	// Calculate effective scores
	aggressorSkillVal := aggressor.GetSkill(aggressorSkill)
	aggressorAttrVal := aggressor.GetAttribute(aggressorAttr)
	defenderSkillVal := defender.GetSkill(defenderSkill)
	defenderAttrVal := defender.GetAttribute(defenderAttr)

	aggressorEffective := int(aggressorSkillVal + aggressorAttrVal)
	defenderEffective := int(defenderSkillVal + defenderAttrVal)

	// Perform the opposed check
	outcome := ResolveOpposedCheck(aggressorEffective, defenderEffective)

	// Create experience context
	context := ExperienceContext{
		AggressorSkill:     aggressorSkill,
		AggressorAttr:      aggressorAttr,
		DefenderSkill:      defenderSkill,
		DefenderAttr:       defenderAttr,
		AggressorSuccess:   outcome.Success,
		DefenderSuccess:    !outcome.Success,
		AggressorEffective: aggressorEffective,
		DefenderEffective:  defenderEffective,
	}

	// Award experience
	AwardExperience(aggressor, defender, context)

	return outcome
}

// AwardExperience awards experience to both participants in a contested action
func AwardExperience(aggressor, defender *Character, context ExperienceContext) {
	if aggressor == nil || defender == nil {
		return
	}

	baseXPValue := CalculateBaseXP()

	// Calculate variance modifiers for each participant
	aggressorVariance := CalculateVarianceModifier(context.DefenderEffective, context.AggressorEffective)
	defenderVariance := CalculateVarianceModifier(context.AggressorEffective, context.DefenderEffective)

	// Calculate final XP for each participant
	aggressorXP := CalculateFinalXP(baseXPValue, aggressorVariance, context.AggressorSuccess)
	defenderXP := CalculateFinalXP(baseXPValue, defenderVariance, context.DefenderSuccess)

	// Award XP to aggressor
	if context.AggressorSkill != "" {
		aggressor.AwardSkillXP(context.AggressorSkill, aggressorXP)
	}
	if context.AggressorAttr != "" {
		aggressor.AwardAttributeXP(context.AggressorAttr, aggressorXP*attributeXPRatio)
	}

	// Award XP to defender
	if context.DefenderSkill != "" {
		defender.AwardSkillXP(context.DefenderSkill, defenderXP)
	}
	if context.DefenderAttr != "" {
		defender.AwardAttributeXP(context.DefenderAttr, defenderXP*attributeXPRatio)
	}
}

// AwardSkillXP awards experience to a specific skill
func (c *Character) AwardSkillXP(skillName string, xpAmount float64) {
	if xpAmount <= 0 {
		return
	}

	c.mutex.Lock()
	defer c.mutex.Unlock()

	currentScore, exists := c.skills[skillName]
	if !exists {
		currentScore = 0.0
		c.skills[skillName] = currentScore
	}

	increment := CalculateScoreIncrement(xpAmount, currentScore)
	if increment > 0 {
		c.skills[skillName] = currentScore + increment
		c.lastEdited = time.Now()

		Logger.Debug("Skill XP awarded",
			"character", c.name,
			"skill", skillName,
			"xp", xpAmount,
			"increment", increment,
			"newScore", c.skills[skillName])
	}
}

// AwardAttributeXP awards experience to a specific attribute
func (c *Character) AwardAttributeXP(attrName string, xpAmount float64) {
	if xpAmount <= 0 {
		return
	}

	c.mutex.Lock()
	defer c.mutex.Unlock()

	currentScore, exists := c.attributes[attrName]
	if !exists {
		currentScore = 0.0
		c.attributes[attrName] = currentScore
	}

	increment := CalculateScoreIncrement(xpAmount, currentScore)
	if increment > 0 {
		c.attributes[attrName] = currentScore + increment
		c.lastEdited = time.Now()

		Logger.Debug("Attribute XP awarded",
			"character", c.name,
			"attribute", attrName,
			"xp", xpAmount,
			"increment", increment,
			"newScore", c.attributes[attrName])
	}
}

// ResolveStaticCheckWithXP performs a static check against a difficulty and awards experience
func ResolveStaticCheckWithXP(character *Character, skill, attr string, difficulty int) Outcome {
	// Handle nil character
	if character == nil {
		return ResolveStaticCheck(0, difficulty)
	}

	// Calculate effective score
	skillVal := character.GetSkill(skill)
	attrVal := character.GetAttribute(attr)
	effective := int(skillVal + attrVal)

	// Perform the static check
	outcome := ResolveStaticCheck(effective, difficulty)

	// Calculate variance modifier based on character score vs difficulty
	varianceModifier := CalculateVarianceModifier(effective, difficulty)

	// Calculate XP award
	baseXPValue := CalculateBaseXP()
	finalXP := CalculateFinalXP(baseXPValue, varianceModifier, outcome.Success)

	// Award XP to character
	if skill != "" {
		character.AwardSkillXP(skill, finalXP)
	}
	if attr != "" {
		character.AwardAttributeXP(attr, finalXP*attributeXPRatio)
	}

	return outcome
}
