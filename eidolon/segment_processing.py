"""
Main segment processing orchestration.

Provides functions for processing different segment types.
"""

from botocore.exceptions import ClientError

from eidolon.character_data import apply_character_updates
from eidolon.character_story import apply_story_outcome_effects
from eidolon.constants import ATTRIBUTE_XP_RATIO, BASE_XP, FAILURE_XP_PENALTY
from eidolon.dynamo import TableName, dynamo
from eidolon.items import add_items_to_inventory
from eidolon.logger import logger
from eidolon.segment_challenges import process_skill_challenges
from eidolon.segment_combat import process_combat_segment
from eidolon.segment_core import map_outcome_to_key


def route_segment_processing(segment_def: dict, character: dict, active_segment: dict) -> tuple:
    """
    Route segment to appropriate processor based on type.

    Args:
        segment_def: Segment definition
        character: Character data
        active_segment: Active segment record

    Returns:
        Tuple of (outcome, results)

    """
    segment_type = active_segment.get("SegmentType")

    if segment_type == "mechanical":
        return process_mechanical_segment(segment_def, character, active_segment)
    elif segment_type == "rest":
        logger.debug(f"Rest segment processed for {active_segment.get('ActiveSegmentID')}")
        return "normal", {}
    elif segment_type == "decision":
        outcome = process_decision_segment(active_segment, segment_def)
        return outcome, {}
    else:
        logger.warning(f"Unknown segment type '{segment_type}' for {active_segment.get('ActiveSegmentID')}, defaulting to normal")
        return "normal", {}


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
        results["ChallengeResults"] = challenge_results
        outcomes.append(challenge_outcome)

        # Apply skill and attribute XP immediately
        skill_xp = {}
        attribute_xp = {}

        for challenge in challenge_results:
            skill = challenge.get("Skill")
            attribute = challenge.get("Attribute")
            passed = challenge.get("Passed", False)

            # Get the best attempt to calculate variance modifier
            attempts = challenge.get("Attempts", [])
            best_attempt = max((a for a in attempts if "Sigma" in a), key=lambda a: a["Sigma"], default=None)

            if best_attempt and (skill or attribute):
                effective_score = best_attempt.get("EffectiveScore", 0)
                difficulty = best_attempt.get("Difficulty", 0)

                # Calculate variance modifier based on experience.md formula
                if effective_score > 0 and difficulty > 0:
                    ratio = min(effective_score, difficulty) / max(effective_score, difficulty)
                    variance_modifier = ratio**2
                else:
                    variance_modifier = 1.0  # Default if can't calculate

                # Calculate base XP with variance modifier
                xp_amount = BASE_XP * variance_modifier

                # Apply failure penalty if challenge wasn't passed
                if not passed:
                    xp_amount *= FAILURE_XP_PENALTY

                # Award XP to skill (full amount)
                if skill:
                    skill_xp[skill] = skill_xp.get(skill, 0) + xp_amount

                # Award XP to attribute (10% of skill XP)
                if attribute:
                    attr_xp_amount = xp_amount * ATTRIBUTE_XP_RATIO
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
            results["XPUpdates"] = xp_updates

    # Process combat if present and has an opponent defined
    combat_config = segment_def.get("Combat", {})
    # Check if combat config exists AND has an OpponentID
    has_opponent = combat_config and combat_config.get("OpponentID")
    if has_opponent:
        logger.info(f"Processing combat encounter for {segment_def.get('SegmentID')}")
        combat_outcome, combat_state = process_combat_segment(active_segment, segment_def, character)
        results["CombatState"] = combat_state
        outcomes.append(combat_outcome)

        # Apply wounds immediately to database
        player_wounds = combat_state.get("PlayerWounds", [])
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
            results["WoundUpdates"] = wound_updates

    # Determine overall outcome
    if not outcomes:
        logger.warning(f"Mechanical segment has no challenges or combat for {segment_def.get('SegmentID')}")
        overall_outcome = "normal"
    elif "death" in outcomes:
        overall_outcome = "death"
    elif "failure" in outcomes:
        overall_outcome = "failure"
    else:
        # Take the worst non-failure outcome
        outcome_priority = ["minimal", "normal", "exceptional"]
        overall_outcome = "normal"
        for outcome in outcome_priority:
            if outcome in outcomes:
                overall_outcome = outcome
                break

    # Apply story outcome effects immediately (wounds, room changes, etc.)
    outcome_key = map_outcome_to_key(overall_outcome)
    outcome_results = segment_def.get("Results", {}).get(outcome_key, {})
    story_effects = outcome_results.get("Effects", {})

    if story_effects:
        character_id = character.get("CharacterID")
        if character_id:
            try:
                apply_story_outcome_effects(character_id, story_effects)
                logger.info(f"Applied story outcome effects for {character_id}")
                # Store effects in results for CharacterUpdates (for client display)
                results["StoryEffects"] = story_effects
            except Exception as err:
                logger.error(f"Failed to apply story outcome effects for {character_id} Error: {err}", exc_info=True)

            reward_items = story_effects.get("Items")
            if reward_items:
                granted_items = add_items_to_inventory(character_id, reward_items)
                if granted_items:
                    results["GrantedItemIDs"] = granted_items

    return overall_outcome, results


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

    # Debug logging
    logger.debug(f"determine_next_segment called for {active_segment_id}")
    logger.debug(f"  segment_type: {segment_type}")
    logger.debug(f"  outcome: {outcome}")
    logger.debug(f"  Results keys: {list(segment_def.get('Results', {}).keys())}")

    if segment_type == "decision":
        # Use decision to determine next segment
        decision = active_segment.get("Decision")
        decision_options = segment_def.get("DecisionOptions", {})

        if decision and decision in decision_options:
            # Support both legacy (string) and rich (dict with NextSegmentID) formats
            decision_value = decision_options.get(decision)
            if isinstance(decision_value, dict):
                next_segment_id = decision_value.get("NextSegmentID")
            else:
                next_segment_id = decision_value
            logger.info(f"Selected decision branch for {active_segment_id}: decision={decision}, next={next_segment_id}")
            return next_segment_id

        # No decision made (timeout) - use default if specified
        default_decision = segment_def.get("DefaultDecision")
        if default_decision and default_decision in decision_options:
            next_segment_id = decision_options.get(default_decision)
            logger.info(f"Using default decision for {active_segment_id}: default={default_decision}, next={next_segment_id}")
            return next_segment_id

        # No valid decision path found
        logger.warning(f"No decision made for {active_segment_id} and no default available - story ends")
        return None

    elif segment_type in ["mechanical", "rest"]:
        # Rest segments always use Normal outcome
        if segment_type == "rest":
            outcome_key = "Normal"
        else:
            outcome_key = map_outcome_to_key(outcome or "normal")

        # Get results dict
        results = segment_def.get("Results", {})
        if not isinstance(results, dict):
            logger.warning(f"Results is not a dict for {segment_id} - story ends")
            return None

        # Get outcome-specific result
        outcome_result = results.get(outcome_key)
        if not outcome_result:
            logger.warning(f"No result found for outcome '{outcome_key}' in {segment_id} - story ends")
            return None

        if not isinstance(outcome_result, dict):
            logger.warning(f"Outcome result for '{outcome_key}' is not a dict in {segment_id} - story ends")
            return None

        # Get NextSegmentID from outcome result
        next_segment_id = outcome_result.get("NextSegmentID")

        if next_segment_id:
            logger.info(f"Using outcome-based next segment for {active_segment_id}: outcome={outcome_key}, next={next_segment_id}")
        else:
            logger.info(f"No NextSegmentID for outcome '{outcome_key}' in {segment_id} - story ends")

        return next_segment_id

    # Unknown segment type
    logger.error(f"Unknown segment type '{segment_type}' for {segment_id} - story ends")
    return None
