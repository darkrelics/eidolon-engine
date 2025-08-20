"""
Skill challenge processing for mechanical segments.

Provides functions for processing skill challenges and determining outcomes.
"""

import math
import random


def process_skill_challenges(segment_def: dict, character: dict) -> tuple:
    """
    Process skill challenges within a mechanical segment and determine outcome.

    Args:
        segment_def: Segment definition from Segments table
        character: Character data

    Returns:
        Tuple of (outcome, challenge_results)
    """
    challenges = segment_def.get("Challenges", [])
    if not challenges:
        return "normal", []

    challenge_results = []
    total_sigma = 0.0
    total_attempts = 0
    critical_failures = 0
    successes = 0

    for challenge in challenges:
        # Accept both lowercase and PascalCase keys for compatibility
        attribute = challenge.get("attribute") or challenge.get("Attribute")
        skill = challenge.get("skill") or challenge.get("Skill")
        difficulty = challenge.get("difficulty") or challenge.get("Difficulty") or 8
        attempts = int(challenge.get("attempts") or challenge.get("Attempts") or 1)

        # Get character's attribute and skill values
        character_attributes = character.get("Attributes", {})
        character_skills = character.get("Skills", {})

        # Try multiple casings for attribute/skill names for compatibility
        if attribute:
            attribute_value = (
                character_attributes.get(attribute, 0)
                or character_attributes.get(attribute.capitalize(), 0)
                or character_attributes.get(attribute.upper(), 0)
                or 0
            )
        else:
            attribute_value = 0

        if skill:
            skill_value = (
                character_skills.get(skill, 0)
                or character_skills.get(skill.capitalize(), 0)
                or character_skills.get(skill.upper(), 0)
                or 0
            )
        else:
            skill_value = 0

        # Combined effective score
        effective_score = attribute_value + skill_value

        # Run multiple attempts for this challenge
        challenge_attempts = []
        best_sigma = -999

        for _ in range(attempts):
            # Simulate static check using normal distribution
            diff = effective_score - difficulty

            # Constants from MUD mechanics
            k_shift = 0.20  # How much rating difference matters
            k_var = 0.35  # Variance scaling
            min_sig = 0.25  # Minimum variance

            # Calculate mean and variance
            mean = k_shift * diff
            variance = 1.0 + k_var * math.tanh(diff / 10.0)
            variance = max(variance, min_sig)

            # Generate outcome using normal distribution
            sigma = random.gauss(mean, variance)
            success = sigma >= 0

            challenge_attempts.append(
                {
                    "effectiveScore": effective_score,
                    "difficulty": difficulty,
                    "sigma": round(sigma, 2),
                    "success": success,
                }
            )

            if sigma > best_sigma:
                best_sigma = sigma

            # Track critical failures
            if sigma < -2.0:
                critical_failures += 1

            total_attempts += 1
            total_sigma += sigma

        # Determine if challenge was passed (best attempt succeeded)
        passed = best_sigma >= 0
        if passed:
            successes += 1

        challenge_results.append(
            {
                "attribute": attribute,
                "skill": skill,
                "difficulty": difficulty,
                "attempts": challenge_attempts,
                "bestSigma": round(best_sigma, 2),
                "passed": passed,
            }
        )

    # Determine overall outcome based on average sigma
    if total_attempts == 0:
        return "failure", []

    avg_sigma = total_sigma / total_attempts

    # Map sigma values to story outcomes
    if critical_failures >= 2 or avg_sigma < -2.0:
        outcome = "death"
    elif avg_sigma < -1.0:
        outcome = "failure"
    elif avg_sigma < 0:
        outcome = "minimal"
    elif avg_sigma < 1.0:
        outcome = "normal"
    else:
        outcome = "exceptional"

    return outcome, challenge_results