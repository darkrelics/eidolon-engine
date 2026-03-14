# Data Validation Strategy

This document outlines the data validation strategy for consistent communication between the Flutter frontend and Python backend in the Eidolon Engine incremental game.

## Overview

The system uses a standardized approach to ensure data consistency:

1. **PascalCase** for all API field names
2. **Strict validation** on both frontend and backend
3. **Shared schemas** for common data structures
4. **Type safety** enforced at both ends

## Field Naming Convention

All field naming follows the standards defined in [Style Guide](style-guide.md#json-field-naming-convention). The validation system enforces these naming conventions at API boundaries.

## Validation Layers

### Frontend Validation

Located in `incremental/lib/utils/`:

- `api_validation.dart` - Core validation utilities
- `api_parser.dart` - Standardized response parsing

Features:

- Required field validation
- Type checking
- UUID format validation
- Schema-based validation

### Backend Validation

Located in `eidolon/requests.py`:

- Strict field validation functions
- Type checking
- Required/optional field handling
- Consistent error messages

## Common Schemas

### Character Response

```json
{
  "Character": {
    "CharacterID": "uuid",
    "CharacterName": "string",
    "PlayerID": "uuid",
    "Health": "number",
    "MaxHealth": "number",
    "Attributes": "map",
    "Skills": "map"
  }
}
```

### Story Response

```json
{
  "Stories": [
    {
      "StoryID": "uuid",
      "Title": "string",
      "Description": "string",
      "Type": "string",
      "Available": "boolean",
      "CooldownRemaining": "number",
      "EstimatedDuration": "number"
    }
  ]
}
```

### Segment Response

```json
{
  "Segment": {
    "SegmentID": "uuid",
    "StoryID": "uuid",
    "Type": "string",
    "TimeRemaining": "number"
  }
}
```

## Error Handling

### Frontend

- Catches `ValidationException` for field/type errors
- Provides user-friendly error messages
- Logs validation failures for debugging

### Backend

- Returns error format defined in [API Documentation](incremental-api.md#standardized-error-response-format)
- HTTP status codes follow documented standards
- Detailed error logging for troubleshooting

## Migration Guide

### Updating Frontend Code

1. Replace `JsonUtils.getFlexible()` with strict parsing using PascalCase keys (e.g., ApiParser or direct key access)
2. Add try-catch blocks for `ValidationException`
3. Ensure all API requests use PascalCase field names

### Updating Backend Code

1. Use strict validation functions from `requests.py`
2. Remove flexible field parsing
3. Ensure all responses use PascalCase

## Story Data Validation

### Local Validation

Story content files can be validated locally before committing:

```bash
# Validate branching (weights, prerequisites, references)
python3 scripts_python/validate_branching.py data/test_story.json

# Validate content structure (segments, challenges, decisions)
python3 scripts_python/validate_story_content.py data/test_story.json

# Validate multiple files
python3 scripts_python/validate_branching.py data/*.json
```

### CI Validation

Story validation runs automatically via GitHub Actions:

**Workflow:** `.github/workflows/story-validation.yml`

**Triggers:**

- Pull requests modifying `data/**/*.json`
- Pushes to `develop`, `qa`, or `prod` branches
- Changes to validation scripts or schemas

**Validators:**

1. **validate_branching.py** — Checks:
   - Branch weights sum to 1.0 (tolerance: 0.001)
   - NextSegmentID references valid segments
   - Prerequisites structure (MinSkills, MinAttributes, RequiredItems)
   - No circular dependencies

2. **validate_story_content.py** — Checks:
   - Segment type structure (mechanical, decision)
   - Results/Challenges/Combat/DecisionOptions validity
   - Required fields present
   - Type correctness

**Data Formats Supported:**

- Flat format: `{"Segments": [...]}`
- DynamoDB format: `{"Stories": [{"Story": {...}, "Segments": [...]}]}`

### Validation Failures

If validation fails:

1. Check the CI output for specific error messages
2. Fix the story data locally
3. Re-run validators locally to confirm fix
4. Push the corrected changes

## Testing Philosophy

### Project Testing Policy

The Eidolon Engine does NOT implement unit tests as a deliberate architectural decision. This policy prioritizes well-designed, simple, readable code over test coverage metrics.

### Rationale

**1. Well-Designed Code is Self-Evident**

Code that is simple, focused, and properly designed is self-evident in correctness. When functions do one thing well with clear inputs and outputs, their correctness can be verified by inspection.

**2. Faulty Tests Create Confusion**

When tests are bad but code is good, developers waste time debugging correct code. Bad tests create false positives, false negatives, and encode implementation details that break during valid refactoring.

**3. Unit Tests Double Maintenance Effort**

Every code change requires updating implementation and tests. This effort multiplication hinders rapid iteration and experimentation.

**4. Unit Tests Resist Architectural Improvements**

Large-scale refactoring breaks hundreds of tests, creating resistance to necessary improvements. The "don't refactor, tests will break" mindset prevents beneficial changes.

**5. Cargo Cult Testing**

Writing tests for 100% coverage without understanding value leads to meaningless tests that verify trivial operations like dictionary access or getter methods.

**6. False Sense of Security**

All tests passing does not mean code is correct. Critical bugs (race conditions, integration failures, performance issues, business logic errors) are often not caught by unit tests.

### What We Do Instead

**Integration Testing:**

- Test real workflows end-to-end
- Run against actual AWS services (local or test account)
- Verify entire system works together

**Manual Testing:**

- Faster than comprehensive unit tests at this scale
- More effective at catching real issues
- Better aligned with actual user experience

**Code Review:**

- Simplicity and clarity verification
- Correct business logic validation
- Proper error handling checks
- Security considerations

**Production Monitoring:**

- Real user behavior patterns
- Actual error rates and types
- Performance bottlenecks
- Edge cases no test anticipated

**Design for Correctness:**

- Type hints to catch errors at development time
- Enums instead of magic strings
- DynamoDB conditional writes for atomic operations
- Fail fast with clear error messages
- Small, focused functions

### Exceptions Where Testing Provides Value

**Complex Business Logic:**

- Algorithms with many edge cases (damage calculation, XP formulas)
- Integration tests testing observable behavior
- Minimal and focused on actual edge cases

**Security-Critical Code:**

- Authentication, authorization, cryptographic functions
- Test security properties, not implementation details
- Use security audits and code review
- Prefer battle-tested libraries

### Policy Summary

The Eidolon Engine does not implement unit tests because:

1. Well-designed code is self-evidently correct
2. Faulty tests create more problems than they solve
3. Unit tests double the effort required for changes
4. Unit tests resist fundamental architectural improvements
5. Test-driven development is cargo cult behavior at this scale
6. False sense of security from "green tests"
7. Better ROI from integration testing, code review, and monitoring

This is a deliberate architectural decision, not technical debt.

## Best Practices

1. **Always validate** API responses before use
2. **Log validation errors** with context
3. **Test edge cases** like missing/null fields through integration tests
4. **Document schemas** for new endpoints
5. **Keep validation logic centralized**
6. **Validate story data** before committing to repository
7. **Run local validators** during content authoring
8. **Focus on integration testing** over unit tests
9. **Design for correctness** using type safety and clear interfaces
10. **Use code review** to catch logic errors
