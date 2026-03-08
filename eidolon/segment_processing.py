"""
Main segment processing orchestration.

Provides functions for processing different segment types.
"""

from botocore.exceptions import ClientError

from eidolon.branching import select_weighted_branch
from eidolon.character_data import apply_character_updates
from eidolon.character_story import apply_story_outcome_effects
from eidolon.constants import ATTRIBUTE_XP_RATIO
from eidolon.dynamo import TableName, dynamo
from eidolon.items import add_items_to_inventory, process_items_with_probability
from eidolon.logger import logger
from eidolon.mechanics import calculate_skill_increase
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


def apply_segment_effects(character_id: str, results: dict) -> None:
    """
    Apply computed segment effects to the character in the database.

    Called AFTER the segment outcome has been safely persisted to active_segments.
    Attempts all effects even if some fail, then raises if any failed.

    Args:
        character_id: Character UUID
        results: Results dict from process_mechanical_segment()

    Raises:
        RuntimeError: If any effect application failed (lists which ones)
    """
    if not character_id:
        raise RuntimeError("Cannot apply segment effects: no character ID")

    failed_effects = []

    # Apply XP updates (skill and attribute increases)
    xp_updates = results.get("XPUpdates")
    if xp_updates:
        try:
            apply_character_updates(character_id, xp_updates)
            logger.info(f"Applied skill and attribute XP for {character_id}")
        except Exception as err:
            logger.error(f"Failed to apply XP updates for {character_id} Error: {err}", exc_info=True)
            failed_effects.append("XP")

    # Apply combat wounds
    wound_updates = results.get("WoundUpdates")
    if wound_updates:
        try:
            apply_character_updates(character_id, wound_updates)
            logger.info(f"Applied combat wounds for {character_id}")
        except Exception as err:
            logger.error(f"Failed to apply wounds for {character_id} Error: {err}", exc_info=True)
            failed_effects.append("Wounds")

    # Apply story outcome effects (room changes, story wounds)
    story_effects = results.get("StoryEffects")
    if story_effects:
        try:
            apply_story_outcome_effects(character_id, story_effects)
            logger.info(f"Applied story outcome effects for {character_id}")
        except Exception as err:
            logger.error(f"Failed to apply story outcome effects for {character_id} Error: {err}", exc_info=True)
            failed_effects.append("StoryEffects")

    # Create and grant items (opponent drops + story rewards)
    item_prototypes = results.get("ItemPrototypes")
    if item_prototypes:
        try:
            granted_items = add_items_to_inventory(character_id, item_prototypes)
            if granted_items:
                results["GrantedItemIDs"] = granted_items
                logger.info(f"Granted {len(granted_items)} items for {character_id}")
        except Exception as err:
            logger.error(f"Failed to grant items for {character_id} Error: {err}", exc_info=True)
            failed_effects.append("Items")

    if failed_effects:
        raise RuntimeError(f"Failed to apply segment effects: {', '.join(failed_effects)}")


def process_decision_segment(active_segment: dict, segment_def: dict) -> str:
    """
    Process a decision segment and generate narrative events.

    Decision segments are purely narrative - no mechanics, no difficulty checks.
    This function generates ClientEvents to enrich the story history.

    Args:
        active_segment: Active segment data with Decision field
        segment_def: Segment definition with DecisionOptions

    Returns:
        Outcome (always "normal" for decisions or "failure" if no decision)
    """
    decision = active_segment.get("Decision")
    decision_options = segment_def.get("DecisionOptions", {})

    if not decision:
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
                decision = default_decision
                active_segment["Decision"] = decision
            except ClientError as err:
                logger.error(f"Failed to update decision for {active_segment.get('ActiveSegmentID')} Error: {err}", exc_info=True)
                raise RuntimeError(f"Failed to update decision: {err}") from err
        else:
            return "failure"

    # Generate narrative ClientEvents for the chosen decision
    client_events = []

    if decision and decision in decision_options:
        option = decision_options.get(decision, {})
        narrative = option.get("Narrative")

        if narrative:
            # Primary narrative event showing what the character did
            client_events.append({"EventType": "narrative", "Title": "Your Choice", "Description": narrative})

        # Simple decision record (no mechanics data)
        client_events.append(
            {"EventType": "decision", "Title": option.get("Text", decision), "Description": option.get("Description", "")}
        )

    # Store events in active segment for history
    active_segment["ClientEvents"] = client_events

    return "normal"


def process_mechanical_segment(segment_def: dict, character: dict, active_segment: dict) -> tuple:
    """
    Process a mechanical segment containing skill challenges and/or combat.

    Computes outcomes and collects effects WITHOUT applying them to the database.
    Effects are applied separately via apply_segment_effects() after the outcome
    is safely persisted, preventing orphaned effects on write failures.

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

        # Compute skill and attribute XP (stored in results, applied later)
        skill_xp = {}
        attribute_xp = {}

        for challenge in challenge_results:
            skill = challenge.get("Skill")
            attribute = challenge.get("Attribute")
            passed = challenge.get("Passed", False)

            attempts = challenge.get("Attempts", [])
            best_attempt = max((a for a in attempts if "Sigma" in a), key=lambda a: a["Sigma"], default=None)

            if best_attempt and (skill or attribute):
                effective_score = best_attempt.get("EffectiveScore", 0)
                difficulty = best_attempt.get("Difficulty", 0)

                current_skill = float(character.get("Skills", {}).get(skill, 0))
                current_attribute = float(character.get("Attributes", {}).get(attribute, 0))

                if skill:
                    skill_increase = calculate_skill_increase(effective_score, difficulty, current_skill, passed)
                    if skill_increase > 0:
                        skill_xp[skill] = skill_xp.get(skill, 0) + skill_increase

                if attribute:
                    attr_increase = (
                        calculate_skill_increase(effective_score, difficulty, current_attribute, passed) * ATTRIBUTE_XP_RATIO
                    )
                    if attr_increase > 0:
                        attribute_xp[attribute] = attribute_xp.get(attribute, 0) + attr_increase

        if skill_xp or attribute_xp:
            xp_updates = {}
            if skill_xp:
                xp_updates["SkillXP"] = skill_xp
            if attribute_xp:
                xp_updates["AttributeXP"] = attribute_xp
            results["XPUpdates"] = xp_updates

    # Process combat if present and has an opponent defined
    combat_config = segment_def.get("Combat", {})
    has_opponent = combat_config and combat_config.get("OpponentID")
    if has_opponent:
        logger.info(f"Processing combat encounter for {segment_def.get('SegmentID')}")
        combat_outcome, combat_state = process_combat_segment(active_segment, segment_def, character)
        results["CombatState"] = combat_state
        outcomes.append(combat_outcome)

        # Collect wound updates (applied later)
        player_wounds = combat_state.get("PlayerWounds", [])
        if player_wounds:
            results["WoundUpdates"] = {"Wounds": player_wounds}

        # Merge combat XP into results (applied later)
        combat_xp = combat_state.get("XPUpdates", {})
        if combat_xp:
            if "XPUpdates" in results:
                if "SkillXP" in combat_xp:
                    existing_skill_xp = results.get("XPUpdates", {}).get("SkillXP", {})
                    for skill, xp in combat_xp.get("SkillXP", {}).items():
                        existing_skill_xp[skill] = existing_skill_xp.get(skill, 0) + xp
                    results["XPUpdates"]["SkillXP"] = existing_skill_xp
                if "AttributeXP" in combat_xp:
                    existing_attr_xp = results.get("XPUpdates", {}).get("AttributeXP", {})
                    for attr, xp in combat_xp.get("AttributeXP", {}).items():
                        existing_attr_xp[attr] = existing_attr_xp.get(attr, 0) + xp
                    results["XPUpdates"]["AttributeXP"] = existing_attr_xp
            else:
                results["XPUpdates"] = combat_xp

        # Collect opponent item prototypes to grant (created later)
        opponent_defeated = combat_state.get("OpponentDefeated", False)
        if opponent_defeated:
            opponent_id = combat_state.get("OpponentID")
            if opponent_id:
                try:
                    opponent_data = dynamo.get_item(TableName.OPPONENTS, {"OpponentID": opponent_id})
                    if opponent_data:
                        opponent_items = opponent_data.get("Items", [])
                        if opponent_items:
                            prototype_ids = process_items_with_probability(opponent_items)
                            if prototype_ids:
                                existing = results.get("ItemPrototypes", [])
                                results["ItemPrototypes"] = existing + prototype_ids
                except Exception as err:
                    logger.error(f"Failed to resolve opponent items for {opponent_id} Error: {err}", exc_info=True)

    # Determine overall outcome
    if not outcomes:
        logger.error(
            f"Mechanical segment {segment_def.get('SegmentID')} has no challenges or combat - "
            f"segment definition is incomplete or corrupted"
        )
        overall_outcome = "normal"
        results["SystemNote"] = "This segment had no challenges configured. Normal outcome granted."
    elif "death" in outcomes:
        overall_outcome = "death"
    elif "failure" in outcomes:
        overall_outcome = "failure"
    else:
        outcome_priority = ["minimal", "normal", "exceptional"]
        overall_outcome = "normal"
        for outcome in outcome_priority:
            if outcome in outcomes:
                overall_outcome = outcome
                break

    # Collect story outcome effects (applied later)
    outcome_key = map_outcome_to_key(overall_outcome)
    outcome_results = segment_def.get("Results", {}).get(outcome_key, {})
    story_effects = outcome_results.get("Effects", {})

    if story_effects:
        results["StoryEffects"] = story_effects

        # Collect story reward item prototypes (created later)
        reward_items = story_effects.get("Items")
        if reward_items:
            try:
                prototype_ids = process_items_with_probability(reward_items)
                if prototype_ids:
                    existing = results.get("ItemPrototypes", [])
                    results["ItemPrototypes"] = existing + prototype_ids
            except Exception as err:
                logger.error(f"Failed to resolve story reward items Error: {err}", exc_info=True)

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
                        "Decision": b.get("Decision", ""),
                        "Weight": b.get("Weight", 0),
                        "Label": f"timeout_{b.get('Decision', '')}",
                        "NextSegmentID": (
                            decision_options.get(b.get("Decision", ""), {}).get("NextSegmentID")
                            if isinstance(decision_options.get(b.get("Decision", "")), dict)
                            else decision_options.get(b.get("Decision", ""))
                        ),
                    }
                    for b in branches
                ]

                # Filter and select
                available = [(i, b) for i, b in enumerate(weighted_branches) if b.get("NextSegmentID")]
                if available:
                    idx, selected = select_weighted_branch(available)
                    next_id = selected.get("NextSegmentID")
                    selected_decision = selected.get("Decision")
                    logger.info(
                        f"Using weighted timeout for {active_segment_id}: decision={selected_decision}, next={next_id}"
                    )
                    return next_id, {
                        "SelectionMethod": "weighted_timeout",
                        "Decision": selected_decision,
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
        # Mechanical segments: direct outcome-based next segment (Death, Failure, Minimal, Normal, Exceptional)
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

        # Direct NextSegmentID lookup for mechanical outcomes
        next_segment_id = outcome_result.get("NextSegmentID", "")
        branch_metadata = {"SelectionMethod": "outcome_based", "Outcome": outcome_key}

        if next_segment_id:
            logger.info(f"Mechanical outcome for {active_segment_id}: outcome={outcome_key}, next={next_segment_id}")
        else:
            logger.info(f"No next segment for outcome '{outcome_key}' in {segment_id} - story ends")

        return next_segment_id, branch_metadata

    # Unknown segment type
    logger.error(f"Unknown segment type '{segment_type}' for {segment_id} - story ends")
    return "", {"SelectionMethod": "unknown_segment_type"}
