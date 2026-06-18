"""
Game mechanics calculations.

Provides pure functions for game mechanics: skill checks, XP calculations, opposed rolls.
This module has no dependencies on character_data to avoid circular imports.
"""

import math
import random

from eidolon.constants import (
    ATTRIBUTE_XP_RATIO,
    BASE_XP,
    FAILURE_XP_PENALTY,
    MAX_SKILL_LEVEL,
    OPPOSED_MIN_SIGMA,
    OPPOSED_SHIFT,
    OPPOSED_VARIANCE,
)


def resolve_opposed_check(challenger: float, target: float) -> dict:
    """
    Resolve an opposed check as the signed margin between two normal distributions.

    The challenger and the target are each modelled as a normal distribution
    centred on their effective score (attribute + skill). The result is the
    signed *margin* between them, drawn directly from the difference of those
    two distributions; the challenger succeeds when the margin is non-negative.

    - ``mean`` shifts the margin in favour of the higher score, scaled by
      ``OPPOSED_SHIFT`` (a one-point score gap moves the mean by 0.2 of the
      spread).
    - ``std_dev`` is the standard deviation (spread) of the margin: ~1.0,
      widening slightly with the score gap via ``tanh`` and floored at
      ``OPPOSED_MIN_SIGMA``. Note ``random.gauss(mu, sigma)`` takes a standard
      deviation, not a variance.

    The returned ``Sigma`` is that signed margin in standard-deviation units;
    callers grade its magnitude into outcome tiers (see ``segment_challenges``).

    Args:
        challenger: Challenger's effective score (attribute + skill).
        target: Target's effective score, or a static difficulty.

    Returns:
        Dict:
            - Success: bool (margin >= 0)
            - Sigma: float (signed margin)
    """
    score_gap: float = challenger - target

    mean: float = OPPOSED_SHIFT * score_gap
    std_dev: float = 1.0 + OPPOSED_VARIANCE * math.tanh(score_gap / 10.0)
    std_dev = max(std_dev, OPPOSED_MIN_SIGMA)

    margin: float = random.gauss(mean, std_dev)

    return {"Success": margin >= 0, "Sigma": margin}


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
