"""
Validate story branching configuration.

Checks:
- Branch weights sum to 1.0
- All NextSegmentIDs reference valid segments
- Prerequisites reference valid skills/attributes
- No circular branch dependencies
"""

import json
import sys
from pathlib import Path


def validate_branch_weights(branches: list, segment_id: str, outcome: str) -> list:
    """Validate that branch weights sum to 1.0."""
    errors = []

    if not branches:
        return errors

    total_weight = sum(b.get("Weight", 0) for b in branches)
    tolerance = 0.001

    if abs(total_weight - 1.0) > tolerance:
        errors.append(
            f"Segment {segment_id}, outcome {outcome}: weights sum to {total_weight}, expected 1.0 (tolerance: {tolerance})"
        )

    # Check individual branch structure
    for i, branch in enumerate(branches):
        if "Weight" not in branch:
            errors.append(f"Segment {segment_id}, outcome {outcome}, branch {i}: missing Weight field")

        if "NextSegmentID" not in branch:
            errors.append(f"Segment {segment_id}, outcome {outcome}, branch {i}: missing NextSegmentID field")

        # Optional Label for analytics
        if "Label" in branch and not isinstance(branch["Label"], str):
            errors.append(f"Segment {segment_id}, outcome {outcome}, branch {i}: Label must be string")

    return errors


def validate_prerequisites(prereqs: dict, segment_id: str, branch_idx: int) -> list:
    """Validate prerequisite structure."""
    errors = []

    if not prereqs:
        return errors

    # Check MinSkills structure
    min_skills = prereqs.get("MinSkills", {})
    if min_skills and not isinstance(min_skills, dict):
        errors.append(f"Segment {segment_id}, branch {branch_idx}: MinSkills must be dict")
    else:
        for skill, value in min_skills.items():
            if not isinstance(value, (int, float)):
                errors.append(f"Segment {segment_id}, branch {branch_idx}: MinSkills.{skill} must be numeric")

    # Check MinAttributes structure
    min_attrs = prereqs.get("MinAttributes", {})
    if min_attrs and not isinstance(min_attrs, dict):
        errors.append(f"Segment {segment_id}, branch {branch_idx}: MinAttributes must be dict")
    else:
        for attr, value in min_attrs.items():
            if not isinstance(value, (int, float)):
                errors.append(f"Segment {segment_id}, branch {branch_idx}: MinAttributes.{attr} must be numeric")

    # Check RequiredItems structure
    required_items = prereqs.get("RequiredItems", [])
    if required_items and not isinstance(required_items, list):
        errors.append(f"Segment {segment_id}, branch {branch_idx}: RequiredItems must be list")

    return errors


def validate_segment_branches(segment: dict, segment_ids: set) -> list:
    """Validate branches in a single segment."""
    errors = []
    segment_id = segment.get("SegmentID", "unknown")
    segment_type = segment.get("SegmentType")

    # Check mechanical/rest segments for branching
    if segment_type in ["mechanical", "rest"]:
        results = segment.get("Results", {})

        for outcome, outcome_data in results.items():
            if not isinstance(outcome_data, dict):
                continue

            branches = outcome_data.get("Branches")

            if branches:
                # Validate weights
                errors.extend(validate_branch_weights(branches, segment_id, outcome))

                # Validate each branch
                for i, branch in enumerate(branches):
                    # Check NextSegmentID exists
                    next_id = branch.get("NextSegmentID")
                    if next_id and next_id not in segment_ids:
                        errors.append(
                            f"Segment {segment_id}, outcome {outcome}, branch {i}: NextSegmentID '{next_id}' not found in story"
                        )

                    # Validate prerequisites
                    prereqs = branch.get("Prerequisites", {})
                    if prereqs:
                        errors.extend(validate_prerequisites(prereqs, segment_id, i))

            # Check fallback
            fallback = outcome_data.get("FallbackSegmentID")
            if fallback and fallback not in segment_ids:
                errors.append(f"Segment {segment_id}, outcome {outcome}: FallbackSegmentID '{fallback}' not found in story")

    # Check decision segments for weighted timeouts
    elif segment_type == "decision":
        timeout_behavior = segment.get("TimeoutBehavior", {})
        if timeout_behavior.get("Type") == "weighted":
            branches = timeout_behavior.get("Branches", [])

            if branches:
                # Validate weights
                total = sum(b.get("Weight", 0) for b in branches)
                if abs(total - 1.0) > 0.001:
                    errors.append(f"Segment {segment_id}: TimeoutBehavior weights sum to {total}, expected 1.0")

                # Check each branch references valid decision
                decision_options = segment.get("DecisionOptions", {})
                for i, branch in enumerate(branches):
                    decision = branch.get("Decision")
                    if decision not in decision_options:
                        errors.append(f"Segment {segment_id}, timeout branch {i}: Decision '{decision}' not in DecisionOptions")

    return errors


def detect_circular_dependencies(segments: list) -> list:
    """Detect circular branch dependencies."""
    errors = []

    # Build adjacency graph
    graph = {}
    for segment in segments:
        segment_id = segment.get("SegmentID")
        successors = set()

        # Collect all possible next segments
        segment_type = segment.get("SegmentType")

        if segment_type == "decision":
            decision_options = segment.get("DecisionOptions", {})
            for decision_value in decision_options.values():
                if isinstance(decision_value, dict):
                    next_id = decision_value.get("NextSegmentID")
                else:
                    next_id = decision_value
                if next_id:
                    successors.add(next_id)

        elif segment_type in ["mechanical", "rest"]:
            results = segment.get("Results", {})
            for outcome_data in results.values():
                if not isinstance(outcome_data, dict):
                    continue

                branches = outcome_data.get("Branches", [])
                for branch in branches:
                    next_id = branch.get("NextSegmentID")
                    if next_id:
                        successors.add(next_id)

                fallback = outcome_data.get("FallbackSegmentID")
                if fallback:
                    successors.add(fallback)

        graph[segment_id] = successors

    # Check for cycles using DFS
    def has_cycle(node, visited, rec_stack):
        visited.add(node)
        rec_stack.add(node)

        for neighbor in graph.get(node, set()):
            if neighbor not in visited:
                if has_cycle(neighbor, visited, rec_stack):
                    return True
            elif neighbor in rec_stack:
                return True

        rec_stack.remove(node)
        return False

    visited = set()
    for segment_id in graph:
        if segment_id not in visited:
            rec_stack = set()
            if has_cycle(segment_id, visited, rec_stack):
                errors.append(f"Circular dependency detected involving segment: {segment_id}")

    return errors


def validate_story_file(file_path: Path) -> tuple:
    """Validate a single story JSON file."""
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as err:
        return [f"Invalid JSON in {file_path}: {err}"], 0
    except Exception as err:
        return [f"Failed to read {file_path}: {err}"], 0

    # Handle both direct format and nested "Stories" format
    segments = []
    if "Stories" in data:
        # Nested format: {"Stories": [{"Story": {...}, "Segments": [...]}]}
        for story_entry in data["Stories"]:
            segments.extend(story_entry.get("Segments", []))
    else:
        # Direct format: {"Segments": [...]}
        segments = data.get("Segments", [])

    segment_ids = {s.get("SegmentID") for s in segments if s.get("SegmentID")}

    errors = []

    # Validate each segment
    for segment in segments:
        errors.extend(validate_segment_branches(segment, segment_ids))

    # Check for circular dependencies
    errors.extend(detect_circular_dependencies(segments))

    return errors, len(segments)


def main():
    """Validate all story files in data directory."""
    # Find story JSON files
    data_dir = Path(__file__).parent.parent / "data"
    story_files = list(data_dir.glob("*story*.json"))

    if not story_files:
        print("No story files found in data directory")
        return 0

    total_errors = []
    total_segments = 0

    for story_file in story_files:
        print(f"\nValidating {story_file.name}...")
        errors, segment_count = validate_story_file(story_file)
        total_segments += segment_count

        if errors:
            print(f"  [FAIL] {len(errors)} error(s) found:")
            for error in errors:
                print(f"    - {error}")
            total_errors.extend(errors)
        else:
            print(f"  [PASS] Valid ({segment_count} segments)")

    print(f"\n{'='*60}")
    print("Validation Summary:")
    print(f"  Files checked: {len(story_files)}")
    print(f"  Total segments: {total_segments}")
    print(f"  Total errors: {len(total_errors)}")

    if total_errors:
        print("\n[FAIL] Validation FAILED")
        return 1
    else:
        print("\n[PASS] All stories valid")
        return 0


if __name__ == "__main__":
    sys.exit(main())
