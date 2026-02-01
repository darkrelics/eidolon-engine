"""
Simulate opposed checks between aggressor and defender.

Usage:
    python simulate_opposed_checks.py <agg_attr> <agg_skill> <def_attr> <def_skill>

Example:
    python simulate_opposed_checks.py 5 3 4 2
"""

import argparse

from eidolon.mechanics import resolve_opposed_check


def run_simulation(agg_attr: float, agg_skill: float, def_attr: float, def_skill: float, trials: int = 100):
    """Run multiple opposed checks and report results."""
    agg_effective = agg_attr + agg_skill
    def_effective = def_attr + def_skill

    agg_wins = 0
    def_wins = 0
    sigma_sum = 0.0

    for _ in range(trials):
        result = resolve_opposed_check(agg_effective, def_effective)
        if result["Success"]:
            agg_wins += 1
        else:
            def_wins += 1
        sigma_sum += result["Sigma"]

    return {
        "trials": trials,
        "aggressor_effective": agg_effective,
        "defender_effective": def_effective,
        "aggressor_wins": agg_wins,
        "defender_wins": def_wins,
        "aggressor_ratio": agg_wins / trials,
        "defender_ratio": def_wins / trials,
        "average_sigma": sigma_sum / trials,
    }


def main():
    parser = argparse.ArgumentParser(description="Simulate opposed checks between aggressor and defender")
    parser.add_argument("agg_attr", type=float, help="Aggressor attribute value")
    parser.add_argument("agg_skill", type=float, help="Aggressor skill value")
    parser.add_argument("def_attr", type=float, help="Defender attribute value")
    parser.add_argument("def_skill", type=float, help="Defender skill value")
    parser.add_argument("--trials", type=int, default=100, help="Number of trials (default: 100)")

    args = parser.parse_args()

    results = run_simulation(args.agg_attr, args.agg_skill, args.def_attr, args.def_skill, args.trials)

    print(f"\nOpposed Check Simulation Results")
    print(f"================================")
    print(f"Trials: {results['trials']}")
    print(f"")
    print(f"Aggressor: attr={args.agg_attr} skill={args.agg_skill} -> effective={results['aggressor_effective']}")
    print(f"Defender:  attr={args.def_attr} skill={args.def_skill} -> effective={results['defender_effective']}")
    print(f"Difference: {results['aggressor_effective'] - results['defender_effective']:+.1f}")
    print(f"")
    print(f"Results:")
    print(f"  Aggressor wins: {results['aggressor_wins']:3d} ({results['aggressor_ratio']:.1%})")
    print(f"  Defender wins:  {results['defender_wins']:3d} ({results['defender_ratio']:.1%})")
    print(f"  Average sigma:  {results['average_sigma']:+.3f}")


if __name__ == "__main__":
    main()
