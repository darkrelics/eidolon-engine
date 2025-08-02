"""
Segment processing utilities for Lambda functions.

Provides functions for processing story segments including mechanical,
decision, and rest segments.
"""

import math
import random
import time
from datetime import datetime, timedelta, timezone

from botocore.exceptions import ClientError
from uuid_extension import uuid7

from eidolon.character import heal_expired_wounds
from eidolon.dynamo import TableName, dynamo
from eidolon.logger import get_logger

logger = get_logger(__name__)

# Valid segment types for the incremental game
VALID_SEGMENT_TYPES = ["mechanical", "decision", "rest"]
MECHANICAL_ONLY_TYPES = ["mechanical"]

# Wound healing durations (matching MUD server)
BASHING_HEAL_TIME = timedelta(minutes=15)
LETHAL_HEAL_TIME = timedelta(hours=6)
AGGRAVATED_HEAL_TIME = timedelta(days=7)


def calculate_heal_time(damage_type: str) -> str:
    """
    Calculate when a wound will heal based on damage type.

    Args:
        damage_type: Type of damage (bashing, lethal, aggravated)

    Returns:
        ISO 8601 timestamp string for when the wound will heal
    """
    heal_times = {
        "bashing": BASHING_HEAL_TIME,
        "lethal": LETHAL_HEAL_TIME,
        "aggravated": AGGRAVATED_HEAL_TIME,
    }

    heal_delta = heal_times.get(damage_type.lower(), LETHAL_HEAL_TIME)
    heal_at = datetime.now(timezone.utc) + heal_delta
    return heal_at.isoformat()


def validate_segment_type(segment_type: str) -> bool:
    """
    Validate that a segment type is recognized.

    Args:
        segment_type: Type of segment to validate

    Returns:
        True if segment type is valid, False otherwise
    """
    return segment_type.lower() in VALID_SEGMENT_TYPES


def is_mechanical_segment(segment_type: str) -> bool:
    """
    Check if a segment type should be processed as mechanical.

    Mechanical segments include challenges and/or combat and are
    processed by the ops_process_segment Lambda via SQS.

    Args:
        segment_type: Type of segment to check

    Returns:
        True if segment should be processed as mechanical
    """
    return segment_type.lower() in MECHANICAL_ONLY_TYPES


def is_simple_segment(segment_type: str) -> bool:
    """
    Check if a segment type can be processed directly by the poller.

    Simple segments (rest and decision) don't require complex processing
    and can be handled directly without queuing.

    Args:
        segment_type: Type of segment to check

    Returns:
        True if segment can be processed directly
    """
    return segment_type.lower() in ["rest", "decision"]


def resolve_opposed_check(aggressor: float, defender: float) -> dict:
    """
    Resolve an opposed check using MUD mechanics.

    Args:
        aggressor: Aggressor's rating
        defender: Defender's rating

    Returns:
        Dictionary with success (bool) and sigma (float)
    """
    # Constants from MUD mechanics
    k_shift = 0.20  # How much rating difference matters
    k_var = 0.35  # Variance scaling
    min_sig = 0.25  # Minimum variance

    # Calculate difference
    diff = aggressor - defender

    # Calculate mean and variance
    mean = k_shift * diff
    variance = 1.0 + k_var * math.tanh(diff / 10.0)
    variance = max(variance, min_sig)

    # Generate outcome using normal distribution
    sigma = random.gauss(mean, variance)
    success = sigma >= 0

    return {"success": success, "sigma": sigma}


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
        # No challenges, default to normal outcome
        return "normal", []

    # Run each challenge using MUD-style mechanics
    challenge_results = []
    total_sigma = 0.0
    total_attempts = 0
    critical_failures = 0
    successes = 0

    for challenge in challenges:
        attribute = challenge.get("attribute")
        skill = challenge.get("skill")
        difficulty = challenge.get("difficulty", 8)
        attempts = challenge.get("attempts", 1)

        # Get character's attribute and skill values
        character_attributes = character.get("Attributes", {})
        character_skills = character.get("Skills", {})

        attribute_value = character_attributes.get(attribute, 0) if attribute else 0
        skill_value = character_skills.get(skill, 0) if skill else 0

        # Combined effective score
        effective_score = attribute_value + skill_value

        # Run multiple attempts for this challenge
        challenge_attempts = []
        best_sigma = -999

        for _ in range(attempts):
            # Simulate static check using normal distribution
            # Based on MUD mechanics: difference affects mean, with some randomness
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
    # Critical failures can lead to death
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


def process_combat_segment(active_segment: dict, segment_def: dict, character: dict) -> tuple:
    """
    Process a combat segment using MUD mechanics for opposed checks.

    Args:
        active_segment: Active segment data
        segment_def: Segment definition from Segments table
        character: Character data

    Returns:
        Tuple of (outcome, combat_state)
    """
    combat_config = segment_def.get("Combat", {})
    opponent_id = combat_config.get("OpponentID")
    max_rounds = combat_config.get("maxRounds", 10)

    # Get opponent data
    try:
        opponent = dynamo.get_item(TableName.OPPONENTS, {"OpponentID": opponent_id})

        if not opponent:
            logger.error("Opponent not found", extra={"opponent_id": opponent_id})
            raise ValueError(f"Opponent not found: {opponent_id}")
    except ClientError as err:
        logger.error(
            "Failed to get opponent data",
            extra={
                "opponent_id": opponent_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to get opponent data: {str(err)}")

    # Initialize combat state from active segment or create new
    combat_state = active_segment.get("CombatState", {})
    player_wounds = combat_state.get("playerWounds", [])
    opponent_wounds = combat_state.get("opponentWounds", [])
    current_round = combat_state.get("round", 0)

    # Get character combat stats
    character_attributes = character.get("Attributes", {})
    character_skills = character.get("Skills", {})
    character_combat = character_attributes.get("combat", 0) + character_skills.get("fighting", 0)
    character_defense = character_attributes.get("dexterity", 0) + character_skills.get("dodge", 0)

    # Get opponent combat stats
    opponent_attributes = opponent.get("Attributes", {})
    opponent_skills = opponent.get("Skills", {})
    opponent_combat = opponent_attributes.get("combat", 0) + opponent_skills.get("fighting", 0)
    opponent_defense = opponent_attributes.get("dexterity", 0) + opponent_skills.get("dodge", 0)
    opponent_health = opponent.get("Health", 5)

    # Track combat results
    combat_log = []

    # Continue combat from current round
    for round_num in range(current_round, min(current_round + 5, max_rounds)):
        round_results = {
            "round": round_num + 1,
            "playerAttack": None,
            "opponentAttack": None,
        }

        # Player attacks opponent using MUD mechanics
        attack_outcome = resolve_opposed_check(character_combat, opponent_defense)

        if attack_outcome["success"]:
            # Determine damage based on sigma
            sigma = attack_outcome["sigma"]
            if sigma > 2.0:
                damage = 3  # Critical hit
                damage_type = "critical"
            elif sigma > 1.0:
                damage = 2  # Solid hit
                damage_type = "solid"
            else:
                damage = 1  # Glancing blow
                damage_type = "glancing"

            # Apply damage as wounds to opponent
            for _ in range(damage):
                wound_type = "lethal" if damage_type == "critical" else "bashing"
                opponent_wounds.append(
                    {
                        "DamageType": wound_type,
                        "HealAt": calculate_heal_time(wound_type),
                        "round": round_num + 1,
                    }
                )

            round_results["playerAttack"] = {
                "hit": True,
                "sigma": round(sigma, 2),
                "damage": damage,
                "damageType": damage_type,
            }

            # Check if opponent is defeated
            lethal_wounds = sum(1 for w in opponent_wounds if w.get("DamageType") == "lethal")
            if lethal_wounds >= opponent_health or len(opponent_wounds) >= opponent_health * 2:
                combat_log.append(round_results)
                return "normal", {
                    "rounds": round_num + 1,
                    "playerWounds": player_wounds,
                    "opponentWounds": opponent_wounds,
                    "combatLog": combat_log,
                    "victor": "player",
                    "opponentDefeated": True,
                    "opponentId": opponent_id,
                }
        else:
            round_results["playerAttack"] = {
                "hit": False,
                "sigma": round(attack_outcome["sigma"], 2),
            }

        # Opponent attacks player using MUD mechanics
        defense_outcome = resolve_opposed_check(opponent_combat, character_defense)

        if defense_outcome["success"]:
            # Determine damage based on sigma
            sigma = defense_outcome["sigma"]
            if sigma > 2.0:
                damage = 3  # Critical hit
                damage_type = "critical"
            elif sigma > 1.0:
                damage = 2  # Solid hit
                damage_type = "solid"
            else:
                damage = 1  # Glancing blow
                damage_type = "glancing"

            # Apply damage as wounds to player
            for _ in range(damage):
                wound_type = "lethal" if damage_type == "critical" else "bashing"
                player_wounds.append(
                    {
                        "DamageType": wound_type,
                        "HealAt": calculate_heal_time(wound_type),
                        "round": round_num + 1,
                    }
                )

            round_results["opponentAttack"] = {
                "hit": True,
                "sigma": round(sigma, 2),
                "damage": damage,
                "damageType": damage_type,
            }

            # Check if player is defeated
            lethal_wounds = sum(1 for w in player_wounds if w.get("DamageType") == "lethal")
            total_wounds = len(player_wounds)

            if lethal_wounds >= 5:  # 5+ lethal wounds = death
                combat_log.append(round_results)
                return "death", {
                    "rounds": round_num + 1,
                    "playerWounds": player_wounds,
                    "opponentWounds": opponent_wounds,
                    "combatLog": combat_log,
                    "victor": "opponent",
                }
            elif total_wounds >= 10:  # 10+ total wounds = incapacitated
                combat_log.append(round_results)
                return "failure", {
                    "rounds": round_num + 1,
                    "playerWounds": player_wounds,
                    "opponentWounds": opponent_wounds,
                    "combatLog": combat_log,
                    "victor": "opponent",
                }
        else:
            round_results["opponentAttack"] = {
                "hit": False,
                "sigma": round(defense_outcome["sigma"], 2),
            }

        combat_log.append(round_results)

    # Max rounds reached - determine outcome based on wounds
    player_total_wounds = len(player_wounds)
    opponent_total_wounds = len(opponent_wounds)

    # Calculate final rounds (round_num might not be defined if no combat occurred)
    final_rounds = len(combat_log)

    if opponent_total_wounds > player_total_wounds * 2:
        # Player dealt significantly more damage
        outcome = "normal"
        victor = "player"
        opponent_defeated = True
    elif player_total_wounds > opponent_total_wounds * 2:
        # Opponent dealt significantly more damage
        outcome = "failure"
        victor = "opponent"
        opponent_defeated = False
    else:
        # Close fight - minor success
        outcome = "minimal"
        victor = "draw"
        opponent_defeated = opponent_total_wounds >= opponent_health

    return outcome, {
        "rounds": final_rounds,
        "playerWounds": player_wounds,
        "opponentWounds": opponent_wounds,
        "combatLog": combat_log,
        "victor": victor,
        "opponentDefeated": opponent_defeated,
        "opponentId": opponent_id,
    }


def process_decision_segment(active_segment: dict, segment_def: dict) -> str:
    """
    Process a decision segment by checking if decision was made.

    Args:
        active_segment: Active segment data
        segment_def: Segment definition from Segments table

    Returns:
        Outcome (always "normal" for decisions or "failure" if no decision)
    """
    decision = active_segment.get("Decision")

    if decision:
        return "normal"
    else:
        # No decision made before timeout - use default if available
        default_decision = segment_def.get("DefaultDecision")
        if default_decision:
            # Update active segment with default decision
            try:
                dynamo.update_item(
                    TableName.ACTIVE_SEGMENTS,
                    Key={"ActiveSegmentID": active_segment.get("ActiveSegmentID")},
                    UpdateExpression="SET #decision = :decision",
                    ExpressionAttributeNames={"#decision": "Decision"},
                    ExpressionAttributeValues={":decision": default_decision},
                )
                return "normal"
            except ClientError as err:
                logger.error(
                    "Failed to update decision",
                    extra={
                        "active_segment_id": active_segment.get("ActiveSegmentID"),
                        "error": str(err),
                        "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
                    },
                    exc_info=True,
                )
                raise RuntimeError(f"Failed to update decision: {str(err)}")
        else:
            return "failure"


def process_mechanical_segment(segment_def: dict, character: dict, active_segment: dict) -> tuple:
    """
    Process a mechanical segment containing skill challenges and/or combat.

    Mechanical segments contain skill challenges and/or combat encounters.
    They can contain skill challenges, combat encounters, or both.

    Args:
        segment_def: Segment definition from Segments table
        character: Character data
        active_segment: Active segment data

    Returns:
        Tuple of (outcome, results)
    """
    results = {}
    outcomes = []

    # Process skill challenges if present
    challenges = segment_def.get("Challenges", [])
    if challenges:
        logger.info(
            "Processing skill challenges",
            extra={
                "segment_id": segment_def.get("SegmentID"),
                "challenge_count": len(challenges),
            },
        )
        challenge_outcome, challenge_results = process_skill_challenges(segment_def, character)
        results["challengeResults"] = challenge_results
        outcomes.append(challenge_outcome)

        # Apply skill and attribute XP immediately
        from eidolon.character import apply_character_updates

        skill_xp = {}
        attribute_xp = {}

        for challenge in challenge_results:
            if challenge.get("passed"):
                skill = challenge.get("skill")
                attribute = challenge.get("attribute")

                if skill:
                    skill_xp[skill] = skill_xp.get(skill, 0) + 0.1
                if attribute:
                    attribute_xp[attribute] = attribute_xp.get(attribute, 0) + 0.05

        if skill_xp or attribute_xp:
            xp_updates = {}
            if skill_xp:
                xp_updates["SkillXP"] = skill_xp
            if attribute_xp:
                xp_updates["AttributeXP"] = attribute_xp

            try:
                character_id = character.get("CharacterID")
                if character_id:
                    apply_character_updates(character_id, xp_updates)
                logger.info(
                    "Applied skill and attribute XP immediately",
                    extra={
                        "character_id": character.get("CharacterID"),
                        "skills_updated": len(skill_xp),
                        "attributes_updated": len(attribute_xp),
                    },
                )
            except Exception as err:
                logger.error(
                    "Failed to apply XP updates",
                    extra={
                        "character_id": character.get("CharacterID"),
                        "error": str(err),
                    },
                    exc_info=True,
                )

    # Process combat if present
    combat_config = segment_def.get("Combat", {})
    if combat_config:
        logger.info(
            "Processing combat encounter",
            extra={
                "segment_id": segment_def.get("SegmentID"),
                "opponent_id": combat_config.get("OpponentID"),
            },
        )
        combat_outcome, combat_state = process_combat_segment(active_segment, segment_def, character)
        results["combatState"] = combat_state
        outcomes.append(combat_outcome)

        # Apply wounds immediately
        player_wounds = combat_state.get("playerWounds", [])
        if player_wounds:
            from eidolon.character import apply_character_updates

            wound_updates = {"Wounds": player_wounds}

            try:
                character_id = character.get("CharacterID")
                if character_id:
                    apply_character_updates(character_id, wound_updates)
                logger.info(
                    "Applied combat wounds immediately",
                    extra={
                        "character_id": character.get("CharacterID"),
                        "wounds_applied": len(player_wounds),
                    },
                )
            except Exception as err:
                logger.error(
                    "Failed to apply wounds",
                    extra={
                        "character_id": character.get("CharacterID"),
                        "error": str(err),
                    },
                    exc_info=True,
                )

    # Determine overall outcome
    if not outcomes:
        # No challenges or combat, default to normal
        logger.warning(
            "Mechanical segment has no challenges or combat",
            extra={"segment_id": segment_def.get("SegmentID")},
        )
        return "normal", results

    # If any outcome is death, overall is death
    if "death" in outcomes:
        return "death", results

    # If any outcome is failure, overall is failure
    if "failure" in outcomes:
        return "failure", results

    # Otherwise, take the worst non-failure outcome
    outcome_priority = ["minimal", "normal", "exceptional"]
    for outcome in outcome_priority:
        if outcome in outcomes:
            return outcome, results

    # Default to normal
    return "normal", results


def process_rest_segment(segment_def: dict, character: dict) -> tuple:
    """
    Process a rest segment.

    Rest segments are simply time delays that allow natural wound healing
    to occur via heal_expired_wounds() at the start of the next segment.

    Args:
        segment_def: Segment definition from Segments table
        character: Character data

    Returns:
        Tuple of (outcome, empty dict)
    """
    logger.info(
        "Rest segment completed",
        extra={"character_id": character.get("CharacterID")},
    )

    # Rest segments always have normal outcome
    # Healing happens automatically via heal_expired_wounds() at segment start
    return "normal", {}


def extract_character_updates_from_results(results: dict, segment_def: dict, outcome: str) -> dict:
    """
    Extract deferred rewards to be applied at segment completion.

    Note: XP and wounds are applied immediately during segment processing.
    This function only extracts rewards that should be deferred.

    Args:
        results: Results from segment processing
        segment_def: Segment definition containing outcome effects
        outcome: The calculated outcome (death/failure/minimal/normal/exceptional)

    Returns:
        Dict containing deferred rewards (combat rewards, story effects)
    """
    updates = {}

    # Extract combat rewards to be applied later
    if results.get("combatState", {}).get("opponentDefeated"):
        opponent_id = results["combatState"].get("opponentId")
        if opponent_id:
            # Get opponent data to store for later reward application
            try:
                opponent_data = dynamo.get_item(TableName.OPPONENTS, {"OpponentID": opponent_id})
                if opponent_data:
                    updates["CombatRewards"] = {
                        "opponentId": opponent_id,
                        "defeated": True,
                        "opponentData": opponent_data,  # Store full opponent data
                    }
            except Exception as err:
                logger.error(
                    "Failed to get opponent data for rewards",
                    extra={"opponent_id": opponent_id, "error": str(err)},
                    exc_info=True,
                )

    # Extract story outcome effects to be applied later
    if outcome in ["death", "failure", "minimal", "normal", "exceptional"]:
        outcome_results = segment_def.get("Results", {}).get(outcome, {})
        outcome_effects = outcome_results.get("effects", {})
        if outcome_effects:
            updates["StoryEffects"] = outcome_effects

    return updates


def generate_combat_client_events(combat_state: dict) -> list:
    """
    Generate client events from combat state for visualization.

    Args:
        combat_state: Combat state containing log and results

    Returns:
        List of client events for UI animation
    """
    events = []

    # Only generate structural combat data - narrative comes from Results
    for round_data in combat_state.get("combatLog", []):
        round_num = round_data.get("round", 0)

        # Player attack event
        player_attack = round_data.get("playerAttack")
        if player_attack:
            event = {"eventType": "combatAttack", "data": player_attack}
            event["data"]["round"] = round_num
            events.append(event)

        # Opponent attack event
        opponent_attack = round_data.get("opponentAttack")
        if opponent_attack:
            event = {"eventType": "combatDefense", "data": opponent_attack}
            event["data"]["round"] = round_num
            events.append(event)

    # Combat outcome is handled by narrative from Results
    return events


def generate_skill_check_events(challenge_results: list) -> list:
    """
    Generate client events from challenge results.

    Args:
        challenge_results: List of challenge results from skill checks

    Returns:
        List of client events for UI display
    """
    events = []

    for challenge in challenge_results:
        # Pass through challenge data - narrative comes from Results
        event = {"eventType": "skillCheck", "data": challenge}
        events.append(event)

    return events


def update_active_segment_outcome(active_segment_id: str, outcome: str, results: dict, segment_def=None) -> None:
    """
    Update active segment with outcome and mark as completed.

    Args:
        active_segment_id: Active segment UUID
        outcome: Outcome type
        results: Challenge or combat results
        segment_def: Optional segment definition containing Results narratives
    """
    update_expression = "SET #status = :status, #outcome = :outcome, ProcessingStatus = :proc_status"
    expression_names = {"#status": "Status", "#outcome": "Outcome"}
    expression_values = {":status": "completed", ":outcome": outcome, ":proc_status": "processed"}

    # Add results based on segment type
    if "challengeResults" in results:
        update_expression += ", ChallengeResults = :results"
        expression_values[":results"] = results["challengeResults"]
    if "combatState" in results:
        update_expression += ", CombatState = :state"
        expression_values[":state"] = results["combatState"]

    # Extract and add deferred rewards
    if segment_def:
        character_updates = extract_character_updates_from_results(results, segment_def, outcome)
        if character_updates:
            update_expression += ", CharacterUpdates = :updates"
            expression_values[":updates"] = character_updates  # type: ignore

    # Generate client events including narrative
    client_events = []

    # Add outcome narrative as the first event if available
    if segment_def and "Results" in segment_def:
        outcome_results = segment_def.get("Results", {}).get(outcome, {})
        if "narrative" in outcome_results:
            client_events.append(
                {
                    "eventType": "narrative",
                    "title": "Story Progress",
                    "description": outcome_results["narrative"],
                    "data": {"outcome": outcome},
                }
            )

    # Add skill check events if present
    if "challengeResults" in results:
        skill_events = generate_skill_check_events(results["challengeResults"])
        client_events.extend(skill_events)

    # Add combat events if present (only for combat segments)
    if "combatState" in results:
        combat_events = generate_combat_client_events(results["combatState"])
        client_events.extend(combat_events)

    if client_events:
        update_expression += ", ClientEvents = :events"
        expression_values[":events"] = client_events  # type: ignore

    try:
        dynamo.update_item(
            TableName.ACTIVE_SEGMENTS,
            Key={"ActiveSegmentID": active_segment_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values,
        )
    except ClientError as err:
        logger.error(
            "Failed to update segment outcome",
            extra={
                "active_segment_id": active_segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to update segment outcome: {str(err)}")


def get_next_segment_and_create(
    character_id: str,
    story_id: str,
    current_segment: dict,
    active_segment: dict,
    outcome: str,
) -> object:
    """
    Determine next segment and create active segment for it.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        current_segment: Current segment definition
        active_segment: Current active segment
        outcome: Outcome of current segment

    Returns:
        Next active segment ID or None

    Raises:
        RuntimeError: If database operations fail
    """
    segment_type = current_segment.get("SegmentType")
    next_segment_id = None

    if segment_type == "decision":
        # Get next segment based on decision
        decision = active_segment.get("Decision")
        decision_options = current_segment.get("DecisionOptions", {})
        next_segment_id = decision_options.get(decision)

    elif segment_type == "mechanical":
        # Check if outcome is terminal
        if outcome not in ["death", "failure"]:
            next_segment_id = current_segment.get("NextSegmentID")

    if not next_segment_id:
        return None

    # Get next segment definition
    try:
        next_segment = dynamo.get_item(TableName.SEGMENTS, {"StoryID": story_id, "SegmentID": next_segment_id})

        if not next_segment:
            logger.error("Next segment not found", extra={"segment_id": next_segment_id})
            return None
    except ClientError as err:
        logger.error(
            "Failed to get next segment",
            extra={
                "segment_id": next_segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to get next segment: {str(err)}")

    # Create active segment for next segment
    return create_next_active_segment(
        character_id,
        active_segment.get("PlayerID"),  # type: ignore
        story_id,
        next_segment,
        active_segment.get("StoryTitle"),  # type: ignore
    )


def create_next_active_segment(character_id: str, player_id: str, story_id: str, segment: dict, story_title: str) -> str:
    """
    Create an active segment record for the next segment.

    Args:
        character_id: Character UUID
        player_id: Player UUID
        story_id: Story UUID
        segment: Segment data from Segments table
        story_title: Story title for display

    Returns:
        Active segment ID
    """
    # Heal any expired wounds before creating new segment
    try:
        heal_result = heal_expired_wounds(character_id)
        if heal_result.get("healed_count", 0) > 0:
            logger.info(
                "Healed wounds before creating next segment",
                extra={"character_id": character_id, "healed_count": heal_result["healed_count"]},
            )
    except Exception as err:
        logger.warning("Failed to heal wounds before segment creation", extra={"character_id": character_id, "error": str(err)})
        # Non-critical - continue with segment creation

    segment_id = segment.get("SegmentID")
    segment_type = segment.get("SegmentType", "mechanical")
    duration = int(segment.get("SegmentDuration", 300))  # Default 5 minutes

    current_time = int(time.time())
    end_time = current_time + duration

    # Generate UUIDv7 for time-based ordering
    active_segment_id = str(uuid7())

    active_segment = {
        "ActiveSegmentID": active_segment_id,
        "CharacterID": character_id,
        "PlayerID": player_id,
        "StoryID": story_id,
        "StoryTitle": story_title,
        "SegmentID": segment_id,
        "SegmentType": segment_type,
        "StartTime": current_time,
        "EndTime": end_time,
        "Status": "active",
    }

    # Add type-specific fields
    if segment_type == "decision":
        active_segment["Decision"] = None
        active_segment["DecisionOptions"] = segment.get("DecisionOptions", {})
    elif segment_type == "mechanical":
        # Mechanical segments can have challenges and/or combat
        active_segment["ChallengeResults"] = []
        active_segment["Outcome"] = None

        # If combat is configured, set up combat state
        combat_config = segment.get("Combat", {})
        if combat_config:
            active_segment["CombatState"] = {
                "round": 0,
                "playerWounds": [],
                "opponentHealth": None,
                "opponentId": combat_config.get("OpponentID"),
            }

    # Store in DynamoDB
    try:
        dynamo.put_item(TableName.ACTIVE_SEGMENTS, active_segment)
    except ClientError as err:
        logger.error(
            "Failed to create active segment",
            extra={
                "active_segment_id": active_segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to create active segment: {str(err)}")

    return active_segment_id


def complete_story(character_id: str, story_id: str, outcome: str) -> None:
    """
    Complete the story, apply rewards, and update character state.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        outcome: Final outcome
    """
    from eidolon.story import (
        apply_story_rewards,
        calculate_story_rewards,
        complete_story_for_character,
        get_story_history,
        get_story_metadata,
    )

    # Complete the story and clean up character state
    complete_story_for_character(character_id, story_id, outcome)

    # Get story metadata for reward calculation
    try:
        story_metadata = get_story_metadata(story_id)
        history = get_story_history(character_id, story_id)

        # Count completed segments from history
        segments_completed = len(history.get("SegmentHistory", []))

        # Calculate and apply rewards
        rewards = calculate_story_rewards(story_metadata, outcome, segments_completed)
        if rewards.get("xp", 0) > 0 or rewards.get("items") or rewards.get("currency", 0) > 0:
            apply_story_rewards(character_id, rewards)

    except Exception as err:
        logger.error(
            "Failed to apply story rewards",
            extra={
                "character_id": character_id,
                "story_id": story_id,
                "outcome": outcome,
                "error": str(err),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to update history completion: {str(err)}")


def process_segment_completely(
    active_segment_id: str,
    character_id: str,
    story_id: str,
    segment_id: str,
    segment_type: str,
) -> dict:
    """
    Process a completed segment including all database operations.

    This is the main orchestration function that handles segment processing.

    Args:
        active_segment_id: Active segment UUID
        character_id: Character UUID
        story_id: Story UUID
        segment_id: Segment UUID
        segment_type: Type of segment

    Returns:
        Dict with outcome and next segment ID

    Raises:
        ValueError: If required data not found
        RuntimeError: If database operations fail
    """
    # Get active segment
    try:
        active_segment = dynamo.get_item(TableName.ACTIVE_SEGMENTS, {"ActiveSegmentID": active_segment_id})

        if not active_segment:
            logger.error(
                "Active segment not found",
                extra={"active_segment_id": active_segment_id},
            )
            raise ValueError("Active segment not found")
    except ClientError as err:
        logger.error(
            "Failed to get active segment",
            extra={
                "active_segment_id": active_segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to get active segment: {str(err)}")

    # Get segment definition
    try:
        segment_def = dynamo.get_item(TableName.SEGMENTS, {"StoryID": story_id, "SegmentID": segment_id})

        if not segment_def:
            logger.error("Segment definition not found", extra={"segment_id": segment_id})
            raise ValueError("Segment not found")
    except ClientError as err:
        logger.error(
            "Failed to get segment definition",
            extra={"segment_id": segment_id, "error": str(err), "error_code": err.response.get("Error", {}).get("Code", "Unknown")},
            exc_info=True,
        )
        raise RuntimeError(f"Failed to get segment definition: {str(err)}")

    # Get character data
    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})

        if not character:
            logger.error("Character not found", extra={"character_id": character_id})
            raise ValueError("Character not found")
    except ClientError as err:
        logger.error(
            "Failed to get character",
            extra={
                "character_id": character_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to get character: {str(err)}")

    # Process segment based on type
    outcome = None
    results = {}

    if segment_type == "mechanical":
        # Mechanical segment type that combines challenges and combat
        outcome, results = process_mechanical_segment(segment_def, character, active_segment)

    elif segment_type == "rest":
        # Rest segment for healing
        outcome, healing_data = process_rest_segment(segment_def, character)
        results.update(healing_data)

    elif segment_type == "decision":
        # Decision segment
        outcome = process_decision_segment(active_segment, segment_def)

    else:
        logger.error("Unknown segment type", extra={"segment_type": segment_type})
        outcome = "failure"

    # Note: Combat rewards and story outcome effects are deferred until segment completion
    # They will be applied by ops_advance_story when the segment timer expires

    # Update active segment with outcome
    update_active_segment_outcome(active_segment_id, outcome, results, segment_def)

    # Add segment to story history
    from eidolon.story import add_segment_to_history

    try:
        add_segment_to_history(character_id, story_id, segment_id, outcome)
    except Exception as err:
        logger.error(
            "Failed to add segment to history",
            extra={
                "character_id": character_id,
                "story_id": story_id,
                "segment_id": segment_id,
                "error": str(err),
            },
            exc_info=True,
        )

    # Determine next segment or complete story
    next_active_segment_id = get_next_segment_and_create(character_id, story_id, segment_def, active_segment, outcome)

    if not next_active_segment_id:
        # No next segment - story is complete
        complete_story(character_id, story_id, outcome)
        logger.info(
            "Story completed",
            extra={
                "character_id": character_id,
                "story_id": story_id,
                "outcome": outcome,
            },
        )
    else:
        logger.info(
            "Created next segment",
            extra={"next_active_segment_id": next_active_segment_id},
        )

    return {
        "outcome": outcome,
        "nextSegment": next_active_segment_id,
    }


def get_completed_segments(max_segments: int) -> list:
    """
    Query for active segments that have reached their end time or will complete soon.

    Args:
        max_segments: Maximum number of segments to return

    Returns:
        List of segments ready for processing

    Raises:
        RuntimeError: If database query fails
    """
    current_time = int(time.time())
    # Look ahead 30 seconds to catch segments that will complete before next poll
    lookahead_time = current_time + 30

    try:
        # Query using the CompletionTimeIndex GSI
        items = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="CompletionTimeIndex",
            KeyConditionExpression="#status = :status AND EndTime <= :lookahead_time",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={":status": "active", ":lookahead_time": lookahead_time},
            ScanIndexForward=True,  # Sort by EndTime ascending (oldest first)
            Limit=max_segments,
        )
        return items  # type: ignore
    except ClientError as err:
        logger.error(
            "Failed to query completed segments",
            extra={"error": str(err), "error_code": err.response.get("Error", {}).get("Code", "Unknown")},
            exc_info=True,
        )
        raise RuntimeError(f"Failed to query completed segments: {str(err)}")


def check_active_segments_exist() -> bool:
    """
    Check if any active segments exist in the table.

    Returns:
        True if active segments exist, False otherwise

    Raises:
        RuntimeError: If database scan fails
    """
    try:
        # Perform minimal scan to check if any active segments exist
        result = dynamo.scan(
            TableName.ACTIVE_SEGMENTS,
            FilterExpression="#status = :status",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={":status": "active"},
            Limit=1,
        )
        return result is not None and len(result.get("items", [])) > 0
    except ClientError as err:
        logger.error(
            "Failed to scan active segments",
            extra={"error": str(err), "error_code": err.response.get("Error", {}).get("Code", "Unknown")},
            exc_info=True,
        )
        raise RuntimeError(f"Failed to scan active segments: {str(err)}")


def delete_active_segment(active_segment_id: str) -> None:
    """
    Delete an active segment from the database.

    Args:
        active_segment_id: Active segment UUID to delete

    Raises:
        ValueError: If active_segment_id is empty
        RuntimeError: If database operation fails (non-critical)
    """
    if not active_segment_id:
        raise ValueError("Active segment ID cannot be empty")

    try:
        dynamo.delete_item(TableName.ACTIVE_SEGMENTS, {"ActiveSegmentID": active_segment_id})
        logger.info("Deleted active segment", extra={"active_segment_id": active_segment_id})
    except ClientError as err:
        # Log but don't raise - deletion failure is non-critical
        logger.warning(
            "Failed to delete active segment",
            extra={
                "active_segment_id": active_segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
        )


def record_abandoned_segment_history(character_id: str, story_id: str, active_segment: dict) -> None:
    """
    Record abandoned segment in history table.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        active_segment: Active segment data

    Raises:
        RuntimeError: If database operation fails
    """
    try:
        history_entry = {
            "CharacterID": character_id,
            "ActiveSegmentID": active_segment.get("ActiveSegmentID"),
            "PlayerID": active_segment.get("PlayerID"),
            "StoryID": story_id,
            "StoryTitle": active_segment.get("StoryTitle"),
            "SegmentID": active_segment.get("SegmentID"),
            "SegmentType": active_segment.get("SegmentType"),
            "StartTime": active_segment.get("StartTime"),
            "EndTime": active_segment.get("EndTime"),
            "ProcessedAt": active_segment.get("ProcessedAt"),
            "CompletedAt": datetime.now(timezone.utc).isoformat(),
            "Outcome": "abandoned",
            "ClientEvents": active_segment.get("ClientEvents", []),
            "CharacterUpdates": {},
            "SkillXPAwarded": {},
            "AttributeXPAwarded": {},
        }

        dynamo.put_item(TableName.SEGMENT_HISTORY, history_entry)

        logger.info(
            "Recorded abandoned segment in history",
            extra={"character_id": character_id, "segment_id": active_segment.get("SegmentID")},
        )
    except ClientError as err:
        logger.error("Failed to record segment history", extra={"character_id": character_id, "error": str(err)}, exc_info=True)
        raise RuntimeError(f"Failed to record segment history: {str(err)}")


def update_character_active_segment(character_id: str, active_segment_id: str) -> None:
    """
    Update character's ActiveSegmentID field.

    Args:
        character_id: Character UUID
        active_segment_id: Active segment UUID to set

    Raises:
        ValueError: If character_id or active_segment_id is empty
        RuntimeError: If database update fails
    """
    if not character_id:
        raise ValueError("Character ID cannot be empty")
    if not active_segment_id:
        raise ValueError("Active segment ID cannot be empty")

    try:
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET ActiveSegmentID = :segment_id",
            ExpressionAttributeValues={":segment_id": active_segment_id},
        )
        logger.info(
            "Updated character active segment", extra={"character_id": character_id, "active_segment_id": active_segment_id}
        )
    except ClientError as err:
        logger.error(
            "Failed to update character active segment",
            extra={
                "character_id": character_id,
                "active_segment_id": active_segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to update character active segment: {str(err)}")


def insert_rest_segment(story_id: str, current_segment_id: str, rest_duration: int = 900, time_remaining: int = 0) -> str:
    """
    Insert a rest segment into the story flow after the current segment.

    This function:
    1. Checks if current segment has at least 30 seconds remaining
    2. If not, attempts to insert after the next segment(s)
    3. Creates a rest segment that points to the appropriate NextSegmentID
    4. Updates the appropriate segment to point to the rest segment

    Args:
        story_id: Story UUID
        current_segment_id: Current segment UUID
        rest_duration: Duration of rest segment in seconds (default 15 minutes)
        time_remaining: Time remaining in current segment (seconds)

    Returns:
        Rest segment ID

    Raises:
        ValueError: If no suitable segment found or segments not found
        RuntimeError: If database operations fail
    """
    MIN_TIME_REQUIRED = 30  # Minimum seconds needed to insert rest

    # Get current segment (A)
    try:
        current_segment = dynamo.get_item(TableName.SEGMENTS, {"StoryID": story_id, "SegmentID": current_segment_id})
        if not current_segment:
            raise ValueError(f"Current segment not found: {current_segment_id}")
    except ClientError as err:
        logger.error(
            "Failed to get current segment",
            extra={
                "segment_id": current_segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to get current segment: {str(err)}")

    # Check if current segment (A) has a next segment (B)
    next_segment_id = current_segment.get("NextSegmentID")
    if not next_segment_id:
        # A is the last segment - early return
        logger.warning(
            "Cannot insert rest - current segment is the last in story",
            extra={"story_id": story_id, "current_segment_id": current_segment_id},
        )
        raise ValueError("Cannot insert rest segment - current segment is the last in the story")

    # Determine where to insert rest
    if time_remaining >= MIN_TIME_REQUIRED:
        # Enough time on A - insert between A and B
        segment_to_update_id = current_segment_id
        original_next_segment_id = next_segment_id

        logger.info(
            "Inserting rest after current segment",
            extra={
                "current_segment_id": current_segment_id,
                "time_remaining": time_remaining,
                "rest_will_point_to": original_next_segment_id,
            },
        )
    else:
        # Not enough time on A - check if we can insert between B and C
        try:
            next_segment = dynamo.get_item(TableName.SEGMENTS, {"StoryID": story_id, "SegmentID": next_segment_id})
            if not next_segment:
                raise ValueError(f"Next segment not found: {next_segment_id}")
        except ClientError as err:
            logger.error(
                "Failed to get next segment",
                extra={
                    "segment_id": next_segment_id,
                    "error": str(err),
                    "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
                },
                exc_info=True,
            )
            raise RuntimeError(f"Failed to get next segment: {str(err)}")

        # Check if B has a next segment (C)
        segment_c_id = next_segment.get("NextSegmentID")
        if not segment_c_id:
            # B is the last segment - early return
            logger.warning(
                "Cannot insert rest - insufficient time on current and next is last segment",
                extra={
                    "story_id": story_id,
                    "current_segment_id": current_segment_id,
                    "next_segment_id": next_segment_id,
                    "time_remaining": time_remaining,
                },
            )
            raise ValueError("Cannot insert rest segment - insufficient time and next segment is the last in the story")

        # Insert between B and C
        segment_to_update_id = next_segment_id
        original_next_segment_id = segment_c_id

        logger.info(
            "Inserting rest after next segment due to insufficient time",
            extra={
                "current_segment_id": current_segment_id,
                "time_remaining": time_remaining,
                "inserting_after": next_segment_id,
                "rest_will_point_to": original_next_segment_id,
            },
        )

    # Generate unique ID for rest segment
    rest_segment_id = str(uuid7())

    # Create rest segment definition
    rest_segment = {
        "StoryID": story_id,
        "SegmentID": rest_segment_id,
        "SegmentType": "rest",
        "ShortStatus": "Resting to heal wounds",
        "DefaultStatus": "Resting to heal wounds",
        "SegmentDuration": rest_duration,
        "NextSegmentID": original_next_segment_id,
    }

    try:
        # Create the rest segment
        dynamo.put_item(TableName.SEGMENTS, rest_segment)

        logger.info(
            "Created rest segment",
            extra={"rest_segment_id": rest_segment_id, "story_id": story_id, "next_segment_id": original_next_segment_id},
        )

        # Update the appropriate segment to point to rest segment
        dynamo.update_item(
            TableName.SEGMENTS,
            Key={"StoryID": story_id, "SegmentID": segment_to_update_id},
            UpdateExpression="SET NextSegmentID = :rest_segment_id",
            ExpressionAttributeValues={":rest_segment_id": rest_segment_id},
        )

        logger.info(
            "Updated segment to point to rest",
            extra={"updated_segment_id": segment_to_update_id, "new_next_segment_id": rest_segment_id},
        )

        return rest_segment_id

    except ClientError as err:
        logger.error(
            "Failed to insert rest segment",
            extra={
                "rest_segment_id": rest_segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        # Attempt rollback
        try:
            dynamo.delete_item(TableName.SEGMENTS, {"StoryID": story_id, "SegmentID": rest_segment_id})
            logger.info("Rolled back rest segment creation")
        except Exception:
            logger.warning("Failed to rollback rest segment")

        raise RuntimeError(f"Failed to insert rest segment: {str(err)}")


def get_active_segment_info(active_segment_id: str) -> dict:
    """
    Get active segment information.

    Args:
        active_segment_id: Active segment UUID

    Returns:
        Active segment data

    Raises:
        ValueError: If active segment not found
        RuntimeError: If database operation fails
    """
    if not active_segment_id:
        raise ValueError("Active segment ID cannot be empty")

    try:
        active_segment = dynamo.get_item(TableName.ACTIVE_SEGMENTS, {"ActiveSegmentID": active_segment_id})
        if not active_segment:
            raise ValueError(f"Active segment not found: {active_segment_id}")

        return active_segment

    except ClientError as err:
        logger.error(
            "Failed to get active segment",
            extra={
                "active_segment_id": active_segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to get active segment: {str(err)}")


def claim_segment_for_processing(active_segment_id: str) -> bool:
    """
    Claim a segment for processing by setting RunningFlag.

    Uses conditional update to ensure only one Lambda processes the segment.
    This prevents race conditions when multiple processors attempt to handle
    the same segment.

    Args:
        active_segment_id: Active segment UUID

    Returns:
        True if segment was claimed, False if already being processed

    Raises:
        RuntimeError: If database operation fails
    """
    try:
        dynamo.update_item(
            TableName.ACTIVE_SEGMENTS,
            Key={"ActiveSegmentID": active_segment_id},
            UpdateExpression="SET RunningFlag = :true, ProcessingStatus = :processing",
            ConditionExpression="attribute_not_exists(RunningFlag) OR RunningFlag = :false",
            ExpressionAttributeValues={
                ":true": True,
                ":false": False,
                ":processing": "processing",
            },
        )
        logger.info(
            "Successfully claimed segment for processing",
            extra={"active_segment_id": active_segment_id},
        )
        return True
    except ClientError as err:
        if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.info(
                "Segment already being processed",
                extra={"active_segment_id": active_segment_id},
            )
            return False
        logger.error(
            "Failed to claim segment",
            extra={
                "active_segment_id": active_segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to claim segment: {str(err)}")


def record_segment_history(character_id: str, story_id: str, active_segment_id: str, segment_data: dict) -> None:
    """
    Record segment completion in history table with all required fields.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        active_segment_id: Active segment UUID
        segment_data: Complete active segment data including all fields

    Raises:
        RuntimeError: If database operation fails
    """
    # Extract XP awards from CharacterUpdates
    character_updates = segment_data.get("CharacterUpdates", {})
    skill_xp_awarded = character_updates.get("SkillXP", {})
    attribute_xp_awarded = character_updates.get("AttributeXP", {})

    # Build complete history entry with all required fields
    history_entry = {
        "CharacterID": character_id,
        "ActiveSegmentID": active_segment_id,
        "PlayerID": segment_data.get("PlayerID"),  # Required for ownership verification
        "StoryID": story_id,
        "StoryTitle": segment_data.get("StoryTitle"),
        "SegmentID": segment_data.get("SegmentID"),
        "SegmentType": segment_data.get("SegmentType"),
        "StartTime": segment_data.get("StartTime"),  # Unix timestamp from active segment
        "EndTime": segment_data.get("EndTime"),  # Unix timestamp from active segment
        "ProcessedAt": segment_data.get("ProcessedAt"),  # When outcomes were calculated
        "CompletedAt": datetime.now(timezone.utc).isoformat(),  # When segment was advanced
        "Outcome": segment_data.get("Outcome"),
        "ClientEvents": segment_data.get("ClientEvents", []),
        "CharacterUpdates": character_updates,  # Complete updates applied
        "SkillXPAwarded": skill_xp_awarded,  # Extracted skill XP
        "AttributeXPAwarded": attribute_xp_awarded,  # Extracted attribute XP
    }

    # Add type-specific data
    if segment_data.get("ChallengeResults"):
        history_entry["ChallengeResults"] = segment_data["ChallengeResults"]
    if segment_data.get("CombatState"):
        history_entry["CombatState"] = segment_data["CombatState"]
    if segment_data.get("Decision"):
        history_entry["Decision"] = segment_data["Decision"]
    if segment_data.get("DecisionMadeAt"):
        history_entry["DecisionMadeAt"] = segment_data["DecisionMadeAt"]

    try:
        # Create segment history record
        dynamo.put_item(TableName.SEGMENT_HISTORY, history_entry)

        logger.info(
            "Segment history recorded",
            extra={
                "character_id": character_id,
                "story_id": story_id,
                "segment_id": segment_data.get("SegmentID"),
                "active_segment_id": active_segment_id,
                "skill_xp_count": len(skill_xp_awarded),
                "attribute_xp_count": len(attribute_xp_awarded),
                "outcome": segment_data.get("Outcome"),
            },
        )
    except ClientError as err:
        logger.error(
            "Failed to record segment history",
            extra={
                "character_id": character_id,
                "story_id": story_id,
                "active_segment_id": active_segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to record segment history: {str(err)}")


def get_active_segment(active_segment_id: str) -> dict:
    """
    Get active segment by ID.

    Args:
        active_segment_id: Active segment UUID

    Returns:
        Active segment data

    Raises:
        ValueError: If segment not found
        RuntimeError: If database operation fails
    """
    try:
        active_segment = dynamo.get_item(
            TableName.ACTIVE_SEGMENTS,
            {"ActiveSegmentID": active_segment_id},
        )
        if not active_segment:
            raise ValueError(f"Active segment not found: {active_segment_id}")
        return active_segment
    except ClientError as err:
        logger.error(
            "Failed to get active segment",
            extra={
                "active_segment_id": active_segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to get active segment: {str(err)}")


def get_segment_definition(story_id: str, segment_id: str) -> dict:
    """
    Get segment definition from Segments table.

    Args:
        story_id: Story UUID
        segment_id: Segment ID

    Returns:
        Segment definition

    Raises:
        ValueError: If segment not found
        RuntimeError: If database operation fails
    """
    try:
        segment_def = dynamo.get_item(
            TableName.SEGMENTS,
            {"StoryID": story_id, "SegmentID": segment_id},
        )
        if not segment_def:
            raise ValueError(f"Segment definition not found: {segment_id}")
        return segment_def
    except ClientError as err:
        logger.error(
            "Failed to get segment definition",
            extra={
                "story_id": story_id,
                "segment_id": segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to get segment definition: {str(err)}")


def determine_next_segment(segment_def: dict, active_segment: dict, outcome: str) -> object:
    """
    Determine the next segment ID based on segment type and outcome.

    Args:
        segment_def: Segment definition from Segments table
        active_segment: Active segment record
        outcome: Segment outcome

    Returns:
        Next segment ID or None if story ends
    """
    segment_type = segment_def.get("SegmentType")

    if segment_type == "decision":
        # Use decision to determine next segment
        decision = active_segment.get("Decision")
        if decision:
            decision_options = segment_def.get("DecisionOptions", {})
            return decision_options.get(decision)
    elif segment_type in ["mechanical", "rest"]:
        # Check if outcome is terminal
        if outcome in ["death", "failure"]:
            # Some outcomes end the story
            results = segment_def.get("Results", {})
            outcome_result = results.get(outcome, {})
            if outcome_result.get("terminal", False):
                return None
        # Otherwise continue to next segment
        return segment_def.get("NextSegmentID")

    return segment_def.get("NextSegmentID")


def update_segment_processing_status(active_segment_id: str, outcome: str, character_updates: dict) -> None:
    """
    Update active segment with processing results.

    Args:
        active_segment_id: Active segment UUID
        outcome: Processing outcome
        character_updates: Character updates to apply

    Raises:
        RuntimeError: If database operation fails
    """
    try:
        dynamo.update_item(
            TableName.ACTIVE_SEGMENTS,
            Key={"ActiveSegmentID": active_segment_id},
            UpdateExpression="SET ProcessingStatus = :status, #outcome = :outcome, CharacterUpdates = :updates",
            ExpressionAttributeNames={"#outcome": "Outcome"},
            ExpressionAttributeValues={
                ":status": "processed",
                ":outcome": outcome,
                ":updates": character_updates,
            },
        )
        logger.info(
            "Updated segment processing status",
            extra={
                "active_segment_id": active_segment_id,
                "outcome": outcome,
                "has_updates": bool(character_updates),
            },
        )
    except ClientError as err:
        logger.error(
            "Failed to update segment processing status",
            extra={
                "active_segment_id": active_segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to update segment results: {str(err)}")


def reset_segment_processing_status(active_segment_id: str) -> None:
    """
    Reset a segment's processing status back to pending.

    Used to retry stuck segments that have been processing too long.

    Args:
        active_segment_id: Active segment UUID

    Raises:
        RuntimeError: If database operation fails
    """
    try:
        dynamo.update_item(
            TableName.ACTIVE_SEGMENTS,
            Key={"ActiveSegmentID": active_segment_id},
            UpdateExpression="SET ProcessingStatus = :status",
            ExpressionAttributeValues={":status": "pending"},
        )
        logger.info("Reset segment processing status to pending", extra={"active_segment_id": active_segment_id})
    except ClientError as err:
        logger.error(
            "Failed to reset segment processing status",
            extra={
                "active_segment_id": active_segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to reset segment processing status: {str(err)}")


def mark_segment_as_completed_exceptional(active_segment_id: str) -> None:
    """
    Mark an exhausted segment as completed with exceptional outcome.

    Used when a segment has passed its end time without being processed,
    giving the player the best possible outcome to protect them from system failures.

    Args:
        active_segment_id: Active segment UUID

    Raises:
        RuntimeError: If database operation fails
    """
    try:
        dynamo.update_item(
            TableName.ACTIVE_SEGMENTS,
            Key={"ActiveSegmentID": active_segment_id},
            UpdateExpression="SET ProcessingStatus = :status, #outcome = :outcome",
            ExpressionAttributeNames={"#outcome": "Outcome"},
            ExpressionAttributeValues={":status": "completed", ":outcome": "exceptional"},
        )
        logger.info(
            "Marked exhausted segment as completed with exceptional outcome", extra={"active_segment_id": active_segment_id}
        )
    except ClientError as err:
        logger.error(
            "Failed to mark segment as completed exceptional",
            extra={
                "active_segment_id": active_segment_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to mark segment as completed exceptional: {str(err)}")
