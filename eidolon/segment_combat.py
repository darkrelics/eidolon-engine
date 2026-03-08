"""
Combat segment processing for mechanical segments.

Provides functions for processing combat encounters using dual action system.
"""

from botocore.exceptions import ClientError

from eidolon.constants import DEFAULT_COMBAT_ROUNDS, PLAYER_DEATH_LETHAL_WOUNDS, PLAYER_INCAPACITATED_TOTAL_WOUNDS
from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger
from eidolon.character_state import calculate_heal_time
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

    # Get opponent data
    try:
        opponent = dynamo.get_item(TableName.OPPONENTS, {"OpponentID": opponent_id})

        if not opponent:
            logger.error(f"Opponent not found for {opponent_id}")
            raise ValueError(f"Opponent not found: {opponent_id}")
    except ClientError as err:
        logger.error(f"Failed to get opponent data for {opponent_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get opponent data: {err}") from err

    # Get character stats
    character_id = character.get("CharacterID")
    character_attributes = character.get("Attributes", {})
    character_skills = character.get("Skills", {})
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
        # Character takes damage IF opponent's attack succeeded (character defense failed)
        if not opp_off_result["Success"]:  # Inverted because we swapped inputs
            # Determine damage amount based on opponent's sigma (inverted from result)
            sigma = -opp_off_result["Sigma"]  # Invert to get opponent's perspective
            damage = 2 if sigma > 3.0 else 1  # Critical hit = 2 wounds, normal = 1 wound

            # Apply wounds using opponent's weapon type
            for _ in range(damage):
                # Check if character is unconscious BEFORE applying this wound
                total_wounds = len(player_wounds)
                is_unconscious = total_wounds >= character_max_health

                damage_type = opponent_weapon_type

                # Special rule: bashing damage to unconscious characters converts existing bashing to lethal
                if is_unconscious and damage_type == "bashing":
                    # Find an existing bashing wound to convert to lethal
                    for wound in player_wounds:
                        if wound.get("DamageType") == "bashing":
                            wound["DamageType"] = "lethal"
                            wound["HealAt"] = calculate_heal_time("lethal")
                            break
                    # Whether converted or not, don't add a new wound to an unconscious character
                    continue

                player_wounds.append({"DamageType": damage_type, "HealAt": calculate_heal_time(damage_type)})

            round_results["Damage"]["CharacterTook"] = damage
            round_results["Damage"]["CharacterWoundType"] = opponent_weapon_type

        # Opponent takes damage IF character's attack succeeded
        if char_off_result["Success"]:
            # Determine damage amount based on sigma
            sigma = char_off_result["Sigma"]
            damage = 2 if sigma > 3.0 else 1  # Critical hit = 2 wounds, normal = 1 wound

            # Apply bashing wounds to opponent (no weapon in interim system)
            for _ in range(damage):
                opponent_wounds.append({"DamageType": "bashing", "HealAt": calculate_heal_time("bashing")})

            round_results["Damage"]["OpponentTook"] = damage
            round_results["Damage"]["OpponentWoundType"] = "bashing"

        # Log round results
        combat_log.append(round_results)

        # STEP 6: Check victory conditions after damage applied
        # Check character death/incapacitation first
        # Count both lethal and aggravated wounds for death check (aggravated is worse than lethal)
        deadly_wounds = sum(1 for w in player_wounds if w.get("DamageType") in ["lethal", "aggravated"])
        total_wounds = len(player_wounds)

        if deadly_wounds >= PLAYER_DEATH_LETHAL_WOUNDS:
            logger.info(f"Character defeated in round {round_num + 1} (deadly wounds: {deadly_wounds})")
            return "death", {
                "Rounds": round_num + 1,
                "PlayerWounds": player_wounds,
                "OpponentWounds": opponent_wounds,
                "CombatLog": combat_log,
                "Victor": "opponent",
                "OpponentDefeated": False,
                "OpponentID": opponent_id,
                "OpponentName": opponent_name,
                "XPUpdates": xp_accumulator,
            }

        if total_wounds >= PLAYER_INCAPACITATED_TOTAL_WOUNDS:
            logger.info(f"Character incapacitated in round {round_num + 1} (total wounds: {total_wounds})")
            return "failure", {
                "Rounds": round_num + 1,
                "PlayerWounds": player_wounds,
                "OpponentWounds": opponent_wounds,
                "CombatLog": combat_log,
                "Victor": "opponent",
                "OpponentDefeated": False,
                "OpponentID": opponent_id,
                "OpponentName": opponent_name,
                "XPUpdates": xp_accumulator,
            }

        # Check opponent defeat - any wounds count equally since opponents don't heal
        opponent_total_wounds = len(opponent_wounds)

        if opponent_total_wounds >= opponent_health:
            # Opponent defeated - determine outcome quality based on character wounds taken
            player_wound_count = len(player_wounds)

            if player_wound_count == 0:
                outcome = "exceptional"  # Flawless victory
            elif player_wound_count <= 2:
                outcome = "normal"  # Clean victory
            else:
                outcome = "minimal"  # Costly victory

            logger.info(f"Opponent defeated in round {round_num + 1} (outcome: {outcome}, character wounds: {player_wound_count})")
            return outcome, {
                "Rounds": round_num + 1,
                "PlayerWounds": player_wounds,
                "OpponentWounds": opponent_wounds,
                "CombatLog": combat_log,
                "Victor": "player",
                "OpponentDefeated": True,
                "OpponentID": opponent_id,
                "OpponentName": opponent_name,
                "XPUpdates": xp_accumulator,
            }

    # Max rounds reached without decisive outcome - opponent escapes
    logger.info(f"Combat reached max rounds ({max_rounds}) - opponent escaped")
    return "failure", {
        "Rounds": max_rounds,
        "PlayerWounds": player_wounds,
        "OpponentWounds": opponent_wounds,
        "CombatLog": combat_log,
        "Victor": "opponent",
        "OpponentDefeated": False,
        "OpponentID": opponent_id,
        "OpponentName": opponent_name,
        "XPUpdates": xp_accumulator,
    }
