"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to process a completed segment.
Determines outcome, applies effects, and creates next segment if applicable.
"""

import math
import random
import time
import uuid
from datetime import datetime
from datetime import timezone

from botocore.exceptions import ClientError

from eidolon.dynamo import dynamo
from eidolon.dynamo import TableName
from eidolon.logger import get_logger
from eidolon.utilities import log_lambda_invocation

# Configure logging
logger = get_logger(__name__)


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


def process_narrative_segment(segment_def: dict, character: dict) -> tuple:
    """
    Process a narrative segment by running challenges and determining outcome.

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
    opponent_id = combat_config.get("opponentId")
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
                opponent_wounds.append(
                    {
                        "type": "lethal" if damage_type == "critical" else "bashing",
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
            lethal_wounds = sum(1 for w in opponent_wounds if w["type"] == "lethal")
            if lethal_wounds >= opponent_health or len(opponent_wounds) >= opponent_health * 2:
                combat_log.append(round_results)
                return "normal", {
                    "rounds": round_num + 1,
                    "playerWounds": player_wounds,
                    "opponentWounds": opponent_wounds,
                    "combatLog": combat_log,
                    "victor": "player",
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
                player_wounds.append(
                    {
                        "type": "lethal" if damage_type == "critical" else "bashing",
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
            lethal_wounds = sum(1 for w in player_wounds if w["type"] == "lethal")
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
    elif player_total_wounds > opponent_total_wounds * 2:
        # Opponent dealt significantly more damage
        outcome = "failure"
        victor = "opponent"
    else:
        # Close fight - minor success
        outcome = "minimal"
        victor = "draw"

    return outcome, {
        "rounds": final_rounds,
        "playerWounds": player_wounds,
        "opponentWounds": opponent_wounds,
        "combatLog": combat_log,
        "victor": victor,
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


def update_active_segment_outcome(active_segment_id: str, outcome: str, results: dict) -> None:
    """
    Update active segment with outcome and mark as completed.

    Args:
        active_segment_id: Active segment UUID
        outcome: Outcome type
        results: Challenge or combat results
    """
    update_expression = "SET #status = :status, #outcome = :outcome"
    expression_names = {"#status": "Status", "#outcome": "Outcome"}
    expression_values = {":status": "completed", ":outcome": outcome}

    # Add results based on segment type
    if "challengeResults" in results:
        update_expression += ", ChallengeResults = :results"
        expression_values[":results"] = results["challengeResults"]
    elif "combatState" in results:
        update_expression += ", CombatState = :state"
        expression_values[":state"] = results["combatState"]

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


def update_history_segment(character_id: str, story_id: str, segment_data: dict) -> None:
    """
    Add segment completion to history.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        segment_data: Data about completed segment
    """
    try:
        # Get existing history
        history = dynamo.get_item(TableName.HISTORY, {"CharacterID": character_id, "StoryID": story_id})

        if history:
            segment_history = history.get("SegmentHistory", [])
            segment_history.append(segment_data)

            dynamo.update_item(
                TableName.HISTORY,
                Key={"CharacterID": character_id, "StoryID": story_id},
                UpdateExpression="SET SegmentHistory = :history",
                ExpressionAttributeValues={":history": segment_history},
            )
    except ClientError as err:
        logger.error(
            "Failed to update history",
            extra={
                "character_id": character_id,
                "story_id": story_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to update history: {str(err)}")


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

    elif segment_type in ["narrative", "combat"]:
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
    segment_id = segment.get("SegmentID")
    segment_type = segment.get("SegmentType", "narrative")
    duration = int(segment.get("SegmentDuration", 300))  # Default 5 minutes

    current_time = int(time.time())
    end_time = current_time + duration

    # Generate unique ID for this active segment
    active_segment_id = str(uuid.uuid4())

    # Create TTL for auto-cleanup (24 hours after end time)
    ttl = end_time + 86400

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
        "TTL": ttl,
    }

    # Add type-specific fields
    if segment_type == "decision":
        active_segment["Decision"] = None
        active_segment["DecisionOptions"] = segment.get("DecisionOptions", {})
    elif segment_type == "narrative":
        active_segment["ChallengeResults"] = []
        active_segment["Outcome"] = None
    elif segment_type == "combat":
        combat_config = segment.get("Combat", {})
        active_segment["CombatState"] = {
            "round": 0,
            "playerWounds": [],
            "opponentHealth": None,
            "opponentId": combat_config.get("opponentId"),
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
    Complete the story and update character state.

    Args:
        character_id: Character UUID
        story_id: Story UUID
        outcome: Final outcome
    """
    try:
        # Update character GameMode back to None
        dynamo.update_item(
            TableName.CHARACTERS,
            Key={"CharacterID": character_id},
            UpdateExpression="SET GameMode = :none",
            ExpressionAttributeValues={":none": "None"},
        )
    except ClientError as err:
        logger.error(
            "Failed to update character GameMode",
            extra={
                "character_id": character_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to update character GameMode: {str(err)}")

    try:
        # Update history with completion
        dynamo.update_item(
            TableName.HISTORY,
            Key={"CharacterID": character_id, "StoryID": story_id},
            UpdateExpression="SET FinishedAt = :finished, FinalOutcome = :outcome",
            ExpressionAttributeValues={
                ":finished": datetime.now(timezone.utc).isoformat(),
                ":outcome": outcome,
            },
        )
    except ClientError as err:
        logger.error(
            "Failed to update history completion",
            extra={
                "character_id": character_id,
                "story_id": story_id,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to update history completion: {str(err)}")


def process_segment_business_logic(
    active_segment_id: str,
    character_id: str,
    story_id: str,
    segment_id: str,
    segment_type: str,
) -> dict:
    """
    Business logic for processing a completed segment.

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

    if segment_type == "narrative":
        outcome, challenge_results = process_narrative_segment(segment_def, character)
        results["challengeResults"] = challenge_results

    elif segment_type == "combat":
        outcome, combat_state = process_combat_segment(active_segment, segment_def, character)
        results["combatState"] = combat_state

    elif segment_type == "decision":
        outcome = process_decision_segment(active_segment, segment_def)

    else:
        logger.error("Unknown segment type", extra={"segment_type": segment_type})
        outcome = "failure"

    # Update active segment with outcome
    update_active_segment_outcome(active_segment_id, outcome, results)

    # Update history
    segment_history_data = {
        "SegmentID": segment_id,
        "SegmentType": segment_type,
        "Outcome": outcome,
        "CompletedAt": datetime.now(timezone.utc).isoformat(),
        **results,
    }
    update_history_segment(character_id, story_id, segment_history_data)  # type: ignore

    # Determine next segment or complete story
    next_active_segment_id = get_next_segment_and_create(
        character_id, story_id, segment_def, active_segment, outcome  # type: ignore
    )

    if not next_active_segment_id:
        # No next segment - story is complete
        complete_story(character_id, story_id, outcome)  # type: ignore
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


def lambda_handler(event: dict, context: object) -> dict:
    """
    Lambda handler to process a completed segment.

    Args:
        event: Event containing segment information
        context: Lambda context

    Returns:
        Processing result
    """
    # Log invocation
    log_lambda_invocation(context, event)

    try:
        # Extract segment information from event
        active_segment_id: str = event.get("activeSegmentId", "")
        character_id = event.get("characterId")
        story_id = event.get("storyId")
        segment_id = event.get("segmentId")
        segment_type = event.get("segmentType")

        logger.info(
            "Processing segment",
            extra={
                "active_segment_id": active_segment_id,
                "segment_type": segment_type,
            },
        )

        # Call business logic
        result = process_segment_business_logic(active_segment_id, character_id, story_id, segment_id, segment_type)  # type: ignore

        logger.info("Lambda response", extra={"status_code": 200})
        return {
            "statusCode": 200,
            "body": {
                "message": "Segment processed successfully",
                "outcome": result["outcome"],
                "nextSegment": result["nextSegment"],
            },
        }

    except ValueError as err:
        logger.error(
            "Invalid request",
            extra={"error": str(err)},
        )
        return {
            "statusCode": 404,
            "body": {"error": str(err)},
        }
    except RuntimeError as err:
        logger.error(
            "Failed to process segment",
            extra={"error": str(err)},
        )
        return {
            "statusCode": 500,
            "body": {"error": "Failed to process segment"},
        }

    except Exception as err:
        logger.error(
            "Unexpected error in lambda_handler",
            extra={"error": str(err)},
            exc_info=True,
        )
        return {
            "statusCode": 500,
            "body": {"error": "Internal server error", "message": str(err)},
        }
