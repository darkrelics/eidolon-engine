"""
Smoke test for narrative lookup functionality.
Verifies that normalized segments return narratives correctly via validate_segment_outcome_results.
"""

import json
import sys
import traceback
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from eidolon.schema import normalize_segment_definition
from eidolon.segment import validate_segment_outcome_results


def load_test_story():
    """Load the test story JSON file."""
    test_file = Path(__file__).parent.parent / "data" / "test_story.json"
    with open(test_file, "r", encoding="utf-8") as f:
        return json.load(f)


def test_narrative_extraction():
    """Test that narrative extraction works correctly after normalization."""
    print("=" * 60)
    print("Testing Narrative Extraction")
    print("=" * 60)

    # Load test story data
    story_data = load_test_story()

    # Get the first mechanical segment (has Results map)
    first_segment = None
    for segment in story_data["Segments"]:
        if segment.get("SegmentType") == "mechanical" and segment.get("Results"):
            first_segment = segment
            break

    if not first_segment:
        print("ERROR: No mechanical segment with Results found in test data")
        return False

    print(f"\nTesting segment: {first_segment.get('SegmentID')}")
    print(f"Segment type: {first_segment.get('SegmentType')}")

    # Normalize the segment (this should lowercase Results keys)
    normalized = normalize_segment_definition(first_segment)

    # Test narrative extraction for each outcome
    outcomes_to_test = ["death", "failure", "minimal", "normal", "exceptional"]

    print("\nNarrative extraction results:")
    print("-" * 40)

    for outcome in outcomes_to_test:
        try:
            # Call the validator to get narrative
            result = validate_segment_outcome_results(normalized, outcome)
            narrative = result.get("Narrative", "")

            if narrative:
                # Truncate for display
                display_narrative = narrative[:60] + "..." if len(narrative) > 60 else narrative
                print(f'PASS: {outcome:12} -> "{display_narrative}"')
            else:
                print(f"INFO: {outcome:12} -> (empty narrative)")

        except Exception as err:
            print(f"FAIL: {outcome:12} -> ERROR: {err}")

    # Special test for "normal" outcome which should have narrative
    print("\n" + "-" * 40)
    print("Testing 'normal' outcome specifically:")

    try:
        result = validate_segment_outcome_results(normalized, "normal")
        narrative = result.get("Narrative", "")

        if narrative:
            print("SUCCESS: Normal outcome narrative found:")
            print(f'  "{narrative}"')
            return True
        else:
            print("FAILURE: Normal outcome narrative is empty!")
            return False

    except Exception as err:
        print(f"FAILURE: Exception getting normal outcome: {err}")
        return False


def main():
    """Run the smoke test."""
    try:
        success = test_narrative_extraction()

        print("\n" + "=" * 60)
        if success:
            print("NARRATIVE LOOKUP TEST PASSED")
            return 0
        print("NARRATIVE LOOKUP TEST FAILED")
        return 1

    except Exception as err:
        print(f"UNEXPECTED ERROR: {err}")

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
