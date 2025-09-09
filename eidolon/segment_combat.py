"""
Combat segment processing for mechanical segments.

Provides functions for processing combat encounters.
"""

from botocore.exceptions import ClientError

from eidolon.constants import (
    COMBAT_DOMINANCE_RATIO,
    COMBAT_OPPONENT_WOUNDS_MULTIPLIER_FOR_DEFEAT,
    COMBAT_ROUNDS_PER_TICK,
    COMBAT_SIGMA_CRITICAL,
    COMBAT_SIGMA_SOLID,
    DEFAULT_COMBAT_ROUNDS,
    PLAYER_DEATH_LETHAL_WOUNDS,
    PLAYER_INCAPACITATED_TOTAL_WOUNDS,
)
from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger
from eidolon.mechanics import calculate_heal_time, resolve_opposed_check


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
    # Enforce PascalCase configuration
    opponent_id = combat_config.get("OpponentID")
    max_rounds = combat_config.get("MaxRounds") or DEFAULT_COMBAT_ROUNDS

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
    player_wounds = combat_state.get("PlayerWounds", [])
    opponent_wounds = combat_state.get("OpponentWounds", [])
    current_round = combat_state.get("Round", 0)

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
    combat_log = []

    # Continue combat from current round
    for round_num in range(int(current_round), min(int(current_round) + COMBAT_ROUNDS_PER_TICK, int(max_rounds))):
        round_results = {
            "Round": round_num + 1,
            "PlayerAttack": None,
            "OpponentAttack": None,
        }

        # Player attacks opponent using MUD mechanics
        attack_outcome = resolve_opposed_check(character_combat, opponent_defense)

        if attack_outcome["success"]:
            # Determine damage based on sigma
            sigma = attack_outcome["sigma"]
            if sigma > COMBAT_SIGMA_CRITICAL:
                damage = 3  # Critical hit
                damage_type = "critical"
            elif sigma > COMBAT_SIGMA_SOLID:
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

            round_results["PlayerAttack"] = {
                "Hit": True,
                "Sigma": round(sigma, 2),
                "Damage": damage,
                "DamageType": damage_type,
            }

            # Check if opponent is defeated
            lethal_wounds = sum(1 for w in opponent_wounds if w.get("DamageType") == "lethal")
            if (
                lethal_wounds >= opponent_health
                or len(opponent_wounds) >= opponent_health * COMBAT_OPPONENT_WOUNDS_MULTIPLIER_FOR_DEFEAT
            ):
                combat_log.append(round_results)
                return "normal", {
                    "Rounds": round_num + 1,
                    "PlayerWounds": player_wounds,
                    "OpponentWounds": opponent_wounds,
                    "CombatLog": combat_log,
                    "Victor": "player",
                    "OpponentDefeated": True,
                    "OpponentID": opponent_id,
                }
        else:
            round_results["PlayerAttack"] = {
                "Hit": False,
                "Sigma": round(attack_outcome["sigma"], 2),
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

            round_results["OpponentAttack"] = {
                "Hit": True,
                "Sigma": round(sigma, 2),
                "Damage": damage,
                "DamageType": damage_type,
            }

            # Check if player is defeated
            lethal_wounds = sum(1 for w in player_wounds if w.get("DamageType") == "lethal")
            total_wounds = len(player_wounds)

            if lethal_wounds >= PLAYER_DEATH_LETHAL_WOUNDS:
                combat_log.append(round_results)
                return "death", {
                    "Rounds": round_num + 1,
                    "PlayerWounds": player_wounds,
                    "OpponentWounds": opponent_wounds,
                    "CombatLog": combat_log,
                    "Victor": "opponent",
                }
            elif total_wounds >= PLAYER_INCAPACITATED_TOTAL_WOUNDS:
                combat_log.append(round_results)
                return "failure", {
                    "Rounds": round_num + 1,
                    "PlayerWounds": player_wounds,
                    "OpponentWounds": opponent_wounds,
                    "CombatLog": combat_log,
                    "Victor": "opponent",
                }
        else:
            round_results["OpponentAttack"] = {
                "Hit": False,
                "Sigma": round(defense_outcome["sigma"], 2),
            }

        combat_log.append(round_results)

    # Max rounds reached - determine outcome based on wounds
    player_total_wounds = len(player_wounds)
    opponent_total_wounds = len(opponent_wounds)

    # Calculate final rounds (round_num might not be defined if no combat occurred)
    final_rounds = len(combat_log)

    if opponent_total_wounds > player_total_wounds * COMBAT_DOMINANCE_RATIO:
        # Player dealt significantly more damage
        outcome = "normal"
        victor = "player"
        opponent_defeated = True
    elif player_total_wounds > opponent_total_wounds * COMBAT_DOMINANCE_RATIO:
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
        "Rounds": final_rounds,
        "PlayerWounds": player_wounds,
        "OpponentWounds": opponent_wounds,
        "CombatLog": combat_log,
        "Victor": victor,
        "OpponentDefeated": opponent_defeated,
        "OpponentID": opponent_id,
    }
