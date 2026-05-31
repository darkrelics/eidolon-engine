"""
Combat segment processing for mechanical segments.

Provides functions for processing combat encounters using dual action system.
"""

from botocore.exceptions import ClientError

from eidolon.character_state import calculate_heal_time
from eidolon.constants import DEFAULT_COMBAT_ROUNDS, PLAYER_DEATH_LETHAL_WOUNDS, PLAYER_INCAPACITATED_TOTAL_WOUNDS
from eidolon.dynamo import TableName, dynamo
from eidolon.equipment import compute_effective_combat_traits
from eidolon.logger import logger
from eidolon.mechanics import resolve_opposed_check_with_xp


def get_character_best_offensive_action(attributes: dict, skills: dict) -> tuple:
    """
    Determine character's best offensive action.

    Args:
        attributes: Character attributes dict
        skills: Character skills dict

    Returns:
        Tuple of (action_name, rating, attribute_name, skill_name)
    """
    actions = {
        "Arcane": (
            attributes.get("Intelligence", 0) + skills.get("Arcane", 0),
            "Intelligence",
            "Arcane",
        ),
        "Brawling": (
            attributes.get("Strength", 0) + skills.get("Brawling", 0),
            "Strength",
            "Brawling",
        ),
        "Melee": (
            attributes.get("Strength", 0) + skills.get("Melee", 0),
            "Strength",
            "Melee",
        ),
        "Archery": (
            attributes.get("Agility", 0) + skills.get("Archery", 0),
            "Agility",
            "Archery",
        ),
    }

    # Find action with highest rating
    best_action = max(actions.items(), key=lambda x: x[1][0])
    action_name = best_action[0]
    rating, attribute_name, skill_name = best_action[1]

    return action_name, rating, attribute_name, skill_name


def get_character_defensive_action(offensive_action: str, attributes: dict, skills: dict) -> tuple:
    """
    Determine character's defensive action and rating based on offensive action.

    Args:
        offensive_action: Name of offensive action being used
        attributes: Character attributes dict
        skills: Character skills dict

    Returns:
        Tuple of (defensive_action, rating, attribute_name, skill_name)
    """
    if offensive_action == "Melee":
        # Melee users can parry
        defensive_action = "Parry"
        attribute_name = "Strength"
        skill_name = "Parry"
        rating = attributes.get("Strength", 0) + skills.get("Parry", 0)
    else:
        # Other combat styles require dodging
        defensive_action = "Dodge"
        attribute_name = "Agility"
        skill_name = "Dodge"
        rating = attributes.get("Agility", 0) + skills.get("Dodge", 0)

    return defensive_action, rating, attribute_name, skill_name


def load_opponent(opponent_id: str) -> dict:
    """Load opponent data from the OPPONENTS table, raising if it is missing."""
    try:
        opponent = dynamo.get_item(TableName.OPPONENTS, {"OpponentID": opponent_id})
        if not opponent:
            logger.error(f"Opponent not found for {opponent_id}")
            raise ValueError(f"Opponent not found: {opponent_id}")
    except ClientError as err:
        logger.error(f"Failed to get opponent data for {opponent_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get opponent data: {err}") from err
    return opponent


def apply_round_damage(
    round_results: dict,
    char_off_result: dict,
    opp_off_result: dict,
    player_wounds: list,
    opponent_wounds: list,
    opponent_weapon_type: str,
    character_max_health: int,
) -> None:
    """Apply one round's damage to the player and opponent wound lists in place.

    Mutates ``player_wounds``, ``opponent_wounds``, and ``round_results["Damage"]``.
    Reported ``CharacterTook`` is the actual change in wound count, so the
    unconscious-bashing conversion (which worsens an existing wound instead of
    adding one) does not report a phantom wound.
    """
    # Character takes damage IF opponent's attack succeeded (character defense failed)
    if not opp_off_result["Success"]:
        sigma = -opp_off_result["Sigma"]  # Invert to get opponent's perspective
        damage = 2 if sigma > 3.0 else 1  # Critical hit = 2 wounds, normal = 1 wound

        wounds_before = len(player_wounds)
        for _ in range(damage):
            # Check if character is unconscious BEFORE applying this wound
            is_unconscious = len(player_wounds) >= character_max_health
            damage_type = opponent_weapon_type

            # Bashing damage to an unconscious character converts existing bashing to lethal
            if is_unconscious and damage_type == "bashing":
                for wound in player_wounds:
                    if wound.get("DamageType") == "bashing":
                        wound["DamageType"] = "lethal"
                        wound["HealAt"] = calculate_heal_time("lethal")
                        break
                # Whether converted or not, don't add a new wound to an unconscious character
                continue

            player_wounds.append({"DamageType": damage_type, "HealAt": calculate_heal_time(damage_type)})

        round_results["Damage"]["CharacterTook"] = len(player_wounds) - wounds_before
        round_results["Damage"]["CharacterWoundType"] = opponent_weapon_type

    # Opponent takes damage IF character's attack succeeded
    if char_off_result["Success"]:
        sigma = char_off_result["Sigma"]
        damage = 2 if sigma > 3.0 else 1  # Critical hit = 2 wounds, normal = 1 wound

        # Apply bashing wounds to opponent (no weapon in interim system)
        for _ in range(damage):
            opponent_wounds.append({"DamageType": "bashing", "HealAt": calculate_heal_time("bashing")})

        round_results["Damage"]["OpponentTook"] = damage
        round_results["Damage"]["OpponentWoundType"] = "bashing"


def check_round_outcome(player_wounds: list, opponent_wounds: list, opponent_health: int) -> tuple:
    """Return ``(outcome, victor, opponent_defeated)`` if combat ended this round, else ``()``.

    Death and incapacitation are checked before opponent defeat. Opponent wounds
    count equally since opponents do not heal. An empty tuple signals that combat
    continues, so callers test the result for truthiness before unpacking.
    """
    # Count both lethal and aggravated wounds for death (aggravated is worse than lethal)
    deadly_wounds = sum(1 for w in player_wounds if w.get("DamageType") in ["lethal", "aggravated"])

    if deadly_wounds >= PLAYER_DEATH_LETHAL_WOUNDS:
        return "death", "opponent", False

    if len(player_wounds) >= PLAYER_INCAPACITATED_TOTAL_WOUNDS:
        return "failure", "opponent", False

    if len(opponent_wounds) >= opponent_health:
        # Outcome quality depends on how many wounds the character took
        player_wound_count = len(player_wounds)
        if player_wound_count == 0:
            outcome = "exceptional"  # Flawless victory
        elif player_wound_count <= 2:
            outcome = "normal"  # Clean victory
        else:
            outcome = "minimal"  # Costly victory
        return outcome, "player", True

    return ()


def build_combat_state(
    rounds: int,
    player_wounds: list,
    opponent_wounds: list,
    combat_log: list,
    victor: str,
    opponent_defeated: bool,
    opponent_id: str,
    opponent_name: str,
    xp_accumulator: dict,
) -> dict:
    """Build the combat_state dict returned alongside the outcome."""
    return {
        "Rounds": rounds,
        "PlayerWounds": player_wounds,
        "OpponentWounds": opponent_wounds,
        "CombatLog": combat_log,
        "Victor": victor,
        "OpponentDefeated": opponent_defeated,
        "OpponentID": opponent_id,
        "OpponentName": opponent_name,
        "XPUpdates": xp_accumulator,
    }


def process_combat_segment(active_segment: dict, segment_def: dict, character: dict) -> tuple:
    """
    Process a combat segment using dual action system (offensive + defensive per combatant).

    Args:
        active_segment: Active segment data
        segment_def: Segment definition from Segments table
        character: Character data

    Returns:
        Tuple of (outcome, combat_state)
    """
    combat_config = segment_def.get("Combat", {})
    opponent_id = combat_config.get("OpponentID")
    max_rounds = int(combat_config.get("MaxRounds") or DEFAULT_COMBAT_ROUNDS)

    opponent = load_opponent(opponent_id)

    # Get character stats, with equipped items' trait mods folded into the
    # effective attributes and skills so worn gear affects ratings (ITEM-2).
    character_id = character.get("CharacterID")
    character_attributes, character_skills = compute_effective_combat_traits(character)
    character_max_health = character.get("MaxHealth", 10)

    # Determine character's best offensive action (done once at combat start)
    char_off_action, char_off_rating, char_off_attr, char_off_skill = get_character_best_offensive_action(
        character_attributes, character_skills
    )

    # Determine character's defensive action (based on offensive choice)
    char_def_action, char_def_rating, char_def_attr, char_def_skill = get_character_defensive_action(
        char_off_action, character_attributes, character_skills
    )

    # Get opponent stats
    opponent_name = opponent.get("Name", "Unknown Opponent")
    opponent_health = opponent.get("Health", 5)
    opponent_weapon_type = opponent.get("WeaponType", "bashing")
    opp_off_action = opponent.get("OffensiveAction", "Melee")
    opp_off_rating = opponent.get("OffensiveRating", 5)
    opp_def_action = opponent.get("DefensiveAction", "Dodge")
    opp_def_rating = opponent.get("DefensiveRating", 5)

    # Initialize wounds
    player_wounds = []
    opponent_wounds = []

    # Track combat results and XP
    combat_log = []
    xp_accumulator = {}

    logger.info(
        f"Combat start: {character.get('CharacterName')} using {char_off_action}+{char_off_attr}({char_off_rating})/"
        f"{char_def_action}+{char_def_attr}({char_def_rating}) vs {opponent.get('Name')} using "
        f"{opp_off_action}({opp_off_rating})/{opp_def_action}({opp_def_rating})"
    )

    # Process all combat rounds
    for round_num in range(max_rounds):
        round_results = {
            "Round": round_num + 1,
            "CharacterOffensive": None,
            "CharacterDefensive": None,
            "OpponentOffensive": None,
            "OpponentDefensive": None,
            "Damage": {"CharacterTook": 0, "OpponentTook": 0},
        }

        # STEP 1: Character attacks opponent (character offensive vs opponent defensive)
        char_off_result = resolve_opposed_check_with_xp(
            character_id,  # type: ignore
            char_off_rating,
            opp_def_rating,
            char_off_skill,
            char_off_attr,
            character_skills,
            character_attributes,
            xp_accumulator,  # type: ignore
        )

        round_results["CharacterOffensive"] = {
            "Action": char_off_action,
            "Rating": char_off_rating,
            "Success": char_off_result["Success"],
            "Sigma": round(char_off_result["Sigma"], 2),
        }

        round_results["OpponentDefensive"] = {
            "Action": opp_def_action,
            "Rating": opp_def_rating,
            "Success": not char_off_result["Success"],  # Inverse of character's attack
            "Sigma": round(-char_off_result["Sigma"], 2),  # Inverse sigma
        }

        # STEP 2: Opponent attacks character (opponent offensive vs character defensive)
        # Swap aggressor/defender for XP calculation so character's defense is the "effective score"
        opp_off_result = resolve_opposed_check_with_xp(
            character_id,  # type: ignore
            char_def_rating,
            opp_off_rating,
            char_def_skill,
            char_def_attr,
            character_skills,
            character_attributes,
            xp_accumulator,  # type: ignore
        )

        # Note: result is from character's perspective (char def vs opp off)
        # Success=True means character's defense beat opponent's offense
        round_results["OpponentOffensive"] = {
            "Action": opp_off_action,
            "Rating": opp_off_rating,
            "Success": not opp_off_result["Success"],  # Inverted because we swapped inputs
            "Sigma": round(-opp_off_result["Sigma"], 2),  # Inverted sigma
        }

        round_results["CharacterDefensive"] = {
            "Action": char_def_action,
            "Rating": char_def_rating,
            "Success": opp_off_result["Success"],  # Character def success when check succeeds
            "Sigma": round(opp_off_result["Sigma"], 2),
        }

        # STEP 3: Apply damage based on opposed check results
        apply_round_damage(
            round_results,
            char_off_result,
            opp_off_result,
            player_wounds,
            opponent_wounds,
            opponent_weapon_type,
            character_max_health,
        )

        # Log round results
        combat_log.append(round_results)

        # STEP 4: Check victory conditions after damage applied
        outcome = check_round_outcome(player_wounds, opponent_wounds, opponent_health)
        if outcome:
            outcome_name, victor, opponent_defeated = outcome
            logger.info(
                f"Combat ended in round {round_num + 1}: {outcome_name} "
                f"(victor: {victor}, character wounds: {len(player_wounds)})"
            )
            return outcome_name, build_combat_state(
                round_num + 1,
                player_wounds,
                opponent_wounds,
                combat_log,
                victor,
                opponent_defeated,
                opponent_id,
                opponent_name,
                xp_accumulator,
            )

    # Max rounds reached without decisive outcome - opponent escapes
    logger.info(f"Combat reached max rounds ({max_rounds}) - opponent escaped")
    return "failure", build_combat_state(
        max_rounds,
        player_wounds,
        opponent_wounds,
        combat_log,
        "opponent",
        False,
        opponent_id,
        opponent_name,
        xp_accumulator,
    )
