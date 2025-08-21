"""
Client event generation for segments.

Provides functions for generating and formatting client events.
"""

from eidolon.models import ClientEvent


def to_pascal_key(key: str) -> str:
    """
    Convert snake_case or camelCase key to PascalCase.

    Args:
        key: Key to convert

    Returns:
        PascalCase version of the key
    """
    parts = key.split("_")
    return "".join(p.capitalize() for p in parts)


def challenge_results_to_pascal(ch_results: list) -> list:
    """
    Convert challenge results to PascalCase for client consumption.

    Args:
        ch_results: List of challenge result dicts

    Returns:
        List with PascalCase keys
    """
    if not ch_results:
        return []

    out = []
    for ch_result in ch_results:
        result = {
            "Attribute": ch_result.get("attribute"),
            "Skill": ch_result.get("skill"),
            "Difficulty": ch_result.get("difficulty"),
            "BestSigma": ch_result.get("bestSigma"),
            "Passed": ch_result.get("passed"),
        }
        # Convert attempts if present
        attempts = ch_result.get("attempts", [])
        if attempts:
            pascal_attempts = []
            for attempt in attempts:
                pascal_attempts.append(
                    {
                        "EffectiveScore": attempt.get("effectiveScore"),
                        "Difficulty": attempt.get("difficulty"),
                        "Sigma": attempt.get("sigma"),
                        "Success": attempt.get("success"),
                    }
                )
            result["Attempts"] = pascal_attempts
        out.append(result)
    return out


def combat_state_to_pascal(state: dict) -> dict:
    """
    Convert combat state to PascalCase for client consumption.

    Args:
        state: Combat state dict

    Returns:
        Dict with PascalCase keys
    """
    if not state:
        return {}

    out = {
        "Round": state.get("round", 1),
        "PlayerHealth": state.get("playerHealth", 0),
        "OpponentHealth": state.get("opponentHealth", 0),
        "PlayerWounds": state.get("playerWounds", 0),
        "OpponentWounds": state.get("opponentWounds", 0),
    }

    # Convert rounds array if present
    rounds = state.get("rounds", [])
    if rounds:
        pascal_rounds = []
        for round_data in rounds:
            pascal_round = {
                "Round": round_data.get("round", 0),
                "PlayerAction": round_data.get("playerAction", ""),
                "OpponentAction": round_data.get("opponentAction", ""),
                "PlayerRoll": round_data.get("playerRoll", 0),
                "OpponentRoll": round_data.get("opponentRoll", 0),
                "PlayerDamage": round_data.get("playerDamage", 0),
                "OpponentDamage": round_data.get("opponentDamage", 0),
                "Outcome": round_data.get("outcome", ""),
            }
            pascal_rounds.append(pascal_round)
        out["Rounds"] = pascal_rounds

    # Add final state fields
    if "victor" in state:
        out["Victor"] = state.get("victor")
    if "finalOutcome" in state:
        out["FinalOutcome"] = state.get("finalOutcome")

    return out


def events_to_pascal(events: list) -> list:
    """
    Convert client events to PascalCase for consistent API responses.

    Args:
        events: List of event dicts

    Returns:
        List with PascalCase keys
    """
    if not events:
        return []

    out = []
    for event in events:
        pascal_event = {}
        for key, value in event.items():
            # Special handling for known keys
            if key == "eventType":
                pascal_event["EventType"] = value
            elif key == "displayTime":
                pascal_event["DisplayTime"] = value
            elif key == "challengeResult":
                pascal_event["ChallengeResult"] = value
            else:
                # Generic PascalCase conversion
                pascal_event[to_pascal_key(key)] = value
        out.append(pascal_event)

    return out


def generate_combat_client_events(combat_state: dict) -> list:
    """
    Generate client events from combat state.

    Args:
        combat_state: Combat state with rounds

    Returns:
        List of client events
    """
    events = []
    if not combat_state:
        return events

    # Add event for each combat round
    for round_data in combat_state.get("rounds", []):
        event = ClientEvent(
            EventType="combat",
            Title=f"Round {round_data.get('round', 0)}",
            Description=f"{round_data.get('playerAction', 'Attack')} vs {round_data.get('opponentAction', 'Attack')}",
            Data=round_data,
        )
        events.append(event.model_dump(by_alias=True, exclude_none=True))

    # Add final combat outcome event
    victor = combat_state.get("victor")
    if victor:
        if victor == "player":
            title = "Victory!"
            description = "You have defeated your opponent."
        else:
            title = "Defeat"
            description = "You have been defeated in combat."

        event = ClientEvent(EventType="combat_result", Title=title, Description=description)
        events.append(event.model_dump(by_alias=True, exclude_none=True))

    return events


def generate_skill_check_events(challenge_results: list) -> list:
    """
    Generate client events from skill challenge results.

    Args:
        challenge_results: List of challenge results

    Returns:
        List of client events
    """
    events = []
    for challenge in challenge_results:
        skill = challenge.get("skill", "")
        attribute = challenge.get("attribute", "")
        passed = challenge.get("passed", False)

        if passed:
            title = f"{skill or attribute} Success"
            description = f"You succeeded at the {skill or attribute} challenge."
        else:
            title = f"{skill or attribute} Failure"
            description = f"You failed the {skill or attribute} challenge."

        event = ClientEvent(EventType="skill_check", Title=title, Description=description, Data=challenge)
        events.append(event.model_dump(by_alias=True, exclude_none=True))

    return events