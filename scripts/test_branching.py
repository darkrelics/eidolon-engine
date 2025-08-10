"""
Test script to verify outcome-based branching works correctly.
Tests the normalization and branching logic with actual test story data.
"""

import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from eidolon.schema import normalize_segment_definition
from eidolon.segment import determine_next_segment


def load_test_story():
    """Load the test story JSON file."""
    test_file = Path(__file__).parent.parent / "data" / "test_story.json"
    with open(test_file, "r", encoding="utf-8") as f:
        return json.load(f)


def test_mechanical_segment_branching():
    """Test that mechanical segments branch correctly based on outcome."""
    story_data = load_test_story()

    # Get the first segment (mechanical type)
    first_segment = None
    for segment in story_data["Segments"]:
        if segment["SegmentID"] == "a1b2c3d4-5e6f-7a8b-9c0d-1e2f3a4b5c6d":
            first_segment = segment
            break

    if not first_segment:
        print("ERROR: Could not find first segment in test data")
        return False

    # Normalize the segment
    normalized = normalize_segment_definition(first_segment)

    # Test each outcome
    test_cases = [
        ("Death", None, "Death outcome should terminate (null NextSegmentID)"),
        ("Failure", None, "Failure outcome should terminate (null NextSegmentID)"),
        ("Minimal", "b2c3d4e5-6f7a-8b9c-0d1e-2f3a4b5c6d7e", "Minimal outcome should advance"),
        ("Normal", "b2c3d4e5-6f7a-8b9c-0d1e-2f3a4b5c6d7e", "Normal outcome should advance"),
        ("Exceptional", "b2c3d4e5-6f7a-8b9c-0d1e-2f3a4b5c6d7e", "Exceptional outcome should advance"),
    ]

    all_passed = True
    active_segment = {"ActiveSegmentID": "test-active-123"}

    for outcome, expected_next, description in test_cases:
        # Test with original casing
        next_id = determine_next_segment(normalized, active_segment, outcome)
        if next_id != expected_next:
            print(f"FAIL: {description}")
            print(f"  Outcome: {outcome}")
            print(f"  Expected: {expected_next}")
            print(f"  Got: {next_id}")
            all_passed = False
        else:
            print(f"PASS: {description}")

        # Also test with lowercase
        next_id_lower = determine_next_segment(normalized, active_segment, outcome.lower())
        if next_id_lower != expected_next:
            print(f"FAIL: {description} (lowercase)")
            print(f"  Outcome: {outcome.lower()}")
            print(f"  Expected: {expected_next}")
            print(f"  Got: {next_id_lower}")
            all_passed = False

    return all_passed


def test_decision_segment_branching():
    """Test that decision segments branch correctly."""
    story_data = load_test_story()

    # Get the decision segment
    decision_segment = None
    for segment in story_data["Segments"]:
        if segment["SegmentID"] == "b2c3d4e5-6f7a-8b9c-0d1e-2f3a4b5c6d7e":
            decision_segment = segment
            break

    if not decision_segment:
        print("ERROR: Could not find decision segment in test data")
        return False

    # Normalize the segment
    normalized = normalize_segment_definition(decision_segment)

    # Test decision branches
    test_cases = [
        ("Left", "c3d4e5f6-7a8b-9c0d-1e2f-3a4b5c6d7e8f", "Left decision should go to brook path"),
        ("Right", "d4e5f6a7-8b9c-0d1e-2f3a-4b5c6d7e8f9a", "Right decision should go to thicket path"),
        (None, "d4e5f6a7-8b9c-0d1e-2f3a-4b5c6d7e8f9a", "No decision should use default (Right)"),
    ]

    all_passed = True

    for decision, expected_next, description in test_cases:
        active_segment = {"ActiveSegmentID": "test-active-456", "Decision": decision}
        next_id = determine_next_segment(normalized, active_segment, "normal")
        if next_id != expected_next:
            print(f"FAIL: {description}")
            print(f"  Decision: {decision}")
            print(f"  Expected: {expected_next}")
            print(f"  Got: {next_id}")
            all_passed = False
        else:
            print(f"PASS: {description}")

    return all_passed


def test_results_normalization():
    """Test that Results keys are properly normalized to lowercase."""
    story_data = load_test_story()

    # Get a segment with mixed-case Results keys
    segment = story_data["Segments"][0]
    normalized = normalize_segment_definition(segment)

    results = normalized.get("Results", {})

    # Check that all keys are lowercase
    all_passed = True
    for key in results.keys():
        if key != key.lower():
            print(f"FAIL: Results key '{key}' is not lowercase")
            all_passed = False

    # Check that expected keys exist
    expected_keys = ["death", "failure", "minimal", "normal", "exceptional"]
    for key in expected_keys:
        if key not in results:
            print(f"FAIL: Expected results key '{key}' not found")
            all_passed = False
        else:
            print(f"PASS: Results key '{key}' exists")

    # Verify NextSegmentID is preserved
    if "NextSegmentID" in results.get("minimal", {}):
        print("PASS: NextSegmentID preserved in minimal outcome")
    else:
        print("FAIL: NextSegmentID not found in minimal outcome")
        all_passed = False

    return all_passed


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Outcome-Based Branching")
    print("=" * 60)

    print("\n1. Testing Results Normalization:")
    print("-" * 40)
    test1_passed = test_results_normalization()

    print("\n2. Testing Mechanical Segment Branching:")
    print("-" * 40)
    test2_passed = test_mechanical_segment_branching()

    print("\n3. Testing Decision Segment Branching:")
    print("-" * 40)
    test3_passed = test_decision_segment_branching()

    print("\n" + "=" * 60)
    if test1_passed and test2_passed and test3_passed:
        print("ALL TESTS PASSED")
        return 0
    print("SOME TESTS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
