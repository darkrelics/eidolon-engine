"""
Game mechanics calculations.

Provides pure functions for game mechanics: skill checks, XP calculations, opposed rolls.
This module has no dependencies on character_data to avoid circular imports.
"""

import math
import random

from eidolon.constants import ATTRIBUTE_XP_RATIO, BASE_XP, FAILURE_XP_PENALTY, MAX_SKILL_LEVEL


def resolve_opposed_check(aggressor: float, defender: float) -> dict:
    """
    Resolve an opposed check using MUD mechanics (without XP).

    Args:
        aggressor: Aggressor's rating
        defender: Defender's rating

    Returns:
        Dict:
            - Success: bool
            - Sigma: float
    """
    # Constants from MUD mechanics
    k_shift = 0.20  # How much rating difference matters
    k_var = 0.35  # Variance scaling
    min_sig = 0.25  # Minimum variance

    # Calculate difference
    diff: float = aggressor - defender

    # Calculate mean and variance
    mean: float = k_shift * diff
    variance: float = 1.0 + k_var * math.tanh(diff / 10.0)
    variance = max(variance, min_sig)

    # Generate outcome using normal distribution
    sigma: float = random.gauss(mean, variance)
    success: bool = sigma >= 0

    return {"Success": success, "Sigma": sigma}


def calculate_skill_increase(effective_score: float, difficulty: float, current_skill: float, success: bool) -> float:
    """
    Calculate skill increase from a single action using exponential XP requirements.

    Matches MUD formula:
    1. XP amount = BASE_XP * variance_modifier (using effective scores)
    2. increment = XP / (10 * 3.5^currentSkillScore)

    Args:
        effective_score: Current effective score (skill + attribute) for variance calculation
        difficulty: Difficulty (opponent effective or static difficulty) for variance calculation
        current_skill: Current skill level alone (for increment calculation)
        success: Whether the action succeeded

    Returns:
        Amount to increase skill by
    """
    # Calculate variance modifier using effective scores (quadratic scaling based on ratio)
    # Matches MUD: ratio = min(S, D) / max(S, D), variance_modifier = ratio^2
    if effective_score == 0 and difficulty == 0:
        variance_modifier = 1.0
    elif max(effective_score, difficulty) == 0:
        variance_modifier = 1.0
    else:
        ratio = min(effective_score, difficulty) / max(effective_score, difficulty)
        variance_modifier = ratio * ratio

    # Base XP for this action
    base_xp = BASE_XP * variance_modifier

    # Apply failure penalty
    if not success:
        if effective_score >= difficulty:
            base_xp = 0.0  # No XP for failing easy challenge
        else:
            base_xp *= FAILURE_XP_PENALTY  # 50% XP for failing hard challenge

    if base_xp <= 0:
        return 0.0

    # Calculate XP requirement for CURRENT SKILL level (exponential)
    # Matches MUD formula: xpRequired = 10.0 * 3.5^currentScore
    xp_required = 10.0 * math.pow(3.5, current_skill)

    # Calculate increment: xpGained / xpRequired
    increment = base_xp / xp_required

    # Cap at max level
    remaining_to_max = MAX_SKILL_LEVEL - current_skill
    if increment > remaining_to_max:
        return remaining_to_max

    return increment


def resolve_opposed_check_with_xp(
    character_id: str,
    aggressor_effective: float,
    defender_effective: float,
    skill_name: str,
    attribute_name: str,
    character_skills: dict,
    character_attributes: dict,
    xp_accumulator: dict,
) -> dict:
    """
    Resolve an opposed check using MUD mechanics and accumulate skill increases.

    Args:
        character_id: Character UUID for XP tracking
        aggressor_effective: Aggressor's effective score (skill + attribute)
        defender_effective: Defender's effective score (skill + attribute)
        skill_name: Name of skill to award increase to
        attribute_name: Name of attribute to award increase to
        character_skills: Character's current skills dict
        character_attributes: Character's current attributes dict
        xp_accumulator: Dict to accumulate skill increases (modified in place)

    Returns:
        Dict:
            - Success: bool
            - Sigma: float
    """
    # Resolve the check
    result = resolve_opposed_check(aggressor_effective, defender_effective)

    # Get current skill and attribute values
    current_skill = float(character_skills.get(skill_name, 0))
    current_attribute = float(character_attributes.get(attribute_name, 0))

    # Calculate skill increase
    skill_increase = calculate_skill_increase(aggressor_effective, defender_effective, current_skill, result["Success"])

    # Calculate attribute increase (uses attribute score for increment calculation)
    attr_increase = (
        calculate_skill_increase(aggressor_effective, defender_effective, current_attribute, result["Success"]) * ATTRIBUTE_XP_RATIO
    )

    # Accumulate skill increase
    if skill_name and skill_increase > 0:
        if "SkillXP" not in xp_accumulator:
            xp_accumulator["SkillXP"] = {}
        xp_accumulator["SkillXP"][skill_name] = xp_accumulator["SkillXP"].get(skill_name, 0) + skill_increase

    # Accumulate attribute increase
    if attribute_name and attr_increase > 0:
        if "AttributeXP" not in xp_accumulator:
            xp_accumulator["AttributeXP"] = {}
        xp_accumulator["AttributeXP"][attribute_name] = xp_accumulator["AttributeXP"].get(attribute_name, 0) + attr_increase

    return result
