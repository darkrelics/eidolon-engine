"""
Combat narrative generation for mechanical segments.

Provides model-based templates for generating engaging combat descriptions
from combat round data.
"""

import random
from typing import Any


# Narrative templates for combat actions
OFFENSIVE_TEMPLATES = {
    "Melee": {
        "success": [
            "{attacker} swings their blade at {defender}, landing a {severity} strike",
            "{attacker}'s melee attack catches {defender} off guard, dealing {severity} damage",
            "{attacker} closes in and delivers a {severity} blow with their weapon",
            "{attacker}'s blade finds its mark, striking {defender} with {severity} force",
        ],
        "failure": [
            "{attacker} swings at {defender}, but the attack is deflected",
            "{attacker}'s melee attack misses as {defender} evades",
            "{attacker} lunges forward, but {defender} sidesteps the blow",
            "{attacker}'s weapon slices through empty air",
        ],
    },
    "Brawling": {
        "success": [
            "{attacker} lands a {severity} punch on {defender}",
            "{attacker} grapples {defender} and delivers a {severity} strike",
            "{attacker}'s fist connects with {severity} impact",
            "{attacker} strikes {defender} with a {severity} blow",
        ],
        "failure": [
            "{attacker} throws a punch, but {defender} blocks it",
            "{attacker}'s strike is parried by {defender}",
            "{attacker} attempts to grapple, but {defender} breaks free",
            "{attacker}'s attack is dodged at the last moment",
        ],
    },
    "Archery": {
        "success": [
            "{attacker} looses an arrow that strikes {defender} with {severity} precision",
            "{attacker}'s shot finds its target, dealing {severity} damage",
            "{attacker} fires a {severity} shot that pierces {defender}",
            "{attacker}'s arrow flies true, hitting {defender} with {severity} force",
        ],
        "failure": [
            "{attacker} fires an arrow, but it sails past {defender}",
            "{attacker}'s shot goes wide as {defender} dodges",
            "{attacker} releases their bowstring, but the arrow misses",
            "{attacker}'s aim is off, and the arrow clatters harmlessly away",
        ],
    },
    "Arcane": {
        "success": [
            "{attacker} unleashes arcane energy that strikes {defender} with {severity} power",
            "{attacker}'s spell blast hits {defender} for {severity} damage",
            "{attacker} channels magic into a {severity} attack against {defender}",
            "{attacker}'s arcane bolt sears {defender} with {severity} intensity",
        ],
        "failure": [
            "{attacker} casts a spell, but {defender} resists the magic",
            "{attacker}'s arcane bolt dissipates before reaching {defender}",
            "{attacker} attempts to channel magic, but the spell fizzles",
            "{attacker}'s magical attack is deflected by {defender}",
        ],
    },
}

DEFENSIVE_TEMPLATES = {
    "Dodge": {
        "success": [
            "{defender} nimbly dodges the attack",
            "{defender} sidesteps at the last moment",
            "{defender} weaves away from danger",
            "{defender} evades with quick reflexes",
        ],
        "failure": [
            "{defender} tries to dodge but is too slow",
            "{defender} attempts to evade but fails",
            "{defender} is caught off-guard",
            "{defender} cannot get out of the way in time",
        ],
    },
    "Parry": {
        "success": [
            "{defender} parries the blow expertly",
            "{defender} deflects the attack with their weapon",
            "{defender} blocks the strike skillfully",
            "{defender} turns aside the attack",
        ],
        "failure": [
            "{defender} attempts to parry but is overwhelmed",
            "{defender} tries to block but the attack breaks through",
            "{defender}'s parry comes too late",
            "{defender} fails to deflect the strike",
        ],
    },
}

# Severity descriptors based on sigma and damage
SEVERITY_NORMAL = ["solid", "strong", "fierce", "powerful"]
SEVERITY_CRITICAL = ["devastating", "crushing", "brutal", "mighty"]


def get_severity_descriptor(sigma: float, damage: int) -> str:
    """
    Get a descriptor for attack severity based on sigma and damage.

    Args:
        sigma: The sigma value from the opposed check
        damage: Amount of damage dealt

    Returns:
        Severity descriptor string
    """
    if damage >= 2 or sigma > 3.0:
        return random.choice(SEVERITY_CRITICAL)
    return random.choice(SEVERITY_NORMAL)


def generate_combat_narrative(round_data: dict, character_name: str, opponent_name: str) -> str:
    """
    Generate a narrative description of a combat round.

    Args:
        round_data: Combat round data containing offensive/defensive actions and damage
        character_name: Name of the player character
        opponent_name: Name of the opponent

    Returns:
        Narrative string describing the combat round
    """
    narratives = []

    # Character's offensive action
    char_offensive = round_data.get("CharacterOffensive", {})
    char_off_action = char_offensive.get("Action", "Melee")
    char_off_success = char_offensive.get("Success", False)
    char_off_sigma = char_offensive.get("Sigma", 0)

    # Opponent's defensive action
    opp_defensive = round_data.get("OpponentDefensive", {})

    # Damage dealt by character
    damage = round_data.get("Damage", {})
    opponent_damage = damage.get("OpponentTook", 0)

    # Generate character attack narrative
    if char_off_action in OFFENSIVE_TEMPLATES:
        templates = OFFENSIVE_TEMPLATES[char_off_action]
        success_key = "success" if char_off_success else "failure"
        template = random.choice(templates[success_key])

        severity = ""
        if char_off_success and opponent_damage > 0:
            severity = get_severity_descriptor(char_off_sigma, opponent_damage)

        narrative = template.format(
            attacker=character_name,
            defender=opponent_name,
            severity=severity,
        ).strip()
        # Clean up double spaces
        narrative = " ".join(narrative.split())
        narratives.append(narrative)

    # Opponent's offensive action
    opp_offensive = round_data.get("OpponentOffensive", {})
    opp_off_action = opp_offensive.get("Action", "Melee")
    opp_off_success = opp_offensive.get("Success", False)
    opp_off_sigma = opp_offensive.get("Sigma", 0)

    # Character's defensive action
    char_defensive = round_data.get("CharacterDefensive", {})

    # Damage dealt to character
    character_damage = damage.get("CharacterTook", 0)

    # Generate opponent attack narrative
    if opp_off_action in OFFENSIVE_TEMPLATES:
        templates = OFFENSIVE_TEMPLATES[opp_off_action]
        success_key = "success" if opp_off_success else "failure"
        template = random.choice(templates[success_key])

        severity = ""
        if opp_off_success and character_damage > 0:
            severity = get_severity_descriptor(opp_off_sigma, character_damage)

        narrative = template.format(
            attacker=opponent_name,
            defender=character_name,
            severity=severity,
        ).strip()
        # Clean up double spaces
        narrative = " ".join(narrative.split())
        narratives.append(narrative)

    # Combine narratives with appropriate punctuation
    if narratives:
        return ". ".join(narratives) + "."

    return "The combatants exchange blows."
