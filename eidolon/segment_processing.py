"""
Main segment processing orchestration.

Provides functions for processing different segment types.
"""

from botocore.exceptions import ClientError

from eidolon.branching import select_next_branch, select_weighted_branch
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


def determine_next_segment(segment_def: dict, active_segment: dict, outcome: str, character: dict) -> tuple:
    """
    Determine the next segment ID based on segment type and outcome.

    Each segment type has distinct logic:
    - Mechanical: Uses Results.{Outcome}.Branches for outcome-based branching
    - Decision: Uses DecisionOptions with optional weighted timeout

    Args:
        segment_def: Segment definition from Segments table
        active_segment: Active segment record
        outcome: Segment outcome
        character: Character record for prerequisite checking

    Returns:
        Tuple of (next_segment_id, branch_metadata)
    """
    segment_type = segment_def.get("SegmentType")
    segment_id = segment_def.get("SegmentID", "unknown")
    active_segment_id = active_segment.get("ActiveSegmentID", "unknown")

    logger.debug(f"determine_next_segment called for {active_segment_id}")
    logger.debug(f"  segment_type: {segment_type}")
    logger.debug(f"  outcome: {outcome}")

    if segment_type == "decision":
        # Use decision to determine next segment (player choice)
        decision = active_segment.get("Decision")
        decision_options = segment_def.get("DecisionOptions", {})

        if decision and decision in decision_options:
            # Support dict with NextSegmentID format
            decision_value = decision_options.get(decision)
            if isinstance(decision_value, dict):
                next_segment_id = decision_value.get("NextSegmentID")
            else:
                next_segment_id = decision_value
            logger.info(f"Selected decision branch for {active_segment_id}: decision={decision}, next={next_segment_id}")
            return next_segment_id, {"SelectionMethod": "player_decision", "Decision": decision}

        # No decision made (timeout) - use weighted branches if available
        timeout_behavior = segment_def.get("TimeoutBehavior", {})
        if timeout_behavior.get("Type") == "weighted":
            branches = timeout_behavior.get("Branches", [])
            if branches:
                # Convert decision branches to standard branch format for selection
                weighted_branches = [
                    {
                        "Decision": b["Decision"],
                        "Weight": b["Weight"],
                        "Label": f"timeout_{b['Decision']}",
                        "NextSegmentID": (
                            decision_options.get(b["Decision"], {}).get("NextSegmentID")
                            if isinstance(decision_options.get(b["Decision"]), dict)
                            else decision_options.get(b["Decision"])
                        ),
                    }
                    for b in branches
                ]

                # Filter and select
                available = [(i, b) for i, b in enumerate(weighted_branches) if b.get("NextSegmentID")]
                if available:
                    idx, selected = select_weighted_branch(available)
                    logger.info(
                        f"Using weighted timeout for {active_segment_id}: decision={selected['Decision']}, next={selected['NextSegmentID']}"
                    )
                    return selected["NextSegmentID"], {
                        "SelectionMethod": "weighted_timeout",
                        "Decision": selected["Decision"],
                        "BranchIndex": idx,
                    }

        # Fallback to default decision
        default_decision = segment_def.get("DefaultDecision")
        if default_decision and default_decision in decision_options:
            decision_value = decision_options.get(default_decision)
            if isinstance(decision_value, dict):
                next_segment_id = decision_value.get("NextSegmentID")
            else:
                next_segment_id = decision_value
            logger.info(f"Using default decision for {active_segment_id}: default={default_decision}, next={next_segment_id}")
            return next_segment_id, {"SelectionMethod": "default_decision", "Decision": default_decision}

        # No valid decision path found
        logger.warning(f"No decision made for {active_segment_id} and no default available - story ends")
        return "", {"SelectionMethod": "no_decision"}

    elif segment_type == "mechanical":
        # Mechanical segments: outcome-based branching (Death, Failure, Minimal, Normal, Exceptional)
        outcome_key = map_outcome_to_key(outcome or "normal")

        # Get results dict
        results = segment_def.get("Results", {})
        if not isinstance(results, dict):
            logger.warning(f"Results is not a dict for {segment_id} - story ends")
            return "", {"SelectionMethod": "invalid_results"}

        # Get outcome-specific result
        outcome_result = results.get(outcome_key)
        if not outcome_result:
            logger.warning(f"No result found for outcome '{outcome_key}' in {segment_id} - story ends")
            return "", {"SelectionMethod": "no_outcome_result"}

        if not isinstance(outcome_result, dict):
            logger.warning(f"Outcome result for '{outcome_key}' is not a dict in {segment_id} - story ends")
            return "", {"SelectionMethod": "invalid_outcome_result"}

        # Use weighted branching system for mechanical outcomes
        branch_result = select_next_branch(outcome_result, character)

        next_segment_id = branch_result["NextSegmentID"]
        branch_metadata = branch_result["BranchMetadata"]

        if next_segment_id:
            logger.info(f"Mechanical outcome branch for {active_segment_id}: outcome={outcome_key}, next={next_segment_id}")
        else:
            logger.info(f"No next segment for outcome '{outcome_key}' in {segment_id} - story ends")

        return next_segment_id, branch_metadata

    # Unknown segment type
    logger.error(f"Unknown segment type '{segment_type}' for {segment_id} - story ends")
    return "", {"SelectionMethod": "unknown_segment_type"}
