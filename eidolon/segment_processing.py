"""
Main segment processing orchestration.

Provides functions for processing different segment types.
"""

from botocore.exceptions import ClientError

from eidolon.character_data import apply_character_updates
from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger
from eidolon.segment_challenges import process_skill_challenges
from eidolon.segment_combat import process_combat_segment
from eidolon.segment_core import extract_character_updates_from_results, get_segment_definition, validate_segment_outcome_results
from eidolon.segment_events import (
    challenge_results_to_pascal,
    combat_state_to_pascal,
    events_to_pascal,
    generate_combat_client_events,
    generate_skill_check_events,
)
from eidolon.segment_state import update_active_segment_outcome


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
        logger.info(f"Processing skill challenges for {segment_def.get('SegmentID')}")
        challenge_outcome, challenge_results = process_skill_challenges(segment_def, character)
        results["challengeResults"] = challenge_results
        outcomes.append(challenge_outcome)

        # Apply skill and attribute XP immediately
        skill_xp = {}
        attribute_xp = {}

        # Constants from experience.md
        base_xp = 0.25  # Base experience per action
        failure_penalty = 0.5  # Failed actions give 50% XP
        attribute_xp_ratio = 0.1  # Attributes gain 10% of skill XP

        for challenge in challenge_results:
            skill = challenge.get("skill")
            attribute = challenge.get("attribute")
            passed = challenge.get("passed", False)

            # Get the best attempt to calculate variance modifier
            best_attempt = {}
            for attempt in challenge.get("attempts", []):
                if attempt.get("sigma") > best_attempt.get("sigma", -10):
                    best_attempt = attempt

            if best_attempt and (skill or attribute):
                effective_score = best_attempt.get("effectiveScore", 0)
                difficulty = best_attempt.get("difficulty", 0)

                # Calculate variance modifier based on experience.md formula
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

    # Process combat if present and has an opponent defined
    combat_config = segment_def.get("Combat", {})
    # Check if combat config exists AND has an OpponentID (either case)
    has_opponent = combat_config and (combat_config.get("OpponentID") or combat_config.get("opponentId"))
    if has_opponent:
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

    Rest segments are simply time delays that allow natural wound healing.

    Args:
        _: Segment definition (unused)
        character: Character data

    Returns:
        Tuple of (outcome, empty dict)
    """
    logger.info(f"Rest segment completed for {character.get('CharacterID')}")
    return "normal", {}




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
                # Explicitly provided per-outcome next segment
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

    # Check if segment has already been processed to prevent double XP application
    if active_segment.get("ProcessingStatus") == "processed":
        logger.info(f"Segment already processed, skipping reprocessing for {active_segment_id}")
        return {"outcome": active_segment.get("Outcome", "normal"), "nextSegment": None, "processed": True, "skipped": True}

    # Get segment definition
    segment_def = get_segment_definition(story_id, segment_id)

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
        outcome, results = process_mechanical_segment(segment_def, character, active_segment)
    elif segment_type == "rest":
        outcome, healing_data = process_rest_segment(segment_def, character)
        results.update(healing_data)
    elif segment_type == "decision":
        outcome = process_decision_segment(active_segment, segment_def)
    else:
        logger.error(f"Unknown segment type for {segment_type}")
        outcome = "failure"

    # Update active segment with outcome
    update_active_segment_outcome(active_segment_id, outcome, results, segment_def)

    logger.info(f"Segment processed, waiting for timer to expire before advancement for {active_segment_id}")

    return {
        "outcome": outcome,
        "nextSegment": None,
        "processed": True,
    }