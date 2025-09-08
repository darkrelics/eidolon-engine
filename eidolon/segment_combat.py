"""
Combat segment processing for mechanical segments.

Provides functions for processing combat encounters.
"""

from botocore.exceptions import ClientError

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
    combat_log = []

    # Continue combat from current round
    for round_num in range(int(current_round), min(int(current_round) + 5, int(max_rounds))):
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
            lethal_wounds = sum(1 for w in opponent_wounds if w.get("DamageType") == "lethal")
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

            round_results["opponentAttack"] = {
                "hit": True,
                "sigma": round(sigma, 2),
                "damage": damage,
                "damageType": damage_type,
            }

            # Check if player is defeated
            lethal_wounds = sum(1 for w in player_wounds if w.get("DamageType") == "lethal")
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
