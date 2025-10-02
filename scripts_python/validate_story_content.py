"""
Validates story segment data offline using strict boundary validation.
"""

import json
import sys
from pathlib import Path


def validate_mechanical_segment(segment: dict):
    """Validate a mechanical segment structure."""
    errors = []
    warnings = []

    results = segment.get("Results", {})
    if results:
        for outcome in ["Death", "Failure", "Minimal", "Normal", "Exceptional"]:
            if outcome in results:
                outcome_data = results[outcome]

                # Narrative should be string (can be empty for normal)
                if "Narrative" in outcome_data:
                    if not isinstance(outcome_data["Narrative"], str):
                        errors.append(f"  - {outcome} Narrative is not a string")

                # Effects should be dict if present
                if "Effects" in outcome_data:
                    if not isinstance(outcome_data["Effects"], dict):
                        errors.append(f"  - {outcome} Effects is not a dict")

                # NextSegmentID should be non-empty string if present
                if "NextSegmentID" in outcome_data:
                    next_id = outcome_data["NextSegmentID"]
                    if next_id is not None and not (isinstance(next_id, str) and next_id):
                        errors.append(f"  - {outcome} NextSegmentID is not a non-empty string")

    challenges = segment.get("Challenges", [])
    for i, challenge in enumerate(challenges):
        if "Attribute" not in challenge:
            errors.append(f"  - Challenge {i+1} missing Attribute field")
        if "Skill" not in challenge:
            errors.append(f"  - Challenge {i+1} missing Skill field")

        # Check Difficulty is numeric
        difficulty = challenge.get("Difficulty")
        if difficulty is not None and not isinstance(difficulty, (int, float)):
            errors.append(f"  - Challenge {i+1} Difficulty is not numeric")

        # Check Attempts is int >= 1
        attempts = challenge.get("Attempts")
        if attempts is not None and (not isinstance(attempts, int) or attempts < 1):
            errors.append(f"  - Challenge {i+1} Attempts must be int >= 1")

    # Check Combat if present and actually has opponent
    combat = segment.get("Combat", {})
    if combat and combat.get("OpponentID"):
        # Only validate Combat if it has an OpponentID (real combat)
        max_rounds = combat.get("MaxRounds")
        if max_rounds is not None:
            if not isinstance(max_rounds, int) or max_rounds < 1:
                errors.append("  - Combat MaxRounds must be int >= 1")

    return errors, warnings


def validate_decision_segment(segment: dict):
    """Validate a decision segment structure."""
    errors = []
    warnings = []

    # DecisionOptions must be dict with at least one entry
    options = segment.get("DecisionOptions", {})
    if not isinstance(options, dict):
        errors.append("  - DecisionOptions is not a dict")
    elif len(options) == 0:
        errors.append("  - DecisionOptions has no entries")

    # DefaultDecision must be valid option if present
    default = segment.get("DefaultDecision")
    if default is not None:
        if default not in options:
            errors.append(f"  - DefaultDecision '{default}' not in DecisionOptions")

    return errors, warnings


def validate_rest_segment(segment: dict):
    """Validate a rest segment structure."""
    errors = []
    warnings = []

    # SegmentDuration must be positive int
    duration = segment.get("SegmentDuration")
    if duration is None:
        errors.append("  - Missing SegmentDuration")
    elif not isinstance(duration, int) or duration <= 0:
        errors.append("  - SegmentDuration must be positive int")

    return errors, warnings


def validate_story_content(story_file: Path) -> bool:
    """
    Validate all segments in a story file.

    Returns:
        True if validation passes (no hard errors), False otherwise.
    """
    print("=" * 60)
    print("Story Content Validation")
    print("=" * 60)

    # Load story data
    try:
        with open(story_file, "r", encoding="utf-8") as f:
            story_data = json.load(f)
    except Exception as err:
        print(f"ERROR: Failed to load story file: {err}")
        return False

    # Handle both formats:
    # 1. Flat format: {"Segments": [...]}
    # 2. DynamoDB format: {"Stories": [{"Story": {...}, "Segments": [...]}]}
    segments_to_validate = []

    if "Segments" in story_data:
        # Flat format
        segments_to_validate = story_data["Segments"]
    elif "Stories" in story_data:
        # DynamoDB wrapper format
        for story_entry in story_data["Stories"]:
            if "Segments" in story_entry:
                segments_to_validate.extend(story_entry["Segments"])
    else:
        print("ERROR: No Segments array or Stories wrapper in story data")
        return False

    if not segments_to_validate:
        print("ERROR: No segments found to validate")
        return False

    total_errors = 0
    total_warnings = 0

    # Validate each segment
    for segment in segments_to_validate:
        segment_id = segment.get("SegmentID", "unknown")
        segment_type = segment.get("SegmentType", "unknown")

        print(f"\nSegment: {segment_id}")
        print(f"Type: {segment_type}")

        # Validate based on type
        errors = []
        warnings = []

        if segment_type == "mechanical":
            errors, warnings = validate_mechanical_segment(segment)
        elif segment_type == "decision":
            errors, warnings = validate_decision_segment(segment)
        elif segment_type == "rest":
            errors, warnings = validate_rest_segment(segment)
        else:
            errors.append(f"  - Unknown segment type: {segment_type}")

        # Report results
        if errors:
            print("  ERRORS:")
            for error in errors:
                print(f"    {error}")
            total_errors += len(errors)

        if warnings:
            print("  WARNINGS:")
            for warning in warnings:
                print(f"    {warning}")
            total_warnings += len(warnings)

        if not errors and not warnings:
            print("  Valid")

    # Summary
    print("\n" + "=" * 60)
    print("Validation Summary")
    print("-" * 60)
    print(f"Total Errors: {total_errors}")
    print(f"Total Warnings: {total_warnings}")

    if total_errors == 0:
        print("\nVALIDATION PASSED")
        return True
    print("\nVALIDATION FAILED")
    return False


def main():
    """Run validation on provided story files or default test files."""
    if len(sys.argv) > 1:
        # Validate files passed as arguments
        all_passed = True
        for file_path in sys.argv[1:]:
            story_file = Path(file_path)
            if not story_file.exists():
                print(f"ERROR: Story file not found: {story_file}")
                all_passed = False
                continue

            print(f"\nValidating: {story_file.name}")
            if not validate_story_content(story_file):
                all_passed = False

        return 0 if all_passed else 1
    else:
        # Default: validate test_story.json
        story_file = Path(__file__).parent.parent / "data" / "test_story.json"

        if not story_file.exists():
            print(f"ERROR: Story file not found: {story_file}")
            return 1

        success = validate_story_content(story_file)
        return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
