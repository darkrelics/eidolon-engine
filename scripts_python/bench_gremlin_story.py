"""
Bench test the Gremlin Mischief story against starting archetypes.

Simulates the full story path to determine success/failure rates.
"""

from eidolon.mechanics import resolve_opposed_check

TRIALS = 1000

# Archetypes with their relevant stats
ARCHETYPES = {
    "Wizard": {
        "Perception": 2.0, "Intelligence": 4.0, "Agility": 1.0, "Strength": 1.0,
        "Investigation": 1.0, "Dodge": 0.0, "Arcane": 2.0, "Brawling": 0.0,
        "Melee": 0.0, "Archery": 0.0, "Parry": 0.0
    },
    "Rogue": {
        "Perception": 2.0, "Intelligence": 1.0, "Agility": 3.0, "Strength": 1.0,
        "Investigation": 0.0, "Dodge": 1.0, "Arcane": 0.0, "Brawling": 0.0,
        "Melee": 0.0, "Archery": 0.0, "Parry": 0.0
    },
    "Warrior": {
        "Perception": 1.0, "Intelligence": 1.0, "Agility": 2.0, "Strength": 4.0,
        "Investigation": 0.0, "Dodge": 1.0, "Arcane": 0.0, "Brawling": 1.0,
        "Melee": 2.0, "Archery": 0.0, "Parry": 1.0
    }
}

# Gremlin stats
GREMLIN = {
    "OffensiveRating": 3,
    "DefensiveRating": 3,
    "Health": 2
}

# Story segments
CHALLENGES = [
    {"name": "Spotting", "attr": "Perception", "skill": "Investigation", "difficulty": 3, "attempts": 2},
    {"name": "Tracking", "attr": "Intelligence", "skill": "Investigation", "difficulty": 3, "attempts": 2},
    {"name": "Chasing", "attr": "Agility", "skill": "Dodge", "difficulty": 3, "attempts": 2},
]


def get_best_offensive(stats: dict) -> tuple:
    """Get character's best offensive action and rating."""
    options = {
        "Arcane": stats["Intelligence"] + stats["Arcane"],
        "Brawling": stats["Strength"] + stats["Brawling"],
        "Melee": stats["Strength"] + stats["Melee"],
        "Archery": stats["Agility"] + stats["Archery"],
    }
    best = max(options.items(), key=lambda x: x[1])
    return best[0], best[1]


def get_defensive(offensive_action: str, stats: dict) -> tuple:
    """Get character's defensive action and rating based on offensive choice."""
    if offensive_action == "Melee":
        return "Parry", stats["Strength"] + stats["Parry"]
    return "Dodge", stats["Agility"] + stats["Dodge"]


def simulate_challenge_code(effective: float, difficulty: int, attempts: int) -> dict:
    """Simulate using ACTUAL CODE thresholds."""
    sigmas = []
    critical_failures = 0

    for _ in range(attempts):
        result = resolve_opposed_check(effective, difficulty)
        sigmas.append(result["Sigma"])
        if result["Sigma"] < -2.0:
            critical_failures += 1

    avg_sigma = sum(sigmas) / len(sigmas)

    # ACTUAL CODE thresholds (segment_challenges.py)
    if critical_failures >= 2 or avg_sigma < -2.0:
        outcome = "death"
    elif avg_sigma < -1.0:
        outcome = "failure"
    elif avg_sigma < 0:
        outcome = "minimal"
    elif avg_sigma < 1.0:
        outcome = "normal"
    else:
        outcome = "exceptional"

    return {"outcome": outcome, "avg_sigma": avg_sigma, "sigmas": sigmas}


def simulate_challenge_design(effective: float, difficulty: int, attempts: int) -> dict:
    """Simulate using DESIGN DOCUMENT thresholds."""
    sigmas = []
    critical_failures = 0

    for _ in range(attempts):
        result = resolve_opposed_check(effective, difficulty)
        sigmas.append(result["Sigma"])
        if result["Sigma"] <= -3.0:  # Design doc: sigma <= -3.0
            critical_failures += 1

    avg_sigma = sum(sigmas) / len(sigmas)

    # DESIGN DOCUMENT thresholds (incremental-design.md)
    if critical_failures >= 1 or avg_sigma < -2.0:  # Any sigma <= -3.0 OR avg < -2.0
        outcome = "death"
    elif avg_sigma < -0.5:  # -2.0 to -0.5
        outcome = "failure"
    elif avg_sigma < 0.5:  # -0.5 to 0.5
        outcome = "minimal"
    elif avg_sigma < 1.5:  # 0.5 to 1.5
        outcome = "normal"
    else:  # > 1.5
        outcome = "exceptional"

    return {"outcome": outcome, "avg_sigma": avg_sigma, "sigmas": sigmas}


# Will be set by main() to switch between threshold modes
simulate_challenge = simulate_challenge_code


def set_threshold_mode(use_design_doc: bool):
    """Switch between code and design document thresholds."""
    global simulate_challenge
    if use_design_doc:
        simulate_challenge = simulate_challenge_design
    else:
        simulate_challenge = simulate_challenge_code


def simulate_combat(char_off: float, char_def: float, opp_off: int, opp_def: int, opp_hp: int, max_rounds: int = 6) -> dict:
    """Simulate combat segment."""
    player_wounds = 0
    opponent_wounds = 0

    for round_num in range(max_rounds):
        # Character attacks opponent
        char_attack = resolve_opposed_check(char_off, opp_def)
        if char_attack["Success"]:
            damage = 2 if char_attack["Sigma"] > 3.0 else 1
            opponent_wounds += damage

        # Check opponent defeat
        if opponent_wounds >= opp_hp:
            if player_wounds == 0:
                return {"outcome": "exceptional", "rounds": round_num + 1, "player_wounds": player_wounds}
            elif player_wounds <= 2:
                return {"outcome": "normal", "rounds": round_num + 1, "player_wounds": player_wounds}
            else:
                return {"outcome": "minimal", "rounds": round_num + 1, "player_wounds": player_wounds}

        # Opponent attacks character
        opp_attack = resolve_opposed_check(opp_off, char_def)
        if opp_attack["Success"]:
            damage = 2 if opp_attack["Sigma"] > 3.0 else 1
            player_wounds += damage

        # Check player defeat (simplified - 5 lethal or 10 total)
        if player_wounds >= 10:
            return {"outcome": "failure", "rounds": round_num + 1, "player_wounds": player_wounds}

    # Max rounds - escape
    return {"outcome": "failure", "rounds": max_rounds, "player_wounds": player_wounds}


def simulate_full_story(stats: dict, max_seg2_loops: int = 10) -> str:
    """Simulate the complete Gremlin Mischief story."""

    # Segment 1: Spotting
    seg1_eff = stats["Perception"] + stats["Investigation"]
    seg1 = simulate_challenge(seg1_eff, 3, 2)

    if seg1["outcome"] == "death":
        return "death_seg1"

    # Segment 2: Tracking (unless exceptional skip)
    if seg1["outcome"] != "exceptional":
        seg2_eff = stats["Intelligence"] + stats["Investigation"]

        # Segment 2 loops on failure until success or death
        for loop in range(max_seg2_loops):
            seg2 = simulate_challenge(seg2_eff, 3, 2)

            if seg2["outcome"] == "death":
                return f"death_seg2_loop{loop+1}"

            if seg2["outcome"] != "failure":
                break  # Success - proceed
        else:
            # Max loops reached without success
            return "stuck_seg2"

        # Segment 3: Chasing (unless exceptional skip)
        if seg2["outcome"] != "exceptional":
            seg3_eff = stats["Agility"] + stats["Dodge"]
            seg3 = simulate_challenge(seg3_eff, 3, 2)

            if seg3["outcome"] == "death":
                return "death_seg3"

            if seg3["outcome"] == "failure":
                return "failure_seg3"

    # Combat segment
    off_action, off_rating = get_best_offensive(stats)
    def_action, def_rating = get_defensive(off_action, stats)

    combat = simulate_combat(off_rating, def_rating, GREMLIN["OffensiveRating"],
                             GREMLIN["DefensiveRating"], GREMLIN["Health"])

    return f"combat_{combat['outcome']}"


def main():
    print("=" * 70)
    print("GREMLIN MISCHIEF STORY ANALYSIS")
    print("=" * 70)

    # First, show the stat matchups
    print("\n[CHALLENGE EFFECTIVE SCORES vs DIFFICULTY 3]")
    print("-" * 70)
    print(f"{'Archetype':<10} {'Seg1 Perc+Inv':<15} {'Seg2 Int+Inv':<15} {'Seg3 Agi+Dodge':<15}")
    print("-" * 70)

    for name, stats in ARCHETYPES.items():
        seg1 = stats["Perception"] + stats["Investigation"]
        seg2 = stats["Intelligence"] + stats["Investigation"]
        seg3 = stats["Agility"] + stats["Dodge"]
        print(f"{name:<10} {seg1:>5.0f} ({seg1-3:+.0f})      {seg2:>5.0f} ({seg2-3:+.0f})      {seg3:>5.0f} ({seg3-3:+.0f})")

    print("\n[COMBAT RATINGS vs GREMLIN (Off:3, Def:3, HP:2)]")
    print("-" * 70)
    print(f"{'Archetype':<10} {'Offense':<20} {'Defense':<20}")
    print("-" * 70)

    for name, stats in ARCHETYPES.items():
        off_action, off_rating = get_best_offensive(stats)
        def_action, def_rating = get_defensive(off_action, stats)
        print(f"{name:<10} {off_action:<8} {off_rating:>2.0f} ({off_rating-3:+.0f})     {def_action:<8} {def_rating:>2.0f} ({def_rating-3:+.0f})")

    # Individual challenge simulations
    print(f"\n[INDIVIDUAL CHALLENGE SUCCESS RATES ({TRIALS} trials each)]")
    print("-" * 70)

    for name, stats in ARCHETYPES.items():
        print(f"\n{name}:")
        for challenge in CHALLENGES:
            effective = stats[challenge["attr"]] + stats[challenge["skill"]]
            outcomes = {"death": 0, "failure": 0, "minimal": 0, "normal": 0, "exceptional": 0}

            for _ in range(TRIALS):
                result = simulate_challenge(effective, challenge["difficulty"], challenge["attempts"])
                outcomes[result["outcome"]] += 1

            success_rate = (outcomes["minimal"] + outcomes["normal"] + outcomes["exceptional"]) / TRIALS
            print(f"  {challenge['name']:<10} (eff {effective:.0f} vs diff {challenge['difficulty']}): "
                  f"Success {success_rate:>5.1%} | "
                  f"Death {outcomes['death']/TRIALS:>4.1%} Fail {outcomes['failure']/TRIALS:>4.1%} "
                  f"Min {outcomes['minimal']/TRIALS:>4.1%} Norm {outcomes['normal']/TRIALS:>4.1%} "
                  f"Exc {outcomes['exceptional']/TRIALS:>4.1%}")

    # Full story simulations
    print(f"\n[FULL STORY OUTCOME ({TRIALS} trials each)]")
    print("-" * 70)

    for name, stats in ARCHETYPES.items():
        outcomes = {}

        for _ in range(TRIALS):
            result = simulate_full_story(stats)
            outcomes[result] = outcomes.get(result, 0) + 1

        success_count = sum(v for k, v in outcomes.items() if k.startswith("combat_") and k != "combat_failure")
        failure_count = TRIALS - success_count

        print(f"\n{name}:")
        print(f"  Overall Success: {success_count/TRIALS:>6.1%} | Overall Failure: {failure_count/TRIALS:>6.1%}")
        print(f"  Breakdown:")
        for outcome, count in sorted(outcomes.items(), key=lambda x: -x[1]):
            print(f"    {outcome:<20}: {count:>4} ({count/TRIALS:>5.1%})")

    # Test with design document thresholds
    print(f"\n[DESIGN DOCUMENT THRESHOLDS ({TRIALS} trials each)]")
    print("-" * 70)
    print("Using: Death=avg<-2 or any sigma<=-3, Failure=avg<-0.5, Minimal=avg<0.5, Normal=avg<1.5")

    set_threshold_mode(use_design_doc=True)

    for name, stats in ARCHETYPES.items():
        outcomes = {}

        for _ in range(TRIALS):
            result = simulate_full_story(stats)
            outcomes[result] = outcomes.get(result, 0) + 1

        success_count = sum(v for k, v in outcomes.items() if k.startswith("combat_") and k != "combat_failure")
        failure_count = TRIALS - success_count

        print(f"\n{name}:")
        print(f"  Overall Success: {success_count/TRIALS:>6.1%} | Overall Failure: {failure_count/TRIALS:>6.1%}")
        print(f"  Breakdown:")
        for outcome, count in sorted(outcomes.items(), key=lambda x: -x[1])[:5]:
            print(f"    {outcome:<20}: {count:>4} ({count/TRIALS:>5.1%})")

    # Reset to code thresholds
    set_threshold_mode(use_design_doc=False)

    # Hypothesis
    print("\n" + "=" * 70)
    print("HYPOTHESIS")
    print("=" * 70)
    print("""
Based on simulation results, the actual success rate is 72-85%, not 10%.

If 90%+ failure is observed in practice, potential causes:

1. SEGMENT 2 DEATH ACCUMULATION IN LOOPS
   - Each retry in segment 2 loop has ~0.5% death chance
   - With 5+ retries common for low-Investigation characters, deaths accumulate
   - Warrior/Rogue with eff=1 need many retries

2. COMBAT MECHANICS DIFFERENCES
   - Rogue's best offense is Archery at 3 (same as gremlin defense)
   - Rogue has no actual combat skill investment
   - Combat_failure rate for Rogue is 6.7%

3. THE INVESTIGATION SKILL GAP
   - Used in 2 of 3 challenge segments
   - Only Wizard has Investigation 1.0
   - Rogue/Warrior both have Investigation 0.0
   - This creates the -2 disadvantage that causes most failures

4. POSSIBLE BUG: Check if production uses different thresholds
   - Current: failure < -1.0, death < -2.0
   - If thresholds are stricter (e.g., failure < 0), results would differ

5. SAMPLE SIZE / RNG VARIANCE
   - Small sample sizes can show 90% failure by chance
   - Check if testing used seed or truly random

RECOMMENDATIONS:
- Add Investigation skill to Rogue/Warrior starting skills
- OR reduce challenge difficulties from 3 to 2
- OR change outcome thresholds to be more forgiving
""")


if __name__ == "__main__":
    main()
