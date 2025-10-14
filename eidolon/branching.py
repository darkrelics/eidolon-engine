"""
Weighted branching for decision segment timeout behavior.

Provides server-side random branch selection for decision timeouts.
"""

import secrets

from eidolon.logger import logger

# Scale factor for weighted random selection (1,000,000 = 6 decimal places; chosen to minimize floating point errors)
RANDOM_SCALE_FACTOR = 1_000_000


def validate_branch_weights(branches: list) -> bool:
    """
    Validate that branch weights sum to 1.0 (with tolerance).

    Args:
        branches: List of branch definitions with Weight field

    Returns:
        True if valid, raises ValueError otherwise

    Raises:
        ValueError: If weights don't sum to 1.0
    """
    if not branches:
        raise ValueError("Branches list cannot be empty")

    total_weight = sum(b.get("Weight", 0) for b in branches)
    tolerance = 0.001  # Allow for floating point precision

    if abs(total_weight - 1.0) > tolerance:
        raise ValueError(f"Branch weights sum to {total_weight}, expected 1.0 (tolerance: {tolerance})")

    return True


def select_weighted_branch(branches: list) -> tuple:
    """
    Select a branch using weighted random selection.

    Uses cryptographically secure randomness.

    Args:
        branches: List of (index, branch) tuples

    Returns:
        Tuple of (original_index, selected_branch)

    Raises:
        ValueError: If branches list is empty or weights invalid
    """
    if not branches:
        raise ValueError("No available branches to select from")

    # Extract branch dicts for weight validation
    branch_dicts = [b for _, b in branches]

    # Validate weights
    validate_branch_weights(branch_dicts)

    # Generate random value using cryptographically secure randomness
    selection = secrets.randbelow(RANDOM_SCALE_FACTOR) / float(RANDOM_SCALE_FACTOR)

    # Weighted selection using cumulative distribution
    cumulative = 0.0
    for original_idx, branch in branches:
        cumulative += branch.get("Weight", 0)
        if selection <= cumulative:
            logger.info(
                f"Selected branch {original_idx} ({branch.get('Label', 'unlabeled')}) "
                f"with weight {branch.get('Weight')} (roll: {selection:.4f})"
            )
            return original_idx, branch

    # Fallback to last branch (shouldn't happen with valid weights)
    logger.warning(f"Weighted selection fell through, using last branch (selection: {selection})")
    return branches[-1]
