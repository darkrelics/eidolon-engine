"""
Segment processing utilities for Lambda functions.

Provides functions for processing story segments including mechanical,
decision, and rest segments.
"""

# pylint: disable=too-many-lines

import math
import random
import time
from datetime import datetime, timezone

from botocore.exceptions import ClientError
from uuid_extension import uuid7

from eidolon.character_data import apply_character_updates
from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger
from eidolon.mechanics import calculate_heal_time, resolve_opposed_check
from eidolon.models import ChallengeResultModel, ClientEvent, CombatStateModel, StorySegment
from eidolon.schema import normalize_segment_definition
from eidolon.time_utils import now_iso, future_iso, seconds_until, now_unix

# Valid segment types for the incremental game
VALID_SEGMENT_TYPES: list = ["mechanical", "decision", "rest"]
MECHANICAL_ONLY_TYPES: list = ["mechanical"]


def _to_pascal_key(key: str) -> str:
    """Convert lowerCamelCase/snake-case to PascalCase; preserve OpponentID/ID."""
    if not isinstance(key, str):
        return key
    kl = key.replace("-", "_").lower()
    if kl in ("opponentid", "opponent_id"):
        return "OpponentID"
    if kl == "id":
        return "ID"
    parts = [p for p in key.replace("-", "_").split("_") if p]
    return "".join(p[:1].upper() + p[1:] for p in parts)


def _challenge_results_to_pascal(ch_results: list) -> list:
    """Convert challenge results to PascalCase, preferring Pydantic when available."""
    out: list = []
    for ch in ch_results or []:
        if not isinstance(ch, dict):
            continue
        try:
            model = ChallengeResultModel.model_validate(ch)
            out.append(model.model_dump(by_alias=True, exclude_none=True))
            continue
        except Exception:
            # Fall back to manual conversion if validation fails
            pass

        item = {
            "Attribute": ch.get("Attribute", ch.get("attribute")),
            "Skill": ch.get("Skill", ch.get("skill")),
            "Difficulty": ch.get("Difficulty", ch.get("difficulty")),
            "BestSigma": ch.get("BestSigma", ch.get("bestSigma")),
            "Passed": ch.get("Passed", ch.get("passed")),
        }
        attempts = []
        for at in ch.get("Attempts", ch.get("attempts", [])):
            attempts.append(
                {
                    "EffectiveScore": at.get("EffectiveScore", at.get("effectiveScore")),
                    "Difficulty": at.get("Difficulty", at.get("difficulty")),
                    "Sigma": at.get("Sigma", at.get("sigma")),
                    "Success": at.get("Success", at.get("success")),
                }
            )
        item["Attempts"] = attempts
        out.append(item)
    return out


def _combat_state_to_pascal(state: dict) -> dict:
    """Convert combat state to PascalCase, preferring Pydantic when available."""
    if not isinstance(state, dict):
        return {}
    try:
        model = CombatStateModel.model_validate(state)
        return model.model_dump(by_alias=True, exclude_none=True)
    except Exception:
        # Fall through to manual conversion
        pass
    pas = {
        "Round": state.get("Round", state.get("round", state.get("rounds", 0))),
        "PlayerWounds": state.get("PlayerWounds", state.get("playerWounds", [])),
        "OpponentWounds": state.get("OpponentWounds", state.get("opponentWounds", [])),
        "OpponentHealth": state.get("OpponentHealth", state.get("opponentHealth")),
        "OpponentID": state.get("OpponentID", state.get("opponentId")),
    }
    log = state.get("CombatLog") or state.get("combatLog") or []
    pc_log = []
    for entry in log:
        if not isinstance(entry, dict):
            continue
        pe = {"Round": entry.get("Round", entry.get("round"))}
        pa = entry.get("PlayerAttack") or entry.get("playerAttack")
        if isinstance(pa, dict):
            pe["PlayerAttack"] = {
                "Hit": pa.get("Hit", pa.get("hit")),
                "Sigma": pa.get("Sigma", pa.get("sigma")),
                "Damage": pa.get("Damage", pa.get("damage")),
                "DamageType": pa.get("DamageType", pa.get("damageType")),
            }
        oa = entry.get("OpponentAttack") or entry.get("opponentAttack")
        if isinstance(oa, dict):
            pe["OpponentAttack"] = {
                "Hit": oa.get("Hit", oa.get("hit")),
                "Sigma": oa.get("Sigma", oa.get("sigma")),
                "Damage": oa.get("Damage", oa.get("damage")),
                "DamageType": oa.get("DamageType", oa.get("damageType")),
            }
        pc_log.append(pe)
    if pc_log:
        pas["CombatLog"] = pc_log
    return pas


def _events_to_pascal(events: list) -> list:
    """Convert client events to PascalCase, preferring Pydantic when available."""
    out = []
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        try:
            model = ClientEvent.model_validate(ev)
            out.append(model.model_dump(by_alias=True, exclude_none=True))
            continue
        except Exception:
            # Fall back to manual conversion
            pass
        pe = {
            "EventType": ev.get("EventType", ev.get("eventType")),
            "Title": ev.get("Title", ev.get("title")),
            "Description": ev.get("Description", ev.get("description")),
        }
        data = ev.get("Data", ev.get("data", {}))
        if isinstance(data, dict):
            pdata = {}
            for k, v in data.items():
                pdata[_to_pascal_key(k)] = v
            pe["Data"] = pdata
        out.append(pe)
    return out


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
    challenge_results: list = []
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
            # Try exact match, then capitalized, then uppercase
            attribute_value = (
                character_attributes.get(attribute, 0)
                or character_attributes.get(attribute.capitalize(), 0)
                or character_attributes.get(attribute.upper(), 0)
                or 0
            )
        else:
            attribute_value = 0

        if skill:
            # Try exact match, then capitalized, then uppercase
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
        challenge_attempts: list = []
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
            variance: float = 1.0 + k_var * math.tanh(diff / 10.0)
            variance = max(variance, min_sig)

            # Generate outcome using normal distribution
            sigma: float = random.gauss(mean, variance)
            success: bool = sigma >= 0

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
        passed: bool = best_sigma >= 0
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

    avg_sigma: float = total_sigma / total_attempts

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
    # Accept both PascalCase and camelCase for compatibility
    opponent_id = combat_config.get("OpponentID") or combat_config.get("opponentId")
    max_rounds = combat_config.get("MaxRounds") or combat_config.get("maxRounds") or 10

    # Get opponent data
    try:
        opponent = dynamo.get_item(TableName.OPPONENTS, {"OpponentID": opponent_id})

        if not opponent:
            logger.error(f"Opponent not found for {opponent_id}")
            raise ValueError(f"Opponent not found: {opponent_id}")
    except ClientError as err:
        logger.error(f"Failed to get opponent data for {opponent_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get opponent data: {err}") from err

    # Initialize combat state from active segment or create new
    combat_state = active_segment.get("CombatState", {})
    # Tolerate both PascalCase and camelCase
    player_wounds = combat_state.get("PlayerWounds", combat_state.get("playerWounds", []))
    opponent_wounds = combat_state.get("OpponentWounds", combat_state.get("opponentWounds", []))
    current_round = combat_state.get("Round", combat_state.get("round", 0))

    # Get character combat stats
    character_attributes = character.get("Attributes", {})
    character_skills = character.get("Skills", {})
    character_combat = character_attributes.get("Strength", 0) + character_skills.get("Melee", 0)
    character_defense = character_attributes.get("Agility", 0) + character_skills.get("Dodge", 0)

    # Get opponent combat stats
    opponent_attributes = opponent.get("Attributes", {})
    opponent_skills = opponent.get("Skills", {})
    opponent_combat = opponent_attributes.get("Strength", 0) + opponent_skills.get("Melee", 0)
    opponent_defense = opponent_attributes.get("Agility", 0) + opponent_skills.get("Dodge", 0)
    opponent_health = opponent.get("Health", 5)

    # Track combat results
    combat_log: list = []

    # Continue combat from current round
    for round_num in range(current_round, min(current_round + 5, max_rounds)):
        round_results: dict = {
            "round": round_num + 1,
            "playerAttack": None,
            "opponentAttack": None,
        }

        # Player attacks opponent using MUD mechanics
        attack_outcome: dict = resolve_opposed_check(character_combat, opponent_defense)

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
            lethal_wounds: int = sum(1 for w in opponent_wounds if w.get("DamageType") == "lethal")
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
        defense_outcome: dict = resolve_opposed_check(opponent_combat, character_defense)

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
            total_wounds: int = len(player_wounds)

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
    player_total_wounds: int = len(player_wounds)
    opponent_total_wounds: int = len(opponent_wounds)

    # Calculate final rounds (round_num might not be defined if no combat occurred)
    final_rounds: int = len(combat_log)

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
                logger.error(f"Failed to update decision for {active_segment.get('ActiveSegmentID')} Error: {err}", exc_info=True)
                raise RuntimeError(f"Failed to update decision: {err}") from err
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
    results: dict = {}
    outcomes: list = []

    # Process skill challenges if present
    challenges = segment_def.get("Challenges", [])
    if challenges:
        logger.info(f"Processing skill challenges for {segment_def.get('SegmentID')}")
        challenge_outcome, challenge_results = process_skill_challenges(segment_def, character)
        results["challengeResults"] = challenge_results
        outcomes.append(challenge_outcome)

        # Apply skill and attribute XP immediately

        skill_xp: dict = {}
        attribute_xp: dict = {}

        # Constants from experience.md
        base_xp = 0.25  # Base experience per action
        failure_penalty = 0.5  # Failed actions give 50% XP
        attribute_xp_ratio = 0.1  # Attributes gain 10% of skill XP

        for challenge in challenge_results:
            skill = challenge.get("skill")
            attribute = challenge.get("attribute")
            passed = challenge.get("passed", False)

            # Get the best attempt to calculate variance modifier
            best_attempt: dict = {}
            for attempt in challenge.get("attempts", []):
                if attempt.get("sigma") > best_attempt.get("sigma", -10):
                    best_attempt = attempt

            if best_attempt and (skill or attribute):
                effective_score = best_attempt.get("effectiveScore", 0)
                difficulty = best_attempt.get("difficulty", 0)

                # Calculate variance modifier based on experience.md formula
                # ratio = min(E_att, E_def) / max(E_att, E_def)
                # xp_modifier = ratio^2
                if effective_score > 0 and difficulty > 0:
                    ratio = min(effective_score, difficulty) / max(effective_score, difficulty)
                    variance_modifier = ratio**2
                else:
                    variance_modifier = 1.0  # Default if can't calculate

                # Calculate base XP with variance modifier
                xp_amount = base_xp * variance_modifier

                # Apply failure penalty if challenge wasn't passed
                if not passed:
                    xp_amount *= failure_penalty

                # Award XP to skill (full amount)
                if skill:
                    skill_xp[skill] = skill_xp.get(skill, 0) + xp_amount

                # Award XP to attribute (10% of skill XP)
                if attribute:
                    attr_xp_amount = xp_amount * attribute_xp_ratio
                    attribute_xp[attribute] = attribute_xp.get(attribute, 0) + attr_xp_amount

        if skill_xp or attribute_xp:
            xp_updates = {}
            if skill_xp:
                xp_updates["SkillXP"] = skill_xp
            if attribute_xp:
                xp_updates["AttributeXP"] = attribute_xp

            # Apply XP immediately to database
            try:
                character_id = character.get("CharacterID")
                if character_id:

                    apply_character_updates(character_id, xp_updates)
                logger.info(f"Applied skill and attribute XP to database for {character.get('CharacterID')}")
            except Exception as err:
                logger.error(f"Failed to apply XP updates for {character.get('CharacterID')} Error: {err}", exc_info=True)

            # Also store XP in results for CharacterUpdates (for client display)
            results["xpUpdates"] = xp_updates

    # Process combat if present
    combat_config = segment_def.get("Combat", {})
    if combat_config:
        logger.info(f"Processing combat encounter for {segment_def.get('SegmentID')}")
        combat_outcome, combat_state = process_combat_segment(active_segment, segment_def, character)
        results["combatState"] = combat_state
        outcomes.append(combat_outcome)

        # Apply wounds immediately to database
        player_wounds = combat_state.get("playerWounds", [])
        if player_wounds:

            wound_updates = {"Wounds": player_wounds}

            try:
                character_id = character.get("CharacterID")
                if character_id:
                    apply_character_updates(character_id, wound_updates)
                logger.info(f"Applied combat wounds to database for {character.get('CharacterID')}")
            except Exception as err:
                logger.error(f"Failed to apply wounds for {character.get('CharacterID')} Error: {err}", exc_info=True)

            # Also store wounds in results for CharacterUpdates (for client display)
            results["woundUpdates"] = wound_updates

    # Determine overall outcome
    if not outcomes:
        # No challenges or combat, default to normal
        logger.warning(f"Mechanical segment has no challenges or combat for {segment_def.get('SegmentID')}")
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


def process_rest_segment(_: dict, character: dict) -> tuple:
    """
    Process a rest segment.

    Rest segments are simply time delays that allow natural wound healing
    to occur.

    Args:
        segment_def: Segment definition from Segments table
        character: Character data

    Returns:
        Tuple of (outcome, empty dict)
    """
    logger.info(f"Rest segment completed for {character.get('CharacterID')}")

    # Rest segments always have normal outcome
    return "normal", {}


def extract_character_updates_from_results(results: dict, segment_def: dict, outcome: str) -> dict:
    """
    Extract all character updates for storage in ActiveSegments.

    Note: XP and wounds are applied immediately to the database during segment processing.
    This function extracts ALL updates (including already-applied XP/wounds) for:
    1. Client to display progressively over segment duration
    2. Segment history recording
    3. Story advancement tracking

    Args:
        results: Results from segment processing (including xpUpdates and woundUpdates)
        segment_def: Segment definition containing outcome effects
        outcome: The calculated outcome (death/failure/minimal/normal/exceptional)

    Returns:
        Dict containing all character updates (XP, wounds, combat rewards, story effects)
    """
    updates = {}

    # Include XP updates (already applied to DB, needed for client display)
    xp_updates = results.get("xpUpdates")
    if xp_updates:
        updates.update(xp_updates)

    # Include wound updates (already applied to DB, needed for client display)
    wound_updates = results.get("woundUpdates")
    if wound_updates:
        updates.update(wound_updates)

    # Extract combat rewards to be applied later
    combat_state = results.get("combatState", {})
    if combat_state.get("opponentDefeated"):
        opponent_id = combat_state.get("opponentId")
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
                logger.error(f"Failed to get opponent data for rewards for {opponent_id} Error: {err}", exc_info=True)

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
    for round_data in combat_state.get("combatLog", combat_state.get("CombatLog", [])):
        round_num = round_data.get("round", round_data.get("Round", 0))

        # Player attack event
        player_attack = round_data.get("playerAttack", round_data.get("PlayerAttack"))
        if player_attack:
            event = {"eventType": "combatAttack", "data": player_attack}
            event["data"]["round"] = round_num
            events.append(event)

        # Opponent attack event
        opponent_attack = round_data.get("opponentAttack", round_data.get("OpponentAttack"))
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
    Update active segment with outcome but keep status as active until timer expires.

    Args:
        active_segment_id: Active segment UUID
        outcome: Outcome type
        results: Challenge or combat results
        segment_def: Optional segment definition containing Results narratives
    """
    # Ensure outcome is populated to support pre-completion outcome reads
    if not outcome:
        logger.warning(f"No outcome computed for {active_segment_id}; defaulting to 'normal'")
        outcome = "normal"

    # Keep status as "active" but mark as processed so poller knows it's ready
    update_expression = "SET #outcome = :outcome, ProcessingStatus = :proc_status"
    expression_names = {"#outcome": "Outcome"}
    expression_values = {":outcome": outcome, ":proc_status": "processed"}

    # Add results based on segment type
    challenge_results = results.get("challengeResults")
    if challenge_results:
        update_expression += ", ChallengeResults = :results"
        # Use simple converter for stability; Pydantic models available in eidolon.models
        expression_values[":results"] = _challenge_results_to_pascal(challenge_results)  # type: ignore
    
    combat_state = results.get("combatState")
    if combat_state:
        update_expression += ", CombatState = :state"
        expression_values[":state"] = _combat_state_to_pascal(combat_state)  # type: ignore

    # Extract and add deferred rewards
    if segment_def:
        character_updates = extract_character_updates_from_results(results, segment_def, outcome)
        if character_updates:
            update_expression += ", CharacterUpdates = :updates"
            expression_values[":updates"] = character_updates  # type: ignore

    # Generate client events including narrative
    client_events = []

    # Add outcome narrative as the first event if available using the validator
    if segment_def:
        try:
            # Use the validator to get narrative and effects with proper casing
            outcome_data = validate_segment_outcome_results(segment_def, outcome)
            narrative = outcome_data.get("Narrative", "")

            if narrative:  # Add narrative event if non-empty
                client_events.append(
                    {
                        "eventType": "narrative",
                        "title": "Story Progress",
                        "description": narrative,
                        "data": {"outcome": outcome},
                    }
                )
        except Exception as err:
            logger.warning(f"Failed to get narrative for outcome {outcome}: {err}")

    # Add skill check events if present
    challenge_results_for_events = results.get("challengeResults")
    if challenge_results_for_events:
        skill_events = generate_skill_check_events(challenge_results_for_events)
        client_events.extend(skill_events)

    # Add combat events if present (only for combat segments)
    combat_state_for_events = results.get("combatState")
    if combat_state_for_events:
        combat_events = generate_combat_client_events(combat_state_for_events)
        client_events.extend(combat_events)

    if client_events:
        update_expression += ", ClientEvents = :events"
        expression_values[":events"] = _events_to_pascal(client_events)  # type: ignore

    try:
        dynamo.update_item(
            TableName.ACTIVE_SEGMENTS,
            Key={"ActiveSegmentID": active_segment_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values,
        )
    except ClientError as err:
        logger.error(f"Failed to update segment outcome for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to update segment outcome: {err}") from err


# Backward-compatible shorter aliases per style guidance
def update_segment_outcome(active_segment_id: str, outcome: str, results: dict, segment_def=None) -> None:
    return update_active_segment_outcome(active_segment_id, outcome, results, segment_def)


def process_mech_segment(segment_def: dict, character: dict, active_segment: dict) -> tuple:
    return process_mechanical_segment(segment_def, character, active_segment)


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

    segment_id = segment.get("SegmentID")
    segment_type = segment.get("SegmentType", "mechanical")
    duration = int(segment.get("SegmentDuration", 300))  # Default 5 minutes

    # Use ISO 8601 timestamps
    start_time = now_iso()
    end_time = future_iso(duration)

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
        "StartTime": start_time,
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
            # Accept both PascalCase and camelCase for compatibility
            opponent_id = combat_config.get("OpponentID") or combat_config.get("opponentId")
            opponent_health = None
            if opponent_id:
                try:
                    opponent = dynamo.get_item(TableName.OPPONENTS, {"OpponentID": opponent_id})
                    if opponent:
                        opponent_health = opponent.get("Health")
                except Exception as err:
                    logger.warning(f"Failed to load opponent for combat state init for {opponent_id} Error: {err}")
            active_segment["CombatState"] = {
                "Round": 0,
                "PlayerWounds": [],
                "OpponentWounds": [],
                "OpponentHealth": opponent_health,
                "OpponentID": opponent_id,
            }

    # Store in DynamoDB
    try:
        dynamo.put_item(TableName.ACTIVE_SEGMENTS, active_segment)
    except ClientError as err:
        logger.error(f"Failed to create active segment for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to create active segment: {err}") from err

    return active_segment_id


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
            logger.error(f"Active segment not found for {active_segment_id}")
            raise ValueError("Active segment not found")
    except ClientError as err:
        logger.error(f"Failed to get active segment for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get active segment: {err}") from err

    # Get segment definition
    try:
        segment_def = dynamo.get_item(TableName.SEGMENTS, {"StoryID": story_id, "SegmentID": segment_id})

        if not segment_def:
            logger.error(f"Segment definition not found for {segment_id}")
            raise ValueError("Segment not found")
    except ClientError as err:
        logger.error(f"Failed to get segment definition for {segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get segment definition: {err}") from err

    # Get character data
    try:
        character = dynamo.get_item(TableName.CHARACTERS, {"CharacterID": character_id})

        if not character:
            logger.error(f"Character not found for {character_id}")
            raise ValueError("Character not found")
    except ClientError as err:
        logger.error(f"Failed to get character for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get character: {err}") from err

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
        logger.error(f"Unknown segment type for {segment_type}")
        outcome = "failure"

    # Note: Combat rewards and story outcome effects are deferred until segment completion
    # They will be applied by ops_advance_story when the segment timer expires

    # Update active segment with outcome
    update_active_segment_outcome(active_segment_id, outcome, results, segment_def)

    logger.info(f"Segment processed, waiting for timer to expire before advancement for {active_segment_id}")

    return {
        "outcome": outcome,
        "nextSegment": None,
        "processed": True,
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
    # Look ahead 30 seconds to catch segments that will complete before next poll
    lookahead_time = future_iso(30)

    try:
        # Query using the EndTimeIndex GSI
        items = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="EndTimeIndex",
            KeyConditionExpression="#status = :status AND EndTime <= :lookahead_time",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={":status": "active", ":lookahead_time": lookahead_time},
            ScanIndexForward=True,  # Sort by EndTime ascending (oldest first)
            Limit=max_segments,
        )
        return items  # type: ignore
    except ClientError as err:
        logger.error(f"Failed to query completed segments Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to query completed segments: {err}") from err


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
        logger.error(f"Failed to scan active segments Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to scan active segments: {err}") from err


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
        dynamo.delete_item(TableName.ACTIVE_SEGMENTS, Key={"ActiveSegmentID": active_segment_id})
        logger.info(f"Deleted active segment for {active_segment_id}")
    except ClientError as err:
        # Log but don't raise - deletion failure is non-critical
        logger.warning(f"Failed to delete active segment for {active_segment_id} Error: {err}")


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
            "CompletedAt": now_unix(),
            "Outcome": "abandoned",
            "ClientEvents": active_segment.get("ClientEvents", []),
            "CharacterUpdates": {},
            "SkillXPAwarded": {},
            "AttributeXPAwarded": {},
        }

        dynamo.put_item(TableName.SEGMENT_HISTORY, history_entry)

        logger.info(f"Recorded abandoned segment in history for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to record segment history for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to record segment history: {err}") from err


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
    min_time_required: int = 30  # Minimum seconds needed to insert rest

    # Get current segment (A)
    try:
        current_segment = dynamo.get_item(TableName.SEGMENTS, {"StoryID": story_id, "SegmentID": current_segment_id})
        if not current_segment:
            raise ValueError(f"Current segment not found: {current_segment_id}")
    except ClientError as err:
        logger.error(f"Failed to get current segment for {current_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get current segment: {err}") from err

    # Check if current segment (A) has a next segment (B)
    next_segment_id = current_segment.get("NextSegmentID")
    if not next_segment_id:
        # A is the last segment - early return
        logger.warning(f"Cannot insert rest - current segment is the last in story for {story_id}")
        raise ValueError("Cannot insert rest segment - current segment is the last in the story")

    # Determine where to insert rest
    if time_remaining >= min_time_required:
        # Enough time on A - insert between A and B
        segment_to_update_id = current_segment_id
        original_next_segment_id = next_segment_id

        logger.info(f"Inserting rest after current segment for {current_segment_id}")
    else:
        # Not enough time on A - check if we can insert between B and C
        try:
            next_segment = dynamo.get_item(TableName.SEGMENTS, {"StoryID": story_id, "SegmentID": next_segment_id})
            if not next_segment:
                raise ValueError(f"Next segment not found: {next_segment_id}")
        except ClientError as err:
            logger.error(f"Failed to get next segment for {next_segment_id} Error: {err}", exc_info=True)
            raise RuntimeError(f"Failed to get next segment: {err}") from err

        # Check if B has a next segment (C)
        segment_c_id = next_segment.get("NextSegmentID")
        if not segment_c_id:
            # B is the last segment - early return
            logger.warning(f"Cannot insert rest - insufficient time on current and next is last segment for {story_id}")
            raise ValueError("Cannot insert rest segment - insufficient time and next segment is the last in the story")

        # Insert between B and C
        segment_to_update_id = next_segment_id
        original_next_segment_id = segment_c_id

        logger.info(f"Inserting rest after next segment due to insufficient time for {current_segment_id}")

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

        logger.info(f"Created rest segment for {rest_segment_id}")

        # Update the appropriate segment to point to rest segment
        dynamo.update_item(
            TableName.SEGMENTS,
            Key={"StoryID": story_id, "SegmentID": segment_to_update_id},
            UpdateExpression="SET NextSegmentID = :rest_segment_id",
            ExpressionAttributeValues={":rest_segment_id": rest_segment_id},
        )

        logger.info(f"Updated segment to point to rest for {segment_to_update_id}")

        return rest_segment_id

    except ClientError as err:
        logger.error(f"Failed to insert rest segment for {rest_segment_id} Error: {err}", exc_info=True)
        # Attempt rollback
        try:
            dynamo.delete_item(TableName.SEGMENTS, Key={"StoryID": story_id, "SegmentID": rest_segment_id})
            logger.info("Rolled back rest segment creation")
        except Exception:
            logger.warning("Failed to rollback rest segment")

        raise RuntimeError(f"Failed to insert rest segment: {err}") from err


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
        logger.error(f"Failed to get active segment for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get active segment: {err}") from err


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
        logger.info(f"Successfully claimed segment for processing for {active_segment_id}")
        return True
    except ClientError as err:
        if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.info(f"Segment already being processed for {active_segment_id}")
            return False
        logger.error(f"Failed to claim segment for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to claim segment: {err}") from err


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
        "CompletedAt": now_unix(),  # When segment was advanced
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

        logger.info(f"Segment history recorded for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to record segment history for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to record segment history: {err}") from err


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
        logger.error(f"Failed to get active segment for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get active segment: {err}") from err


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
        # Normalize mixed-case inputs from content or tools
        normalized = normalize_segment_definition(segment_def)
        # Validate and return canonical PascalCase dict (tolerant fallback)
        try:
            _model = StorySegment.model_validate(normalized)
            return _model.model_dump(by_alias=True, exclude_none=True)
        except Exception:
            # Fall back to normalized dict when validation fails (tolerant)
            return normalized
    except ClientError as err:
        logger.error(f"Failed to get segment definition for {segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get segment definition: {err}") from err


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
    segment_id = segment_def.get("SegmentID", "unknown")
    active_segment_id = active_segment.get("ActiveSegmentID", "unknown")

    if segment_type == "decision":
        # Use decision to determine next segment
        decision = active_segment.get("Decision")
        decision_options = segment_def.get("DecisionOptions", {})

        if decision and decision in decision_options:
            next_segment_id = decision_options.get(decision)
            logger.info(f"Selected decision branch for {active_segment_id}: decision={decision}, next={next_segment_id}")
            return next_segment_id
        else:
            # No decision made (timeout) - use default if specified
            default_decision = segment_def.get("DefaultDecision")
            if default_decision and default_decision in decision_options:
                next_segment_id = decision_options.get(default_decision)
                logger.info(f"Using default decision for {active_segment_id}: default={default_decision}, next={next_segment_id}")
                return next_segment_id
            # Fall back to NextSegmentID if no default specified
            fallback = segment_def.get("NextSegmentID")
            if not decision:
                logger.warning(f"No decision made for {active_segment_id}, no default available, using fallback: {fallback}")
            return fallback

    elif segment_type in ["mechanical", "rest"]:
        # Normalize outcome to lowercase for consistent lookup
        outcome_key = str(outcome).lower() if outcome else "normal"

        # Get results dict (should have lowercase keys after normalization)
        results = segment_def.get("Results", {})
        if not isinstance(results, dict):
            logger.warning(f"Results is not a dict for {segment_id}, treating as no branching")
            results = {}

        # Check for per-outcome NextSegmentID
        outcome_result = results.get(outcome_key)
        if outcome_result:
            if isinstance(outcome_result, dict) and "NextSegmentID" in outcome_result:
                # Explicitly provided per-outcome next segment (None means terminal)
                next_segment_id = outcome_result.get("NextSegmentID")
                logger.info(f"Using per-outcome branch for {active_segment_id}: outcome={outcome_key}, next={next_segment_id}")
                return next_segment_id

        # Fall back to segment-level NextSegmentID
        fallback = segment_def.get("NextSegmentID")

        # Log warning if no next segment for non-terminal outcomes
        if fallback is None and outcome_key not in ["death", "failure"]:
            logger.warning(f"No next segment found for {active_segment_id} with outcome '{outcome_key}' - story will terminate")
        elif fallback is not None:
            logger.info(f"Using segment-level NextSegmentID for {active_segment_id}: outcome={outcome_key}, next={fallback}")

        return fallback

    # Unknown segment type - use segment-level NextSegmentID
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
    # Ensure outcome is populated to support pre-completion outcome reads
    if not outcome:
        logger.warning(f"No outcome computed for {active_segment_id}; defaulting to 'normal'")
        outcome = "normal"

    try:
        dynamo.update_item(
            TableName.ACTIVE_SEGMENTS,
            Key={"ActiveSegmentID": active_segment_id},
            UpdateExpression="SET ProcessingStatus = :status, #outcome = :outcome, CharacterUpdates = :updates, RunningFlag = :false",
            ExpressionAttributeNames={"#outcome": "Outcome"},
            ExpressionAttributeValues={
                ":status": "processed",
                ":outcome": outcome,
                ":updates": character_updates,
                ":false": False,
            },
        )
        logger.info(f"Updated segment processing status for {active_segment_id}")
    except ClientError as err:
        logger.error(f"Failed to update segment processing status for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to update segment results: {err}") from err


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
            UpdateExpression="SET ProcessingStatus = :status, RunningFlag = :false",
            ExpressionAttributeValues={":status": "pending", ":false": False},
        )
        logger.info(f"Reset segment processing status to pending for {active_segment_id}")
    except ClientError as err:
        logger.error(f"Failed to reset segment processing status for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to reset segment processing status: {err}") from err


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
            UpdateExpression="SET ProcessingStatus = :proc_status, #status = :status, #outcome = :outcome, RunningFlag = :false",
            ExpressionAttributeNames={"#outcome": "Outcome", "#status": "Status"},
            ExpressionAttributeValues={":proc_status": "processed", ":status": "completed", ":outcome": "exceptional", ":false": False},
        )
        logger.info(f"Marked exhausted segment as completed with exceptional outcome for {active_segment_id}")
    except ClientError as err:
        logger.error(f"Failed to mark segment as completed exceptional for {active_segment_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to mark segment as completed exceptional: {err}") from err


def validate_segment_outcome_results(segment: dict, outcome: str) -> dict:
    """
    Validate and extract outcome data from segment Results field.

    Ensures the Results field and its contents are properly structured,
    providing safe defaults when data is missing or malformed.

    Args:
        segment: Segment definition from database
        outcome: Outcome string (e.g., "exceptional", "normal", "failure")

    Returns:
        Dict with validated narrative and effects, guaranteed to have PascalCase keys:
            - Narrative (str): The outcome narrative text
            - Effects (dict): Effects to apply (may be empty)
    """
    # Get Results field, ensure it's a dict
    results = segment.get("Results")

    if results is None:
        logger.warning(f"Segment has no Results field for {segment.get('SegmentID')}")
        # Special handling for exceptional outcome (used by poller for timed-out segments)
        if outcome == "exceptional":
            return {"Narrative": "Your actions exceeded all expectations, achieving extraordinary results.", "Effects": {}}
        return {"Narrative": "", "Effects": {}}

    if not isinstance(results, dict):
        logger.error(f"Results field is not a dictionary for {segment.get('SegmentID')}")
        return {"Narrative": "", "Effects": {}}

    # Get outcome-specific result using lowercase keys (after normalization)
    outcome_key = str(outcome).lower() if outcome else "normal"
    outcome_result = results.get(outcome_key)

    if outcome_result is None:
        logger.info(f"No specific result for outcome for {segment.get('SegmentID')}")
        # Provide default for exceptional (safety mechanism for timed-out segments)
        if outcome == "exceptional":
            return {"Narrative": "Your actions exceeded all expectations, achieving extraordinary results.", "Effects": {}}
        return {"Narrative": "", "Effects": {}}

    if not isinstance(outcome_result, dict):
        logger.error(f"Outcome result is not a dictionary for {segment.get('SegmentID')}")
        return {"Narrative": "", "Effects": {}}

    # Validate narrative field
    narrative = outcome_result.get("Narrative", "")
    if not isinstance(narrative, str):
        logger.warning(f"Narrative is not a string for {segment.get('SegmentID')}")
    narrative = str(narrative) if narrative else ""

    # Validate effects field
    effects = outcome_result.get("Effects", {})
    if not isinstance(effects, dict):
        logger.warning(f"Effects is not a dictionary for {segment.get('SegmentID')}")
        effects = {}

    return {"Narrative": narrative, "Effects": effects}
