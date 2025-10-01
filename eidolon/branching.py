"""
Weighted branching and conditional path selection for story segments.

Provides server-side random branch selection with stat/item prerequisites.
"""

import secrets

from eidolon.logger import logger


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


def check_branch_prerequisites(branch: dict, character: dict) -> bool:
    """
    Check if character meets branch prerequisites.

    Args:
        branch: Branch definition with optional Prerequisites field
        character: Character record with Skills, Attributes, Inventory

    Returns:
        True if all prerequisites are met
    """
    prereqs = branch.get("Prerequisites", {})

    # No prerequisites = always available
    if not prereqs:
        return True

    # Check minimum skills
    min_skills = prereqs.get("MinSkills", {})
    char_skills = character.get("Skills", {})
    for skill, min_val in min_skills.items():
        if char_skills.get(skill, 0) < min_val:
            logger.debug(f"Branch {branch.get('Label', 'unlabeled')} filtered: {skill} {char_skills.get(skill, 0)} < {min_val}")
            return False

    # Check minimum attributes
    min_attrs = prereqs.get("MinAttributes", {})
    char_attrs = character.get("Attributes", {})
    for attr, min_val in min_attrs.items():
        if char_attrs.get(attr, 0) < min_val:
            logger.debug(f"Branch {branch.get('Label', 'unlabeled')} filtered: {attr} {char_attrs.get(attr, 0)} < {min_val}")
            return False

    # Check required items (prototype IDs in inventory)
    required_items = prereqs.get("RequiredItems", [])
    if required_items:
        char_inventory = character.get("Inventory", {})
        # Simplified check - assumes presence of any item passes
        # Item prototype validation will be added when item system is implemented
        if not char_inventory:
            logger.debug(f"Branch {branch.get('Label', 'unlabeled')} filtered: no inventory")
            return False

    return True


def filter_branches_by_prerequisites(branches: list, character: dict) -> list:
    """
    Filter branches based on character prerequisites.

    Args:
        branches: List of branch definitions
        character: Character record with Skills, Attributes, Inventory

    Returns:
        List of (original_index, branch) tuples that passed prerequisites
    """
    available = []

    for idx, branch in enumerate(branches):
        if check_branch_prerequisites(branch, character):
            available.append((idx, branch))

    logger.info(f"Filtered branches: {len(available)}/{len(branches)} available after prerequisite check")
    return available


def select_weighted_branch(branches: list) -> tuple:
    """
    Select a branch using weighted random selection.

    Uses cryptographically secure randomness.

    Args:
        branches: List of (index, branch) tuples (already filtered)

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
    selection = secrets.randbelow(1_000_000) / 1_000_000.0

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


def select_next_branch(outcome_result: dict, character: dict) -> dict:
    """
    Select next branch from outcome result using weighted random selection.

    Args:
        outcome_result: Result dict from segment definition containing Branches array
        character: Character record for prerequisite checking

    Returns:
        Dict with:
          - NextSegmentID: Selected segment ID (or empty string if story ends)
          - BranchMetadata: Tracking info for history

    Raises:
        ValueError: If branch selection fails
    """
    branches = outcome_result.get("Branches", [])

    # No branches = story ends
    if not branches:
        logger.info("No branches defined, story ends")
        return {
            "NextSegmentID": "",
            "BranchMetadata": {"SelectionMethod": "no_branches", "BranchLabel": "", "BranchIndex": -1},
        }

    # Filter by prerequisites
    available = filter_branches_by_prerequisites(branches, character)

    if not available:
        # No branches passed prerequisites - use fallback or end story
        fallback = outcome_result.get("FallbackSegmentID", "")
        if fallback:
            logger.warning(f"No branches passed prerequisites, using fallback: {fallback}")
            return {
                "NextSegmentID": fallback,
                "BranchMetadata": {
                    "SelectionMethod": "prerequisite_fallback",
                    "BranchLabel": "fallback",
                    "BranchIndex": -1,
                    "TotalBranches": len(branches),
                    "AvailableBranches": 0,
                },
            }
        else:
            logger.warning("No branches passed prerequisites and no fallback defined, story ends")
            return {
                "NextSegmentID": "",
                "BranchMetadata": {
                    "SelectionMethod": "no_available_branches",
                    "BranchLabel": "",
                    "BranchIndex": -1,
                    "TotalBranches": len(branches),
                    "AvailableBranches": 0,
                },
            }

    # Renormalize weights for available branches only
    total_available_weight = sum(b.get("Weight", 0) for _, b in available)
    if total_available_weight <= 0:
        raise ValueError("Available branches have total weight <= 0")

    renormalized = []
    for idx, branch in available:
        normalized_branch = branch.copy()
        normalized_branch["Weight"] = branch["Weight"] / total_available_weight
        renormalized.append((idx, normalized_branch))

    # Select weighted branch
    selected_idx, selected_branch = select_weighted_branch(renormalized)

    return {
        "NextSegmentID": selected_branch.get("NextSegmentID", ""),
        "BranchMetadata": {
            "SelectionMethod": "weighted_random",
            "BranchLabel": selected_branch.get("Label", ""),
            "BranchIndex": selected_idx,
            "TotalBranches": len(branches),
            "AvailableBranches": len(available),
        },
    }
