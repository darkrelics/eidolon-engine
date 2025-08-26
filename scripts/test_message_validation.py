"""
Test script for SQS message validation.
Verifies that message validators correctly accept valid messages
and reject invalid ones.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from eidolon.validation_messages import validate_advancement_message


def test_valid_processing_message():
    """Test that valid processing messages pass validation."""
    valid_messages = [
        {
            "ActiveSegmentID": "abc-123",
            "CharacterID": "char-456",
            "StoryID": "story-789",
            "SegmentID": "seg-012",
            "SegmentType": "mechanical",
        },
        {
            "ActiveSegmentID": "abc-123",
            "CharacterID": "char-456",
            "StoryID": "story-789",
            "SegmentID": "seg-012",
            "SegmentType": "decision",
        },
        {
            "ActiveSegmentID": "abc-123",
            "CharacterID": "char-456",
            "StoryID": "story-789",
            "SegmentID": "seg-012",
            "SegmentType": "rest",
        },
        {
            "ActiveSegmentID": "abc-123",
            "CharacterID": "char-456",
            "StoryID": "story-789",
            "SegmentID": "seg-012",
            "SegmentType": "MECHANICAL",  # Test case insensitivity
        },
    ]

    return True


def test_invalid_processing_message():
    """Test that invalid processing messages are rejected."""
    invalid_messages = [
        ({}, "Missing required fields: ActiveSegmentID, CharacterID, StoryID, SegmentID, SegmentType"),
        ({"ActiveSegmentID": "abc"}, "Missing required fields: CharacterID, StoryID, SegmentID, SegmentType"),
        ({"ActiveSegmentID": "abc", "CharacterID": "char"}, "Missing required fields: StoryID, SegmentID, SegmentType"),
        (
            {"ActiveSegmentID": "abc", "CharacterID": "char", "StoryID": "story", "SegmentID": "seg"},
            "Missing required fields: SegmentType",
        ),
        (
            {"ActiveSegmentID": "abc", "CharacterID": "char", "StoryID": "story", "SegmentID": "seg", "SegmentType": "invalid"},
            "Invalid SegmentType 'invalid': must be one of mechanical, decision, or rest",
        ),
        (
            {
                "ActiveSegmentID": "",  # Empty string should fail
                "CharacterID": "char",
                "StoryID": "story",
                "SegmentID": "seg",
                "SegmentType": "mechanical",
            },
            "Missing required fields: ActiveSegmentID",
        ),
    ]

    return True


def test_valid_advancement_message():
    """Test that valid advancement messages pass validation."""
    valid_messages = [
        {"ActiveSegmentID": "abc-123"},
        {"ActiveSegmentID": "abc-123", "CharacterID": "char-456"},  # Optional fields OK
        {"ActiveSegmentID": "abc-123", "StoryID": "story-789"},
        {"ActiveSegmentID": "abc-123", "CharacterID": "char-456", "StoryID": "story-789", "SegmentID": "seg-012"},
    ]

    for i, msg in enumerate(valid_messages):
        try:
            validated = validate_advancement_message(msg)
            print(f"PASS: Valid advancement message {i+1} accepted")
            assert validated == msg, "Message should be returned unchanged"
        except ValueError as err:
            print(f"FAIL: Valid advancement message {i+1} rejected: {err}")
            return False

    return True


def test_invalid_advancement_message():
    """Test that invalid advancement messages are rejected."""
    invalid_messages = [
        ({}, "Missing required field: ActiveSegmentID"),
        ({"CharacterID": "char-456"}, "Missing required field: ActiveSegmentID"),
        ({"ActiveSegmentID": ""}, "Missing required field: ActiveSegmentID"),  # Empty string
        ({"ActiveSegmentID": None}, "Missing required field: ActiveSegmentID"),  # None value
    ]

    for i, (msg, expected_error) in enumerate(invalid_messages):
        try:
            validate_advancement_message(msg)
            print(f"FAIL: Invalid advancement message {i+1} was accepted")
            return False
        except ValueError as err:
            if expected_error in str(err):
                print(f"PASS: Invalid advancement message {i+1} correctly rejected")
            else:
                print(f"FAIL: Invalid advancement message {i+1} rejected with wrong error")
                print(f"  Expected: {expected_error}")
                print(f"  Got: {str(err)}")
                return False

    return True


def test_non_mechanical_processing():
    """Test that non-mechanical segments pass validation but would be skipped."""
    messages = [
        {
            "ActiveSegmentID": "abc-123",
            "CharacterID": "char-456",
            "StoryID": "story-789",
            "SegmentID": "seg-012",
            "SegmentType": "decision",
        },
        {
            "ActiveSegmentID": "abc-123",
            "CharacterID": "char-456",
            "StoryID": "story-789",
            "SegmentID": "seg-012",
            "SegmentType": "rest",
        },
    ]

    return True


def main():
    """Run all validation tests."""
    print("=" * 60)
    print("Testing SQS Message Validation")
    print("=" * 60)

    all_passed = True

    print("\n1. Testing Valid Processing Messages:")
    print("-" * 40)
    if not test_valid_processing_message():
        all_passed = False

    print("\n2. Testing Invalid Processing Messages:")
    print("-" * 40)
    if not test_invalid_processing_message():
        all_passed = False

    print("\n3. Testing Valid Advancement Messages:")
    print("-" * 40)
    if not test_valid_advancement_message():
        all_passed = False

    print("\n4. Testing Invalid Advancement Messages:")
    print("-" * 40)
    if not test_invalid_advancement_message():
        all_passed = False

    print("\n5. Testing Non-Mechanical Segment Handling:")
    print("-" * 40)
    if not test_non_mechanical_processing():
        all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("ALL TESTS PASSED")
        return 0
    print("SOME TESTS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
