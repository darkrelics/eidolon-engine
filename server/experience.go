/*
Eidolon Engine

Copyright 2024-2025 Jason E. Robinson

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

	remainingToMax := maxScore - currentScore

	xpRequired := CalculateXPRequirement(currentScore)

	increment := xpGained / xpRequired

	if increment > remainingToMax {
		return remainingToMax
	}

	return increment
}

// ResolveOpposedCheckWithXP performs an opposed check and awards experience
func ResolveOpposedCheckWithXP(aggressor, defender *Character, aggressorSkill, aggressorAttr, defenderSkill, defenderAttr string) Outcome {
	aggressorSkillVal := aggressor.GetSkill(aggressorSkill)
	aggressorAttrVal := aggressor.GetAttribute(aggressorAttr)
	defenderSkillVal := defender.GetSkill(defenderSkill)
	defenderAttrVal := defender.GetAttribute(defenderAttr)

	aggressorEffective := int(aggressorSkillVal + aggressorAttrVal)
	defenderEffective := int(defenderSkillVal + defenderAttrVal)

	outcome := ResolveOpposedCheck(aggressorEffective, defenderEffective)

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

	AwardExperience(aggressor, defender, context)

	return outcome
}

// AwardExperience awards experience to both participants in a contested action
func AwardExperience(aggressor, defender *Character, context ExperienceContext) {
	if aggressor == nil || defender == nil {
		return
	}

	baseXPValue := CalculateBaseXP()

	// For aggressor: reward based on taking on stronger opponents
	aggressorVariance := CalculateVarianceModifier(context.AggressorEffective, context.DefenderEffective)
	// For defender: reward based on defending against weaker opponents is less
	defenderVariance := CalculateVarianceModifier(context.AggressorEffective, context.DefenderEffective)

	aggressorXP := CalculateFinalXP(baseXPValue, aggressorVariance, context.AggressorSuccess)
	defenderXP := CalculateFinalXP(baseXPValue, defenderVariance, context.DefenderSuccess)

	Logger.Info("Experience awarding for contested action",
		"aggressor", aggressor.name,
		"defender", defender.name,
		"aggressorXP", aggressorXP,
		"defenderXP", defenderXP,
		"aggressorSuccess", context.AggressorSuccess,
		"defenderSuccess", context.DefenderSuccess)

	if context.AggressorSkill != "" {
		aggressor.AwardSkillXP(context.AggressorSkill, aggressorXP)
	}
	if context.AggressorAttr != "" {
		aggressor.AwardAttributeXP(context.AggressorAttr, aggressorXP*attributeXPRatio)
	}

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

		Logger.Info("Skill experience awarded",
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

		Logger.Info("Attribute experience awarded",
			"character", c.name,
			"attribute", attrName,
			"xp", xpAmount,
			"increment", increment,
			"newScore", c.attributes[attrName])
	}
}

// ResolveStaticCheckWithXP performs a static check against a difficulty and awards experience
func ResolveStaticCheckWithXP(character *Character, skill, attr string, difficulty int) Outcome {
	if character == nil {
		return ResolveStaticCheck(0, difficulty)
	}

	skillVal := character.GetSkill(skill)
	attrVal := character.GetAttribute(attr)
	effective := int(skillVal + attrVal)

	outcome := ResolveStaticCheck(effective, difficulty)

	varianceModifier := CalculateVarianceModifier(effective, difficulty)

	baseXPValue := CalculateBaseXP()
	finalXP := CalculateFinalXP(baseXPValue, varianceModifier, outcome.Success)

	if skill != "" {
		character.AwardSkillXP(skill, finalXP)
	}
	if attr != "" {
		character.AwardAttributeXP(attr, finalXP*attributeXPRatio)
	}

	return outcome
}
