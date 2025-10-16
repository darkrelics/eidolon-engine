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
        option = decision_options[decision]
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

                # Calculate skill increase directly using same formula as combat
                from eidolon.mechanics import calculate_skill_increase

                # Get current skill and attribute values from character
                current_skill = float(character.get("Skills", {}).get(skill, 0))
                current_attribute = float(character.get("Attributes", {}).get(attribute, 0))

                # Calculate skill increase
                if skill:
                    skill_increase = calculate_skill_increase(effective_score, difficulty, current_skill, passed)
                    if skill_increase > 0:
                        skill_xp[skill] = skill_xp.get(skill, 0) + skill_increase

                # Calculate attribute increase (uses attribute score for increment)
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

        # Apply combat XP immediately to database
        combat_xp = combat_state.get("XPUpdates", {})
        if combat_xp:
            try:
                character_id = character.get("CharacterID")
                if character_id:
                    apply_character_updates(character_id, combat_xp)
                logger.info(f"Applied combat XP to database for {character.get('CharacterID')}")
            except Exception as err:
                logger.error(f"Failed to apply combat XP for {character.get('CharacterID')} Error: {err}", exc_info=True)

            # Merge combat XP into results (for client display)
            if "XPUpdates" in results:
                # Merge with challenge XP
                if "SkillXP" in combat_xp:
                    for skill, xp in combat_xp["SkillXP"].items():
                        results["XPUpdates"]["SkillXP"][skill] = results["XPUpdates"]["SkillXP"].get(skill, 0) + xp
                if "AttributeXP" in combat_xp:
                    for attr, xp in combat_xp["AttributeXP"].items():
                        results["XPUpdates"]["AttributeXP"][attr] = results["XPUpdates"]["AttributeXP"].get(attr, 0) + xp
            else:
                results["XPUpdates"] = combat_xp

        # Process opponent items if defeated
        opponent_defeated = combat_state.get("OpponentDefeated", False)
        if opponent_defeated:
            opponent_id = combat_state.get("OpponentID")
            if opponent_id:
                try:
                    opponent_data = dynamo.get_item(TableName.OPPONENTS, {"OpponentID": opponent_id})
                    if opponent_data:
                        opponent_items = opponent_data.get("Items", [])
                        if opponent_items:
                            character_id = character.get("CharacterID")
                            if character_id:
                                # Process opponent items with probability
                                prototype_ids = process_items_with_probability(opponent_items)
                                if prototype_ids:
                                    granted_items = add_items_to_inventory(character_id, prototype_ids)
                                    if granted_items:
                                        # Merge with any items from story effects
                                        existing_items = results.get("GrantedItemIDs", [])
                                        results["GrantedItemIDs"] = existing_items + granted_items
                                        logger.info(f"Granted {len(granted_items)} items from defeated opponent {opponent_id}")
                except Exception as err:
                    logger.error(f"Failed to process opponent items for {opponent_id} Error: {err}", exc_info=True)

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
                # Store effects in results for CharacterUpdates (for client display)
                results["StoryEffects"] = story_effects
            except Exception as err:
                logger.error(f"Failed to apply story outcome effects for {character_id} Error: {err}", exc_info=True)

            reward_items = story_effects.get("Items")
            if reward_items:
                # Process probability for items (handles both simple and probabilistic formats)
                prototype_ids = process_items_with_probability(reward_items)
                if prototype_ids:
                    granted_items = add_items_to_inventory(character_id, prototype_ids)
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
