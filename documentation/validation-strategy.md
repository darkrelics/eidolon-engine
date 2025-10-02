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

## Best Practices

1. **Always validate** API responses before use
2. **Log validation errors** with context
3. **Test edge cases** like missing/null fields
4. **Document schemas** for new endpoints
5. **Keep validation logic centralized**
6. **Validate story data** before committing to repository
7. **Run local validators** during content authoring
