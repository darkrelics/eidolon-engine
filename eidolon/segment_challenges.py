"""
Skill challenge processing for mechanical segments.

Provides functions for processing skill challenges and determining outcomes.
"""

from eidolon.constants import SIGMA_CRITICAL_FAILURE, SIGMA_DEATH_AVG, SIGMA_FAILURE, SIGMA_MINIMAL, SIGMA_NORMAL
from eidolon.mechanics import resolve_opposed_check


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
        attribute = challenge.get("Attribute")
        skill = challenge.get("Skill")
        difficulty = challenge.get("Difficulty") or 8
        attempts = int(challenge.get("Attempts") or 1)

        # Get character's attribute and skill values
        character_attributes = character.get("Attributes", {})
        character_skills = character.get("Skills", {})

        # Try multiple casings for attribute/skill names for compatibility
        if attribute:
            # Enforce exact key usage per style guide (no case-tolerant reads)
            attribute_value = character_attributes.get(attribute, 0)
        else:
            attribute_value = 0

        if skill:
            # Enforce exact key usage per style guide (no case-tolerant reads)
            skill_value = character_skills.get(skill, 0)
        else:
            skill_value = 0

        # Combined effective score
        effective_score = attribute_value + skill_value

        # Run multiple attempts for this challenge. Each attempt is the signed
        # margin between the character's effective score and the difficulty,
        # via the shared opposed-check model (mechanics.resolve_opposed_check).
        challenge_attempts = []
        best_sigma = -999
        challenge_sigma_sum = 0.0

        for _ in range(attempts):
            result = resolve_opposed_check(effective_score, difficulty)
            sigma = result["Sigma"]
            success = result["Success"]

            challenge_attempts.append(
                {
                    "EffectiveScore": effective_score,
                    "Difficulty": difficulty,
                    "Sigma": round(sigma, 2),
                    "Success": success,
                }
            )

            if sigma > best_sigma:
                best_sigma = sigma

            # Track critical failures (any sigma <= SIGMA_CRITICAL_FAILURE causes death per design doc)
            if sigma <= SIGMA_CRITICAL_FAILURE:
                critical_failures += 1

            total_attempts += 1
            total_sigma += sigma
            challenge_sigma_sum += sigma

        # "Passed" reflects the challenge's AVERAGE performance - the same basis
        # as the segment outcome below - so the displayed success/failure can no
        # longer contradict the outcome tier (a multi-attempt challenge no longer
        # reads "succeeded" while the segment resolves to "failure").
        challenge_avg_sigma = challenge_sigma_sum / len(challenge_attempts) if challenge_attempts else 0.0
        passed = challenge_avg_sigma >= 0
        if passed:
            successes += 1

        challenge_results.append(
            {
                "Attribute": attribute,
                "Skill": skill,
                "Difficulty": difficulty,
                "Attempts": challenge_attempts,
                "BestSigma": round(best_sigma, 2),
                "AverageSigma": round(challenge_avg_sigma, 2),
                "Passed": passed,
            }
        )

    # Determine overall outcome based on average sigma
    if total_attempts == 0:
        return "failure", []

    avg_sigma = total_sigma / total_attempts

    # Map sigma values to story outcomes (per design doc incremental-design.md)
    if critical_failures >= 1 or avg_sigma < SIGMA_DEATH_AVG:
        outcome = "death"
    elif avg_sigma < SIGMA_FAILURE:
        outcome = "failure"
    elif avg_sigma < SIGMA_MINIMAL:
        outcome = "minimal"
    elif avg_sigma < SIGMA_NORMAL:
        outcome = "normal"
    else:
        outcome = "exceptional"

    return outcome, challenge_results
